"""S2 — Retrieval fidelity (docs/04 §3) + a simple lexical retriever.

The lexical retriever is a stand-in; genePhen / Vertex retrieval replaces it behind the
same `retrieve(query, chunks, k)` signature.
"""
from __future__ import annotations

import re
from typing import Dict, List

from ..schemas import Chunk, Document, InventoryUnit


def _toks(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


class LexicalRetriever:
    """Token-overlap retriever (BM25-lite). Deterministic, dependency-free."""

    def retrieve(self, query: str, chunks: List[Chunk], k: int = 3) -> List[Chunk]:
        q = _toks(query)
        scored = sorted(chunks, key=lambda c: len(q & _toks(c.text)), reverse=True)
        return scored[:k]


def retrieval_metrics(retriever, chunks: List[Chunk], inventory: List[InventoryUnit],
                      doc: Document, k: int = 3) -> Dict[str, float]:
    hits, ceiling = 0, 0
    for u in inventory:
        query = _fact_query(u, doc)
        top = retriever.retrieve(query, chunks, k)
        if any(c.contains(u.span.start, u.span.end) for c in top):
            hits += 1                                   # retrievable as a whole unit
        if any(u.value in c.text for c in top):
            ceiling += 1                                # value present at all (recall ceiling)
    n = len(inventory) or 1
    return {
        "fact_hit_rate": round(hits / n, 3),
        "retrieval_ceiling": round(ceiling / n, 3),
    }


def _fact_query(u: InventoryUnit, doc: Document, window: int = 40) -> str:
    """Build a query from the fact's surrounding context, WITHOUT leaking its value."""
    s, e = u.span.start, u.span.end
    ctx = doc.text[max(0, s - window):s] + " " + doc.text[e:e + window]
    return ctx.replace(u.value, " ")
