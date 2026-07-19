"""Core data structures shared across ingestion, backends, and metrics.

Everything is plain dataclasses (stdlib only) so the harness runs with no heavy
dependencies. Model-based metrics (NLI, LLM-judge) attach later behind the pluggable
interfaces in metrics/ — the defaults use lexical/grounding fallbacks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


@dataclass(frozen=True)
class Span:
    """A source passage, with its offsets into the linearized document text."""
    doc_id: str
    start: int
    end: int
    text: str
    source_type: str = "prose"      # prose | table | figure_caption | xml_field
    recovered: bool = False         # True if we recovered it post-hoc, not backend-emitted


@dataclass
class Cell:
    """One (record, field, value) unit — the atom of generation-stage scoring."""
    record_id: str
    field: str
    value: str
    provenance: Optional[Span] = None
    input_span: Optional[Span] = None   # the text actually fed to the model (docs/05 §1)


@dataclass
class Record:
    """A generated table row (a variant, a case, or a relation triple)."""
    record_id: str
    kind: str                        # mutation | case | triple
    values: Dict[str, str] = field(default_factory=dict)
    provenance: Dict[str, Span] = field(default_factory=dict)
    input_span: Optional[Span] = None

    def cells(self) -> Iterator[Cell]:
        for f, v in self.values.items():
            if v is None or str(v).strip() == "":
                continue
            yield Cell(self.record_id, f, str(v),
                       provenance=self.provenance.get(f),
                       input_span=self.input_span)


@dataclass(frozen=True)
class Segment:
    """Ground-truth structural unit from the source markup (a section or a table)."""
    kind: str                        # section | table
    label: str
    start: int
    end: int


@dataclass(frozen=True)
class Chunk:
    """A retrievable unit produced by a chunker."""
    id: int
    start: int
    end: int
    text: str

    def contains(self, start: int, end: int, tol: int = 0) -> bool:
        return self.start - tol <= start and end <= self.end + tol


@dataclass(frozen=True)
class InventoryUnit:
    """A source-derived 'should-capture' fact — the reference-free recall standard."""
    kind: str                        # variant | case_cell | triple
    key: str
    value: str
    span: Span
    detector: str


@dataclass
class Document:
    """A source document, linearized to text with structure + boundaries preserved."""
    doc_id: str
    text: str
    segments: List[Segment] = field(default_factory=list)
    boundaries: List[int] = field(default_factory=list)

    @property
    def sections(self) -> List[Segment]:
        return [s for s in self.segments if s.kind == "section"]

    @property
    def tables(self) -> List[Segment]:
        return [s for s in self.segments if s.kind == "table"]


@dataclass
class ExtractionTask:
    """What the backend is asked to extract, and the retrieval query for it."""
    kind: str                        # mutation | case | triple
    fields: List[str]
    query: str = ""
    instructions: str = ""


@dataclass
class BackendResult:
    """Uniform backend output. `chunks` + `retrieved_context` are the two signals the
    genePhen plugin will emit in a later phase (docs/05 §3); here the mock backend fills
    them so S1/S2 metrics run end-to-end."""
    records: List[Record]
    chunks: List[Chunk] = field(default_factory=list)
    retrieved_context: List[Chunk] = field(default_factory=list)
    provenance_supported: bool = False
    raw: Any = None
