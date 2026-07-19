"""CLI: run the fidelity harness end-to-end on a PMC/PubMed XML document.

    python -m genephen_eval.cli --xml prototype/sample/hspb1_pubmed_sample.xml
    python -m genephen_eval.cli --xml doc.xml --chunker naive_fixed --task case
"""
from __future__ import annotations

import argparse

from .backends.mock import MockRAGBackend
from .ingestion import parse_pmc_xml
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
}


def main() -> int:
    ap = argparse.ArgumentParser(description="genephen_eval fidelity harness")
    ap.add_argument("--xml", required=True, help="PMC/PubMed XML document")
    ap.add_argument("--task", default="case", choices=list(TASKS))
    ap.add_argument("--chunker", default="section_aware",
                    choices=["section_aware", "naive_fixed"])
    ap.add_argument("--backend", default="mock_rag")
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--samples", type=int, default=5)
    args = ap.parse_args()

    doc = parse_pmc_xml(args.xml)
    backend = MockRAGBackend(name=f"{args.backend}:{args.chunker}",
                             chunker=args.chunker, top_k=args.top_k)
    result = run_experiment(backend, doc, TASKS[args.task],
                            ExperimentConfig(samples_per_cell=args.samples, top_k=args.top_k))
    print(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
