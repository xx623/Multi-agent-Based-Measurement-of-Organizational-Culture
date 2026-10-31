"""Reader paraphrase fields may not smuggle passage text past the excerpt boundary,
but exact provenance-checked quotes of at most 25 words are allowed anywhere."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import validate as V  # noqa: E402
from pipeline import views  # noqa: E402
from pipeline.schemas import load_codebook  # noqa: E402

VOC = load_codebook(ROOT)["vocabularies"]
SENT = ("Every plant manager now reviews safety incidents with their team each Monday, and the notes go to the "
        "regional leads the same day.")
WINDOW = {"units": [{"sid": "S1", "speaker_role": "executive", "window_role": "focus", "text": SENT}]}


def rec(conduct, excerpt, qualifications=None):
    return {"passage_id": "P", "items": [{
        "id": "E1", "actor": "plant managers", "conduct": conduct, "timing": "each Monday", "status": "ongoing",
        "content_type": "routine", "direction": "unclear", "origin": "unstated",
        "scope": {"type": "unit or function", "target": "plants", "extent": "all"},
        "qualifications": qualifications or [], "excerpt": excerpt, "excerpt_sentence": "S1"}],
        "declarations": [], "unresolved_flags": [], "flag_responses": [], "removed_item_ids": []}


class BoundaryRule(unittest.TestCase):
    def test_copy_longer_than_25_words_is_rejected(self):
        long_sentence = ("Across all of our regions the plant managers now review every safety incident with their "
                         "teams each Monday morning and send the review notes to the regional leads the same day "
                         "without exception.")
        window = {"units": [{"sid": "S1", "speaker_role": "executive", "window_role": "focus", "text": long_sentence}]}
        r = rec("the plant managers now review every safety incident with their teams each Monday morning and send "
                "the review notes to the regional leads the same day without exception",
                "review every safety incident with their teams each Monday")
        errors, _ = V.validate_record(r, passage_id="P", phase="initial", window=window, vocab=VOC)
        self.assertTrue(any("consecutive passage words" in e for e in errors))

    def test_short_verbatim_fragment_inside_a_field_is_allowed(self):
        r = rec("they review safety incidents with their team each Monday, as the regional leads require",
                "Every plant manager now reviews safety incidents")
        errors, _ = V.validate_record(r, passage_id="P", phase="initial", window=WINDOW, vocab=VOC)
        self.assertEqual(errors, [])

    def test_paraphrase_and_exact_quotes_are_accepted(self):
        r = rec("weekly review of safety incidents by plant managers with their teams",
                "reviews safety incidents with their team each Monday",
                qualifications=["the notes go to the regional leads the same day"])   # exact quote, allowed
        errors, _ = V.validate_record(r, passage_id="P", phase="initial", window=WINDOW, vocab=VOC)
        self.assertEqual(errors, [])
        view = views.build_view(r, WINDOW)
        self.assertEqual(views.leak_report(view, r, WINDOW), [])

    def test_excerpt_sentence_is_corrected_when_quote_is_verbatim_elsewhere(self):
        window = {"units": [{"sid": "S1", "speaker_role": "executive", "window_role": "focus", "text": "We had a solid year."},
                            {"sid": "S2", "speaker_role": "executive", "window_role": "focus", "text": SENT}]}
        r = rec("weekly safety review", "reviews safety incidents with their team each Monday")
        r["items"][0]["excerpt_sentence"] = "S1"
        errors, warnings = V.validate_record(r, passage_id="P", phase="initial", window=window, vocab=VOC)
        self.assertEqual(errors, [])
        self.assertEqual(r["items"][0]["excerpt_sentence"], "S2")
        self.assertTrue(any("corrected" in w for w in warnings))

    def test_status_direction_mixup_gets_directive_message(self):
        r = rec("weekly safety review", "reviews safety incidents with their team each Monday")
        r["items"][0]["status"] = "required"
        errors, _ = V.validate_record(r, passage_id="P", phase="initial", window=WINDOW, vocab=VOC)
        self.assertTrue(any("is a direction value" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
