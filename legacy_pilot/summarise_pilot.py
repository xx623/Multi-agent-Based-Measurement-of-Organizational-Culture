"""Descriptive summary of the legacy ten-agent pilot (May 2026).

Reads ``all_agent_responses.csv`` (one row per call-level input, every agent's fields)
and writes ``pilot_summary.json`` and ``pilot_summary.md``. Standard library only.
The numbers are descriptive: the pilot had no gold standard, no information boundaries
and no logging of tokens or latency, so no validity claim follows from them.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
TYPE_AGENTS = {
    "collaboration_people_focused_agent": "Collaboration and People-Focused",
    "customer_oriented_agent": "Customer-Oriented",
    "innovation_adaptability_agent": "Innovation and Adaptability",
    "integrity_risk_management_agent": "Integrity and Risk Management",
    "performance_oriented_agent": "Performance-Oriented",
    "miscellaneous_agent": "Miscellaneous",
}


def truthy(v: str) -> bool:
    return str(v).strip().lower() == "true"


def main() -> None:
    source = HERE / "all_agent_responses.csv"
    if not source.exists():
        raise SystemExit("all_agent_responses.csv is withheld because it quotes licensed transcripts at length "
                         "(see README.md); pilot_summary.json holds the figures. Place the file here to recompute.")
    rows = list(csv.DictReader(source.open(encoding="utf-8", newline="")))
    n = len(rows)
    calls = {r["input_id"].rsplit("_", 1)[0] for r in rows}
    components = sum(len(r["input_id"].rsplit("_", 1)[1].split(",")) for r in rows)
    judge_type = Counter(r["judge_generator_agent__culture_type"] for r in rows)
    final_cls = Counter(r["judge_generator_agent__final_classification"] for r in rows)
    tone = Counter(r["judge_generator_agent__tone"] for r in rows)
    faith = Counter(r["evidence_verifier_agent__overall_faithfulness"] for r in rows)
    uncertain = sum(truthy(r["judge_generator_agent__uncertainty_flag"]) for r in rows)
    causal = sum(truthy(r["judge_generator_agent__has_explicit_causal_analysis"]) for r in rows)
    per_agent = {}
    for key, label in TYPE_AGENTS.items():
        assigns = sum(truthy(r[f"{key}__should_assign"]) for r in rows)
        confs = [float(r[f"{key}__confidence"]) for r in rows if r[f"{key}__confidence"] not in ("", None)]
        per_agent[label] = {"should_assign_true": assigns,
                            "mean_confidence": round(sum(confs) / len(confs), 2) if confs else None}
    multi = 0
    judge_follows_max_conf = 0
    for r in rows:
        assigning = [(float(r[f"{k}__confidence"] or 0), lab) for k, lab in TYPE_AGENTS.items()
                     if truthy(r[f"{k}__should_assign"])]
        if len(assigning) > 1:
            multi += 1
        if assigning and max(assigning)[1] == r["judge_generator_agent__culture_type"]:
            judge_follows_max_conf += 1
    summary = {
        "source_file": "all_agent_responses.csv",
        "run_date": "2026-05-04",
        "model": "gemini-2.5-flash-lite (OpenAI-compatible endpoint), temperature 0, JSON mode",
        "design": "single prompt simulating ten agents in sequence; no information boundaries",
        "call_level_inputs_with_parsed_output": n,
        "call_level_inputs_sent": 17,
        "unparseable_outputs": 1,
        "earnings_calls_covered": len(calls),
        "screened_executive_components_covered": components,
        "judge_final_classification": dict(final_cls),
        "judge_culture_type": dict(judge_type),
        "judge_tone": dict(tone),
        "verifier_overall_faithfulness": dict(faith),
        "judge_uncertainty_flag_true": uncertain,
        "judge_explicit_causal_analysis_true": causal,
        "type_agents": per_agent,
        "inputs_with_two_or_more_type_agents_recommending": multi,
        "inputs_where_judge_type_equals_highest_confidence_recommendation": judge_follows_max_conf,
        "tokens_latency_cost": "not logged by the legacy pipeline",
    }
    (HERE / "pilot_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = ["# Legacy pilot: descriptive summary", "",
             f"Run date 2026-05-04; {summary['model']}; {summary['design']}.", "",
             "| Quantity | Value |", "|---|---|",
             f"| Call-level inputs sent / parsed | 17 / {n} |",
             f"| Earnings calls covered | {len(calls)} |",
             f"| Screened executive components covered | {components} |",
             f"| Judge final classification | {dict(final_cls)} |",
             f"| Judge culture type | {dict(judge_type)} |",
             f"| Judge tone | {dict(tone)} |",
             f"| Verifier overall faithfulness | {dict(faith)} |",
             f"| Judge uncertainty flag true | {uncertain} |",
             f"| Judge explicit causal analysis true | {causal} |",
             f"| Inputs with two or more type agents recommending assignment | {multi} |",
             f"| Inputs where the Judge's type equals the highest-confidence recommendation | {judge_follows_max_conf} |",
             "| Tokens, latency, cost | not logged |", "",
             "| Type agent | should_assign = true | mean confidence |", "|---|---|---|"]
    for label, v in per_agent.items():
        lines.append(f"| {label} | {v['should_assign_true']} | {v['mean_confidence']} |")
    (HERE / "pilot_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
