"""The interpretation view must carry no declarations, spans or passage text beyond excerpts (B.0)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import views  # noqa: E402

WINDOW = {"units": [
    {"sid": "S1", "speaker_role": "executive", "window_role": "focus", "text": "We champion innovation."},
    {"sid": "S2", "speaker_role": "executive", "window_role": "focus",
     "text": "We stopped twelve pilots this year; teams must share unsuccessful results at monthly reviews."}]}
RECORD = {"passage_id": "P", "items": [
    {"id": "E1", "actor": "company", "conduct": "stopped twelve pilots", "timing": "this year", "status": "completed",
     "content_type": "episode", "direction": "unclear", "origin": "unstated",
     "scope": {"type": "unspecified", "target": "Not stated", "extent": "unspecified"}, "qualifications": [],
     "excerpt": "We stopped twelve pilots this year", "excerpt_sentence": "S2",
     "excerpt_span": {"sentence": "S2", "start": 0, "end": 34}}],
    "declarations": [{"id": "D1", "text": "We champion innovation.", "sentence": "S1"}],
    "unresolved_flags": [
        {"flag_id": "F1", "type": "MISSING_ITEM", "target_item": "none", "source_states": "present",
         "note": "the clause teams must share unsuccessful results at monthly reviews was not recorded"},
        {"flag_id": "F2", "type": "SCOPE_OR_STATUS_ERROR", "target_item": "E1", "source_states": "absent",
         "note": "which units stopped the pilots is not stated"}],
    "flag_responses": [{"flag_id": "F1", "action": "defended", "source_states": "present", "reason": "x"}],
    "removed_item_ids": []}


class ViewBoundary(unittest.TestCase):
    def test_view_drops_declarations_spans_and_sentence_fields(self):
        view = views.build_view(RECORD, WINDOW)
        self.assertEqual(set(view), {"passage_id", "items", "unresolved", "completeness_uncertain"})
        self.assertNotIn("excerpt_sentence", view["items"][0])
        self.assertNotIn("excerpt_span", view["items"][0])
        self.assertNotIn("champion", str(view))
        self.assertEqual(views.leak_report(view, RECORD, WINDOW), [])

    def test_note_with_passage_text_is_replaced_by_generic_note(self):
        view = views.build_view(RECORD, WINDOW)
        notes = {u["type"]: u["note"] for u in view["unresolved"]}
        self.assertNotIn("monthly reviews", notes["MISSING_ITEM"])       # passage text outside excerpts
        self.assertIn("which units stopped the pilots", notes["SCOPE_OR_STATUS_ERROR"])  # own words kept
        self.assertEqual(view["unresolved"][1]["evidence_ids"], ["E1"])
        self.assertEqual(view["unresolved"][0]["evidence_ids"], [])

    def test_completeness_uncertain_follows_missing_item_flags(self):
        self.assertTrue(views.build_view(RECORD, WINDOW)["completeness_uncertain"])
        rec = dict(RECORD, unresolved_flags=[RECORD["unresolved_flags"][1]])
        self.assertFalse(views.build_view(rec, WINDOW)["completeness_uncertain"])

    def test_leak_report_catches_declaration_and_passage_text(self):
        leaky = {"items": [{"excerpt": "We stopped twelve pilots this year"}], "note": "We champion innovation."}
        problems = views.leak_report(leaky, RECORD, WINDOW)
        self.assertTrue(any("declaration" in p for p in problems))
        leaky2 = {"text": "teams must share unsuccessful results at monthly reviews please"}
        self.assertTrue(views.leak_report(leaky2, RECORD, WINDOW))


if __name__ == "__main__":
    unittest.main()
