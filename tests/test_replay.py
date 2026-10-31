"""Replay the recorded run of the constructed passage through controller and validators (offline).

Skipped when demo/recorded/DEMO-C_001 is absent (for example in a fresh checkout before the
pilot logs were added).
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import views  # noqa: E402
from pipeline.summary import derive_summary  # noqa: E402
from pipeline.controller import ArmConfig, WorkflowRunner  # noqa: E402
from pipeline.llm_client import ReplayBackend  # noqa: E402

RECORDED = ROOT / "demo" / "recorded" / "DEMO-C_001"


@unittest.skipUnless(RECORDED.exists(), "recorded demo run not present")
class RecordedReplay(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_recorded_outputs_still_pass_every_validator(self):
        src = json.loads((RECORDED / "input.json").read_text(encoding="utf-8"))
        cfg = json.loads((RECORDED / "config.json").read_text(encoding="utf-8"))
        arms = ArmConfig(**{k: v for k, v in cfg["arms"].items() if k != "label"})
        runner = WorkflowRunner(ReplayBackend(RECORDED / "calls"), self.tmp / "run", arms,
                                with_experts=cfg.get("with_experts", False), max_validation_retries=0)
        summary = runner.run(src)
        self.assertEqual(summary["status"], "valid", summary.get("errors"))
        self.assertEqual(summary["calls"], 14 if cfg.get("with_experts") else 8)
        self.assertEqual(summary["boundary_violations"], 0)

    def test_summary_is_derived_from_logged_files(self):
        s = derive_summary(RECORDED)
        self.assertEqual(s["status"], "valid")
        self.assertEqual(s["calls"], 8)
        self.assertEqual(s["boundary_violations"], 0)
        self.assertEqual(s["boundary_checked_calls"], 5)
        self.assertGreaterEqual(s["tokens_in"], s["tokens_in_accepted"])
        self.assertEqual(s["calls_retried"], s["validation_retries"])

    def test_interpretation_inputs_carry_no_declaration_or_passage_text(self):
        window = json.loads((RECORDED / "input.json").read_text(encoding="utf-8"))["source_window"]
        record = json.loads((RECORDED / "record_revised.json").read_text(encoding="utf-8"))
        for inputs in sorted((RECORDED / "calls").glob("*.inputs.json")):
            call_id = inputs.name.split("_", 1)[1].split(".")[0]
            if call_id in ("R1", "S1", "R2"):
                continue
            payload = json.loads(inputs.read_text(encoding="utf-8"))
            payload.pop("codebook", None)
            if payload.get("full_masked_window") not in (None, "withheld in this arm"):
                continue   # control arm B exposes the window on purpose
            self.assertEqual(views.leak_report(payload, record, window), [], inputs.name)


if __name__ == "__main__":
    unittest.main()
