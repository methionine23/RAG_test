"""Experiment runner: orchestrate ingest → (backend: chunk → retrieve → extract) →
S1/S2/S3 metrics → attribution, swept over a temperature grid with K samples per cell
for self-consistency (docs/02 §7).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .backends.base import SummarizerBackend
from .inventory import build_inventory
from .metrics import attribution, consistency, generation, retrieval, sectioning
from .schemas import Document, ExtractionTask

DEFAULT_TEMPERATURES = [0.0, 0.3, 0.6, 1.0]


@dataclass
class ExperimentConfig:
    temperatures: List[float] = field(default_factory=lambda: list(DEFAULT_TEMPERATURES))
    samples_per_cell: int = 5           # K for self-consistency
    top_k: int = 3


def run_experiment(backend: SummarizerBackend, doc: Document, task: ExtractionTask,
                   config: Optional[ExperimentConfig] = None) -> Dict:
    config = config or ExperimentConfig()
    inv = build_inventory(doc)
    retriever = retrieval.LexicalRetriever()

    per_temperature = []
    for T in config.temperatures:
        samples = [backend.summarize(task, doc, T, seed=s)
                   for s in range(config.samples_per_cell)]

        # S1/S2 depend only on the chunker+retriever, identical across samples → compute once.
        s1 = sectioning.sectioning_metrics(samples[0].chunks, doc, inv)
        s2 = retrieval.retrieval_metrics(retriever, samples[0].chunks, inv, doc, config.top_k)

        # S3 + attribution are stochastic → average across the K samples.
        faiths, hallucs, recalls, recall_cc, budgets, provs = [], [], [], [], [], []
        missing_sets = []
        for smp in samples:
            f = generation.cell_faithfulness(smp.records, doc.text)
            rc = generation.silver_recall(inv, smp.records)
            at = attribution.attribute(inv, smp.chunks, smp.retrieved_context, smp.records, doc)
            faiths.append(f["faithfulness"]); hallucs.append(f["hallucination_rate"])
            recalls.append(rc["silver_recall"]); recall_cc.append(rc["recall_case_cells"])
            budgets.append(at["loss_budget"])
            provs.append(generation.provenance_scores(smp.records, doc.text)["attribution_validity"])
            missing_sets.append(set(rc["missing"]))

        faith = _mean(faiths); halluc = _mean(hallucs); recall = _mean(recalls)
        budget = {k: _mean([b[k] for b in budgets])
                  for k in ("ok", "SECTIONING", "RETRIEVAL", "GENERATION")}
        stab = consistency.stability([s.records for s in samples])
        persistently_missing = sorted(set.intersection(*missing_sets)) if missing_sets else []

        fidelity = round(0.5 * faith + 0.3 * recall + 0.2 * (1 - halluc), 3)

        per_temperature.append({
            "temperature": T,
            "sectioning": s1,
            "retrieval": s2,
            "faithfulness": round(faith, 3),
            "hallucination_rate": round(halluc, 3),
            "silver_recall": round(recall, 3),
            "recall_case_cells": round(_mean(recall_cc), 3),
            "attribution": {"loss_budget": {k: round(v, 3) for k, v in budget.items()}},
            "provenance": {"attribution_validity": round(_mean(provs), 3)},
            "stability": {k: stab[k] for k in ("mean_fact_stability", "mean_set_jaccard")},
            "fidelity": fidelity,
            "missing": persistently_missing,
        })

    return {
        "backend": backend.name,
        "doc_id": doc.doc_id,
        "task": task.kind,
        "n_inventory": len(inv),
        "by_temperature": per_temperature,
    }


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0
