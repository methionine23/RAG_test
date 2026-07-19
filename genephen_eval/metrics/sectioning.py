"""S1 — Sectioning / chunking fidelity (docs/04 §2). Reference-free: the ground-truth
structure comes from the source markup."""
from __future__ import annotations

from typing import Dict, List

from ..schemas import Chunk, Document, InventoryUnit


def sectioning_metrics(chunks: List[Chunk], doc: Document,
                       inventory: List[InventoryUnit], boundary_tol: int = 2) -> Dict[str, float]:
    interior = [c.start for c in chunks if c.start != 0]
    aligned = sum(any(abs(b - x) <= boundary_tol for b in doc.boundaries) for x in interior)
    boundary_alignment = aligned / len(interior) if interior else 1.0

    tables = doc.tables
    intact = sum(any(c.contains(t.start, t.end) for c in chunks) for t in tables)
    table_integrity = intact / len(tables) if tables else 1.0

    local = sum(any(c.contains(u.span.start, u.span.end) for c in chunks) for u in inventory)
    fact_locality = local / len(inventory) if inventory else 1.0

    covered = set()
    for c in chunks:
        covered.update(range(c.start, c.end))
    coverage = len(covered) / len(doc.text) if doc.text else 1.0

    return {
        "boundary_alignment": round(boundary_alignment, 3),
        "table_integrity": round(table_integrity, 3),
        "fact_locality": round(fact_locality, 3),
        "coverage": round(coverage, 3),
    }
