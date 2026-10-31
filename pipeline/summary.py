"""Derive a passage summary from the files a run writes.

The controller calls ``derive_summary`` after every run, and ``run_workflow.py pilot-summary``
re-derives summaries from released logs, so the figures in ``summary.json``, ``pilot_summary.md``
and the technical appendix all come from one computation. Token counts and model time include
every attempt, retries included; accepted-attempt figures are reported alongside.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .costs import cost_for

ISOLATION_CHECKED = ("J1", "J2", "T1", "T2", "T3", "T4", "T5", "T6")
ALWAYS_CHECKED = ("C1", "C2", "A1")


def _load(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _output(run_dir: Path, call_id: str):
    hits = sorted((run_dir / "calls").glob(f"*_{call_id}.output.json"))
    return _load(hits[0]) if hits else None


def _count(items, key) -> dict:
    return dict(Counter(str(x.get(key)) for x in items or [] if isinstance(x, dict)))


def _tokens(attempts: list[dict], key: str):
    values = [(a.get("meta") or {}).get(key) for a in attempts]
    return sum(v or 0 for v in values) if any(values) else None


def _latency(attempts: list[dict]) -> float:
    return round(sum(((a.get("meta") or {}).get("latency_s") or 0.0) for a in attempts), 1)


def derive_summary(run_dir) -> dict:
    run_dir = Path(run_dir)
    cfg = _load(run_dir / "config.json") or {}
    inp = _load(run_dir / "input.json") or {}
    arms = cfg.get("arms") or {}
    log_path = run_dir / "log.jsonl"
    log = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()] \
        if log_path.exists() else []
    process = _load(run_dir / "final" / "process.json") or {}
    measurement = _load(run_dir / "final" / "measurement.json")
    r1, s1, r2, j1, c1, j2, c2, a1 = (_output(run_dir, c) for c in ("R1", "S1", "R2", "J1", "C1", "J2", "C2", "A1"))
    experts = [x for x in (_output(run_dir, f"T{i}") for i in range(1, 7)) if x]
    view = _load(run_dir / "record_interp.json")
    errors = process.get("errors") or []

    attempts = [a for e in log for a in e.get("attempts", [])]
    accepted = [e["attempts"][-1] for e in log if e.get("attempts")]
    cost, basis = 0.0, None
    for e in log:
        model = (e.get("backend_params") or {}).get("model", "")
        for a in e.get("attempts", []):
            meta = a.get("meta") or {}
            c, basis = cost_for(meta.get("model") or model, meta.get("input_tokens"), meta.get("output_tokens"))
            cost += c
    checked = set(ALWAYS_CHECKED) | (set(ISOLATION_CHECKED) if arms.get("isolation", True) else set())

    s: dict = {
        "passage_id": inp.get("passage_id") or cfg.get("passage_id"),
        "group_key": cfg.get("group_key") or inp.get("group_key") or "ungrouped",
        "license": cfg.get("license") or inp.get("license") or (inp.get("provenance") or {}).get("license"),
        "arm": arms.get("label"),
        "with_experts": bool(cfg.get("with_experts", False)),
        "status": process.get("output_state") or "invalid",
        "failed_call": process.get("failed_call"),
        "errors": errors[:5],
        "calls": len(log),
        "calls_retried": sum(1 for e in log if len(e.get("attempts", [])) > 1),
        "validation_retries": sum(len(e.get("attempts", [])) - 1 for e in log),
        "retries_by_call": dict(Counter(e["output_id"] for e in log if len(e.get("attempts", [])) > 1)),
        "tokens_in": _tokens(attempts, "input_tokens"),
        "tokens_out": _tokens(attempts, "output_tokens"),
        "tokens_in_accepted": _tokens(accepted, "input_tokens"),
        "tokens_out_accepted": _tokens(accepted, "output_tokens"),
        "model_latency_s": _latency(attempts),
        "model_latency_s_accepted": _latency(accepted),
        "wall_s": round(sum(e.get("wall_s") or 0.0 for e in log), 1),
        "cost_usd": round(cost, 6),
        "cost_basis": basis,
        "boundary_checked_calls": sum(1 for e in log if e.get("output_id") in checked),
        "boundary_violations": sum(1 for x in errors if "boundary violation" in str(x)),
    }
    if r1:
        s["reader_initial_items"] = len(r1.get("items", []))
        s["reader_initial_declarations"] = len(r1.get("declarations", []))
    if s1:
        s["skeptic_flags"] = len(s1.get("flags", []))
        s["skeptic_flag_types"] = _count(s1.get("flags"), "type")
    if r2:
        s["reader_revised_items"] = len(r2.get("items", []))
        s["reader_revised_declarations"] = len(r2.get("declarations", []))
        s["reader_removed_items"] = len(r2.get("removed_item_ids", []))
        s["reader_flag_responses"] = _count(r2.get("flag_responses"), "action")
    if view:
        s["unresolved_source_flags"] = len(view.get("unresolved", []))
        s["completeness_uncertain"] = bool(view.get("completeness_uncertain"))
    if experts:
        s["experts_run"] = len(experts)
        s["expert_entries"] = sum(len(x.get("entries", [])) for x in experts)
    if j1:
        s["judge1_claims"] = len(j1.get("claims", []))
        s["judge1_claim_status"] = _count(j1.get("claims"), "status")
        s["judge1_claim_categories"] = _count(j1.get("claims"), "category")
    if c1:
        s["critic1_objections"] = len(c1.get("objections", []))
        s["critic1_criteria"] = _count(c1.get("objections"), "criterion")
        s["critic1_accepted"] = len(c1.get("accepted_claims", []))
    if j2:
        s["judge2_claims"] = len(j2.get("claims", []))
        s["judge2_claim_status"] = _count(j2.get("claims"), "status")
        s["judge2_responses"] = _count(j2.get("objection_responses"), "action")
    if c2:
        s["critic2_objections"] = len(c2.get("objections", []))
        s["critic2_resolved"] = len(c2.get("resolved_objection_ids", []))
    if a1 and measurement is not None:
        j2_status = {c.get("id"): c.get("status") for c in (j2 or {}).get("claims", [])}
        actions = process.get("actions", [])
        retained = []
        for cat, body in measurement.get("categories", {}).items():
            for c in body.get("claims", []):
                retained.append({"category": cat, "claim_ref": c.get("claim_ref"), "relevance": c.get("relevance"),
                                 "direction": c.get("direction"), "content_type": c.get("content_type"),
                                 "origin": c.get("origin"), "scope": c.get("scope"),
                                 "limitation_kinds": [lim.get("kind") for lim in c.get("limitations", [])]})
        s["adjudication_actions"] = _count(actions, "action")
        s["adjudication_withheld_by_j2_status"] = dict(Counter(str(j2_status.get(a.get("claim_ref")))
                                                               for a in actions if a.get("action") == "withhold"))
        s["claims_in_measurement"] = len(retained)
        s["retained_claims"] = retained
        s["category_summary"] = {name: {"relevance": b.get("relevance"), "direction": b.get("direction"),
                                        "claims": len(b.get("claims", []))}
                                 for name, b in measurement.get("categories", {}).items()}
        s["limitation_kinds"] = dict(Counter(k for c in retained for k in c["limitation_kinds"]))
        s["unresolved_objections"] = len(process.get("unresolved_objections", []))
        s["escalate_to_human"] = bool(process.get("escalate_to_human"))
        s["abstention_reason"] = process.get("abstention_reason") or None
    return s
