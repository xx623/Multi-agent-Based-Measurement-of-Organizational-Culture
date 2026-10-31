# Prompts

| Folder | Content | Used by |
|---|---|---|
| `current/` | The prompts of Technical Appendix Section B: `reader.txt` (B.1), `evidence_skeptic.txt` (B.2), `expertise_agent.txt` (B.3 template with `{CATEGORY}`, `{DEFINITION}`, `{INDICATORS}`, `{NON_QUALIFYING}`), `judge.txt` (B.4), `interpretive_critic.txt` (B.5), `adjudicator.txt` (B.6), plus `reader_selfcheck.txt`, the generic self-check instruction the Reader receives in control arm C. Each file carries the appendix text verbatim, followed by an INPUT block with `{{placeholders}}` and an OUTPUT FORMAT block that the controller fills with the schema skeleton. | The five-role prototype (`pipeline/controller.py`); `expertise_agent.txt` only with `--with-experts` |
| `earlier/appendix_draft_2026-10-29/` | The B.1–B.6 drafts of the appendix version of 29 October 2026, kept for comparison. They used a single `scope` string, no `direction`, `origin` or `content_type`, and no `source_states`. | Not run |
| `earlier/eleven_agent_pack_2026-10-29/` | The eleven-template pack built before the prototype: six legacy category specialists (byte-identical to the May 2026 pilot, hashes in `preservation_checks.json`), Reader, Evidence skeptic, Judge, Interpretive critic and Adjudicator templates with a twelve-cell (type by channel) output design, routing schedule and input adapter. | Not run; superseded by `current/` |
| `../legacy_pilot/multi_agent_prompt_calls.txt` | The single prompt that simulated ten agents in the May 2026 predecessor pilot. | Legacy pilot only |

The codebook (`../codebook.json`) holds the six category definitions, indicator and
non-qualifying lists (Table B2), controlled vocabularies and coding rules; the controller
passes it to the Judge, critic and adjudicator and instantiates the expertise template
from it.
