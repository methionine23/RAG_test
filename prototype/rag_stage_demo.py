#!/usr/bin/env python3
"""
Stage-decomposed RAG fidelity demo: SECTIONING/CHUNKING -> RETRIEVAL -> (generation).

Answers the requirement to measure fidelity at the *chunking* and *retrieval* stages,
not only final summarization, so that a wrong/missing table cell can be attributed to
the stage that caused it. Runs offline (stdlib only: xml.etree, re) on the synthetic
PubMed-XML fixture in sample/hspb1_pubmed_sample.xml.

It compares two chunkers on the SAME document:
  * naive_fixed   -- fixed-size character window, structure-blind (splits tables)
  * section_aware -- one chunk per section; each source table kept intact

and reports, per chunker:
  Sectioning fidelity : boundary alignment, table integrity, fact locality, coverage
  Retrieval fidelity  : fact-level hit-rate, context recall, retrieval ceiling
  Attribution         : for each gold fact, WHY it would be lost (sectioning/retrieval)

Run:  python3 prototype/rag_stage_demo.py
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "sample", "hspb1_pubmed_sample.xml")

VARIANT_RE = re.compile(r"p\.[A-Z][a-z]{2}\d+[A-Z][a-z]{2}|c\.\d+[ACGT]>[ACGT]")


@dataclass
class Segment:
    """A ground-truth section (or a table) with its span in the linearized document."""
    kind: str          # 'section' | 'table'
    label: str
    start: int
    end: int


@dataclass
class Fact:
    """A source-derived 'should-capture' unit with its span in the linearized document."""
    kind: str          # 'variant' | 'case_cell'
    key: str
    text: str
    start: int
    end: int


# --------------------------------------------------------------------------- #
# 1. Parse XML -> linearized doc + ground-truth segments + fact inventory
# --------------------------------------------------------------------------- #

def linearize(path: str):
    tree = ET.parse(path)
    root = tree.getroot()
    doc = ""
    segments: list[Segment] = []
    boundaries: set[int] = {0}

    for sec in root.iter("sec"):
        sec_start = len(doc)
        title = sec.findtext("title") or sec.get("sec-type", "section")
        doc += f"[{title}] "
        for p in sec.findall("p"):
            doc += " ".join((p.text or "").split()) + " "
            boundaries.add(len(doc))            # paragraph boundary
        # tables inside the section are linearized as their own segment
        for tw in sec.findall(".//table-wrap"):
            tbl_start = len(doc)
            label = tw.findtext("label") or "Table"
            headers = [th.text or "" for th in tw.findall(".//thead//th")]
            doc += f"{label}: " + " | ".join(headers) + " ;; "
            for tr in tw.findall(".//tbody//tr"):
                cells = [td.text or "" for td in tr.findall("td")]
                doc += " | ".join(cells) + " ;; "
                boundaries.add(len(doc))        # row boundary
            segments.append(Segment("table", label, tbl_start, len(doc)))
        segments.append(Segment("section", title, sec_start, len(doc)))
        boundaries.add(len(doc))                # section boundary

    # --- fact inventory (fully source-grounded) ---
    facts: list[Fact] = []
    for m in re.finditer(VARIANT_RE, doc):
        facts.append(Fact("variant", m.group(0), m.group(0), m.start(), m.end()))
    # case cells: (variant, inheritance) tuples from the table rows we linearized
    for m in re.finditer(r"(\d)\s*\|\s*(Male|Female)\s*\|\s*(\d+)\s*\|\s*(p\.\w+)\s*\|\s*(AD|AR)", doc):
        case, sex, onset, variant, inh = m.groups()
        facts.append(Fact("case_cell", f"case{case}.onset", onset,
                           m.start(3), m.start(3) + len(onset)))
    return doc, segments, sorted(boundaries), facts


# --------------------------------------------------------------------------- #
# 2. Chunkers
# --------------------------------------------------------------------------- #

def naive_fixed(doc: str, size: int = 320):
    return [(i, min(i + size, len(doc))) for i in range(0, len(doc), size)]


def section_aware(doc: str, segments: list[Segment]):
    # one chunk per top-level section; tables (nested) are emitted as standalone chunks
    chunks = []
    for s in segments:
        chunks.append((s.start, s.end))
    # dedupe/merge identical spans, keep sorted
    return sorted(set(chunks))


# --------------------------------------------------------------------------- #
# 3. Sectioning-stage fidelity metrics
# --------------------------------------------------------------------------- #

def contains(span, chunk, tol=0):
    return chunk[0] - tol <= span[0] and span[1] <= chunk[1] + tol


def sectioning_metrics(chunks, segments, boundaries, facts, doc):
    interior = [c[0] for c in chunks if c[0] != 0]
    aligned = sum(any(abs(b - x) <= 2 for x in boundaries) for b in interior)
    boundary_alignment = aligned / len(interior) if interior else 1.0

    tables = [s for s in segments if s.kind == "table"]
    table_intact = sum(any(contains((t.start, t.end), c) for c in chunks) for t in tables)
    table_integrity = table_intact / len(tables) if tables else 1.0

    local = sum(any(contains((f.start, f.end), c) for c in chunks) for f in facts)
    fact_locality = local / len(facts) if facts else 1.0

    covered = set()
    for c in chunks:
        covered.update(range(c[0], c[1]))
    coverage = len(covered) / len(doc) if doc else 1.0

    return {
        "boundary_alignment": round(boundary_alignment, 2),
        "table_integrity": round(table_integrity, 2),
        "fact_locality": round(fact_locality, 2),
        "coverage": round(coverage, 2),
    }


# --------------------------------------------------------------------------- #
# 4. Retrieval-stage fidelity metrics (toy token-overlap retriever)
# --------------------------------------------------------------------------- #

def toks(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def retrieve(query, chunks, doc, k=2):
    scored = sorted(chunks, key=lambda c: len(toks(query) & toks(doc[c[0]:c[1]])), reverse=True)
    return scored[:k]


def retrieval_metrics(chunks, facts, doc, k=2):
    hits, ceiling = 0, 0
    for f in facts:
        # query built from the fact's context, WITHOUT leaking the value itself
        ctx = doc[max(0, f.start - 40):f.start] + doc[f.end:f.end + 40]
        query = re.sub(re.escape(f.text), "", ctx)
        top = retrieve(query, chunks, doc, k)
        # hit: a retrieved chunk fully CONTAINS the fact (retrievable as a unit)
        if any(contains((f.start, f.end), c) for c in top):
            hits += 1
        # ceiling: the fact value is PRESENT anywhere in retrieved text (max achievable)
        if any(f.text in doc[c[0]:c[1]] for c in top):
            ceiling += 1
    n = len(facts)
    return {
        "fact_hit_rate": round(hits / n, 2),
        "retrieval_ceiling": round(ceiling / n, 2),
    }


# --------------------------------------------------------------------------- #
# 5. Error attribution
# --------------------------------------------------------------------------- #

def attribute(chunks, facts, doc, k=2):
    rows = []
    for f in facts:
        local = any(contains((f.start, f.end), c) for c in chunks)
        ctx = doc[max(0, f.start - 40):f.start] + doc[f.end:f.end + 40]
        query = re.sub(re.escape(f.text), "", ctx)
        top = retrieve(query, chunks, doc, k)
        retrieved_whole = any(contains((f.start, f.end), c) for c in top)
        if not local:
            cause = "SECTIONING (fact split across chunks)"
        elif not retrieved_whole:
            cause = "RETRIEVAL (chunk not in top-k)"
        else:
            cause = "ok (reaches generation intact)"
        rows.append((f.kind, f.key or f.text, cause))
    return rows


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

def run_chunker(name, chunks, segments, boundaries, facts, doc):
    print(f"\n### chunker = {name}   ({len(chunks)} chunks)")
    sm = sectioning_metrics(chunks, segments, boundaries, facts, doc)
    rm = retrieval_metrics(chunks, facts, doc)
    print("  sectioning:", "  ".join(f"{k}={v}" for k, v in sm.items()))
    print("  retrieval :", "  ".join(f"{k}={v}" for k, v in rm.items()))
    print("  attribution of each gold fact:")
    for kind, key, cause in attribute(chunks, facts, doc):
        print(f"      {kind:<10} {key:<16} -> {cause}")
    return sm, rm


def main():
    doc, segments, boundaries, facts = linearize(FIXTURE)
    print("=" * 76)
    print("STAGE-DECOMPOSED RAG FIDELITY  (sectioning -> retrieval -> generation)")
    print("=" * 76)
    print(f"linearized doc: {len(doc)} chars | "
          f"{len([s for s in segments if s.kind=='section'])} sections | "
          f"{len([s for s in segments if s.kind=='table'])} table | "
          f"{len(facts)} gold facts")

    run_chunker("naive_fixed(320)", naive_fixed(doc), segments, boundaries, facts, doc)
    run_chunker("section_aware", section_aware(doc, segments), segments, boundaries, facts, doc)

    print("\n" + "=" * 76)
    print("Takeaway: the two chunkers see the SAME document and the SAME retriever,")
    print("yet differ on table integrity + fact locality, which caps retrieval and")
    print("therefore end-to-end recall. Attribution shows exactly which stage loses")
    print("each fact -- the signal needed to compare genePhen vs Vertex chunking.")
    print("=" * 76)


if __name__ == "__main__":
    main()
