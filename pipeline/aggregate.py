"""Pilot summary and firm-period profiles from finished run directories.

``pilot_summary`` reports what the proposal's Section 5 promises for the pilot log:
passages processed, flag and challenge figures, narrowing and withholding, escalations,
operational failures, and tokens, model time and cost per completed passage (retries
included). All figures are descriptive; none is a validity claim. Technical Appendix H
quotes the table that ``pilot_summary_markdown`` writes.

``build_profile`` aggregates final measurement records by group key (firm-quarter):
claims per category and direction, strongest relevance, limitations and the
declaration-ledger count. Silence is not absence and no dominant type is derived.
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

RELEVANCE_RANK = {"none": 0, "weak": 1, "moderate": 2, "strong": 3}
SOURCE_LABEL = {"synthetic": "constructed", "public": "public", "restricted": "licensed"}
CRITERION_LABEL = {"a": "alternative reading", "b": "episode generalized to a norm",
                   "c": "culture inferred from a formal rule", "d": "reliance on a plan or declaration",
                   "e": "scope wider than the view", "f": "direction, origin or content type misstated",
                   "g": "undercut by an unresolved source objection"}
CALL_LABEL = {"R1": "Reader (initial)", "S1": "skeptic", "R2": "Reader (revision)", "J1": "Judge round 1",
              "C1": "critic round 1", "J2": "Judge round 2", "C2": "critic round 2", "A1": "adjudicator"}
FLAG_LABEL = {"OMITTED_QUALIFIER": "omitted qualifier", "MISSING_ITEM": "missing item",
              "IGNORED_COUNTEREVIDENCE": "ignored counterevidence", "UNSUPPORTED_CLAIM": "unsupported claim",
              "SCOPE_OR_STATUS_ERROR": "scope or status error", "WEAK_EXCERPT": "weak excerpt"}
RESPONSE_LABEL = {"added_item": "item added", "amended": "amended", "defended": "defended",
                  "removed_item": "item removed"}


def load_summaries(run_dirs: Iterable[Path]) -> list[dict]:
    out = []
    for rd in run_dirs:
        p = Path(rd) / "summary.json"
        if p.exists():
            out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 1) if xs else None


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def _total(rows, key):
    return sum((r.get(key) or 0) for r in rows)


def _counter(rows, key) -> dict:
    c: Counter = Counter()
    for r in rows:
        c.update(r.get(key) or {})
    return dict(c)


def pilot_summary(run_dirs: Iterable[Path], label: str = "") -> dict:
    s = load_summaries(run_dirs)
    done = [x for x in s if x.get("status") in ("valid", "abstained")]
    invalid = [x for x in s if x.get("status") == "invalid"]
    by_source: dict[str, Counter] = {}
    for x in s:
        by_source.setdefault(SOURCE_LABEL.get(x.get("license"), str(x.get("license"))), Counter())[x.get("status")] += 1
    retained = Counter(f"{c['category']}, {c['relevance']}, {c['direction']} {c['content_type']}"
                       for x in done for c in x.get("retained_claims", []))
    return {
        "label": label,
        "passages_processed": len(s),
        "passages_valid": sum(x.get("status") == "valid" for x in done),
        "passages_abstained": sum(x.get("status") == "abstained" for x in done),
        "passages_invalid_after_retry": len(invalid),
        "by_source": {k: dict(v) for k, v in by_source.items()},
        "invalid_passages": [{"passage_id": x.get("passage_id"), "failed_call": x.get("failed_call"),
                              "first_error": str((x.get("errors") or [""])[0])[:240]} for x in invalid],
        "arms": dict(Counter(x.get("arm") for x in s)),
        "with_experts": dict(Counter(str(x.get("with_experts")) for x in s)),
        "reader_items_initial_total": _total(done, "reader_initial_items"),
        "reader_items_revised_total": _total(done, "reader_revised_items"),
        "reader_items_removed_total": _total(done, "reader_removed_items"),
        "declarations_revised_total": _total(done, "reader_revised_declarations"),
        "skeptic_flags_total": _total(done, "skeptic_flags"),
        "passages_with_flags": sum(1 for x in done if (x.get("skeptic_flags") or 0) > 0),
        "flag_types": _counter(done, "skeptic_flag_types"),
        "reader_flag_responses": _counter(done, "reader_flag_responses"),
        "unresolved_source_flags_total": _total(done, "unresolved_source_flags"),
        "completeness_uncertain_passages": sum(bool(x.get("completeness_uncertain")) for x in done),
        "expert_entries_total": _total(done, "expert_entries"),
        "judge1_claims_total": _total(done, "judge1_claims"),
        "judge1_claim_status": _counter(done, "judge1_claim_status"),
        "judge1_claim_categories": _counter(done, "judge1_claim_categories"),
        "critic1_objections_total": _total(done, "critic1_objections"),
        "objection_criteria": _counter(done, "critic1_criteria"),
        "critic1_accepted_total": _total(done, "critic1_accepted"),
        "judge2_responses": _counter(done, "judge2_responses"),
        "judge2_claims_total": _total(done, "judge2_claims"),
        "judge2_claim_status": _counter(done, "judge2_claim_status"),
        "passages_with_no_round2_claim": sum(1 for x in done if (x.get("judge2_claims") or 0) == 0),
        "critic2_objections_total": _total(done, "critic2_objections"),
        "critic2_resolved_total": _total(done, "critic2_resolved"),
        "adjudication_actions": _counter(done, "adjudication_actions"),
        "adjudication_withheld_by_j2_status": _counter(done, "adjudication_withheld_by_j2_status"),
        "claims_in_measurement_total": _total(done, "claims_in_measurement"),
        "passages_with_retained_claims": sum(1 for x in done if x.get("claims_in_measurement")),
        "retained_claims": dict(retained),
        "limitation_kinds": _counter(done, "limitation_kinds"),
        "escalated_passages": sum(bool(x.get("escalate_to_human")) for x in done),
        "boundary_checked_calls": _total(s, "boundary_checked_calls"),
        "boundary_violations": _total(s, "boundary_violations"),
        "calls_total": _total(s, "calls"),
        "calls_retried": _total(s, "calls_retried"),
        "retries_by_call": _counter(s, "retries_by_call"),
        "tokens_in_per_completed_passage_mean": _mean([x.get("tokens_in") for x in done]),
        "tokens_out_per_completed_passage_mean": _mean([x.get("tokens_out") for x in done]),
        "tokens_in_accepted_per_completed_passage_mean": _mean([x.get("tokens_in_accepted") for x in done]),
        "tokens_out_accepted_per_completed_passage_mean": _mean([x.get("tokens_out_accepted") for x in done]),
        "model_latency_s_per_completed_passage_mean": _mean([x.get("model_latency_s") for x in done]),
        "model_latency_s_per_completed_passage_median": _median([x.get("model_latency_s") for x in done]),
        "cost_usd_per_completed_passage_mean": _mean([x.get("cost_usd") for x in done]),
        "cost_basis": next((x.get("cost_basis") for x in s if x.get("cost_basis")), None),
        "passages": [{k: x.get(k) for k in ("passage_id", "license", "status", "arm", "skeptic_flags",
                                            "critic1_objections", "judge2_claims", "adjudication_actions",
                                            "claims_in_measurement", "escalate_to_human", "calls_retried",
                                            "tokens_in", "tokens_out", "model_latency_s")} for x in s],
    }


def _fmt_counts(d: dict, labels: dict | None = None, order: list | None = None) -> str:
    keys = order or sorted(d, key=lambda k: (-d[k], str(k)))
    return ", ".join(f"{(labels or {}).get(k, k)} {d[k]}" for k in keys if k in d)


def headline_rows(s: dict) -> list[tuple[str, str]]:
    """The rows of Technical Appendix Table H1, in the same wording."""
    n_done = s["passages_valid"] + s["passages_abstained"]
    src = s["by_source"]

    def src_cell(name):
        c = src.get(name, {})
        return f"{name} {c.get('valid', 0)} / {c.get('abstained', 0)} / {c.get('invalid', 0)}"

    j1, j2 = s["judge1_claim_status"], s["judge2_claim_status"]
    status_order = ["supported", "partially supported", "insufficient evidence"]
    src_of = {p["passage_id"]: SOURCE_LABEL.get(p.get("license"), p.get("license")) for p in s["passages"]}

    def reason(err: str) -> str:
        if "excerpt has" in err:
            return "excerpt over the 25-word limit after the retry"
        if "not verbatim" in err or "not an exact substring" in err:
            return "excerpt not verbatim after the retry"
        if "boundary violation" in err:
            return "boundary violation in interpretation inputs"
        return err.split(": ", 1)[-1][:80]
    inval = "; ".join(f"{src_of.get(x['passage_id'], '')} passage {x['passage_id']}, "
                      f"{CALL_LABEL.get(x['failed_call'], x['failed_call'])}: {reason(x['first_error'])}"
                      for x in s["invalid_passages"])
    retained = "; ".join(f"{k[0].lower() + k[1:]} ({v})" for k, v in sorted(s["retained_claims"].items(), key=lambda kv: -kv[1]))
    resolved = s["critic2_resolved_total"]
    return [
        ("Passages processed", f"{s['passages_processed']}: {s['passages_valid']} valid, {s['passages_abstained']} explicit "
                               f"abstentions, {s['passages_invalid_after_retry']} invalid after the permitted retry"),
        ("By source (valid / abstained / invalid)", "; ".join(src_cell(k) for k in ("constructed", "public", "licensed"))),
        ("Reader's conduct items, initial and revised", f"{s['reader_items_initial_total']} and "
                                                                       f"{s['reader_items_revised_total']} ({n_done} passages)"),
        ("Declarations in the ledger", str(s["declarations_revised_total"])),
        ("Skeptic flags", f"{s['skeptic_flags_total']} in {s['passages_with_flags']} of {n_done} passages: "
                          f"{_fmt_counts(s['flag_types'], FLAG_LABEL)}"),
        ("Reader responses to flags", _fmt_counts(s["reader_flag_responses"], RESPONSE_LABEL)),
        ("Unresolved source objections in the view",
         f"{s['unresolved_source_flags_total']}; completeness uncertain in {s['completeness_uncertain_passages']} of {n_done} passages"),
        ("Judge claims, round 1", f"{s['judge1_claims_total']}: {_fmt_counts(j1, order=status_order)}"),
        ("Critic objections, round 1", f"{s['critic1_objections_total']}: {_fmt_counts(s['objection_criteria'], CRITERION_LABEL)}; "
                                       f"{s['critic1_accepted_total']} claims accepted without objection"),
        ("Judge responses to objections, round 2", _fmt_counts(s["judge2_responses"],
                                                              {"accept": "objection accepted", "narrow": "claim narrowed",
                                                               "defend": "claim defended"})),
        ("Judge claims, round 2", f"{s['judge2_claims_total']}: {_fmt_counts(j2, order=status_order)}; no claim left in "
                                  f"{s['passages_with_no_round2_claim']} passages"),
        ("Critic objections, round 2", f"{s['critic2_objections_total']}; {resolved} round-1 objection{'' if resolved == 1 else 's'} resolved"),
        ("Adjudication of round-2 claims", f"{_fmt_counts(s['adjudication_actions'], {'accept': 'accepted', 'narrow': 'narrowed', 'withhold': 'withheld'}, ['accept', 'narrow', 'withhold'])}"
                                           f" ({s['adjudication_withheld_by_j2_status'].get('insufficient evidence', 0)} of the withheld already marked insufficient evidence by the Judge)"),
        ("Claims in the final measurement records", f"{s['claims_in_measurement_total']} in {s['passages_with_retained_claims']} passages: "
                                                    f"{retained}"),
        ("Limitations on retained claims", _fmt_counts(s["limitation_kinds"], {"SOURCE_INHERENT": "source-inherent",
                                                                             "RESOLVABLE": "resolvable",
                                                                             "UNDETERMINED": "undetermined"}) or "none"),
        ("Passages escalated to human review", f"{s['escalated_passages']} of {n_done}"),
        ("Boundary checks on interpretation calls; violations",
         f"{s['boundary_checked_calls']}; {s['boundary_violations']}"),
        ("Calls needing the one permitted retry", f"{s['calls_retried']} of {s['calls_total']}: "
                                                  f"{_fmt_counts(s['retries_by_call'], CALL_LABEL)}"),
        ("Invalid passages", f"{len(s['invalid_passages'])}: {inval}" if inval else "none"),
        ("Tokens per completed passage, mean",
         f"{s['tokens_in_per_completed_passage_mean']:,.0f} input and {s['tokens_out_per_completed_passage_mean']:,.0f} output "
         f"with retries ({s['tokens_in_accepted_per_completed_passage_mean']:,.0f} and "
         f"{s['tokens_out_accepted_per_completed_passage_mean']:,.0f} without); "
         + ("local inference, no marginal price" if str(s["cost_basis"]).startswith("local") else str(s["cost_basis"]))),
        ("Model time per completed passage", f"mean {s['model_latency_s_per_completed_passage_mean']} s, "
                                             f"median {s['model_latency_s_per_completed_passage_median']} s, retries included"),
    ]


def pilot_summary_markdown(summary: dict) -> str:
    lines = [f"# Pilot summary: {summary.get('label', '')}".rstrip(": "), "",
             "Descriptive figures from single runs at fixed decoding; no validity claim. Technical Appendix H, "
             "Table H1, quotes this table.", "", "| Quantity | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in headline_rows(summary)]
    lines += ["", "| Passage | Source | Status | Flags | Objections | Round-2 claims | Actions | Retained | Escalate | "
                  "Retried calls | Tokens in/out | Model time s |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in summary["passages"]:
        lines.append(f"| {p['passage_id']} | {SOURCE_LABEL.get(p['license'], p['license'])} | {p['status']} | "
                     f"{p['skeptic_flags']} | {p['critic1_objections']} | {p['judge2_claims']} | {p['adjudication_actions']} | "
                     f"{p['claims_in_measurement']} | {p['escalate_to_human']} | {p['calls_retried']} | "
                     f"{p['tokens_in']}/{p['tokens_out']} | {p['model_latency_s']} |")
    return "\n".join(lines) + "\n"


def build_profile(run_dirs: Iterable[Path]) -> list[dict]:
    cells: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "passages": 0, "claims": 0, "by_direction": Counter(), "strongest_relevance": "none",
        "source_inherent_limitations": 0, "resolvable_or_undetermined": 0, "escalated_passages": 0})
    declarations: dict[str, int] = defaultdict(int)
    for rd in run_dirs:
        rd = Path(rd)
        if not (rd / "final" / "measurement.json").exists():
            continue
        summary = json.loads((rd / "summary.json").read_text(encoding="utf-8"))
        group = summary.get("group_key") or "ungrouped"
        declarations[group] += summary.get("reader_revised_declarations", summary.get("reader_initial_declarations", 0)) or 0
        m = json.loads((rd / "final" / "measurement.json").read_text(encoding="utf-8"))
        for cat, body in m["categories"].items():
            cell = cells[(group, cat)]
            cell["passages"] += 1
            cell["claims"] += len(body["claims"])
            if summary.get("escalate_to_human"):
                cell["escalated_passages"] += 1
            if RELEVANCE_RANK.get(body["relevance"], 0) > RELEVANCE_RANK.get(cell["strongest_relevance"], 0):
                cell["strongest_relevance"] = body["relevance"]
            for c in body["claims"]:
                cell["by_direction"][c["direction"]] += 1
                for lim in c.get("limitations", []):
                    if lim["kind"] == "SOURCE_INHERENT":
                        cell["source_inherent_limitations"] += 1
                    else:
                        cell["resolvable_or_undetermined"] += 1
    rows = []
    for (group, cat), v in sorted(cells.items()):
        rows.append({"group_key": group, "category": cat, "passages": v["passages"], "claims": v["claims"],
                     "strongest_relevance": v["strongest_relevance"],
                     "by_direction": ";".join(f"{k}:{n}" for k, n in sorted(v["by_direction"].items())),
                     "source_inherent_limitations": v["source_inherent_limitations"],
                     "resolvable_or_undetermined_limitations": v["resolvable_or_undetermined"],
                     "escalated_passages": v["escalated_passages"], "declaration_ledger_count": declarations[group]})
    return rows


def write_csv(rows: list[dict], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        if rows:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
