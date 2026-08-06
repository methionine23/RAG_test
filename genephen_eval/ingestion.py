"""Ingestion: parse source documents into a linearized `Document` with structure
preserved, and split them into `Chunk`s.

`parse_pmc_xml` handles PubMed/PMC-style XML (the UC1 source). `parse_gtr_xml` handles
NIH GTR (Genetic Testing Registry) XML (the UC3 source), routed along the GTR schema
(lab test → gene / condition / method) rather than by character windows (docs/04 §7).
Both emit the same `Document` output contract. The PDF parser (UC2) is a future module
with the same contract.
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


def parse_gtr_xml(path: str, doc_id: str | None = None) -> Document:
    """Parse NIH GTR (Genetic Testing Registry) XML into a linearized Document.

    Each `<GTRLabTest>` becomes one `section` Segment; its schema fields (gene, lab,
    each condition, each method) are linearized as `field: value ;;` lines with a
    boundary recorded at every element edge. This is the UC3 "chunk along the schema"
    source (docs/04 §7): sectioning fidelity ≈ correct element-to-field routing.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    doc_id = doc_id or (root.findtext(".//GTRLabTest/TestName") or path)

    text = ""
    segments: List[Segment] = []
    boundaries = {0}

    for test in root.iter("GTRLabTest"):
        sec_start = len(text)
        name = " ".join((test.findtext("TestName") or "Genetic Test").split())
        text += f"[Test: {name}] "
        boundaries.add(len(text))

        genes = [(g.findtext("Symbol") or g.text or "").strip()
                 for g in test.findall(".//Gene")]
        genes = [g for g in genes if g]
        if genes:
            text += "Gene: " + ", ".join(genes) + " ;; "
            boundaries.add(len(text))

        org = (test.findtext("Organization") or "").strip()
        if org:
            text += f"Lab: {org} ;; "
            boundaries.add(len(text))

        for cond in test.findall(".//Condition"):
            cname = " ".join((cond.findtext("Name") or "").split())
            if cname:
                text += f"Condition: {cname} ;; "
                boundaries.add(len(text))

        for meth in test.findall(".//Method"):
            mname = " ".join((meth.findtext("Name") or "").split())
            if mname:
                text += f"Method: {mname} ;; "
                boundaries.add(len(text))

        segments.append(Segment("section", name, sec_start, len(text)))
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


def chunk_gtr_schema(doc: Document) -> List[Chunk]:
    """UC3 schema-aware chunker: one chunk per GTR lab test (docs/04 §7).

    The test is the schema-natural retrievable unit — keeping a test's gene, conditions
    and methods together preserves element-to-field routing. Mechanically equivalent to
    `section_aware` on GTR docs (all segments are sections), but named to make the UC3
    intent explicit and to stay correct if GTR parsing later emits table segments too.
    """
    spans = sorted({(s.start, s.end) for s in doc.sections})
    return [Chunk(i, s, e, doc.text[s:e]) for i, (s, e) in enumerate(spans)]


CHUNKERS = {
    "naive_fixed": chunk_naive_fixed,
    "section_aware": chunk_section_aware,
    "gtr_schema": chunk_gtr_schema,
}
