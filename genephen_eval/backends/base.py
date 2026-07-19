"""The `SummarizerBackend` interface — the key abstraction that makes genePhen, Vertex,
and the baseline notebook agent directly comparable on identical inputs (docs/03 §3)."""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ..schemas import BackendResult, Document, ExtractionTask


@runtime_checkable
class SummarizerBackend(Protocol):
    name: str

    def summarize(self, task: ExtractionTask, doc: Document,
                  temperature: float, seed: Optional[int] = None) -> BackendResult:
        """Extract `task` from `doc` at the given decoding temperature.

        Must populate `records`, and — for stage-decomposed scoring — the `chunks` it
        used and the `retrieved_context` it conditioned on. Set `provenance_supported`
        True only if per-cell source spans are emitted natively.
        """
        ...
