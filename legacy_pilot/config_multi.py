"""Configuration for information extraction pipeline (multi-agent version).

Key differences from config.py:
- Adds MULTI_AGENT_PROMPT pointing to multi_agent_prompt_calls.txt.
- Adds MULTI_AGENT_RESULTS and MULTI_AGENT_DB for per-component output storage.
- COMBINED_RESULTS and FINAL_RESULTS_DIR use _multi / _Multi suffixes to avoid
  collisions with the round1 pipeline outputs.
- RAG (Round 2) remains absent; all other settings are unchanged.
"""

import os
from pathlib import Path

# ── Input paths ────────────────────────────────────────────────────────────────
CULTURE_SEGMENTS_PATH = Path(
    "../../data/processed/culture_segments/all_culture_segments.csv"
)

# ── Output paths ───────────────────────────────────────────────────────────────
OUTPUT_DIR = Path("../../data/processed/culture_extraction")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Round-1 paths kept for reference; not written by the multi-agent pipeline.
ROUND1_RESULTS = OUTPUT_DIR / "round1_results.csv"

# Multi-agent specific output paths.
MULTI_AGENT_DB      = OUTPUT_DIR / "multi_agent_extraction.db"
MULTI_AGENT_RESULTS = OUTPUT_DIR / "multi_agent_results.csv"
COMBINED_RESULTS    = OUTPUT_DIR / "combined_extraction_results_multi.csv"
AGENT_DETAIL_CSV    = OUTPUT_DIR / "all_agent_responses.csv"

FINAL_RESULTS_DIR = OUTPUT_DIR / "Normalized_Results_Multi"
Path(FINAL_RESULTS_DIR).mkdir(parents=True, exist_ok=True)

# ── Prompt paths ───────────────────────────────────────────────────────────────
PROMPTS_DIR = Path(__file__).parent / "prompts"
ROUND1_PROMPT      = PROMPTS_DIR / "round1_prompt.txt"
MULTI_AGENT_PROMPT = PROMPTS_DIR / "multi_agent_prompt_calls.txt"
NORMALIZATION_DIR  = PROMPTS_DIR / "normalization"

# ── GPT model configuration (identical to original) ───────────────────────────
GPT_MODEL    = "gemini-2.5-flash-lite"
BASE_URL     = "https://generativelanguage.googleapis.com/v1beta/openai/"
API_KEY      = os.getenv("GEMINI_API_KEY")
MAX_WORKERS  = 20
CHUNK_SIZE   = 5   # kept for normalization sub-steps; extraction uses 1 per call
