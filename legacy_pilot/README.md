# Predecessor pilot (May 2026): category-specialist prompts on raw transcript components

This folder documents the pilot that preceded the current design. It is kept for
provenance and audit. All ten "agents" were simulated sequentially inside a single model
call with full access to the raw transcript component, so nothing in it tests information
boundaries or targeted challenge. Its outputs exposed the failure modes the current design
targets, which is why it is cited in Section 5 of the proposal and Section H.4 of the
technical appendix.

## What was run

| Item | Value |
|---|---|
| Date | 4 May 2026 |
| Model | `gemini-2.5-flash-lite` (hosted) through the OpenAI-compatible endpoint, temperature 0, `response_format = json_object` |
| Prompt | `multi_agent_prompt_calls.txt` (ten roles: six type specialists, tone, causal structure, evidence verifier, judge) |
| Unit of analysis | one call per model call; all screened executive components of a call concatenated |
| Corpus | 33 licensed earnings-call transcripts of calls held 29–30 January 2026 (not redistributed) |
| Screening | 1,560 speaker turns parsed, 776 executive non-boilerplate; keyword + word-sense seed 11; BERT classifier top-probability 34; LLM relevance filter kept 28 components in 17 calls |
| Inputs | 17 call-level inputs sent; 16 returned parseable JSON; 1 reply truncated mid-JSON |
| Logging | outputs only; tokens, latency and cost were not logged |

## Files in this folder

| File | Content |
|---|---|
| `multi_agent_prompt_calls.txt` | the single prompt simulating ten agents |
| `pilot_summary.md`, `pilot_summary.json` | the descriptive figures quoted in the proposal (Section 5) and the technical appendix (Section H.4) |
| `extract_culture_multi.py`, `config_multi.py` | the extraction script and configuration used (API key read from the environment; none stored) |
| `sankey_legacy_pilot_top3.png` | legacy visualisation of judge types, causes and effects (normalized category labels only) |
| `summarise_pilot.py` | recomputes the summary from the per-call outputs listed below |

## Withheld per-call outputs

The pilot ran on unmasked licensed transcripts, and its per-call outputs quote them at
length: the agents' reasons, evidence summaries and causal triples contain 737 text spans
longer than 25 words, the longest 95 words, and identify the 16 firms by ticker. The
transcript licence and the release rule of Technical Appendix F (source text only as
verified excerpts of at most 25 words) do not allow publishing them, so these three files
are withheld. The authors keep them and can share them with the editors under the
provider's terms; the fingerprints below let anyone who receives them check that they are
the files behind `pilot_summary.json`.

| Withheld file | Content | SHA-256 |
|---|---|---|
| `all_agent_responses.csv` | every agent's fields for the 16 parsed inputs | `584032781fd8b9977ad0d4e1b9ac8d8c41a478ebcec91b3b0fc0643b7c844878` |
| `combined_extraction_results_multi.csv` | judge fields only, in the downstream format of the legacy pipeline | `1b7db3be912d784bc453af3c10a123b3698050aa1fedfd6e1a924de3d062f9c3` |
| `multi_agent_extraction.db` | SQLite log of the 17 raw model replies, including the truncated one | `4580b87ea878455d9579781f30d18d8a7a320dccf2c2378582bf9e3ddf52d495` |

Placing `all_agent_responses.csv` in this folder and running `python summarise_pilot.py`
regenerates `pilot_summary.json` and `pilot_summary.md`.

`extract_culture_multi.py` imports `gpt_funcs` and database helpers from the earnings-call
adaptation of the replication kit of Li, Mai, Shen, Yang and Zhang (2026), *Review of
Financial Studies* 39(1), Harvard Dataverse doi:10.7910/DVN/SGHZJ8, released under CC0
1.0. Those helpers and the screening stages are not reproduced here; the script is kept so
that the exact prompt filling and output flattening can be audited.

## The failure modes the outputs exposed

* **Labels inferred from reported outcomes rather than conduct.** The judge's evidence
  summaries cited results, such as the share of sales coming from new products or a strong
  year for product development, as grounds for a culture label; no field recorded whether
  any conduct, expectation or routine was reported. The current design codes reported
  normative content only, keeps episodes and outcomes apart from expectations, rules and
  routines, and makes the critic test every evidence-to-construct step.
* **Single labels where several expectations coexisted.** In 15 of 16 inputs two or more
  type specialists recommended assignment (Innovation in 15, Performance in 14), yet the
  judge returned one type per input and the tone agent returned "Positive" in all 16; the
  judge followed the highest-confidence recommendation in only 7 of 16. The current design
  returns claims, several per category and several categories per passage, with direction
  and structured scope instead of a single type and a tone.
* **A verifier that could not separate extraction from interpretation.** The evidence
  verifier rated 15 of 16 outputs "High" faithfulness by checking quotations against the
  same passage the other agents had read. The current design gives the source stage and
  the interpretation stage different information access and different critics.
