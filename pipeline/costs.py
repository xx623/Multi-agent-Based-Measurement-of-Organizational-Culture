"""Per-call cost accounting (Technical Appendix E).

Prices are USD per million tokens at the provider's list price on the date given; the
table is edited, never fetched, so a run's cost basis is reproducible. Local inference
(Ollama, vLLM) has no marginal price; tokens and latency are still logged and the cost
column records 0 with the basis "local inference". Every attempt counts, retries included.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

PRICES_USD_PER_M = {
    # model id substring : (input, output, price-list date)
    "gemini-2.5-flash-lite": (0.10, 0.40, "2026-05-04"),
    "gemini-2.5-flash": (0.30, 2.50, "2026-05-04"),
    "gpt-4o-mini": (0.15, 0.60, "2026-01-01"),
}
LOCAL_MARKERS = ("qwen", "llama", "gemma", "mistral", "gpt-oss", "phi", "deepseek", "culture-")


def cost_for(model: str, tokens_in: int | None, tokens_out: int | None) -> tuple[float, str]:
    model = (model or "").lower()
    if tokens_in is None and tokens_out is None:
        return 0.0, "no usage reported"
    for key, (p_in, p_out, date) in PRICES_USD_PER_M.items():
        if key in model:
            cost = (tokens_in or 0) / 1e6 * p_in + (tokens_out or 0) / 1e6 * p_out
            return round(cost, 6), f"{key} list price {p_in}/{p_out} USD per M tokens as of {date}"
    if any(m in model for m in LOCAL_MARKERS) or not model:
        return 0.0, "local inference (no marginal price; tokens and latency logged)"
    return 0.0, "price not in table; add it to pipeline/costs.py"


def write_cost_log(run_dirs: list[Path], out_csv: Path) -> int:
    """One row per call: tokens and model time over all attempts and for the accepted attempt."""
    rows = []
    for rd in run_dirs:
        log = Path(rd) / "log.jsonl"
        if not log.exists():
            continue
        pid = Path(rd).name
        for line in log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            attempts = e.get("attempts", [])
            last = attempts[-1]["meta"] if attempts else {}
            model = last.get("model") or e.get("backend_params", {}).get("model")
            cost = sum(cost_for(model, (a.get("meta") or {}).get("input_tokens"),
                                (a.get("meta") or {}).get("output_tokens"))[0] for a in attempts)
            rows.append({
                "passage_dir": pid, "call": e["output_id"], "arm": e.get("arm"), "model": model,
                "attempts": len(attempts),
                "tokens_in_all_attempts": sum((a.get("meta") or {}).get("input_tokens") or 0 for a in attempts),
                "tokens_out_all_attempts": sum((a.get("meta") or {}).get("output_tokens") or 0 for a in attempts),
                "tokens_in_accepted": last.get("input_tokens"), "tokens_out_accepted": last.get("output_tokens"),
                "latency_s_all_attempts": round(sum((a.get("meta") or {}).get("latency_s") or 0 for a in attempts), 3),
                "latency_s_accepted": last.get("latency_s"), "served_from_cache": bool(last.get("cached")),
                "wall_s": e.get("wall_s"), "cost_usd": round(cost, 6), "cost_basis": e.get("cost_basis")})
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["passage_dir"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)
