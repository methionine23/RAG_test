# genephen_eval

Reference-free, **stage-decomposed** fidelity evaluation for LLM/RAG clinical-genetic
summarization. Standalone harness — genePhen and Vertex RAG Engine attach later as
`SummarizerBackend`s (a future phase; see `../docs/05`).

## Run it

```bash
# end-to-end fidelity report on a PMC/PubMed XML doc (mock backend, no network/model)
python -m genephen_eval.cli --xml prototype/sample/hspb1_pubmed_sample.xml --task case

# compare a structure-blind vs section-aware chunker
python -m genephen_eval.cli --xml prototype/sample/hspb1_pubmed_sample.xml --chunker naive_fixed

# tests (stdlib unittest, no pytest required)
python -m unittest discover -s tests
```

## What it computes (per docs/02 & docs/04)

| Stage | Module | Metrics |
| --- | --- | --- |
| S1 Sectioning/chunking | `metrics/sectioning.py` | boundary alignment, table integrity, fact locality, coverage |
| S2 Retrieval | `metrics/retrieval.py` | fact hit-rate, context recall, retrieval ceiling |
| S3 Generation | `metrics/generation.py` | tiered faithfulness, hallucination rate, silver recall, provenance |
| Robustness | `metrics/consistency.py` | SelfCheckGPT-style stability across K samples |
| Attribution | `metrics/attribution.py` | per-fact loss budget: SECTIONING / RETRIEVAL / GENERATION |

The runner (`runner.py`) sweeps a **temperature grid** with **K samples per cell** and
reports a table where — with the mock backend — faithfulness and recall fall, the
hallucination rate rises, self-consistency drops, and the attribution budget shifts to
GENERATION as temperature increases. S1/S2 stay flat (structure/retrieval are fixed by
the chunker/retriever), so the added loss is correctly localized to generation.

## Architecture

```
schemas.py     Span / Cell / Record / Chunk / InventoryUnit / Document / BackendResult
ingestion.py   parse_pmc_xml + chunkers (naive_fixed, section_aware)
inventory.py   source-derived fact inventory (variants + case cells) = reference-free recall standard
metrics/       sectioning, retrieval, generation, consistency, attribution
backends/      base.SummarizerBackend (interface) + mock.MockRAGBackend (deterministic, offline)
runner.py      temperature × K-sample orchestration → stage metrics + attribution
report.py      text report
cli.py         `python -m genephen_eval.cli`
```

## Pluggability (what changes when real models arrive)

- **Backend**: implement `SummarizerBackend.summarize(...)` for genePhen / Vertex; emit
  `chunks` (chunk boundaries) and `retrieved_context` so S1/S2 score real internals.
- **Faithfulness tier-2/3**: pass an `entailment_fn` (MiniCheck/AlignScore) into
  `cell_faithfulness`; add the guarded LLM-judge for hard cells.
- **Retriever**: swap `LexicalRetriever` for the RAG engine's retriever behind the same
  `retrieve(query, chunks, k)` signature.
- **Inventory**: add tmVar-style NER + clinical NER to `inventory.py`.

Everything else — metrics, attribution, temperature sweep, reporting — stays put.
