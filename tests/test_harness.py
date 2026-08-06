"""Unit + end-to-end tests for genephen_eval. Run: python -m unittest discover -s tests"""
import os
import unittest

from genephen_eval.backends.mock import MockRAGBackend
from genephen_eval.ingestion import (chunk_gtr_schema, chunk_naive_fixed,
                                     chunk_section_aware, parse_gtr_xml, parse_pmc_xml)
from genephen_eval.inventory import build_inventory
from genephen_eval.metrics import consistency, retrieval, sectioning
from genephen_eval.metrics.attribution import attribute
from genephen_eval.metrics.generation import (cell_faithfulness, ground, silver_recall,
                                             _present)
from genephen_eval.runner import ExperimentConfig, run_experiment
from genephen_eval.schemas import Record

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "prototype", "sample",
                       "hspb1_pubmed_sample.xml")
GTR_FIXTURE = os.path.join(os.path.dirname(__file__), "..", "prototype", "sample",
                           "gtr_hspb1_sample.xml")


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


class TestGTR(unittest.TestCase):
    """UC3 — NIH GTR XML: schema-routed sectioning + triple extraction."""

    def setUp(self):
        self.doc = parse_gtr_xml(GTR_FIXTURE)
        self.inv = build_inventory(self.doc)
        from genephen_eval.cli import TASKS
        self.task = TASKS["gtr"]

    def test_parse_routes_tests_and_fields(self):
        self.assertEqual(len(self.doc.sections), 2)      # two lab tests
        self.assertIn("Condition:", self.doc.text)
        self.assertIn("Method:", self.doc.text)
        self.assertIn("Charcot-Marie-Tooth disease axonal type 2F", self.doc.text)

    def test_inventory_builds_triples_only(self):
        self.assertEqual({u.kind for u in self.inv}, {"triple"})
        # 3 conditions + 3 methods across the two tests
        self.assertEqual(len(self.inv), 6)
        self.assertIn("Next generation sequencing panel", {u.value for u in self.inv})

    def test_inventory_spans_point_at_source_value(self):
        # each fact's recorded span must slice back to its exact value
        for u in self.inv:
            self.assertEqual(self.doc.text[u.span.start:u.span.end], u.value)

    def test_schema_chunker_keeps_each_test_whole(self):
        chunks = chunk_gtr_schema(self.doc)
        self.assertEqual(len(chunks), 2)
        s1 = sectioning.sectioning_metrics(chunks, self.doc, self.inv)
        self.assertEqual(s1["boundary_alignment"], 1.0)
        self.assertEqual(s1["fact_locality"], 1.0)

    def test_schema_chunker_beats_naive_on_boundaries(self):
        sa = sectioning.sectioning_metrics(chunk_gtr_schema(self.doc), self.doc, self.inv)
        nv = sectioning.sectioning_metrics(chunk_naive_fixed(self.doc, 120), self.doc, self.inv)
        self.assertGreater(sa["boundary_alignment"], nv["boundary_alignment"])

    def test_gtr_detectors_inert_on_pmc(self):
        # the GTR markers must not fire on a PMC document (no cross-schema bleed)
        pmc_inv = build_inventory(parse_pmc_xml(FIXTURE))
        self.assertNotIn("triple", {u.kind for u in pmc_inv})

    def test_end_to_end_temperature_degrades_gtr(self):
        res = run_experiment(MockRAGBackend(chunker="gtr_schema"), self.doc, self.task,
                             ExperimentConfig(samples_per_cell=8))
        rows = res["by_temperature"]
        self.assertEqual(res["n_inventory"], 6)
        self.assertEqual(rows[0]["silver_recall"], 1.0)                  # faithful at T=0
        self.assertEqual(rows[0]["faithfulness"], 1.0)
        recalls = [r["silver_recall"] for r in rows]
        self.assertEqual(recalls, sorted(recalls, reverse=True))         # monotone down
        # loss with this perfect chunker/retriever is generation, never sectioning
        self.assertEqual(rows[0]["attribution"]["loss_budget"]["SECTIONING"], 0.0)
        self.assertGreater(rows[-1]["attribution"]["loss_budget"]["GENERATION"], 0.0)


if __name__ == "__main__":
    unittest.main()
