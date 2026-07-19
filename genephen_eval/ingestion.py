"""Ingestion: parse source documents into a linearized `Document` with structure
preserved, and split them into `Chunk`s.

`parse_pmc_xml` handles PubMed/PMC-style XML (the UC1 source). GTR-XML and PDF parsers
(UC2/UC3) are future modules with the same `Document` output contract (docs/04 §7).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import List

from .schemas import Chunk, Document, Segment


def parse_pmc_xml(path: str, doc_id: str | None = None) -> Document:
    """Parse PMC/PubMed full-text XML into a linearized Document.

    Sections and tables become `Segment`s; paragraph / section / table-row boundaries
    are recorded so sectioning fidelity can be measured against true structure.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    doc_id = doc_id or (root.findtext(".//article-id[@pub-id-type='pmid']") or path)

    text = ""
    segments: List[Segment] = []
    boundaries = {0}

    for sec in root.iter("sec"):
        sec_start = len(text)
        title = sec.findtext("title") or sec.get("sec-type", "section")
        text += f"[{title}] "
        for p in sec.findall("p"):
            text += " ".join((p.text or "").split()) + " "
            boundaries.add(len(text))
        for tw in sec.findall(".//table-wrap"):
            tbl_start = len(text)
            label = tw.findtext("label") or "Table"
            headers = [(th.text or "") for th in tw.findall(".//thead//th")]
            text += f"{label}: " + " | ".join(headers) + " ;; "
            for tr in tw.findall(".//tbody//tr"):
                cells = [(td.text or "") for td in tr.findall("td")]
                text += " | ".join(cells) + " ;; "
                boundaries.add(len(text))
            segments.append(Segment("table", label, tbl_start, len(text)))
        segments.append(Segment("section", title, sec_start, len(text)))
        boundaries.add(len(text))

    return Document(doc_id=str(doc_id), text=text, segments=segments,
                    boundaries=sorted(boundaries))


# --------------------------------------------------------------------------- #
# Chunkers
# --------------------------------------------------------------------------- #

def chunk_naive_fixed(doc: Document, size: int = 320) -> List[Chunk]:
    """Structure-blind fixed-size character window (baseline / worst case)."""
    out = []
    for i, s in enumerate(range(0, len(doc.text), size)):
        e = min(s + size, len(doc.text))
        out.append(Chunk(i, s, e, doc.text[s:e]))
    return out


def chunk_section_aware(doc: Document) -> List[Chunk]:
    """One chunk per section; each source table is kept intact as its own chunk."""
    spans = sorted({(s.start, s.end) for s in doc.segments})
    return [Chunk(i, s, e, doc.text[s:e]) for i, (s, e) in enumerate(spans)]


CHUNKERS = {
    "naive_fixed": chunk_naive_fixed,
    "section_aware": chunk_section_aware,
}
