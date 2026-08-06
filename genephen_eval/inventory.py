"""Source-derived fact inventory — the reference-free recall standard (docs/02 §4).

High-recall, fully source-grounded detectors build the set of 'should-capture' facts.
Every unit keeps its source span so inventory quality can be audited on the P5
calibration set. Real harness adds tmVar-style NER + clinical NER; here we ship an
HGVS-regex variant detector and a linearized-table case-cell detector.
"""
from __future__ import annotations

import re
from typing import List

from .schemas import Document, InventoryUnit, Span

VARIANT_RE = re.compile(r"p\.[A-Z][a-z]{2}\d+[A-Z][a-z]{2}|c\.\d+[ACGT]>[ACGT]")
# a linearized table row: case | sex | onset | p.variant | inheritance | symptom
CASE_ROW_RE = re.compile(
    r"(?P<case>\d)\s*\|\s*(?P<sex>Male|Female)\s*\|\s*(?P<onset>\d+)\s*\|\s*"
    r"(?P<variant>p\.\w+)\s*\|\s*(?P<inh>AD|AR|XL)"
)
# GTR (UC3) linearized schema markers, emitted by ingestion.parse_gtr_xml. These fire
# only on GTR-linearized text and are inert on PMC docs (and vice versa), so a single
# build_inventory can run every detector unconditionally.
GTR_COND_RE = re.compile(r"Condition:\s*(?P<cond>.+?)\s*;;")
GTR_METHOD_RE = re.compile(r"Method:\s*(?P<method>.+?)\s*;;")


def build_inventory(doc: Document) -> List[InventoryUnit]:
    units: List[InventoryUnit] = []

    for m in VARIANT_RE.finditer(doc.text):
        units.append(InventoryUnit(
            kind="variant", key=m.group(0), value=m.group(0),
            span=Span(doc.doc_id, m.start(), m.end(), m.group(0)),
            detector="hgvs_regex",
        ))

    for m in CASE_ROW_RE.finditer(doc.text):
        for fld, grp in (("onset", "onset"), ("sex", "sex"), ("inheritance", "inh"),
                         ("variant", "variant")):
            val = m.group(grp)
            units.append(InventoryUnit(
                kind="case_cell",
                key=f"case{m.group('case')}.{fld}",
                value=val,
                span=Span(doc.doc_id, m.start(grp), m.start(grp) + len(val), val,
                          source_type="table"),
                detector="table_row_regex",
            ))

    units.extend(_gtr_units(doc))
    return _dedupe(units)


def _gtr_units(doc: Document) -> List[InventoryUnit]:
    """UC3 GTR facts as (test → condition) and (test → method) relation triples.

    Scanned per section so each fact is attributed to its lab test and gets an absolute
    source span (section offset + local match offset). The gene is the constant subject
    of every triple and always present, so recall targets the conditions and methods.
    """
    units: List[InventoryUnit] = []
    for si, sec in enumerate(doc.sections):
        seg = doc.text[sec.start:sec.end]
        for i, m in enumerate(GTR_COND_RE.finditer(seg)):
            val = m.group("cond")
            start = sec.start + m.start("cond")
            units.append(InventoryUnit(
                kind="triple", key=f"test{si}.condition.{i}", value=val,
                span=Span(doc.doc_id, start, start + len(val), val, source_type="xml_field"),
                detector="gtr_schema",
            ))
        for j, m in enumerate(GTR_METHOD_RE.finditer(seg)):
            val = m.group("method")
            start = sec.start + m.start("method")
            units.append(InventoryUnit(
                kind="triple", key=f"test{si}.method.{j}", value=val,
                span=Span(doc.doc_id, start, start + len(val), val, source_type="xml_field"),
                detector="gtr_schema",
            ))
    return units


def _dedupe(units: List[InventoryUnit]) -> List[InventoryUnit]:
    """Collapse repeated variant mentions to their first occurrence; keep case cells."""
    seen = set()
    out = []
    for u in units:
        sig = (u.kind, u.key) if u.kind in ("case_cell", "triple") else (u.kind, u.value)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(u)
    return out
