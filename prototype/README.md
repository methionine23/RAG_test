# Prototype — reference-free fidelity demo

A tiny, **dependency-free, offline** demonstration of the reference-free fidelity
metrics designed in [`../docs/02_metrics_and_experiments.md`](../docs/02_metrics_and_experiments.md).

```bash
python3 fidelity_demo.py
```

## What it shows

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
