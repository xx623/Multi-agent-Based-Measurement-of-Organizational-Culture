"""Window builder (parsing, masking, sentence IDs) and release-safe redaction."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import redact, windows  # noqa: E402

SYN = ROOT / "demo" / "inputs" / "synthetic_transcript_lseg.txt"


class WindowBuilder(unittest.TestCase):
    def test_synthetic_transcript_parsed_masked_and_numbered(self):
        tr = windows.parse_lseg_transcript(SYN.read_text(encoding="utf-8"), "CTEST", ticker="NGI")
        self.assertEqual(tr.company, "Northgate Industrial Inc")
        self.assertEqual(len(tr.turns), 11)
        masker = windows.build_masker(tr, {"LOCATION": ["Ohio", "Texas", "Dallas", "Houston"]})
        ws = windows.build_windows(tr, masker, sentences_per_passage=4, context=1, license_tag="synthetic")
        self.assertGreaterEqual(len(ws), 3)
        joined = json.dumps(ws)
        for raw in ("Northgate", "Lindqvist", "Castellanos", "Raman", "Okafor", "Fischer", "Ohio", "Dallas"):
            self.assertNotIn(raw, joined)
        for w in ws:
            sids = [u["sid"] for u in w["source_window"]["units"]]
            self.assertEqual(sids, [f"S{i}" for i in range(1, len(sids) + 1)])
            self.assertEqual(w["license"], "synthetic")
        qa = [w for w in ws if w["provenance"]["section"] == "qa"]
        self.assertTrue(qa and qa[0]["source_window"]["units"][0]["speaker_role"] == "analyst")

    def test_ner_pass_adds_entities_when_spacy_available(self):
        try:
            import spacy  # noqa: F401
            spacy.load("en_core_web_sm")
        except Exception:
            self.skipTest("spaCy model not installed")
        tr = windows.parse_lseg_transcript(SYN.read_text(encoding="utf-8"), "CTEST")
        masker = windows.build_masker(tr)
        added = windows.add_ner_entities(masker, [t.text for t in tr.turns])
        self.assertGreater(added, 0)
        self.assertNotIn("Ohio", masker.mask("opened two sites in Ohio"))


class Redaction(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        run = self.tmp / "run" / "P1"
        (run / "calls").mkdir(parents=True)
        (run / "final").mkdir()
        window = {"units": [{"sid": "S1", "speaker_role": "executive", "window_role": "focus",
                             "text": "Every plant manager now reviews safety incidents with their team each Monday."},
                            {"sid": "S2", "speaker_role": "executive", "window_role": "focus",
                             "text": "We sold three non-core plants and opened two sites in [LOCATION_001]."}]}
        (run / "input.json").write_text(json.dumps({"passage_id": "P1", "license": "restricted",
                                                    "source_window": window}), encoding="utf-8")
        rendered = "[S1] (executive, FOCUS) " + window["units"][0]["text"] + "\n[S2] (executive, FOCUS) " + \
                   window["units"][1]["text"]
        (run / "calls" / "01_R1.prompt.txt").write_text("PROMPT\n" + rendered + "\nEND", encoding="utf-8")
        record = {"passage_id": "P1", "items": [{"id": "E1", "excerpt": "reviews safety incidents with their team each Monday",
                                                 "excerpt_sentence": "S1"}]}
        (run / "record_revised.json").write_text(json.dumps(record), encoding="utf-8")
        (run / "calls" / "02_S1.output.json").write_text(json.dumps({"question": "Does every plant manager now reviews safety incidents with their team each Monday apply to all plants?"}), encoding="utf-8")
        (run / "summary.json").write_text(json.dumps({"passage_id": "P1", "status": "valid"}), encoding="utf-8")
        self.run = run

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_restricted_passage_loses_window_but_keeps_excerpts(self):
        reports = redact.redact_batch(self.tmp / "run", self.tmp / "release")
        self.assertTrue(reports[0]["redacted"])
        prompt = (self.tmp / "release" / "P1" / "calls" / "01_R1.prompt.txt").read_text(encoding="utf-8")
        self.assertNotIn("We sold three non-core plants", prompt)
        self.assertIn("SOURCE WINDOW REDACTED", prompt)
        rec = (self.tmp / "release" / "P1" / "record_revised.json").read_text(encoding="utf-8")
        self.assertIn("reviews safety incidents with their team each Monday", rec)
        inp = json.loads((self.tmp / "release" / "P1" / "input.json").read_text(encoding="utf-8"))
        self.assertEqual(inp["source_window"]["units"][0]["text"], "[redacted]")
        skeptic = (self.tmp / "release" / "P1" / "calls" / "02_S1.output.json").read_text(encoding="utf-8")
        self.assertNotIn("Every plant manager now", skeptic)

    def test_private_terms_replaced_whole_word_in_their_call_only(self):
        (self.run / "calls" / "04_J1.output.json").write_text(
            json.dumps({"claim": "injuries that occur at ACME and at ACMEX plants"}), encoding="utf-8")
        terms = {"P1": {"ACME": "[COMPANY_001]"}, "P2": {"ACMEX": "[COMPANY_009]"}}
        reports = redact.redact_batch(self.tmp / "run", self.tmp / "release3", terms)
        self.assertEqual(reports[0]["private_terms_replaced"], 1)
        out = (self.tmp / "release3" / "P1" / "calls" / "04_J1.output.json").read_text(encoding="utf-8")
        self.assertIn("occur at [COMPANY_001] and at ACMEX plants", out)
        report_text = (self.tmp / "release3" / "P1" / "REDACTION.json").read_text(encoding="utf-8")
        self.assertNotIn("ACME", report_text)

    def test_public_passage_is_copied_unchanged(self):
        inp = json.loads((self.run / "input.json").read_text(encoding="utf-8"))
        inp["license"] = "public"
        (self.run / "input.json").write_text(json.dumps(inp), encoding="utf-8")
        reports = redact.redact_batch(self.tmp / "run", self.tmp / "release2")
        self.assertFalse(reports[0]["redacted"])
        self.assertIn("We sold three non-core plants",
                      (self.tmp / "release2" / "P1" / "calls" / "01_R1.prompt.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
