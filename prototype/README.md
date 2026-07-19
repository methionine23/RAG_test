# Prototype — reference-free fidelity demos

Tiny, **dependency-free, offline** demonstrations of the metrics designed in
[`../docs/02`](../docs/02_metrics_and_experiments.md) (cell-level fidelity) and
[`../docs/04`](../docs/04_rag_stage_evaluation.md) (stage-decomposed fidelity).

```bash
python3 fidelity_demo.py     # cell-level: faithfulness / recall / provenance / stability
python3 rag_stage_demo.py    # stage-level: sectioning + retrieval fidelity + attribution
```

## Files

| File | Purpose |
| --- | --- |
| `fidelity_demo.py` | cell-level reference-free fidelity on a toy mutation table (§ below) |
| `rag_stage_demo.py` | parses `sample/hspb1_pubmed_sample.xml`, compares a structure-blind vs section-aware chunker, and attributes each lost fact to sectioning or retrieval |
| `fetch_entrez.py` | pull real full HSPB1 XML from NCBI (run where NCBI egress is allowed; blocked in the agent sandbox) |
| `sample/hspb1_pubmed_sample.xml` | synthetic PubMed-XML fixture (structurally modeled, not a redistributed article) |

## What `fidelity_demo.py` shows

On a toy HSPB1-style passage + a deliberately-imperfect extracted mutation table, with
**no gold reference table**, it computes:

| Section | Dimension | What it demonstrates |
| --- | --- | --- |
| `[1] FAITHFULNESS` | faithfulness | per-cell tier-1 grounding (exact / normalized / absent); a reworded HGVS form (`p.S135F`) rescued by normalization; a wrong `inheritance` value flagged as a hallucination |
| `[2] PROVENANCE` | attribution | best-matching source sentence recovered per cell (backend emitted none) |
| `[3] COMPLETENESS` | recall | silver recall vs a source-derived variant inventory; a variant present in the source but missing from the table |
| `[4] ROBUSTNESS` | stability | SelfCheckGPT-style stability across K sampled generations; an unstable variant that only appears in some samples |

## What is a stub (and becomes real in the harness)

- **Tier-2 entailment** here is token overlap → real harness uses **MiniCheck / AlignScore**.
- **Tier-3 support** is not invoked here → real harness uses a **guarded TREC-style
  LLM judge** (cross-family model, fixed rubric, self-consistent, human-calibrated).
- **Normalization** is a 2-entry hand map → real harness uses **hgvs / Mutalyzer**.
- **Inventory** is an HGVS regex → real harness adds **tmVar-style NER + source-table
  parsing + clinical NER**.
- **Samples** are hard-coded → real harness draws K generations per backend/temperature.

The scoring *structure* (tiers, silver recall, stability, weighted fidelity) mirrors the
real design so this file is a faithful skeleton, not a throwaway.

## What `rag_stage_demo.py` shows

On the PubMed-XML fixture, with **no gold table**, it computes stage-decomposed fidelity
(`docs/04`) for two chunkers over the same document and retriever:

| chunker | boundary_align | table_integrity | fact_locality | fact_hit_rate | retrieval_ceiling |
| --- | --- | --- | --- | --- | --- |
| `naive_fixed(320)` | 0.00 | 0.00 | 0.92 | 0.92 | 0.92 |
| `section_aware` | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

The per-fact **attribution** column labels each gold fact `SECTIONING` / `RETRIEVAL` /
`ok`, showing the naive chunker splitting a variant at a chunk boundary. Stubs replaced
in the real harness: the toy token-overlap retriever → genePhen / Vertex retrieval; the
XML section parser → a PDF layout parser (UC2) and a GTR-schema parser (UC3).
