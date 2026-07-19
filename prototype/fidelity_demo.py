#!/usr/bin/env python3
"""
Reference-free fidelity demo for clinical-genetic table extraction.

A stdlib-only, offline STUB of the metric stack in docs/02. It demonstrates the
three reference-free dimensions end-to-end on a toy HSPB1-style example:

  * Faithfulness   -- is each generated cell supported by the source?  (tier-1
                      exact/normalized grounding + a lexical-entailment fallback)
  * Completeness   -- silver recall: coverage of a source-derived variant inventory
  * Provenance     -- best-matching source sentence recovered per cell
  * Robustness     -- SelfCheckGPT-style stability across K sampled generations

In the real harness (docs/03) tier-2 uses MiniCheck/AlignScore and tier-3 uses a
guarded TREC-style LLM judge. Here those are approximated with token overlap so the
demo runs with no dependencies and no network.

Run:  python3 prototype/fidelity_demo.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Toy data: a source passage + a model-extracted mutation table.
# The table is deliberately imperfect:
#   - CASE row for c.404C>T / p.Ser135Phe  -> faithful (exact in source)
#   - a REWORDED-wrong inheritance value    -> hallucination (source says AD, table AR)
#   - c.250G>A / p.Gly84Arg is in source    -> MISSING from the table (recall hit)
# --------------------------------------------------------------------------- #

SOURCE = """\
We report two families with distal hereditary motor neuropathy caused by HSPB1 variants.
In Family 1, the proband carried a heterozygous c.404C>T (p.Ser135Phe) variant in HSPB1,
segregating with an autosomal dominant pattern across three generations.
Functional assays showed the p.Ser135Phe mutant reduced chaperone activity.
In Family 2, a second heterozygous variant c.250G>A (p.Gly84Arg) was identified in HSPB1
in a patient with adult-onset lower-limb weakness.
"""

# One equivalent surface variant map for tier-1 "normalized" grounding.
# (The real harness uses hgvs/Mutalyzer; here a tiny hand map suffices for the demo.)
HGVS_EQUIV = {
    "p.S135F": "p.Ser135Phe",
    "p.G84R": "p.Gly84Arg",
}


@dataclass
class Cell:
    record_id: str
    field: str
    value: str


@dataclass
class Record:
    record_id: str
    cells: dict


# The model output for ONE run (the "primary" sample we score in detail).
PRIMARY_TABLE = [
    Record("V1", {
        "gene": "HSPB1",
        "hgvs_c": "c.404C>T",
        "hgvs_p": "p.S135F",          # reworded surface form -> should match via normalization
        "zygosity": "heterozygous",
        "inheritance": "autosomal recessive",  # WRONG: source says dominant -> hallucination
    }),
]

# K sampled generations (variant sets only) to demonstrate stability / SelfCheck.
# Higher-temperature-like variance: c.250G>A shows up in only some samples.
SAMPLED_VARIANT_SETS = [
    {"c.404C>T"},
    {"c.404C>T", "c.250G>A"},
    {"c.404C>T"},
    {"c.404C>T", "c.404C>T"},   # dup collapses
    {"c.404C>T", "c.250G>A"},
]

TAU = 0.5  # hallucination threshold

# Categorical / identifier fields are exact-match by nature: if the specific value
# isn't grounded in the source it is unsupported (real harness: confirmed by the
# LLM judge). Only genuinely free-text fields fall back to tier-2 lexical entailment.
CATEGORICAL_FIELDS = {"gene", "hgvs_c", "hgvs_p", "transcript", "dbsnp",
                      "zygosity", "inheritance", "classification"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def tokens(s: str) -> set:
    return set(re.findall(r"[a-z0-9.>]+", s.lower()))


def normalize_value(v: str) -> str:
    return HGVS_EQUIV.get(v, v)


def best_span(value: str, srcs: list[str]) -> tuple[str, float]:
    """Recovered provenance: source sentence with highest token overlap with the value."""
    vt = tokens(value)
    if not vt:
        return "", 0.0
    best, best_score = "", 0.0
    for s in srcs:
        score = len(vt & tokens(s)) / len(vt)
        if score > best_score:
            best, best_score = s, score
    return best, best_score


# --------------------------------------------------------------------------- #
# Metric 1: faithfulness (tiered, reference-free)
# --------------------------------------------------------------------------- #

def ground(value: str, source: str) -> str:
    """Tier-1 grounding: exact | normalized | absent."""
    if value.lower() in source.lower():
        return "exact"
    if normalize_value(value).lower() in source.lower():
        return "normalized"
    return "absent"


def lexical_entailment(value: str, span: str) -> float:
    """Tier-2 stand-in for MiniCheck/AlignScore: token-overlap of value against its span."""
    vt = tokens(value)
    return (len(vt & tokens(span)) / len(vt)) if vt else 0.0


def score_cell(cell: Cell, source: str, srcs: list[str]) -> dict:
    g = ground(cell.value, source)
    span, span_score = best_span(cell.value, srcs)
    if g == "exact":
        s = 1.0
    elif g == "normalized":
        s = 0.9
    elif cell.field in CATEGORICAL_FIELDS:
        # absent + categorical -> the specific value is not supported
        s = 0.0
    else:
        # free-text field: tier-2 fallback (real harness: NLI/LLM-judge vs the cited span)
        s = round(lexical_entailment(cell.value, span), 2)
    return {
        "cell": f"{cell.record_id}.{cell.field}",
        "value": cell.value,
        "grounding": g,
        "s_faith": s,
        "provenance": span,
        "prov_score": round(span_score, 2),
        "hallucination": s < TAU,
    }


# --------------------------------------------------------------------------- #
# Metric 2: completeness (silver recall vs source-derived inventory)
# --------------------------------------------------------------------------- #

VARIANT_RE = re.compile(r"\bc\.\d+[ACGT]>[ACGT]\b|\bp\.[A-Z][a-z]{2}\d+[A-Z][a-z]{2}\b")


def build_inventory(source: str) -> set:
    """High-recall, fully source-grounded 'should-capture' variant set."""
    return set(VARIANT_RE.findall(source))


def silver_recall(inventory: set, extracted: set) -> tuple[float, set]:
    # match c. keys; also credit p. forms present in inventory
    inv_c = {v for v in inventory if v.startswith("c.")}
    hit = inv_c & extracted
    recall = len(hit) / len(inv_c) if inv_c else 1.0
    missing = inv_c - extracted
    return recall, missing


# --------------------------------------------------------------------------- #
# Metric 3: self-consistency (SelfCheckGPT-style)
# --------------------------------------------------------------------------- #

def stability(samples: list[set]) -> dict:
    from itertools import combinations
    all_vars = set().union(*samples)
    per_var = {v: sum(v in s for s in samples) / len(samples) for v in all_vars}
    jac = [len(a & b) / len(a | b) for a, b in combinations([s for s in samples], 2) if (a | b)]
    return {
        "per_variant_stability": {k: round(v, 2) for k, v in sorted(per_var.items())},
        "mean_set_jaccard": round(sum(jac) / len(jac), 2) if jac else 1.0,
    }


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

def main() -> None:
    srcs = sentences(SOURCE)
    cells = [Cell(r.record_id, f, v) for r in PRIMARY_TABLE for f, v in r.cells.items()]

    print("=" * 74)
    print("REFERENCE-FREE FIDELITY DEMO  (toy HSPB1 example, stdlib-only stub)")
    print("=" * 74)

    # --- Faithfulness ---
    print("\n[1] FAITHFULNESS  (per-cell grounding vs source)")
    print("-" * 74)
    scored = [score_cell(c, SOURCE, srcs) for c in cells]
    for r in scored:
        flag = "  <== HALLUCINATION" if r["hallucination"] else ""
        print(f"  {r['cell']:<18} {r['value']:<22} "
              f"grounding={r['grounding']:<10} s_faith={r['s_faith']:<4}{flag}")
    faith = sum(r["s_faith"] for r in scored) / len(scored)
    halluc = sum(r["hallucination"] for r in scored) / len(scored)
    print(f"\n  table faithfulness = {faith:.2f}   hallucination_rate = {halluc:.0%}")

    # --- Provenance ---
    print("\n[2] PROVENANCE  (recovered best-matching source sentence per cell)")
    print("-" * 74)
    for r in scored:
        if r["provenance"]:
            print(f"  {r['cell']:<18} (match={r['prov_score']}) -> \"{r['provenance'][:60]}...\"")

    # --- Completeness ---
    print("\n[3] COMPLETENESS  (silver recall vs source-derived inventory)")
    print("-" * 74)
    inv = build_inventory(SOURCE)
    extracted = {r.cells.get("hgvs_c") for r in PRIMARY_TABLE}
    extracted.discard(None)
    recall, missing = silver_recall(inv, extracted)
    print(f"  inventory (source-derived): {sorted(inv)}")
    print(f"  extracted (c.):             {sorted(extracted)}")
    print(f"  silver_recall = {recall:.2f}   missing = {sorted(missing) or 'none'}"
          + ("   <== MISSED VARIANT" if missing else ""))

    # --- Robustness ---
    print("\n[4] ROBUSTNESS  (SelfCheckGPT-style stability across K samples)")
    print("-" * 74)
    st = stability(SAMPLED_VARIANT_SETS)
    for v, s in st["per_variant_stability"].items():
        note = "  (unstable extraction)" if s < 1.0 else ""
        print(f"  {v:<12} appears in {s:.0%} of samples{note}")
    print(f"  mean set Jaccard across samples = {st['mean_set_jaccard']}")

    # --- Overall ---
    print("\n" + "=" * 74)
    fidelity = 0.5 * faith + 0.3 * recall + 0.2 * (1 - halluc)
    print(f"OVERALL FIDELITY (0.5*faith + 0.3*recall + 0.2*(1-halluc)) = {fidelity:.2f}")
    print("=" * 74)
    print("\nWhat the demo caught, reference-free (no gold table):")
    print("  * a reworded surface form (p.S135F) rescued via normalization")
    print("  * an inaccurate inheritance value flagged as a hallucination")
    print("  * a variant present in the source but MISSING from the table")
    print("  * an unstable variant that only appears at higher sampling variance")


if __name__ == "__main__":
    main()
