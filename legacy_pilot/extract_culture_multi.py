"""Culture information extraction pipeline — multi-agent version.

Key differences from extract_culture.py (round1):
- Processing granularity: component-level instead of call-level.
  Each culture component is sent to the LLM in a separate API call.
  No call-level grouping or skip-marker concatenation.
- Prompt: multi_agent_prompt_calls.txt (10 simulated agents) instead of
  round1_prompt.txt (sequential CoT Q1-Q7).
  Agent structure: 6 independent type agents (1–6) → Tone (7) → Causal (8)
  → Verifier (9) → Judge (10). No separate screening agent; NoCulture is
  determined by the Judge when all type agents report no sufficient evidence.
  Each culture type (Collaboration, Customer, Innovation, Integrity,
  Performance, Miscellaneous) is a separate agent with its own output block.
- Template filling: {{input_id}} and {{component_text}} in the system prompt
  are pre-filled per call before the API call, so chunk_size is always 1.
- Output schema: flat JSON with one top-level key per agent (11 keys total);
  final answers are taken from judge_generator_agent. A custom retrieval
  function parses this structure (gpt_funcs._process_cursor only handles
  all_results / results arrays).
- NoCulture filtering: components where judge_generator_agent.final_classification
  == "NoCulture" are dropped before saving combined results.
- Column names in COMBINED_RESULTS are compatible with normalize_culture_multi.py.

Usage:
    python extract_culture_multi.py run_extraction_pipeline
    python extract_culture_multi.py run_multi_agent_extraction
    python extract_culture_multi.py combine_extraction_results
"""

from __future__ import annotations

import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fire
import pandas as pd
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent.parent))
sys.path.append(str(Path(__file__).parent.parent))

from config_multi import (
    CULTURE_SEGMENTS_PATH,
    OUTPUT_DIR,
    MULTI_AGENT_DB,
    MULTI_AGENT_RESULTS,
    COMBINED_RESULTS,
    AGENT_DETAIL_CSV,
    MULTI_AGENT_PROMPT,
    GPT_MODEL,
    BASE_URL,
    API_KEY,
    MAX_WORKERS,
)
from gpt_funcs import GPTDataFrameClassifier, safe_delete_db


# ── Load culture components at component level ─────────────────────────────────

def load_culture_components() -> pd.DataFrame:
    """Load culture components grouped at the call level.

    Multiple components from the same call are combined with skip markers,
    matching the round1 pipeline's call-level consolidation logic.
    One row per call; input_id = call_id + "_" + comma-separated component_ids.

    Returns:
        DataFrame with columns: call_id, component_ids, input_id, segment_text
    """
    culture_df = pd.read_csv(CULTURE_SEGMENTS_PATH)

    if "call_id" not in culture_df.columns and "report_id" in culture_df.columns:
        culture_df["call_id"] = culture_df["report_id"]
    if "component_id" not in culture_df.columns and "seg_id" in culture_df.columns:
        culture_df["component_id"] = culture_df["seg_id"]

    culture_df["call_id"]      = culture_df["call_id"].astype(str)
    culture_df["component_id"] = culture_df["component_id"].astype(int)
    culture_df = culture_df.sort_values(["call_id", "component_id"]).reset_index(drop=True)

    def combine_components(group):
        group = group.sort_values("component_id").reset_index(drop=True)
        parts = []
        for i, row in group.iterrows():
            if i > 0 and row["component_id"] > group.iloc[i - 1]["component_id"] + 1:
                parts.append("\n[...]\n")
            parts.append(row["segment_text"])
        return "\n".join(parts)

    grouped = (
        culture_df.groupby("call_id")
        .agg({"call_id": "first", "component_id": lambda x: ",".join(map(str, x))})
        .reset_index(drop=True)
        .rename(columns={"component_id": "component_ids"})
    )
    grouped["segment_text"] = (
        culture_df.groupby("call_id")
        .apply(combine_components)
        .reset_index(drop=True)
    )
    grouped["input_id"] = (
        grouped["call_id"].astype(str) + "_" + grouped["component_ids"].astype(str)
    )

    print(f"Loaded {len(culture_df)} culture components from {len(grouped)} calls")
    grouped.to_csv(
        CULTURE_SEGMENTS_PATH.parent / "all_culture_segments_grouped_multi.csv",
        index=False,
    )
    return grouped


# ── Multi-agent DB helpers ─────────────────────────────────────────────────────

def retrieve_multi_agent_results(db_path: Path) -> pd.DataFrame:
    """Parse multi-agent results from SQLite.

    The multi-agent prompt returns a single top-level JSON object per component
    (keys: input_id, collaboration_people_focused_agent, customer_oriented_agent,
    innovation_adaptability_agent, integrity_risk_management_agent,
    performance_oriented_agent, miscellaneous_agent, tone_agent,
    causal_structure_agent, evidence_verifier_agent, judge_generator_agent).
    gpt_funcs._process_cursor only handles all_results / results arrays, so we
    need a dedicated parser here.

    Returns:
        DataFrame where each row is one component's full multi-agent output.
    """
    if not db_path.exists():
        return pd.DataFrame()

    results = []
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT json_result FROM gpt_results")
        for (raw,) in cursor:
            raw = raw.replace("```json", "").replace("```", "")
            try:
                data = json.loads(raw)
                if "input_id" in data:
                    results.append(data)
                else:
                    print(f"Unexpected multi-agent JSON keys: {list(data.keys())}")
            except json.JSONDecodeError as e:
                print(f"JSON parse error: {e}")

    return pd.DataFrame(results) if results else pd.DataFrame()


def get_existing_multi_agent_ids(db_path: Path) -> set[str]:
    """Return the set of input_ids already stored in the multi-agent DB."""
    df = retrieve_multi_agent_results(db_path)
    if not df.empty and "input_id" in df.columns:
        return set(df["input_id"].astype(str))
    return set()


# ── Multi-agent extraction ─────────────────────────────────────────────────────

def run_multi_agent_extraction(sample_size: int = None) -> None:
    """Run multi-agent extraction on individual culture components.

    Template placeholders {{input_id}} and {{component_text}} in the system
    prompt are pre-filled per component before each API call, ensuring the model
    receives a fully-formed task rather than a raw JSON chunk.

    Args:
        sample_size: Optional number of components to sample (for testing).
    """
    print("=== Multi-Agent Culture Information Extraction ===")

    culture_df = load_culture_components()

    if sample_size is not None:
        culture_df = culture_df.sample(
            n=min(sample_size, len(culture_df)), random_state=42
        )
        print(f"Processing sample of {len(culture_df)} components")

    culture_df = culture_df.sample(frac=1, random_state=42).reset_index(drop=True)

    db_path = MULTI_AGENT_DB
    safe_delete_db(
        db_path,
        "Removing existing multi-agent database. Select 'no' to resume an interrupted run.",
    )

    # Resume support: filter out already-processed components.
    existing_ids = get_existing_multi_agent_ids(db_path)
    if existing_ids:
        before = len(culture_df)
        culture_df = culture_df[
            ~culture_df["input_id"].astype(str).isin(existing_ids)
        ].reset_index(drop=True)
        print(f"Skipping {before - len(culture_df)} already processed. "
              f"Remaining: {len(culture_df)}")

    if culture_df.empty:
        print("No new components to process.")
        return

    sys_msg_template = MULTI_AGENT_PROMPT.read_text()
    gpt_classifier   = GPTDataFrameClassifier(
        model_name=GPT_MODEL, base_url=BASE_URL, api_key=API_KEY
    )

    # Open DB connection for sequential writes (thread-safe pattern from gpt_funcs).
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    GPTDataFrameClassifier.create_table_if_not_exists(conn)

    def process_row(row: pd.Series) -> str | None:
        sys_msg = (
            sys_msg_template
            .replace("{{input_id}}", str(row["input_id"]))
            .replace("{{component_text}}", str(row["segment_text"]))
        )
        try:
            return gpt_classifier.gpt_process(
                sys_msg_content=sys_msg,
                human_msg_content="Please proceed with the analysis as described above.",
            )
        except Exception as e:
            print(f"API error for {row['input_id']}: {e}")
            return None

    rows = [row for _, row in culture_df.iterrows()]
    print(f"Running multi-agent extraction on {len(rows)} calls...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_row, row): row["input_id"] for row in rows}
        for future in tqdm(as_completed(futures), total=len(futures)):
            try:
                result = future.result()
                if result is not None:
                    GPTDataFrameClassifier.store_json_result(conn, result)
            except Exception as e:
                print(f"Error storing result: {e}")

    conn.close()

    results_df = retrieve_multi_agent_results(db_path)
    results_df.to_csv(MULTI_AGENT_RESULTS, index=False)
    print(f"Multi-agent extraction complete. "
          f"{len(results_df)} results saved to {MULTI_AGENT_RESULTS}")

    # Summary of final classifications.
    if not results_df.empty and "judge_generator_agent" in results_df.columns:
        classifications = results_df["judge_generator_agent"].apply(
            lambda x: x.get("final_classification", "unknown")
            if isinstance(x, dict) else "unknown"
        )
        print("\nFinal classification distribution:")
        for cls, cnt in classifications.value_counts().items():
            print(f"  {cls}: {cnt}")


# ── Agent detail CSV ──────────────────────────────────────────────────────────

TYPE_AGENTS = [
    "collaboration_people_focused_agent",
    "customer_oriented_agent",
    "innovation_adaptability_agent",
    "integrity_risk_management_agent",
    "performance_oriented_agent",
    "miscellaneous_agent",
]


def _join(val) -> str:
    """Flatten a list or scalar to a semicolon-separated string."""
    if isinstance(val, list):
        return " ; ".join(str(v) for v in val)
    return "" if val is None else str(val)


def save_agent_detail_csv(results_df: pd.DataFrame) -> None:
    """Write a flat CSV with every agent's full response for each input.

    One row per input_id. Columns are prefixed by agent name so each agent's
    output fields are grouped together and easy to filter in a spreadsheet.

    Type agents (1–6) columns: reasons_for, reasons_against, should_assign, confidence.
    Tone agent columns: tone, tone_supporting_evidence, tone_counter_evidence,
        tone_confidence, tone_rationale.
    Causal agent columns: has_explicit_causal_analysis, causal_supporting_evidence,
        causal_counter_evidence, raw_cause_phrases, raw_effect_phrases,
        raw_causal_triples, causal_confidence, causal_rationale.
    Verifier agent columns: type_supported, tone_supported, causality_supported,
        unsupported_claims, evidence_gaps, overall_faithfulness, verifier_rationale.
    Judge agent columns: all final output fields.
    """
    if results_df.empty:
        print("No results to save for agent detail CSV.")
        return

    rows = []
    for record in results_df.to_dict(orient="records"):
        row: dict = {"input_id": record.get("input_id", "")}

        # ── Type agents 1–6 ──
        for agent_key in TYPE_AGENTS:
            agent = record.get(agent_key, {})
            if not isinstance(agent, dict):
                agent = {}
            prefix = agent_key
            row[f"{prefix}__reasons_for"]     = _join(agent.get("reasons_for", []))
            row[f"{prefix}__reasons_against"] = _join(agent.get("reasons_against", []))
            row[f"{prefix}__should_assign"]   = agent.get("should_assign", "")
            row[f"{prefix}__confidence"]      = agent.get("confidence", "")

        # ── Tone agent ──
        tone = record.get("tone_agent", {})
        if not isinstance(tone, dict):
            tone = {}
        row["tone_agent__tone"]                     = tone.get("tone", "")
        row["tone_agent__tone_supporting_evidence"]  = _join(tone.get("tone_supporting_evidence", []))
        row["tone_agent__tone_counter_evidence"]     = _join(tone.get("tone_counter_evidence", []))
        row["tone_agent__tone_confidence"]           = tone.get("tone_confidence", "")
        row["tone_agent__tone_rationale"]            = tone.get("tone_rationale", "")

        # ── Causal structure agent ──
        causal = record.get("causal_structure_agent", {})
        if not isinstance(causal, dict):
            causal = {}
        row["causal_structure_agent__has_explicit_causal_analysis"] = causal.get("has_explicit_causal_analysis", "")
        row["causal_structure_agent__causal_supporting_evidence"]   = _join(causal.get("causal_supporting_evidence", []))
        row["causal_structure_agent__causal_counter_evidence"]      = _join(causal.get("causal_counter_evidence", []))
        row["causal_structure_agent__raw_cause_phrases"]            = _join(causal.get("raw_cause_phrases", []))
        row["causal_structure_agent__raw_effect_phrases"]           = _join(causal.get("raw_effect_phrases", []))
        row["causal_structure_agent__raw_causal_triples"]           = _join(causal.get("raw_causal_triples", []))
        row["causal_structure_agent__causal_confidence"]            = causal.get("causal_confidence", "")
        row["causal_structure_agent__causal_rationale"]             = causal.get("causal_rationale", "")

        # ── Evidence verifier agent ──
        verifier = record.get("evidence_verifier_agent", {})
        if not isinstance(verifier, dict):
            verifier = {}
        row["evidence_verifier_agent__type_supported"]       = verifier.get("type_supported", "")
        row["evidence_verifier_agent__tone_supported"]       = verifier.get("tone_supported", "")
        row["evidence_verifier_agent__causality_supported"]  = verifier.get("causality_supported", "")
        row["evidence_verifier_agent__unsupported_claims"]   = _join(verifier.get("unsupported_claims", []))
        row["evidence_verifier_agent__evidence_gaps"]        = _join(verifier.get("evidence_gaps", []))
        row["evidence_verifier_agent__overall_faithfulness"] = verifier.get("overall_faithfulness", "")
        row["evidence_verifier_agent__verifier_rationale"]   = verifier.get("verifier_rationale", "")

        # ── Judge / Generator agent ──
        judge = record.get("judge_generator_agent", {})
        if not isinstance(judge, dict):
            judge = {}
        row["judge_generator_agent__final_classification"]         = judge.get("final_classification", "")
        row["judge_generator_agent__identified_corporate_culture"] = judge.get("identified_corporate_culture", "")
        row["judge_generator_agent__culture_type"]                 = judge.get("culture_type", "")
        row["judge_generator_agent__tone"]                         = judge.get("tone", "")
        row["judge_generator_agent__has_explicit_causal_analysis"] = judge.get("has_explicit_causal_analysis", "")
        row["judge_generator_agent__raw_cause_phrases"]            = _join(judge.get("raw_cause_phrases", []))
        row["judge_generator_agent__raw_effect_phrases"]           = _join(judge.get("raw_effect_phrases", []))
        row["judge_generator_agent__raw_causal_triples"]           = _join(judge.get("raw_causal_triples", []))
        row["judge_generator_agent__evidence_summary"]             = _join(judge.get("evidence_summary", []))
        row["judge_generator_agent__uncertainty_flag"]             = judge.get("uncertainty_flag", "")
        row["judge_generator_agent__final_rationale"]              = judge.get("final_rationale", "")

        rows.append(row)

    detail_df = pd.DataFrame(rows)
    detail_df.to_csv(AGENT_DETAIL_CSV, index=False)
    print(f"Agent detail CSV saved to {AGENT_DETAIL_CSV} ({len(detail_df)} rows, {len(detail_df.columns)} columns)")


# ── Combine results ────────────────────────────────────────────────────────────

def combine_extraction_results() -> None:
    """Extract final fields from judge_generator_agent and write combined CSV.

    Reads from MULTI_AGENT_DB (preferred) or MULTI_AGENT_RESULTS CSV.
    Filters NoCulture rows, maps nested agent output to flat columns compatible
    with normalize_culture_multi.py, and saves to COMBINED_RESULTS.

    Column mapping (multi-agent → downstream):
        judge_generator_agent.culture_type            → type
        judge_generator_agent.tone                    → tone
        judge_generator_agent.has_explicit_causal_analysis → reason ("YES"/"NO")
        judge_generator_agent.raw_cause_phrases       → causes
        judge_generator_agent.raw_effect_phrases      → outcomes
        judge_generator_agent.raw_causal_triples      → causal_rels
        judge_generator_agent.evidence_summary        → evidence_summary (new)
        judge_generator_agent.uncertainty_flag        → uncertainty_flag (new)
    """
    print("=== Combining Multi-Agent Extraction Results ===")

    if MULTI_AGENT_DB.exists():
        results_df = retrieve_multi_agent_results(MULTI_AGENT_DB)
    elif MULTI_AGENT_RESULTS.exists():
        results_df = pd.read_csv(MULTI_AGENT_RESULTS)
        # judge_generator_agent column is a string when loaded from CSV.
        import ast
        results_df["judge_generator_agent"] = results_df[
            "judge_generator_agent"
        ].apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x)
    else:
        print("No multi-agent results found. Run run_multi_agent_extraction first.")
        return

    if results_df.empty:
        print("No results to combine.")
        return

    def extract_judge_fields(row: dict) -> dict:
        judge = row.get("judge_generator_agent", {}) if isinstance(row, dict) else {}
        if not isinstance(judge, dict):
            judge = {}
        return {
            "final_classification":       judge.get("final_classification", "NoCulture"),
            "raw_type":                   judge.get("identified_corporate_culture", ""),
            "type":                       judge.get("culture_type", ""),
            "tone":                       judge.get("tone", ""),
            "reason":                     "YES" if judge.get("has_explicit_causal_analysis", False) else "NO",
            "causes":                     judge.get("raw_cause_phrases", []),
            "outcomes":                   judge.get("raw_effect_phrases", []),
            "causal_rels":                judge.get("raw_causal_triples", []),
            "evidence_summary":           judge.get("evidence_summary", []),
            "uncertainty_flag":           judge.get("uncertainty_flag", False),
            "final_rationale":            judge.get("final_rationale", ""),
        }

    judge_rows = results_df.to_dict(orient="records")
    judge_df   = pd.DataFrame([extract_judge_fields(r) for r in judge_rows])
    combined_df = pd.concat(
        [results_df[["input_id"]].reset_index(drop=True), judge_df], axis=1
    )

    # call_comp_id alias for compatibility with normalize_culture_multi.py.
    combined_df["call_comp_id"] = combined_df["input_id"]
    combined_df["rag_round"]    = 0

    # Filter NoCulture.
    no_culture_count = (combined_df["final_classification"] == "NoCulture").sum()
    print(f"NoCulture components (filtered out): {no_culture_count}")
    combined_df = combined_df[
        combined_df["final_classification"] != "NoCulture"
    ].copy()
    combined_df.drop(columns=["final_classification"], inplace=True)

    # Parse call_id and component_ids from input_id (e.g. "AAPL_20260129_5,8,12").
    # rsplit on the last "_" so ticker+date stays intact as call_id.
    combined_df[["call_id", "component_ids"]] = combined_df["input_id"].str.rsplit(
        "_", n=1, expand=True
    )
    combined_df["first_component_id"] = (
        combined_df["component_ids"].str.split(",").str[0].astype(int)
    )

    combined_df.to_csv(COMBINED_RESULTS, index=False)
    print(f"Final results: {len(combined_df)} culture components")
    print(f"Saved to {COMBINED_RESULTS}")

    if "type" in combined_df.columns:
        print("\nCulture type distribution:")
        for ctype, cnt in combined_df["type"].value_counts().items():
            print(f"  {ctype}: {cnt}")

    # Save full per-agent detail CSV (all 10 agents, all inputs including NoCulture).
    save_agent_detail_csv(results_df)


# ── Full pipeline ──────────────────────────────────────────────────────────────

def run_extraction_pipeline(sample_size: int = None) -> None:
    """Run the complete multi-agent extraction pipeline."""
    print("=== Multi-Agent Culture Extraction Pipeline ===")
    run_multi_agent_extraction(sample_size=sample_size)
    combine_extraction_results()
    print("=== Extraction Pipeline Complete ===")


if __name__ == "__main__":
    fire.Fire()
