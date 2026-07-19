# 02 — Reference-Free Metrics & Experiment Design

This is the technical core: how we score fidelity *without human gold tables*, and the
experiment matrix that reproduces and quantifies the temperature effect.

---

## 1. Units of evaluation

- **Claim / cell** `(record_id, field, value)` — one extracted table cell.
- **Record / row** — a set of cells describing one variant or one case.
- **Evidence span** `(doc_id, char_start, char_end, text)` — a source passage.
- **Provenance** — the evidence span the summarizer *claims* a cell came from (or, if the
  backend emits none, the span we *recover* by retrieval).
- **Fact inventory** — the mechanically-built set of "should-capture" units from the
  source (the reference-free stand-in for gold; see §4).

## 2. Faithfulness (precision-like, reference-free)

For each generated cell `c` with value `v` and evidence span(s) `E`:

**2.1 Value grounding (tier 1, cheap, high precision).**
`ground(v, E)` ∈ {exact, normalized, absent}.
- *exact* — `v` (or a whitelisted surface variant) occurs verbatim in `E`/source.
- *normalized* — `v` matches a source mention after domain normalization
  (HGVS c.↔p. via `hgvs`/Mutalyzer; units; HPO synonyms). Normalization is used **only
  at match time**; scoring normalization correctness is out of scope (docs/00 §2).
- *absent* — no surface/normalized match ⇒ candidate hallucination or heavy rewording.

This tier alone catches the user's #1 failure mode (reworded-into-wrong values) for
string-typed fields (variant, gene, zygosity).

**2.2 Entailment check (tier 2, for free-text / derived cells).**
`nli_support(claim_text, E)` ∈ [0,1] using a robust checker (MiniCheck/AlignScore
ensemble). `claim_text` = a templated verbalization of the cell,
e.g. *"Patient CASE-3 had onset at age 12."* Cell-level keeps NLI inputs short/dense
(counters arXiv 2511.07689).

**2.3 LLM-judge support (tier 3, hard cells only).**
For cells where tiers 1–2 disagree or are low-confidence, an LLM judge returns the TREC
3-level label {full, partial, none} with the evidence span, plus a one-line rationale.
Guards: cross-family judge, fixed rubric, `judge_temp≈0`, `k_judge=3` self-consistency
(majority vote). Calibrated against humans in P5.

**Cell faithfulness score**
```
s_faith(c) = 1.0   if grounding == exact
           = 0.9   if grounding == normalized
           = nli_support(c)                       (tier 2), else
           = {full:1.0, partial:0.5, none:0.0}    (tier 3 judge)
```
**Table faithfulness** = mean `s_faith(c)` over cells; also report **hallucination rate**
= fraction of cells with `s_faith < τ` (default τ=0.5), and a per-field breakdown.

## 3. Provenance / attribution

For each cell with a *claimed* provenance span `p`:
- **attribution validity** = TREC support of `c` against `p` (does the cited span
  actually support the value?).
- **attribution coverage** = fraction of cells that carry any provenance.
- If the backend emits no provenance, we **recover** `p*` = top retrieved sentence and
  report `recovered=True` (a weaker, backend-favorable proxy — flagged in results).

## 4. Completeness / recall (reference-free via source inventory)

We cannot compute true recall without gold, so we build a **source-derived fact
inventory** `I` — a high-recall, fully source-grounded set of extractable units — and
measure coverage of `I`. Every unit in `I` is a verbatim source string, so `I` is honest
even if imperfect; we label these scores **silver recall**.

**Building `I`:**
- *Variants* — union of detectors over the full text + parsed tables: HGVS regex
  (`c.`, `p.`, `g.`, rs IDs), a variant-mention NER (tmVar-style), and gene-symbol
  gazetteer. Dedupe by normalized key.
- *Clinical-case units* — parse the **paper's own tables** (richest signal: papers
  usually tabulate cases) into `(case, field, value)` cells; add NER for sex, age,
  HPO phenotypes, inheritance from prose.
- Each unit keeps its source span (for auditing inventory quality on the calibration set).

**Coverage / silver recall**
```
recall_silver = |I ∩ extracted| / |I|
```
matched by normalized key (variants) or fuzzy field-value match (cases). Report overall
and per-field, plus **Tuple-F1** (records) and **Cell-F1** (cells) in the Schema-Driven-IE
sense, using `I` as the silver reference.

**Caveats (report them):** `I` can miss units the detectors don't catch (undercount ⇒
optimistic recall) and can include spurious mentions (overcount ⇒ pessimistic). P5 audits
`I` precision/recall on a handful of papers to bound the bias.

## 5. Self-consistency & the temperature study

**SelfCheckGPT-style stability.** For a fixed input, sample `K` generations at
temperature `T`. For each candidate cell, `stability(c) = ` fraction of the `K` samples
that produce an equivalent cell.
- **Unstable-but-present** cells (low stability) → fragile extractions.
- **Consistency across samples** correlates with faithfulness (per SelfCheckGPT) — a
  reference-free signal requiring no judge.

**Aggregate stability** per config: mean cell stability, plus set-level agreement
(Jaccard of extracted variant sets across the `K` samples).

## 6. Metric summary table

| Metric | Dimension | Reference-free basis | Output |
| --- | --- | --- | --- |
| `s_faith` (tiered) | Faithfulness | source text / retrieved context | [0,1] per cell → mean + halluc. rate |
| `attribution_validity` | Provenance | cited/retrieved span | TREC 3-level → [0,1] |
| `attribution_coverage` | Provenance | — | fraction |
| `recall_silver`, Cell-F1, Tuple-F1 | Completeness | source inventory `I` | [0,1], per-field |
| `stability`, set-Jaccard | Robustness | K-sample self-consistency | [0,1] |

Overall **Fidelity Score** (reported *alongside*, never instead of, the components):
`Fidelity = w1·faith + w2·recall_silver + w3·attribution_validity` with default
`w = (0.5, 0.3, 0.2)`, weights configurable.

## 7. Experiment matrix

**Factors**
- **Backend**: `genephen`, `vertex_rag_engine`, `baseline_llm_norag`.
- **Temperature**: `{0.0, 0.2, 0.5, 0.7, 1.0}`.
- **Samples per cell**: `K = 5` (for stability/SelfCheck).
- **Use case**: UC1 (HSPB1), UC2 (biochem pathway), UC3 (GTR XML).
- **Table type**: mutation, clinical-case (UC1/UC3); relation-triples (UC2).
- **Seeds**: fixed set for reproducibility; all generations cached by
  `(backend, doc, prompt, T, seed)`.

**Primary hypotheses**
- H1: `s_faith` decreases and `hallucination_rate` increases with `T` (monotone-ish).
- H2: `stability` / set-Jaccard decrease with `T` (SelfCheckGPT signal strengthens).
- H3: RAG backends (genephen, vertex) beat `baseline_llm_norag` on faithfulness and
  attribution, especially on UC1/UC2 (retrieval grounds values).
- H4: Fidelity loss ranks by source structure: UC3 (structured) < UC1 < UC2
  (unstructured) — i.e., more structure → higher fidelity.

**Analysis outputs**
- Temperature curves (faith, recall, stability) per backend, with bootstrap CIs.
- Head-to-head genePhen vs Vertex per field and per use case.
- Per-field failure taxonomy (which columns hallucinate/omit most).
- Judge-vs-human agreement (P5) to certify the automated numbers.

## 8. Per-use-case specifics

**UC1 — HSPB1 (core).** Corpus 30–50 PDFs (prefer PMC OA; store PMCID/DOI + hash, not
redistributed PDFs). Table-aware ingestion; separate text vs table streams (AutoPM3
pattern). Both mutation and clinical-case schemas. Full temperature × backend matrix.
Borrow AutoPM3's variant-hit accuracy / in-trans recall framing for the mutation table.

**UC2 — Biochem pathway PDF.** Single very long doc → chunking stress + cross-page
multi-hop. Deliverable is **relation triples** `(entity, relation, entity)` (e.g.
enzyme→catalyzes→reaction). Faithfulness = triple supported by source; completeness =
coverage of a triple inventory (relation-extraction detectors + section parsing).
Tests whether retrieval assembles multi-hop facts faithfully.

**UC3 — NIH GTR XML.** Structured source ⇒ near-explicit ground truth in XML fields.
Ingest via XML-aware parser mapping GTR elements → schema fields. Because the source is
unambiguous, this **isolates rewording drift**: any `s_faith < 1` is (mostly) the model
paraphrasing a known field value into something else. Strong control for the generation
step independent of retrieval noise.

## 9. Calibration (P5)

- Sample ~50–100 cells across configs; two annotators label {supported / not} and
  {source-unit captured / missed}.
- Report metric–human agreement (Cohen's κ, Pearson) for `s_faith` and `recall_silver`;
  target: within the human–human range (justified by arXiv 2504.15205 / 2510.09738).
- Audit inventory `I` precision/recall on those papers to bound silver-recall bias.
