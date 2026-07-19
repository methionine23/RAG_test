# RAG Fidelity for Clinical-Genetic Literature Summarization

Evaluating the **fidelity (faithfulness + completeness + provenance)** of LLM- and
RAG-based summarization when turning genetics papers into structured **mutation** and
**clinical-case** tables.

## Why this exists

Summarizing genetics literature into tables with an LLM agent produces two recurring
failures:

1. **Inaccuracy** — values get re-worded into something subtly (or grossly) wrong.
2. **Missing information** — variants / case facts present in the paper never make it
   into the table.

Both worsen as decoding **temperature** rises. This project builds a tool and an
experiment protocol to *measure* these effects rigorously, so we can compare
summarizer backends (the custom **genePhen** RAG, **Vertex AI RAG Engine**, and
no-RAG baselines) and tune them on evidence rather than anecdote.

## Design decisions (locked for this iteration)

| Decision | Choice |
| --- | --- |
| Ground truth | **Reference-free** — no human gold tables. Score against *source-derived* evidence and a mechanically-built fact inventory (see `docs/02`). |
| Fidelity dimensions | **Faithfulness / no-hallucination**, **Completeness / recall**, **Provenance / attribution**. (Variant *normalization* correctness is out of scope for now.) |
| Codebase | **Net-new standalone harness**; genePhen + Vertex plug in as pluggable `SummarizerBackend`s. |
| Scope this session | Plan + design docs + a **runnable reference-free fidelity prototype** (`prototype/`). |

## Repository map

```
README.md                        ← you are here
docs/
  00_PLAN.md                     master plan: goals, phases, deliverables, risks, timeline
  01_literature_review.md        metrics + benchmarks catalog (cited), and what we adopt
  02_metrics_and_experiments.md  reference-free metric definitions, the 3 use cases, temperature study
  03_schemas_and_architecture.md data schemas + harness architecture + backend interface
  04_rag_stage_evaluation.md     stage-decomposed fidelity (sectioning → retrieval → generation) + attribution
  05_prior_art_and_genephen_plugin.md  baseline notebook analysis + genePhen plugin path
genephen_eval/                   ← the evaluation harness (real, tested package)
  schemas.py ingestion.py inventory.py runner.py report.py cli.py
  metrics/   sectioning · retrieval · generation · consistency · attribution
  backends/  base (SummarizerBackend) · mock (deterministic, offline)
  README.md
tests/test_harness.py            13 unit + end-to-end tests (stdlib unittest)
prototype/                       ← standalone illustrative demos + data
  fidelity_demo.py rag_stage_demo.py fetch_entrez.py sample/hspb1_pubmed_sample.xml
pyproject.toml
```

## Quick start (no deps / no network)

```bash
# the harness: end-to-end fidelity report (ingest → chunk → retrieve → extract → S1/S2/S3 → attribution)
python3 -m genephen_eval.cli --xml prototype/sample/hspb1_pubmed_sample.xml --task case
python3 -m genephen_eval.cli --xml prototype/sample/hspb1_pubmed_sample.xml --chunker naive_fixed
python3 -m unittest discover -s tests          # 13 tests

# the standalone illustrative demos
python3 prototype/fidelity_demo.py             # cell-level faithfulness / recall / provenance / stability
python3 prototype/rag_stage_demo.py            # sectioning + retrieval fidelity + per-fact attribution
```

The harness sweeps a temperature grid with K samples per cell; with the offline mock
backend, faithfulness and recall fall, hallucination rises, self-consistency drops, and
the attribution loss budget shifts to GENERATION as temperature increases — while S1/S2
stay flat. genePhen / Vertex plug in later behind `SummarizerBackend` (see
`genephen_eval/README.md` and `docs/05`).

> **Note on data:** NCBI Entrez egress is blocked inside the agent sandbox, so the demos
> use a synthetic fixture. Run `prototype/fetch_entrez.py` in your Vertex/GCP environment
> to pull real full XML (`db=pmc`) for the HSPB1 use case.
