"""Error attribution (docs/04 §5): assign each inventory fact to the stage that lost it.

  not local in any chunk           -> SECTIONING
  local but not retrieved in top-k -> RETRIEVAL
  retrieved but absent from output -> GENERATION
  present & grounded in output     -> ok
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List

from ..schemas import Chunk, Document, InventoryUnit, Record
from .generation import DEFAULT_EQUIV
from .retrieval import _fact_query


def attribute(inventory: List[InventoryUnit], chunks: List[Chunk],
              retrieved: List[Chunk], records: List[Record], doc: Document) -> Dict:
    extracted = set()
    for rec in records:
        for cell in rec.cells():
            extracted.add(cell.value)
            extracted.add(DEFAULT_EQUIV.get(cell.value, cell.value))

    rows = []
    counts = Counter()
    for u in inventory:
        local = any(c.contains(u.span.start, u.span.end) for c in chunks)
        in_retrieved = any(c.contains(u.span.start, u.span.end) for c in retrieved) \
            or any(u.value in c.text for c in retrieved)
        in_output = u.value in extracted or DEFAULT_EQUIV.get(u.value, u.value) in extracted

        if in_output:
            cause = "ok"
        elif not local:
            cause = "SECTIONING"
        elif not in_retrieved:
            cause = "RETRIEVAL"
        else:
            cause = "GENERATION"
        counts[cause] += 1
        rows.append({"kind": u.kind, "key": u.key, "cause": cause})

    total = len(inventory) or 1
    budget = {k: round(counts.get(k, 0) / total, 3)
              for k in ("ok", "SECTIONING", "RETRIEVAL", "GENERATION")}
    return {"loss_budget": budget, "counts": dict(counts), "rows": rows}
