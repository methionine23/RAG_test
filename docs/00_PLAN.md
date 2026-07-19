# 00 — Master Plan

**Project:** Evaluating RAG fidelity on literature-based clinical-genetic summarization
**Owner:** methionine23
**Status:** Planning (this doc) + prototype
**Branch:** `claude/rag-fidelity-genetic-summarization-6rak7j`

---

## 1. Problem statement

An LLM agent summarizes genetics papers into two kinds of structured tables:

- **Mutation table** — one row per variant (gene, HGVS c./p., zygosity, inheritance,
  classification, evidence, …).
- **Clinical-case table** — one row per patient/case (case id, sex, age of onset,
  phenotype/HPO, variant(s) carried, family history, outcome, …).

Observed failure modes:

- **Rewording drift** — the model paraphrases a source value into an inaccurate one.
- **Omission** — variants / case facts present in the source are dropped.
- **Temperature sensitivity** — both get worse as decoding temperature increases.

We need a **fidelity measurement tool** and a **repeatable experiment protocol** to
quantify these, compare backends (genePhen RAG, Vertex AI RAG Engine, no-RAG
baseline), and quantify the temperature/faithfulness trade-off.

## 2. Goals & non-goals

**Goals**
- G1. A reference-free, cell-level **fidelity score** for extracted tables covering
  faithfulness, completeness, and provenance.
- G2. A **backend-agnostic harness** so genePhen and Vertex are swappable and directly
  comparable on the same inputs and metrics.
- G3. A **temperature × backend experiment matrix** that reproduces and quantifies the
  observed degradation, with self-consistency (SelfCheckGPT-style) as a stability
  signal.
- G4. Three concrete **use cases** spanning structured → semi-structured → unstructured
  source material (see §5).
- G5. An **evaluation report / leaderboard** that ranks configurations and surfaces
  per-field failure patterns.

**Non-goals (this iteration)**
- Variant *normalization* correctness (HGVS validation via Mutalyzer/hgvs, transcript
  mapping). Wrong-normalization is scored only insofar as it breaks source grounding;
  a dedicated normalization metric is deferred.
- Building a large human-annotated gold benchmark. We are explicitly **reference-free**;
  any human labels are a small calibration set, not a training/eval gold set.
- Improving genePhen/Vertex retrieval itself — we *measure*, we don't tune the RAG here
  (though the report will inform tuning).

## 3. Core idea: treat "summarization fidelity" as "structured-extraction fidelity"

Because the deliverables are **tables**, not prose, we evaluate at the granularity of
**cells** (field–value units) and **rows** (records) rather than scoring free text.
This is cleaner, more diagnostic, and sidesteps a known trap: whole-document
factual-consistency metrics degrade on long, information-dense inputs (arXiv
2511.07689). Scoring short claim↔evidence pairs at the cell level keeps every judgment
local and dense — a principled response to that finding. See `docs/02`.

Each generated cell becomes a **claim**. Reference-free fidelity is then three
questions per claim / per record:

1. **Faithfulness** — is this cell *supported* by the source? (precision-like)
2. **Provenance** — *where* in the source, and does that span actually support it?
3. **Completeness** — of everything the source offers, how much did we capture?
   (recall-like, measured against a mechanically-built source inventory, not human gold)

## 4. Workstreams & phases

| Phase | Name | Key outputs | Depends on |
| --- | --- | --- | --- |
| P0 | Scoping & schemas | This plan, table/claim/provenance schemas, harness skeleton, prototype metric | — |
| P1 | UC1 corpus & ingestion | 30–50 HSPB1 PDFs ingested, table-aware chunking, GTR/XML + PDF parsers | P0 |
| P2 | Backends wired | `SummarizerBackend` for genePhen, Vertex RAG Engine, no-RAG baseline; provenance capture | P1 |
| P3 | Metric stack | Faithfulness (NLI + LLM-judge + exact-value grounding), coverage vs inventory, attribution, self-consistency | P0 |
| P4 | Experiment matrix | Temperature sweep × backend × use case; runs logged, cached, reproducible | P2, P3 |
| P5 | Calibration | Small human spot-check set; judge-vs-human agreement; metric reliability report | P3 |
| P6 | UC2 & UC3 | Long biochem PDF (pathway/relation fidelity); GTR XML (structured-source control) | P3 |
| P7 | Analysis & report | Leaderboard, per-field failure analysis, temperature curves, recommendations | P4–P6 |

Phases P1/P2/P3 run largely in parallel after P0. P5 gates any strong claim that the
automated metrics are trustworthy.

## 5. The three use cases (why each is here)

They deliberately span a **source-structure spectrum**, which isolates different
failure modes:

- **UC1 — HSPB1 papers (30–50), the core.** Semi-structured: prose + the papers' own
  tables/figures. Primary benchmark for mutation + clinical-case extraction; where the
  temperature study runs. Small enough to build a real RAG (genePhen + Vertex) over.
- **UC2 — Large biochemistry PDF with pathways.** Unstructured, very long, *relational*
  (enzyme → reaction → product). Tests long-document chunking + multi-hop/cross-page
  fidelity and **relation-level** (triple) faithfulness rather than tabular cells.
- **UC3 — NIH GTR XML.** Already semi-structured with its own schema. Acts as a
  **control**: the "source of truth" is nearly explicit in XML fields, so it isolates
  pure **rewording drift** (faithfulness with minimal retrieval ambiguity) and tests
  XML-aware ingestion vs PDF parsing.

Reading them together: **UC3 (structured) → UC1 (semi-structured) → UC2 (unstructured)**
lets us attribute fidelity loss to source structure, retrieval, or generation.

## 6. Deliverables

- Design docs `docs/00`–`docs/03` (this set).
- `prototype/fidelity_demo.py` — runnable reference-free fidelity demo (this session).
- (Later) `genephen_eval/` harness package: ingestion, backends, metrics, runner, report.
- (Later) Experiment configs + a results/report notebook and a comparison leaderboard.

## 7. Risks & mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Reference-free **recall is "silver"** (source-inventory misses or over-counts) | Biased completeness scores | Build inventory from high-recall detectors + the paper's own tables; report recall as *coverage-of-inventory*, audit inventory quality on the calibration set |
| **LLM-judge unreliability / self-preference** | Wrong faithfulness scores | Use a *different* model family as judge; fixed rubric; low judge temperature; judge self-consistency; human spot-check (P5). Research: GPT-4o support-judgments fall within human–human agreement (arXiv 2504.15205), Pearson ~0.85 (arXiv 2510.09738) — good but not free |
| **Long-doc metric degradation** (arXiv 2511.07689) | Faithfulness metric noise on big papers/UC2 | Score at cell↔evidence-span level, not whole-doc; prefer MiniCheck/UniEval-style robust checkers over SummaC-ZS/AlignScore alone; ensemble + report agreement |
| **PDF table parsing errors** propagate into both extraction *and* the source inventory | Confounds backend comparison | Use a strong table-aware parser (Docling/GROBID/PyMuPDF), separate text vs table streams (à la AutoPM3), and log parse quality per doc |
| **Vertex/genePhen access** (creds, ephemeral container) | Can't run live | Backends behind an interface; cache all generations; support offline replay; design docs don't depend on live runs |
| **Corpus licensing** for 30–50 HSPB1 PDFs | Redistribution issues | Prefer PMC Open Access subset; store DOIs/PMCIDs + hashes, not redistributed PDFs, in the repo |
| **Normalization drift** breaks exact-match grounding (`c.404C>T` vs `p.Ser135Phe`) | False "unfaithful" flags | Allow normalized comparison (hgvs/Mutalyzer) *at match time only*; keep normalization scoring itself out of scope |

## 8. Open questions carried into design

- Does genePhen expose per-cell provenance (source offsets), or must we recover it by
  post-hoc retrieval? (Affects the attribution metric — see `docs/03`.)
- Vertex RAG Engine: which chunking/embedding config, and can we read back the retrieved
  chunks per generation (needed for faithfulness-vs-*retrieved-context*)?
- For UC1, final paper list + access route (PMC OA vs licensed).
- Judge model choice and budget per experiment cell.

## 9. Success criteria

- Metrics reproduce the **temperature → fidelity** degradation the user observed, with
  confidence intervals.
- Automated faithfulness agrees with the human spot-check within the human–human range.
- The harness runs the *same* inputs through genePhen and Vertex and produces a
  head-to-head, per-field fidelity comparison.
