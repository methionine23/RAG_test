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
prototype/
  fidelity_demo.py               runnable, stdlib-only reference-free fidelity demo
  README.md                      how to run it and what it approximates
```

## Quick start (prototype)

```bash
python3 prototype/fidelity_demo.py
```

No dependencies, no network — it runs a toy HSPB1-style example end-to-end and prints
per-cell support, an overall faithfulness score, coverage/recall against a
source-derived variant inventory, and flags a hallucinated cell and a missing variant.
It is a *stub* of the real metric stack described in `docs/02`.
