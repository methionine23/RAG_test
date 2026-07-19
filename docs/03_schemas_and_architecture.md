# 03 — Data Schemas & Harness Architecture

## 1. Table schemas

Schemas are the contract between summarizer backends and the metric stack. They are
JSON-serializable; every value-bearing field can carry provenance.

### 1.1 Mutation table (one row per variant)

| Field | Type | Notes |
| --- | --- | --- |
| `record_id` | str | stable id within a doc |
| `gene` | str | e.g. `HSPB1` |
| `hgvs_c` | str? | coding, e.g. `c.404C>T` |
| `hgvs_p` | str? | protein, e.g. `p.Ser135Phe` |
| `transcript` | str? | RefSeq id if given |
| `dbsnp` | str? | `rs...` |
| `zygosity` | enum? | het/hom/compound-het/hemi |
| `inheritance` | enum? | AD/AR/XL/de novo |
| `classification` | enum? | ACMG P/LP/VUS/LB/B |
| `disease` | str? | associated phenotype/disease |
| `evidence` | str? | functional/segregation note |
| `_provenance` | list[Span] | per-field spans (see §1.4) |

### 1.2 Clinical-case table (one row per case)

Categories mirror CaseReportBench's system-level structure (arXiv 2505.17265).

| Field | Type | Notes |
| --- | --- | --- |
| `case_id` | str | |
| `sex` | enum? | |
| `age_onset` | str? | keep source units |
| `phenotype` | list[str] | free text + HPO ids if present |
| `variants` | list[str] | links to mutation `record_id`s |
| `family_history` | str? | |
| `labs_imaging` | str? | |
| `treatment` | str? | |
| `outcome` | str? | |
| `_provenance` | list[Span] | |

### 1.3 Relation triple (UC2 pathways)

`{subject, relation, object, _provenance}` — e.g.
`{"HSPB1", "phosphorylated_by", "MAPKAPK2", [Span…]}`.

### 1.4 Span / provenance

`Span = {doc_id, char_start, char_end, text, source_type}` where `source_type ∈
{prose, table, figure_caption, xml_field}`. `recovered: bool` marks spans we retrieved
post-hoc rather than ones the backend emitted (docs/02 §3).

### 1.5 Fact inventory unit

`InventoryUnit = {kind: variant|case_cell|triple, key, value, span, detector}` — the
reference-free "should-capture" unit (docs/02 §4). `detector` records provenance of the
detector (regex/NER/table-parser) for auditing.

## 2. Harness architecture

```
genephen_eval/
  schemas/            dataclasses/pydantic models above + JSON schema
  ingestion/
    pdf.py            table-aware PDF parse (Docling/GROBID/PyMuPDF); text vs table streams
    xml_gtr.py        GTR-XML → schema fields
    chunking.py       table-aware, section-aware chunker
  inventory/
    variants.py       HGVS regex + variant NER (tmVar-style) + gene gazetteer
    cases.py          source-table parser + clinical NER (sex/age/HPO)
    triples.py        relation extraction for UC2
  backends/
    base.py           SummarizerBackend interface (§3)
    genephen.py       wraps the custom genePhen RAG
    vertex.py         Vertex AI RAG Engine client
    baseline.py       direct LLM, no retrieval (ablation)
  metrics/
    grounding.py      tier-1 exact/normalized value grounding
    nli.py            tier-2 MiniCheck/AlignScore ensemble
    judge.py          tier-3 TREC 3-level LLM-judge (guarded)
    faithfulness.py   combines tiers → s_faith, hallucination rate
    attribution.py    provenance validity/coverage
    completeness.py   coverage vs inventory → recall_silver, Cell/Tuple-F1
    consistency.py    SelfCheckGPT-style stability across K samples
  runner/
    config.py         experiment matrix config (backend×T×UC×seed)
    cache.py          generation + judge cache keyed by (backend,doc,prompt,T,seed)
    run.py            orchestration; parallel over cells/docs
    report.py         leaderboard, temperature curves, per-field failure tables
  calibration/        human spot-check tooling + agreement stats (P5)
```

## 3. `SummarizerBackend` interface (the key abstraction)

```python
class SummarizerBackend(Protocol):
    name: str
    def summarize(
        self,
        task: ExtractionTask,      # schema + instructions (mutation | case | triple)
        source: SourceBundle,      # doc(s), pre-parsed streams, or a corpus handle
        temperature: float,
        seed: int | None = None,
    ) -> BackendResult: ...
        # BackendResult = { table: list[Record],
        #                   retrieved_context: list[Span] | None,
        #                   provenance_supported: bool,   # did it emit per-cell spans?
        #                   raw: Any }                      # raw response for audit
```

Design points:
- **Uniform inputs/outputs** so genePhen, Vertex, and baseline are directly comparable on
  identical prompts and schemas.
- `retrieved_context` lets us score faithfulness against *what the RAG actually
  retrieved* (RAGAS-style) in addition to the full source.
- `provenance_supported` flags whether attribution is native or recovered (docs/02 §3).
- Everything is **cached**; live Vertex/genePhen calls are optional and replayable —
  the ephemeral container never blocks analysis.

## 4. genePhen & Vertex integration notes (to confirm)

- **genePhen**: does it expose (a) per-cell source offsets, and (b) the retrieved chunks
  per generation? If yes, native provenance + RAGAS-style context scoring. If no, we
  recover provenance via retrieval and mark `recovered=True`.
- **Vertex AI RAG Engine**: capture the retrieved chunks (grounding metadata) per
  generation; pin chunking/embedding config in `runner/config.py` so runs are
  reproducible; respect project/creds via env, never hard-coded.

## 5. Reproducibility & provenance of results

- Every generation/judge call cached and content-addressed; configs are declarative and
  committed.
- Corpus stored as **identifiers + hashes** (PMCID/DOI), not redistributed PDFs.
- Fixed seeds; all randomness (sampling temperature aside) controlled.
- Report bundles: config hash, corpus manifest, metric versions, judge model id.
