"""S3 — Generation fidelity: faithfulness, completeness, provenance (docs/02 §2–4).

Tiered faithfulness:
  tier 1  exact / normalized value grounding   (implemented here)
  tier 2  NLI entailment for free-text fields   (pluggable `entailment_fn`; lexical default)
  tier 3  guarded LLM-judge for hard cells       (future; interface only)
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional

from ..schemas import InventoryUnit, Record

# Default HGVS surface-form equivalences used at MATCH time only (normalization
# *correctness* is out of scope; docs/00 §2). Real harness: hgvs / Mutalyzer.
DEFAULT_EQUIV = {
    "p.S135F": "p.Ser135Phe", "p.G84R": "p.Gly84Arg", "p.P182L": "p.Pro182Leu",
}

CATEGORICAL_FIELDS = {"gene", "hgvs_c", "hgvs_p", "variant", "Mutation", "transcript",
                      "dbsnp", "sex", "Sex", "zygosity", "inheritance", "classification",
                      "age_onset", "Age_of_onset", "Age", "onset"}

FREE_TEXT_FIELDS = {"symptom", "Symptoms", "Laboratory_findings", "Family_history",
                    "disease", "evidence",
                    # UC3 GTR schema fields: disease/method names are free text, so a
                    # reworded surface form earns partial (lexical/NLI) credit.
                    "condition", "method", "test", "test_name"}


def _toks(s: str) -> set:
    return set(re.findall(r"[a-z0-9.>]+", s.lower()))


def _present(value: str, source: str) -> bool:
    """Word-boundary match, so short codes ('AR', 'AD') don't match inside words
    ('Marie', 'Arg'). Falls back to substring for values without word chars at the edge."""
    v = value.strip()
    if not v:
        return False
    return re.search(r"(?<!\w)" + re.escape(v) + r"(?!\w)", source, re.IGNORECASE) is not None


def ground(value: str, source: str, equiv: Dict[str, str]) -> str:
    """tier-1 grounding: exact | normalized | absent."""
    if _present(value, source):
        return "exact"
    if _present(equiv.get(value, value), source):
        return "normalized"
    return "absent"


def _lexical_entailment(value: str, source: str) -> float:
    vt = _toks(value)
    if not vt:
        return 0.0
    # best single-sentence overlap keeps the judgment local/dense (docs/04 caveat)
    best = 0.0
    for sent in re.split(r"(?<=[.;])\s+", source):
        best = max(best, len(vt & _toks(sent)) / len(vt))
    return best


def cell_faithfulness(records: List[Record], source: str,
                      equiv: Optional[Dict[str, str]] = None,
                      entailment_fn: Optional[Callable[[str, str], float]] = None,
                      tau: float = 0.5) -> Dict:
    equiv = equiv or DEFAULT_EQUIV
    entail = entailment_fn or _lexical_entailment
    per_cell = []
    for rec in records:
        for cell in rec.cells():
            g = ground(cell.value, source, equiv)
            if g == "exact":
                s = 1.0
            elif g == "normalized":
                s = 0.9
            elif cell.field in CATEGORICAL_FIELDS:
                s = 0.0                          # specific categorical value unsupported
            else:
                s = round(entail(cell.value, source), 3)
            per_cell.append({"cell": f"{cell.record_id}.{cell.field}", "value": cell.value,
                             "grounding": g, "s_faith": s, "hallucination": s < tau})
    n = len(per_cell) or 1
    return {
        "faithfulness": round(sum(c["s_faith"] for c in per_cell) / n, 3),
        "hallucination_rate": round(sum(c["hallucination"] for c in per_cell) / n, 3),
        "n_cells": len(per_cell),
        "per_cell": per_cell,
    }


def silver_recall(inventory: List[InventoryUnit], records: List[Record]) -> Dict:
    """Coverage of the source-derived inventory (reference-free recall, docs/02 §4)."""
    extracted_vals = set()
    extracted_case = set()
    for rec in records:
        for cell in rec.cells():
            extracted_vals.add(cell.value)
            extracted_vals.add(DEFAULT_EQUIV.get(cell.value, cell.value))
            extracted_case.add(f"{rec.record_id}.{cell.field}:{cell.value}")

    def hit(u: InventoryUnit) -> bool:
        if u.value in extracted_vals or DEFAULT_EQUIV.get(u.value, u.value) in extracted_vals:
            return True
        return any(u.value in c for c in extracted_case)

    inv = inventory or []
    variants = [u for u in inv if u.kind == "variant"]
    cases = [u for u in inv if u.kind == "case_cell"]
    hits = [u for u in inv if hit(u)]
    missing = [u.key for u in inv if not hit(u)]

    def r(us):
        return round(sum(hit(u) for u in us) / len(us), 3) if us else 1.0

    return {
        "silver_recall": round(len(hits) / len(inv), 3) if inv else 1.0,
        "recall_variants": r(variants),
        "recall_case_cells": r(cases),
        "missing": missing,
    }


def provenance_scores(records: List[Record], source: str) -> Dict:
    cells = [c for rec in records for c in rec.cells()]
    with_prov = [c for c in cells if c.provenance is not None]
    valid = sum(1 for c in with_prov
                if c.value.lower() in (c.provenance.text or "").lower()
                or DEFAULT_EQUIV.get(c.value, c.value).lower() in (c.provenance.text or "").lower())
    n = len(cells) or 1
    return {
        "attribution_coverage": round(len(with_prov) / n, 3),
        "attribution_validity": round(valid / len(with_prov), 3) if with_prov else 0.0,
    }
