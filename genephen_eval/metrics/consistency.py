"""SelfCheckGPT-style self-consistency across K sampled generations (docs/02 §5).

Sampling variance is the signal: a fact that appears in only some samples is a fragile
extraction. This is the backbone of the temperature study.
"""
from __future__ import annotations

from itertools import combinations
from typing import Dict, List

from ..schemas import Record


def _fact_set(records: List[Record]) -> set:
    """Set-of-facts fingerprint of one generation (record.field:value)."""
    return {f"{rec.record_id}.{cell.field}:{cell.value}"
            for rec in records for cell in rec.cells()}


def stability(samples: List[List[Record]]) -> Dict:
    """samples = K generations (each a list[Record]) for the SAME input/config."""
    sets = [_fact_set(s) for s in samples]
    universe = set().union(*sets) if sets else set()
    per_fact = {f: sum(f in s for s in sets) / len(sets) for f in universe} if sets else {}
    mean_fact_stability = round(sum(per_fact.values()) / len(per_fact), 3) if per_fact else 1.0
    jac = [len(a & b) / len(a | b) for a, b in combinations(sets, 2) if (a | b)]
    return {
        "mean_fact_stability": mean_fact_stability,
        "mean_set_jaccard": round(sum(jac) / len(jac), 3) if jac else 1.0,
        "n_samples": len(sets),
        "unstable_facts": sorted(f for f, v in per_fact.items() if v < 1.0),
    }
