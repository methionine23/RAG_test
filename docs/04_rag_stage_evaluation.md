# 04 — Stage-Decomposed RAG Fidelity (Sectioning → Retrieval → Generation)

> Added to answer the requirement: **measure fidelity of both the chunking/sectioning
> and retrieval stages**, not just final summarization — so a wrong or missing table
> cell can be *attributed* to the stage that caused it. This is the methodological core
> of the project and the main benchmark contribution.

## 1. Why decompose

"The table is wrong" is not actionable. A missing variant can be lost because it was
**split across chunks** (sectioning), **not retrieved** (retrieval), or **retrieved but
mis-extracted / reworded** (generation). Each has a different fix (chunker vs retriever
vs prompt/model). We therefore score fidelity at every stage and compute an **error
attribution** that assigns each lost/incorrect fact to a stage.

```
Document ──▶ Sectioning/Chunking ──▶ Retrieval ──▶ Generation ──▶ Table
             (structure preserved?)   (evidence      (faithful +
                                        fetched?)      complete?)
   S1 metrics                S2 metrics            S3 metrics (docs/02)
                         └──────────── attribution ───────────┘
```

Each stage imposes a **ceiling** on the next: a fact split at S1 is hard to retrieve
whole at S2; a fact absent from retrieved context at S2 cannot be faithfully produced at
S3. Reporting the ceilings makes the loss budget explicit.

## 2. S1 — Sectioning / chunking fidelity

Ground-truth structure comes from the source markup: PubMed/PMC XML (`<abstract>`,
`<sec sec-type>`, `<table-wrap>`, `<p>`), GTR XML elements, or a PDF layout parser
(Docling/GROBID) for the biochem doc. Metrics (all reference-free — structure is in the
source):

| Metric | Definition | Why it matters |
| --- | --- | --- |
| **Boundary alignment** | fraction of chunk boundaries that fall on true section/paragraph/table-row boundaries (not mid-sentence/mid-row) | mid-unit splits fragment facts |
| **Table integrity** | fraction of source tables kept intact (or correctly linearized) within one chunk | genetics case/variant tables are the richest evidence; splitting header from rows destroys column semantics |
| **Fact locality** | fraction of inventory facts (docs/02 §4) wholly contained in a single chunk | a split fact is not retrievable as a unit → downstream omission |
| **Section purity** | fraction of chunks drawn from ≤1 section (low cross-section bleed) | contamination injects distractor context into retrieval |
| **Coverage** | fraction of source tokens present in ≥1 chunk | dropped content = guaranteed omission |

## 3. S2 — Retrieval fidelity

For a target field/fact and a top-k retrieval:

| Metric | Definition | Basis |
| --- | --- | --- |
| **Fact hit-rate** | fraction of inventory facts whose containing chunk is in top-k | bridges S1→S2: locality (S1) decides which chunk holds the fact; retrieval decides if it is fetched |
| **Context recall** | fraction of gold-evidence passages present in retrieved context | RAGAS-style (reference-free proxy via the fact inventory) |
| **Context precision** | rank-weighted fraction of retrieved chunks that carry evidence | distractor load on the generator |
| **Retrieval ceiling** | fraction of facts whose value is present *anywhere* in retrieved context | hard upper bound on end-to-end recall given this retrieval |

## 4. S3 — Generation fidelity (scored twice)

Reuse the cell-level faithfulness/completeness/provenance metrics from `docs/02`, but
compute them against **two references**:

- **vs retrieved context** (RAGAS faithfulness): isolates the generator — did the model
  stay grounded in what it was given?
- **vs full source**: end-to-end — what a human reviewer sees.

The gap between them is retrieval-induced loss.

## 5. Error attribution (the payoff)

For every inventory fact, classify the outcome:

```
not local (S1 split)            -> SECTIONING error
local but not in top-k (S2)     -> RETRIEVAL error
retrieved but missing/wrong (S3)-> GENERATION error (hallucination or omission)
present & correct in table      -> ok
```

Aggregate to a **loss budget** per configuration, e.g. *"of 18 missed/incorrect cells:
40% sectioning, 35% retrieval, 25% generation."* This is the head-to-head signal for
**genePhen vs Vertex RAG Engine** and for tuning chunkers.

## 6. Working prototype

`prototype/rag_stage_demo.py` implements S1+S2+attribution end-to-end (stdlib-only) on
`prototype/sample/hspb1_pubmed_sample.xml`, comparing a structure-blind `naive_fixed`
chunker against a `section_aware` one. Representative output:

| chunker | boundary_align | table_integrity | fact_locality | fact_hit_rate | retrieval_ceiling |
| --- | --- | --- | --- | --- | --- |
| naive_fixed(320) | 0.00 | 0.00 | 0.92 | 0.92 | 0.92 |
| section_aware | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Same document, same retriever — the chunker alone moves table integrity and the
retrieval ceiling, and the per-fact attribution shows the naive chunker splitting a
variant at a chunk boundary (a *sectioning* loss). In the real harness the toy retriever
is replaced by genePhen / Vertex retrieval and the NLI/LLM-judge generator (docs/02–03).

## 7. Per-use-case sectioning notes (schema-specific RAG)

The user's point that **GTR XML and the biochem PDF need schema-specific RAG** maps
directly onto S1:

- **UC1 HSPB1 (PubMed/PMC XML).** Section + table markup is explicit → a high-fidelity
  section-aware chunker is achievable; UC1 is where S1/S2/S3 are all exercised and the
  temperature study runs. Use **1–2 full XML** docs from Entrez (`fetch_entrez.py`);
  full text, not abstracts, because the analysis needs case-level detail.
- **UC3 NIH GTR XML.** Chunk **along the GTR schema** (lab / test / condition / method
  elements), not by character windows. Sectioning fidelity ≈ correct element-to-field
  routing; because the schema is explicit this is the cleanest S1 and isolates S3
  rewording drift. **Implemented** (offline): `ingestion.parse_gtr_xml` routes each
  `<GTRLabTest>` into a section with `gene / lab / condition / method` fields;
  `chunk_gtr_schema` keeps one test per chunk; `inventory._gtr_units` builds
  (test→condition) and (test→method) relation triples as the recall standard; the mock
  backend's `--task gtr` extractor injects the same temperature-driven omission /
  rewording / hallucination. Synthetic fixture `prototype/sample/gtr_hspb1_sample.xml`
  (swap for real `efetch db=gtr` output). With the schema chunker S1/S2 are perfect and
  all temperature loss attributes to GENERATION — exactly the isolation this UC is for.
- **UC2 biochem PDF (pathways).** No native markup → S1 depends on a layout/section
  parser; define a **pathway schema** (entity / reaction / relation) and chunk by
  parsed sections + figure/caption blocks. Highest-risk S1; relation-triple facts
  (docs/02 §8) drive S2/S3.

## 8. Reference-free stance + optional gold

We remain reference-free by default (fact inventory + source structure). But the user's
existing **`HSPB1_ground_truth.tsv`** (from the baseline notebook, see `docs/05`) is an
ideal **calibration set (P5)**: it lets us verify that silver-recall and faithfulness
scores agree with human judgment, and lets S3 optionally run in reference-based mode
(field-level P/R/F1, à la CaseReportBench) when gold is available — without making the
method depend on it.
