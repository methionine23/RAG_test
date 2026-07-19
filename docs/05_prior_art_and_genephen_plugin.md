# 05 — Baseline Notebook & the genePhen Plugin Path

## 1. What the baseline notebook establishes

`llm_summarization.ipynb` (pre-genePhen) is the starting point this evaluation formalizes.
It runs on **Vertex AI `gemini-2.0-flash`, temperature=0**, over PubMed data pulled via
**Entrez**, with three agents:

- **SummaryReportAgent** — one combined narrative summary (Key Findings / Significance /
  Limitations) across a gene's abstracts. *(Out of scope for cell-level scoring; treated
  as a free-text summary → faithfulness via docs/02 tier-2/3.)*
- **DetailedReportAgent** — per-paper structured JSON extraction. **This defines our
  extraction schema** (see §2).
- **EvaluationAgent** — field-by-field comparison to a reference table
  (`HSPB1_ground_truth.tsv`): exact match for structured fields, `SequenceMatcher`
  ratio for free-text (Symptoms); prints per-field accuracy + mismatches. This *is* the
  "human-spottable" check, done programmatically.

### Two findings that shape the plan
1. **Extracts from `Title` only.** `extract_by_pmid` feeds `row.get("Title")` to the LLM,
   not the abstract/full text — so most fields are structurally unrecoverable. Our
   harness must log **which text span was actually fed to the model** (part of provenance)
   so "the field wasn't in the input" is never miscounted as a model hallucination.
2. **Runs on abstracts, and exact-match scoring is brittle.** Abstracts lack case-level
   detail; and exact string match penalizes correct-but-reworded values (`"male"` vs
   `"M"`, `"35 years"` vs `"35"`). This is precisely the rewording-drift problem — our
   tiered grounding (exact → normalized → NLI/judge, docs/02 §2) replaces brittle
   equality, and moving to **full XML** (Entrez `db=pmc`) restores the detail.

## 2. Adopted extraction schema (aligned to the notebook)

The clinical-case schema in `docs/03` is aligned to the notebook's fields so the
evaluation is drop-in for the existing agents:

`Mutation, Age, Sex, Age_of_onset, Symptoms, Laboratory_findings, Family_history`
(+ `case_id`, `PMID`, and per-cell `_provenance`). The mutation schema (docs/03 §1.1)
extends `Mutation` into normalized `hgvs_c` / `hgvs_p` / `gene` for grounding.

## 3. genePhen plugin path (future phase)

The evaluation harness is built standalone (decision in `README.md`), but is designed to
attach to genePhen as a **plugin** in a later phase:

```
genePhen  ──emits──▶  { table rows, retrieved chunks, chunk boundaries, input spans }
                              │
                              ▼
              genephen_eval  (this project)
              SummarizerBackend adapter  ──▶  S1/S2/S3 metrics + attribution + report
```

- The baseline notebook's `DetailedReportAgent` becomes one `SummarizerBackend`
  (`backends/baseline.py`); genePhen and Vertex RAG Engine become two more. Same inputs,
  same schema, same metrics → apples-to-apples (docs/03 §3).
- The notebook's `EvaluationAgent` is **superseded** by the metric stack: keep its
  field-by-field readout as a human-friendly view, but back it with tiered grounding
  (not exact match) and add the S1/S2 stage metrics it lacks entirely.
- **Plugin contract (future):** genePhen exposes a hook returning, per generation, the
  `retrieved_context` spans and the `chunk_boundaries` used. With those two signals the
  harness computes the full stage decomposition (docs/04) against genePhen's *actual*
  internals rather than recovering them post-hoc. This is the concrete integration ask
  for genePhen and the deliverable of the plugin phase.

## 4. Migration checklist (baseline → harness)

- [ ] Feed full text (Entrez `db=pmc`), not `Title`; record the exact input span per field.
- [ ] Replace exact-match scoring with tiered grounding (docs/02 §2).
- [ ] Add S1 sectioning + S2 retrieval metrics (docs/04) around the extraction call.
- [ ] Wrap `DetailedReportAgent` as `backends/baseline.py`; add genePhen + Vertex backends.
- [ ] Use `HSPB1_ground_truth.tsv` as the P5 calibration set, not as a hard dependency.
- [ ] Run the temperature sweep (the notebook fixes temp=0; the whole point is to vary it).
