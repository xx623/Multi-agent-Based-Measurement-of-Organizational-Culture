"""Regenerate manifest.json (SHA-256 of tracked files) and verification.json / .txt.

Run from the repository root: ``python tools/make_manifest.py``. The verification files
record software checks only (tests, offline replay of a recorded run, template hashes,
presence of pilot logs); they are not evidence of measurement validity.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "runs", "work", "__pycache__", ".pytest_cache", ".venv"}
SKIP_FILES = {"manifest.json", "verification.json", "verification.txt"}


def tracked_files() -> list[Path]:
    out = []
    for p in sorted(ROOT.rglob("*")):
        if p.is_dir() or p.suffix == ".pyc" or p.name in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        out.append(p)
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    files = {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p) for p in tracked_files()}
    proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT,
                          capture_output=True, text=True)
    test_out = proc.stdout + proc.stderr
    (ROOT / "verification.txt").write_text(test_out, encoding="utf-8")
    ran = failures = errors = 0
    for line in test_out.splitlines():
        if line.startswith("Ran "):
            ran = int(line.split()[1])
        if line.startswith("FAILED"):
            for part in line[len("FAILED ("):-1].split(", "):
                k, v = part.split("=")
                failures = int(v) if k == "failures" else failures
                errors = int(v) if k == "errors" else errors
    recorded = ROOT / "demo" / "recorded" / "DEMO-C_001"
    replay_ok = False
    if recorded.exists():
        rp = subprocess.run([sys.executable, "run_workflow.py", "replay", "--recorded", str(recorded), "--out",
                             str(ROOT / "runs" / "_verification_replay")], cwd=ROOT, capture_output=True, text=True)
        replay_ok = rp.returncode == 0 and '"status": "valid"' in rp.stdout
    pilots = sorted((ROOT / "logs").glob("*/pilot_summary.json"))
    pilot_info = []
    for p in pilots:
        s = json.loads(p.read_text(encoding="utf-8"))
        pilot_info.append({"batch": p.parent.name, "passages_processed": s.get("passages_processed"),
                           "valid": s.get("passages_valid"), "invalid": s.get("passages_invalid_after_retry")})
    verification = {
        "status": "software_checks_only_not_measurement_validation",
        "date": dt.date.today().isoformat(),
        "prompt_files_current": len(list((ROOT / "prompts" / "current").glob("*.txt"))),
        "schema_files": len(list((ROOT / "schemas").glob("*.json"))),
        "tests_run": ran, "test_failures": failures, "test_errors": errors,
        "recorded_demo_replay_valid": replay_ok,
        "five_role_prototype_executed_with_pinned_open_weight_model": bool(pilot_info),
        "pilot_batches": pilot_info,
        "expertise_agents_executed": any("experts" in p["batch"] for p in pilot_info),
        "measurement_validity_established": False,
    }
    (ROOT / "verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    manifest = {"artifact_type": "stage1_research_artifact_prototype", "date": dt.date.today().isoformat(),
                "files": files}
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verification, indent=2))
    print(f"{len(files)} files in manifest")


if __name__ == "__main__":
    main()
