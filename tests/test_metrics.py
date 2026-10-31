import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validation"))

import metrics  # noqa: E402
import resampling  # noqa: E402

CATS = ["Collaboration and people-focused", "Customer-oriented", "Innovation and adaptability",
        "Integrity and risk management", "Performance-oriented", "Other reported norms"]


def measurement(innov_rel="strong", innov_dir="required", extent="all"):
    cats = {c: {"relevance": "none", "direction": "none", "claims": []} for c in CATS}
    if innov_rel != "none":
        cats["Innovation and adaptability"] = {"relevance": innov_rel, "direction": innov_dir, "claims": [
            {"claim_ref": "K1", "relevance": innov_rel, "direction": innov_dir,
             "scope": {"type": "team or role", "target": "teams", "extent": extent}}]}
    return {"passage_id": "P", "categories": cats}


class Metrics(unittest.TestCase):
    def test_relevance_agreement_and_f1(self):
        ref, pred = metrics.category_relevance(measurement()), metrics.category_relevance(measurement())
        self.assertEqual(metrics.relevance_exact_agreement([(ref, pred)]), 1.0)
        self.assertEqual(metrics.relevance_macro_f1([(ref, pred)]), 1.0)
        pred2 = metrics.category_relevance(measurement(innov_rel="none"))
        self.assertLess(metrics.relevance_macro_f1([(ref, pred2)]), 1.0)
        self.assertAlmostEqual(metrics.relevance_exact_agreement([(ref, pred2)]), 5 / 6)

    def test_direction_and_scope(self):
        ref, pred = measurement(), measurement(innov_dir="encouraged")
        self.assertEqual(metrics.direction_agreement([(metrics.category_direction(ref), metrics.category_direction(pred))],
                                                     [metrics.category_relevance(ref)]), 0.0)
        self.assertEqual(metrics.scope_agreement([(metrics.category_scope(ref), metrics.category_scope(measurement(extent="one")))]), 0.0)
        self.assertEqual(metrics.scope_agreement([(metrics.category_scope(ref), metrics.category_scope(pred))]), 1.0)

    def test_pair_scoring(self):
        orig = metrics.scored_fields(measurement())
        edited_same = metrics.scored_fields(measurement())
        self.assertTrue(metrics.pair_correct_irrelevant(orig, edited_same, orig))
        self.assertFalse(metrics.pair_correct_irrelevant(orig, metrics.scored_fields(measurement(innov_dir="encouraged")), orig))
        flipped = metrics.scored_fields(measurement(innov_dir="discouraged"))
        self.assertTrue(metrics.pair_correct_relevant(orig, flipped, category="Innovation and adaptability",
                                                      field="direction", expected_before="required",
                                                      expected_after="discouraged", reference_original=orig,
                                                      reference_edited=flipped))
        self.assertFalse(metrics.pair_correct_relevant(orig, orig, category="Innovation and adaptability",
                                                       field="direction", expected_before="required",
                                                       expected_after="discouraged", reference_original=orig,
                                                       reference_edited=flipped))

    def test_coverage_completeness_and_failures(self):
        procs = [{"output_state": "valid", "escalate_to_human": True}, {"output_state": "invalid"},
                 {"output_state": "abstained"}]
        self.assertAlmostEqual(metrics.decision_coverage(procs), 1 / 3)
        self.assertAlmostEqual(metrics.failure_rate(procs), 1 / 3)
        self.assertAlmostEqual(metrics.escalation_rate(procs), 1 / 3)
        rec = [{"excerpt": "teams must share unsuccessful results", "excerpt_sentence": "S2"}]
        ref = [{"excerpt": "teams must share unsuccessful results at monthly reviews", "excerpt_sentence": "S2"},
               {"excerpt": "stopped twelve pilots", "excerpt_sentence": "S2"}]
        self.assertEqual(metrics.evidence_completeness(rec, ref), 0.5)
        self.assertAlmostEqual(metrics.erroneous_exclusion([({"A": "strong", "B": "none"}, {"A": "none"}, "valid")]), 1.0)

    def test_firm_bootstrap_keeps_units_together(self):
        groups = {"f1": [1, 1], "f2": [0, 0], "f3": [1, 0]}
        out = resampling.firm_bootstrap(lambda xs: sum(xs) / len(xs), groups, n_boot=200)
        self.assertLessEqual(out["ci_low"], out["point"])
        self.assertGreaterEqual(out["ci_high"], out["point"])
        diff = resampling.paired_difference(lambda xs: sum(xs) / len(xs), lambda xs: 0.0, groups, n_boot=100,
                                            one_sided_lower=True)
        self.assertIn("lower_95", diff)


if __name__ == "__main__":
    unittest.main()
