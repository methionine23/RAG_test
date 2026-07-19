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
prototype/
  fidelity_demo.py               stdlib-only reference-free cell-level fidelity demo
  rag_stage_demo.py              stdlib-only sectioning + retrieval fidelity + attribution demo
  fetch_entrez.py                pull full HSPB1 XML from NCBI (run where NCBI egress is allowed)
  sample/hspb1_pubmed_sample.xml synthetic PubMed-XML fixture (offline demo input)
  README.md                      how to run the demos and what they approximate
```

## Quick start (prototypes, no deps / no network)

```bash
python3 prototype/fidelity_demo.py     # cell-level faithfulness / recall / provenance / stability
python3 prototype/rag_stage_demo.py    # sectioning + retrieval fidelity, with per-fact stage attribution
```

`fidelity_demo.py` runs a toy HSPB1 example and flags a hallucinated cell + a missing
variant with no gold table. `rag_stage_demo.py` parses the PubMed-XML fixture, compares a
structure-blind chunker vs a section-aware one, and shows *which stage* (sectioning vs
retrieval) loses each fact. Both are stubs of the metric stack in `docs/02` and `docs/04`.

> **Note on data:** NCBI Entrez egress is blocked inside the agent sandbox, so the demos
> use a synthetic fixture. Run `prototype/fetch_entrez.py` in your Vertex/GCP environment
> to pull real full XML (`db=pmc`) for the HSPB1 use case.
