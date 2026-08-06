"""CLI: run the fidelity harness end-to-end on a source document.

    # UC1 — PMC/PubMed full-text XML
    python -m genephen_eval.cli --xml prototype/sample/hspb1_pubmed_sample.xml
    python -m genephen_eval.cli --xml doc.xml --chunker naive_fixed --task case

    # UC3 — NIH GTR XML (schema-routed)
    python -m genephen_eval.cli --gtr prototype/sample/gtr_hspb1_sample.xml --task gtr
"""
from __future__ import annotations

import argparse

from .backends.mock import MockRAGBackend
from .ingestion import parse_gtr_xml, parse_pmc_xml
from .report import render
from .runner import ExperimentConfig, run_experiment
from .schemas import ExtractionTask

TASKS = {
    "case": ExtractionTask(
        kind="case",
        fields=["sex", "Age_of_onset", "variant", "inheritance"],
        query="clinical case patient sex age of onset variant inheritance symptom",
    ),
    "mutation": ExtractionTask(
        kind="mutation",
        fields=["gene", "hgvs_p"],
        query="HSPB1 variant mutation protein change",
    ),
    "gtr": ExtractionTask(
        kind="gtr",
        fields=["gene", "condition", "method"],
        query="genetic test gene condition disease method sequencing analysis panel",
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser(description="genephen_eval fidelity harness")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--xml", help="PMC/PubMed XML document (UC1)")
    src.add_argument("--gtr", help="NIH GTR XML document (UC3)")
    ap.add_argument("--task", default=None, choices=list(TASKS))
    ap.add_argument("--chunker", default=None,
                    choices=["section_aware", "naive_fixed", "gtr_schema"])
    ap.add_argument("--backend", default="mock_rag")
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--samples", type=int, default=5)
    args = ap.parse_args()

    if args.gtr:
        doc = parse_gtr_xml(args.gtr)
        task = TASKS[args.task or "gtr"]
        chunker = args.chunker or "gtr_schema"
    else:
        doc = parse_pmc_xml(args.xml)
        task = TASKS[args.task or "case"]
        chunker = args.chunker or "section_aware"

    backend = MockRAGBackend(name=f"{args.backend}:{chunker}",
                             chunker=chunker, top_k=args.top_k)
    result = run_experiment(backend, doc, task,
                            ExperimentConfig(samples_per_cell=args.samples, top_k=args.top_k))
    print(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
