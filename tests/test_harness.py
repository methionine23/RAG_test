"""Unit + end-to-end tests for genephen_eval. Run: python -m unittest discover -s tests"""
import os
import unittest

from genephen_eval.backends.mock import MockRAGBackend
from genephen_eval.ingestion import (chunk_naive_fixed, chunk_section_aware,
                                     parse_pmc_xml)
from genephen_eval.inventory import build_inventory
from genephen_eval.metrics import consistency, retrieval, sectioning
from genephen_eval.metrics.attribution import attribute
from genephen_eval.metrics.generation import (cell_faithfulness, ground, silver_recall,
                                             _present)
from genephen_eval.runner import ExperimentConfig, run_experiment
from genephen_eval.schemas import Record

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "prototype", "sample",
                       "hspb1_pubmed_sample.xml")


class TestIngestion(unittest.TestCase):
    def setUp(self):
        self.doc = parse_pmc_xml(FIXTURE)

    def test_sections_and_table_parsed(self):
        self.assertGreaterEqual(len(self.doc.sections), 3)
        self.assertEqual(len(self.doc.tables), 1)
        self.assertIn("p.Ser135Phe", self.doc.text)

    def test_section_aware_keeps_table_intact(self):
        chunks = chunk_section_aware(self.doc)
        tbl = self.doc.tables[0]
        self.assertTrue(any(c.contains(tbl.start, tbl.end) for c in chunks))

    def test_naive_splits_table(self):
        chunks = chunk_naive_fixed(self.doc, size=120)
        tbl = self.doc.tables[0]
        self.assertFalse(any(c.contains(tbl.start, tbl.end) for c in chunks))


class TestInventory(unittest.TestCase):
    def test_builds_variants_and_case_cells(self):
        inv = build_inventory(parse_pmc_xml(FIXTURE))
        kinds = {u.kind for u in inv}
        self.assertEqual(kinds, {"variant", "case_cell"})
        self.assertIn("p.Pro182Leu", {u.value for u in inv})


class TestGrounding(unittest.TestCase):
    def test_word_boundary_avoids_false_match(self):
        # 'AR' must NOT match inside 'Marie'/'Arg'
        self.assertFalse(_present("AR", "Charcot-Marie-Tooth p.Gly84Arg"))
        self.assertTrue(_present("AD", "inheritance AD ;; pattern"))

    def test_ground_tiers(self):
        src = "variant p.Ser135Phe segregating AD"
        self.assertEqual(ground("p.Ser135Phe", src, {}), "exact")
        self.assertEqual(ground("p.S135F", src, {"p.S135F": "p.Ser135Phe"}), "normalized")
        self.assertEqual(ground("AR", src, {}), "absent")

    def test_hallucinated_categorical_flagged(self):
        rec = Record("case1", "case", {"inheritance": "AR", "sex": "Male"})
        out = cell_faithfulness([rec], "the case was Male with AD inheritance")
        cells = {c["cell"]: c for c in out["per_cell"]}
        self.assertTrue(cells["case1.inheritance"]["hallucination"])
        self.assertFalse(cells["case1.sex"]["hallucination"])


class TestStageMetrics(unittest.TestCase):
    def setUp(self):
        self.doc = parse_pmc_xml(FIXTURE)
        self.inv = build_inventory(self.doc)

    def test_section_aware_beats_naive_on_sectioning(self):
        sa = sectioning.sectioning_metrics(chunk_section_aware(self.doc), self.doc, self.inv)
        nv = sectioning.sectioning_metrics(chunk_naive_fixed(self.doc, 120), self.doc, self.inv)
        self.assertEqual(sa["table_integrity"], 1.0)
        self.assertLess(nv["table_integrity"], sa["table_integrity"])

    def test_retrieval_ceiling_bounds_recall(self):
        chunks = chunk_section_aware(self.doc)
        rm = retrieval.retrieval_metrics(retrieval.LexicalRetriever(), chunks, self.inv,
                                         self.doc, k=3)
        self.assertGreaterEqual(rm["retrieval_ceiling"], rm["fact_hit_rate"])

    def test_attribution_partitions_all_facts(self):
        chunks = chunk_section_aware(self.doc)
        recs = [Record("case1", "case", {"variant": "p.Ser135Phe"})]
        at = attribute(self.inv, chunks, chunks, recs, self.doc)
        self.assertEqual(sum(at["counts"].values()), len(self.inv))


class TestConsistency(unittest.TestCase):
    def test_stability_detects_variance(self):
        a = [Record("v0", "mutation", {"hgvs_p": "p.Ser135Phe"})]
        b = [Record("v0", "mutation", {"hgvs_p": "p.Ser135Phe"}),
             Record("v1", "mutation", {"hgvs_p": "p.Gly84Arg"})]
        st = consistency.stability([a, b, a])
        self.assertLess(st["mean_fact_stability"], 1.0)
        self.assertIn("v1.hgvs_p:p.Gly84Arg", st["unstable_facts"])


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.doc = parse_pmc_xml(FIXTURE)
        from genephen_eval.cli import TASKS
        self.task = TASKS["case"]

    def test_temperature_degrades_recall_and_stability(self):
        backend = MockRAGBackend(chunker="section_aware")
        res = run_experiment(backend, self.doc, self.task, ExperimentConfig(samples_per_cell=8))
        rows = res["by_temperature"]
        recalls = [r["silver_recall"] for r in rows]
        stabs = [r["stability"]["mean_fact_stability"] for r in rows]
        self.assertEqual(recalls, sorted(recalls, reverse=True))   # monotone non-increasing
        self.assertEqual(stabs, sorted(stabs, reverse=True))
        self.assertGreater(rows[-1]["hallucination_rate"], rows[0]["hallucination_rate"])

    def test_naive_chunker_incurs_sectioning_loss(self):
        sa = run_experiment(MockRAGBackend(chunker="section_aware"), self.doc, self.task,
                            ExperimentConfig(samples_per_cell=4))
        nv = run_experiment(MockRAGBackend(chunker="naive_fixed", chunk_size=120), self.doc,
                            self.task, ExperimentConfig(samples_per_cell=4))
        sa_loss = sa["by_temperature"][0]["attribution"]["loss_budget"]["SECTIONING"]
        nv_loss = nv["by_temperature"][0]["attribution"]["loss_budget"]["SECTIONING"]
        self.assertEqual(sa_loss, 0.0)
        self.assertGreater(nv_loss, 0.0)


if __name__ == "__main__":
    unittest.main()
