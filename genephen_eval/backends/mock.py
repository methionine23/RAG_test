"""Deterministic offline backend that simulates an LLM/RAG extractor.

It performs a REAL chunk → retrieve → extract pipeline over the parsed document, then
injects temperature-driven errors (omission, rewording, hallucination) with a
deterministic hash-based pseudo-RNG (no Math.random / time — reproducible and
resume-safe). This lets the whole metric suite, the temperature study, and
self-consistency run end-to-end with no network or model. genePhen / Vertex replace it
behind the same `SummarizerBackend` interface.
"""
from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional

from ..ingestion import CHUNKERS
from ..inventory import CASE_ROW_RE, GTR_COND_RE, GTR_METHOD_RE, VARIANT_RE
from ..schemas import BackendResult, Chunk, Document, ExtractionTask, Record, Span
from ..metrics.retrieval import LexicalRetriever

_SHORT = {"p.Ser135Phe": "p.S135F", "p.Gly84Arg": "p.G84R", "p.Pro182Leu": "p.P182L"}

# UC3: near-synonym surface forms for GTR conditions/methods. A reworded value is no
# longer an exact match (hurts self-consistency, earns only partial faithfulness) but
# stays recognizably the same fact — the generation-stage "drift" signal for triples.
_GTR_REWORD = {
    "Charcot-Marie-Tooth disease axonal type 2F": "axonal CMT type 2F",
    "Distal hereditary motor neuronopathy type 2B": "distal HMN type 2B",
    "Hereditary motor and sensory neuropathy": "hereditary motor-sensory neuropathy",
    "Sequence analysis of the entire coding region": "full coding-region sequence analysis",
    "Deletion duplication analysis": "del/dup analysis",
    "Next generation sequencing panel": "NGS gene panel",
}


def _u(*parts) -> float:
    """Deterministic uniform in [0,1) from a key — replaces Math.random for reproducibility."""
    h = hashlib.sha1(":".join(map(str, parts)).encode()).hexdigest()
    return (int(h[:8], 16) % 100000) / 100000.0


class MockRAGBackend:
    def __init__(self, name: str = "mock_rag", chunker: str = "section_aware",
                 top_k: int = 3, chunk_size: int = 320):
        self.name = name
        self.chunker = chunker
        self.top_k = top_k
        self.chunk_size = chunk_size
        self.retriever = LexicalRetriever()

    def _chunk(self, doc: Document) -> List[Chunk]:
        fn = CHUNKERS[self.chunker]
        return fn(doc, self.chunk_size) if self.chunker == "naive_fixed" else fn(doc)

    def summarize(self, task: ExtractionTask, doc: Document,
                  temperature: float, seed: Optional[int] = None) -> BackendResult:
        seed = 0 if seed is None else seed
        chunks = self._chunk(doc)
        query = task.query or " ".join(task.fields)
        retrieved = self.retriever.retrieve(query, chunks, self.top_k)
        ctx = " ;; ".join(c.text for c in retrieved)

        if task.kind == "case":
            records = self._extract_cases(ctx, retrieved, temperature, seed)
        elif task.kind == "gtr":
            records = self._extract_gtr(ctx, retrieved, temperature, seed)
        else:
            records = self._extract_variants(ctx, retrieved, temperature, seed)
        return BackendResult(records=records, chunks=chunks, retrieved_context=retrieved,
                             provenance_supported=True, raw={"query": query})

    # -- extraction + temperature-driven error injection -------------------- #

    def _prov(self, value: str, retrieved: List[Chunk]) -> Optional[Span]:
        for c in retrieved:
            if value in c.text or _SHORT.get(value, "") in c.text:
                return Span("retrieved", c.start, c.end, c.text, recovered=True)
        return None

    def _extract_cases(self, ctx, retrieved, temperature, seed) -> List[Record]:
        out: List[Record] = []
        for m in CASE_ROW_RE.finditer(ctx):
            case = m.group("case")
            rid = f"case{case}"
            # omission: more likely at higher temperature
            if _u("omit", rid, seed) < temperature * 0.5:
                continue
            variant = m.group("variant")
            inh = m.group("inh")
            # rewording: normalizable surface form (faithful but hurts consistency)
            if _u("reword", rid, seed) < temperature * 0.6:
                variant = _SHORT.get(variant, variant)
            # hallucination: flip inheritance to an ungrounded value
            if _u("halluc", rid, seed) < temperature * 0.35:
                inh = "AR" if inh == "AD" else "AD"
            values: Dict[str, str] = {
                "sex": m.group("sex"),
                "Age_of_onset": m.group("onset"),
                "variant": variant,
                "inheritance": inh,
            }
            # cell-level omission
            if _u("dropcell", rid, seed) < temperature * 0.4:
                values.pop("Age_of_onset", None)
            prov = {f: self._prov(v, retrieved) for f, v in values.items()
                    if self._prov(v, retrieved)}
            out.append(Record(rid, "case", values, provenance=prov,
                              input_span=Span("retrieved", retrieved[0].start,
                                              retrieved[-1].end, ctx) if retrieved else None))
        return out

    def _extract_variants(self, ctx, retrieved, temperature, seed) -> List[Record]:
        out, seen = [], set()
        for i, m in enumerate(VARIANT_RE.finditer(ctx)):
            v = m.group(0)
            if v in seen:
                continue
            seen.add(v)
            rid = f"var{i}"
            if _u("omit", rid, seed) < temperature * 0.5:
                continue
            if _u("reword", rid, seed) < temperature * 0.6:
                v = _SHORT.get(v, v)
            values = {"gene": "HSPB1", "hgvs_p": v}
            prov = {f: self._prov(val, retrieved) for f, val in values.items()
                    if self._prov(val, retrieved)}
            out.append(Record(rid, "mutation", values, provenance=prov))
        return out

    def _extract_gtr(self, ctx, retrieved, temperature, seed) -> List[Record]:
        """UC3: emit (test → gene → condition) and (test → gene → method) triples.

        The retrieved context is split back into per-test blocks (the schema chunker
        keeps one test per chunk) so each condition/method is tied to its test and gene.
        Temperature drives the same three failure modes as the case extractor: omission,
        rewording to a near-synonym, and hallucination to an ungrounded value.
        """
        out: List[Record] = []
        blocks = re.split(r"\[Test:", ctx)
        for bi, block in enumerate(blocks):
            if "Condition:" not in block and "Method:" not in block:
                continue
            gene_m = re.search(r"Gene:\s*(.+?)\s*;;", block)
            gene = gene_m.group(1).split(",")[0].strip() if gene_m else "HSPB1"
            tid = f"test{bi}"

            def _emit(rid, field, value):
                if _u("omit", rid, seed) < temperature * 0.5:
                    return
                if _u("reword", rid, seed) < temperature * 0.6:
                    value = _GTR_REWORD.get(value, value)
                if _u("halluc", rid, seed) < temperature * 0.3:
                    value = "unrelated condition"
                values = {"gene": gene, field: value}
                prov = {f: self._prov(v, retrieved) for f, v in values.items()
                        if self._prov(v, retrieved)}
                out.append(Record(rid, "triple", values, provenance=prov,
                                  input_span=Span("retrieved", retrieved[0].start,
                                                  retrieved[-1].end, ctx) if retrieved else None))

            for i, m in enumerate(GTR_COND_RE.finditer(block)):
                _emit(f"{tid}.cond{i}", "condition", m.group("cond"))
            for j, m in enumerate(GTR_METHOD_RE.finditer(block)):
                _emit(f"{tid}.meth{j}", "method", m.group("method"))
        return out
