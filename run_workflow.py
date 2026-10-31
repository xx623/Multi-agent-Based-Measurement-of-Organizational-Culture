#!/usr/bin/env python3
"""Command-line entry point for the multi-agent measurement prototype.

    python run_workflow.py demo                       # pinned local model on demo/inputs, writes new logs
    python run_workflow.py run --input <file|dir>     # same, any inputs; arm switches; --with-experts
    python run_workflow.py replay --recorded logs/<batch>/<passage>  # re-run recorded outputs offline
    python run_workflow.py windows --transcript <call.txt> --out-dir work/<call> [--ner spacy]
    python run_workflow.py pilot-summary --runs logs/<batch>
    python run_workflow.py redact --runs runs/<batch> --out logs/<batch> [--private-terms <file outside the repo>]
    python run_workflow.py export-schemas

Model settings come from config/model_pins.json unless overridden by --model / --base-url
or the environment variables LLM_MODEL, LLM_BASE_URL, LLM_API_KEY.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import aggregate, costs, redact, schemas, windows  # noqa: E402
from pipeline.controller import ArmConfig, WorkflowRunner  # noqa: E402
from pipeline.llm_client import make_backend  # noqa: E402
from pipeline.summary import derive_summary  # noqa: E402


PRIVATE_TERMS_HELP = ("JSON file {call_id: {term: placeholder}} of identifiers the masking table missed, replaced "
                      "in release copies of restricted passages; keep it outside the repository")


def _stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def _pins() -> dict:
    p = ROOT / "config" / "model_pins.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _load_inputs(spec: str) -> list[dict]:
    p = Path(spec)
    files = sorted(p.rglob("*.json")) if p.is_dir() else [p]
    inputs = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "passage_id" in data and "source_window" in data:
            inputs.append(data)
    if not inputs:
        raise SystemExit(f"no passage inputs found at {spec}")
    return inputs


def _backend_from_args(args) -> object:
    pins = _pins().get("pinned_model", {})
    decoding = _pins().get("decoding", {})
    model = args.model or os.environ.get("LLM_MODEL") or pins.get("served_as") or pins.get("model_tag")
    base_url = args.base_url or os.environ.get("LLM_BASE_URL") or pins.get("base_url")
    return make_backend("openai", cache_dir=args.cache_dir, model=model, base_url=base_url,
                        temperature=decoding.get("temperature", 0.0), seed=decoding.get("seed", 12345),
                        json_mode=decoding.get("json_mode", True))


def _run_batch(inputs, backend, out_dir: Path, arms: ArmConfig, retries: int, with_experts: bool,
               quiet: bool, label: str, release_dir: Path | None,
               private_terms: dict | None = None) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, src in enumerate(inputs, 1):
        run_dir = out_dir / _safe(src["passage_id"])
        progress = (lambda m: None) if quiet else (lambda m: print("   " + m, flush=True))
        runner = WorkflowRunner(backend, run_dir, arms, with_experts=with_experts, max_validation_retries=retries,
                                progress=progress)
        print(f"[{i}/{len(inputs)}] {src['passage_id']} (arm {arms.label})", flush=True)
        summary = runner.run(src)
        results.append(summary)
        print(f"   -> {summary.get('status')}; flags {summary.get('skeptic_flags')}, objections "
              f"{summary.get('critic1_objections')}, actions {summary.get('adjudication_actions')}, "
              f"tokens {summary.get('tokens_in')}/{summary.get('tokens_out')}, {summary.get('wall_s')} s", flush=True)
    run_dirs = [out_dir / _safe(r["passage_id"]) for r in results]
    batch = {"label": label, "arms": arms.as_dict(), "with_experts": with_experts, "backend": backend.name,
             "backend_params": backend.params, "finished_at": dt.datetime.now().isoformat(),
             "passages": results}
    (out_dir / "batch_summary.json").write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    costs.write_cost_log(run_dirs, out_dir / "cost_log.csv")
    summary = aggregate.pilot_summary(run_dirs, label)
    (out_dir / "pilot_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str),
                                                encoding="utf-8")
    (out_dir / "pilot_summary.md").write_text(aggregate.pilot_summary_markdown(summary), encoding="utf-8")
    aggregate.write_csv(aggregate.build_profile(run_dirs), out_dir / "profile.csv")
    if release_dir:
        reports = redact.redact_batch(out_dir, release_dir, private_terms)
        print(f"release copy written to {release_dir} ({sum(r['redacted'] for r in reports)} passages redacted)")
    print(f"\n{summary['passages_valid']} valid, {summary['passages_abstained']} abstained, "
          f"{summary['passages_invalid_after_retry']} invalid. Outputs in {out_dir}")
    return results


def _private_terms(args) -> dict | None:
    path = getattr(args, "private_terms", None)
    return redact.load_private_terms(path) if path else None


def cmd_demo(args):
    arms = ArmConfig()
    backend = _backend_from_args(args)
    out = Path(args.out) if args.out else ROOT / "runs" / f"demo_{_stamp()}"
    _run_batch(_load_inputs(str(ROOT / "demo" / "inputs")), backend, out, arms, args.max_validation_retries,
               args.with_experts, args.quiet, "demo", Path(args.release_dir) if args.release_dir else None,
               _private_terms(args))


def cmd_run(args):
    arms = ArmConfig(isolation=not args.no_isolation, evidence_inquiry=not args.no_evidence_inquiry,
                     interpretive_inquiry=not args.no_interpretive_inquiry)
    backend = _backend_from_args(args)
    out = Path(args.out) if args.out else ROOT / "runs" / f"{_stamp()}_{arms.label}"
    _run_batch(_load_inputs(args.input), backend, out, arms, args.max_validation_retries, args.with_experts,
               args.quiet, args.label or "", Path(args.release_dir) if args.release_dir else None,
               _private_terms(args))


def cmd_replay(args):
    rec = Path(args.recorded)
    src = json.loads((rec / "input.json").read_text(encoding="utf-8"))
    cfg = json.loads((rec / "config.json").read_text(encoding="utf-8"))
    arms = ArmConfig(**{k: v for k, v in cfg["arms"].items() if k != "label"})
    backend = make_backend("replay", fixtures=str(rec / "calls"))
    out = Path(args.out) if args.out else ROOT / "runs" / f"replay_{_stamp()}"
    runner = WorkflowRunner(backend, out / _safe(src["passage_id"]), arms, with_experts=cfg.get("with_experts", False),
                            max_validation_retries=0)
    summary = runner.run(src)
    print(json.dumps({k: summary.get(k) for k in ("passage_id", "status", "calls", "skeptic_flags", "critic1_objections",
                                                  "adjudication_actions", "escalate_to_human", "boundary_violations")},
                     indent=2))


def cmd_windows(args):
    info = windows.build_from_transcript(Path(args.transcript), Path(args.out_dir),
                                         sentences_per_passage=args.sentences, context=args.context,
                                         mask_terms=Path(args.mask_terms) if args.mask_terms else None,
                                         keep_ids=args.keep_ids, salt=args.salt, turns_json=args.turns_json,
                                         ner=args.ner, license_tag=args.license)
    print(json.dumps(info, indent=2))


def cmd_pilot_summary(args):
    runs = [p for p in Path(args.runs).iterdir() if p.is_dir() and (p / "log.jsonl").exists()]
    for rd in runs:   # re-derive each passage summary from its logged files (single source of truth)
        old = json.loads((rd / "summary.json").read_text(encoding="utf-8")) if (rd / "summary.json").exists() else {}
        new = derive_summary(rd)
        new["wall_s"] = old.get("wall_s", new["wall_s"])
        (rd / "summary.json").write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = aggregate.pilot_summary(runs, args.label or Path(args.runs).name)
    out = Path(args.out) if args.out else Path(args.runs)
    (out / "pilot_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (out / "pilot_summary.md").write_text(aggregate.pilot_summary_markdown(summary), encoding="utf-8")
    costs.write_cost_log(runs, out / "cost_log.csv")
    aggregate.write_csv(aggregate.build_profile(runs), out / "profile.csv")
    print((out / "pilot_summary.md").read_text(encoding="utf-8"))


def cmd_redact(args):
    reports = redact.redact_batch(Path(args.runs), Path(args.out), _private_terms(args))
    print(json.dumps(reports, indent=2))


def cmd_export_schemas(args):
    written = schemas.export(Path(args.out), schemas.load_codebook(ROOT))
    print("\n".join(str(p.relative_to(ROOT)) for p in written))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def model_args(p):
        p.add_argument("--model")
        p.add_argument("--base-url")
        p.add_argument("--cache-dir", default=str(ROOT / "runs" / "_cache"))
        p.add_argument("--max-validation-retries", type=int, default=1)
        p.add_argument("--with-experts", action="store_true", help="run the six expertise agents (extension)")
        p.add_argument("--release-dir", help="also write a release-safe (redacted) copy here")
        p.add_argument("--private-terms", help=PRIVATE_TERMS_HELP)
        p.add_argument("--out")
        p.add_argument("--quiet", action="store_true")

    d = sub.add_parser("demo", help="run the pipeline on demo/inputs with the pinned model")
    model_args(d)
    d.set_defaults(func=cmd_demo)

    r = sub.add_parser("run", help="run the pipeline on a passage file or a directory of passages")
    r.add_argument("--input", required=True)
    r.add_argument("--label", default="")
    r.add_argument("--no-isolation", action="store_true", help="control arm B")
    r.add_argument("--no-evidence-inquiry", action="store_true", help="control arm C")
    r.add_argument("--no-interpretive-inquiry", action="store_true", help="control arm E")
    model_args(r)
    r.set_defaults(func=cmd_run)

    rp = sub.add_parser("replay", help="replay a recorded passage run offline through controller and validators")
    rp.add_argument("--recorded", required=True, help="a passage run directory containing calls/ and input.json")
    rp.add_argument("--out")
    rp.set_defaults(func=cmd_replay)

    w = sub.add_parser("windows", help="parse, mask and window one transcript")
    w.add_argument("--transcript", required=True)
    w.add_argument("--out-dir", required=True)
    w.add_argument("--sentences", type=int, default=8)
    w.add_argument("--context", type=int, default=2)
    w.add_argument("--mask-terms")
    w.add_argument("--keep-ids", action="store_true")
    w.add_argument("--salt", default="")
    w.add_argument("--turns-json", action="store_true")
    w.add_argument("--ner", choices=["spacy"], help="add spaCy named entities to the mask table")
    w.add_argument("--license", choices=["restricted", "public", "synthetic"], default="restricted")
    w.set_defaults(func=cmd_windows)

    ps = sub.add_parser("pilot-summary", help="summarise finished runs")
    ps.add_argument("--runs", required=True)
    ps.add_argument("--label", default="")
    ps.add_argument("--out")
    ps.set_defaults(func=cmd_pilot_summary)

    rd = sub.add_parser("redact", help="write a release-safe copy of a batch of runs")
    rd.add_argument("--runs", required=True)
    rd.add_argument("--out", required=True)
    rd.add_argument("--private-terms", help=PRIVATE_TERMS_HELP)
    rd.set_defaults(func=cmd_redact)

    e = sub.add_parser("export-schemas")
    e.add_argument("--out", default=str(ROOT / "schemas"))
    e.set_defaults(func=cmd_export_schemas)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
