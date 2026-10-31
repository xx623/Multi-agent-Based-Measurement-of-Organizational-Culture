# Multi-agent Based Measurement of Organizational Culture 

Research artifact for a Stage 1 proposal to the *Organization Science* special issue
**AI-Enabled Frontiers in Organizational Science**. Authors are anonymized for review;
the repository carries no author-identifying metadata in commits, paths or text.

**The instrument.** A measurement design that separates what an earnings-call passage
*reports* from what that report *warrants* about organizational culture, and gives each
question its own information access and its own critic. A Reader builds an evidence
record from a masked passage and an Evidence skeptic challenges it (source stage); a Judge
proposes claims from the interpretation view of that record and an Interpretive critic
challenges the step from evidence to construct over two rounds; an Adjudicator that sees
only the view and the four statements produces the final measurement record with
evidence, scope, direction and tagged limitations. Six category expertise agents sit
between view and Judge in the full design.

## Status at submission

| Component | Status |
|---|---|
| Five-role prototype (Reader, Evidence skeptic, Judge, Interpretive critic, Adjudicator) with the prompts of Technical Appendix B, JSON schemas and validators | **Implemented and run end to end** on masked passages with the pinned open-weight model; logs in `logs/` |
| Interpretation view constructor (`record_interp`, Appendix B.0) with leak checks on every interpretation input | Implemented, tested |
| Arm switches for the three budget-matched contrasts (A/B, C/D, E/F) with content-addressed caching of shared calls | Implemented; control arms exercised on the constructed passage (`logs/arms_*`) |
| Six expertise agents (Appendix B.3) | Implemented as an opt-in stage (`--with-experts`); exercised once on the constructed passage (`logs/experts_*`); not part of the pilot batch |
| Transcript parsing, masking (rule-based plus optional spaCy NER), passage windows with sentence IDs | Implemented, tested |
| Release-safe log redaction for licensed sources | Implemented, tested |
| Validation protocol: paired-edit templates, annotation guidelines and controlled vocabularies, preregistration draft, metrics and firm-level resampling code | Drafted and unit-tested (`validation/`) |
| Expert reference labels, the six-arm evaluation, comparators | Not started (Stage 2) |

All pilot figures are descriptive. No validity claim is made anywhere in this repository.

## Quick start

Python 3.10+; the core uses the standard library only. Live runs need `pip install "openai>=1.0"`
and an OpenAI-compatible server for the pinned model.

```bash
python -m unittest discover -s tests          # 41 tests: validators, boundary rule, view, windows, redaction, metrics, recorded replay
python run_workflow.py replay --recorded demo/recorded/DEMO-C_001   # offline replay of a recorded run
python run_workflow.py export-schemas         # regenerate schemas/ from the codebook
```

### Pinned model and the demo

The prototype runs on **Qwen2.5-14B-Instruct** (Apache-2.0), quantization Q4_K_M, served
by Ollama with a 20,480-token context. Name, Ollama tag, weights digest, runtime version
and decoding parameters are in `config/model_pins.json`; the served variant is built from
`config/Modelfile`. To reproduce the environment:

```bash
ollama pull qwen2.5:14b                                   # ~9 GB; compare the digest with config/model_pins.json
ollama show qwen2.5:14b --modelfile                       # prints the FROM sha256 digest
ollama create culture-qwen2.5-14b-20k -f config/Modelfile
make demo        # = python run_workflow.py demo : runs demo/inputs/ (constructed passage + 4 public passages),
                 #   writes new logs under runs/, prints flags, objections, actions, tokens and latency per passage
```

Any other OpenAI-compatible endpoint works with `--model` / `--base-url` or the
environment variables `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`. Expected runtime per
passage on one RTX 5080 (16 GB): see the pilot table below; on a hosted model it is
bounded by the eight sequential calls.

### Running your own passages

```bash
python run_workflow.py windows --transcript call.txt --out-dir work/call --ner spacy --license restricted
python run_workflow.py run --input work/call/windows --release-dir logs/my_batch
python run_workflow.py run --input work/call/windows --no-isolation          # control arm B
python run_workflow.py run --input work/call/windows --no-evidence-inquiry   # control arm C
python run_workflow.py run --input work/call/windows --no-interpretive-inquiry   # control arm E
python run_workflow.py run --input work/call/windows --with-experts          # fourteen-call full design
python run_workflow.py pilot-summary --runs runs/<batch>
```

`work/<call>/private/` receives the masking table; it must not be published.

## What the pilot did

Pilot batch: full design, five roles, pinned model, single run at fixed decoding. Descriptive only; Technical Appendix H, Table H1, reports the same rows.

| Quantity | Value |
|---|---|
| Passages processed | 17: 12 valid, 4 explicit abstentions, 1 invalid after the permitted retry |
| By source (valid / abstained / invalid) | constructed 1 / 0 / 0; public 3 / 1 / 0; licensed 8 / 3 / 1 |
| Reader's conduct items, initial and revised | 43 and 62 (16 passages) |
| Declarations in the ledger | 11 |
| Skeptic flags | 52 in 16 of 16 passages: omitted qualifier 31, missing item 20, ignored counterevidence 1 |
| Reader responses to flags | item added 21, defended 19, amended 12 |
| Unresolved source objections in the view | 36; completeness uncertain in 6 of 16 passages |
| Judge claims, round 1 | 28: supported 5, partially supported 2, insufficient evidence 21 |
| Critic objections, round 1 | 23: episode generalized to a norm 15, alternative reading 7, culture inferred from a formal rule 1; 5 claims accepted without objection |
| Judge responses to objections, round 2 | objection accepted 18, claim narrowed 3, claim defended 2 |
| Judge claims, round 2 | 12: supported 4, partially supported 2, insufficient evidence 6; no claim left in 9 passages |
| Critic objections, round 2 | 22; 1 round-1 objection resolved |
| Adjudication of round-2 claims | accepted 1, narrowed 2, withheld 9 (6 of the withheld already marked insufficient evidence by the Judge) |
| Claims in the final measurement records | 3 in 3 passages: performance-oriented, strong, required routine (2); collaboration and people-focused, weak, required routine (1) |
| Limitations on retained claims | source-inherent 2, resolvable 1 |
| Passages escalated to human review | 6 of 16 |
| Boundary checks on interpretation calls; violations | 80; 0 |
| Calls needing the one permitted retry | 43 of 129: adjudicator 13, critic round 2 9, Judge round 1 8, Reader (revision) 7, Reader (initial) 4, Judge round 2 2 |
| Invalid passages | 1: licensed passage C096470cf42:w003, Reader (initial): excerpt over the 25-word limit after the retry |
| Tokens per completed passage, mean | 36,841 input and 4,304 output with retries (27,042 and 3,028 without); local inference, no marginal price |
| Model time per completed passage | mean 63.0 s, median 61.1 s, retries included |

| Additional runs on the constructed passage | Outcome |
|---|---|
| control arm `--no-evidence-inquiry` (arm ACF) | valid; adjudication {'narrow': 1}; retained claims 1 |
| control arm `--no-interpretive-inquiry` (arm ADE) | valid; adjudication {'narrow': 1}; retained claims 1 |
| control arm `--no-isolation` (arm BDF) | valid; adjudication {'narrow': 1}; retained claims 1 |
| expertise extension (`--with-experts`, fourteen calls) | abstained; adjudication {'withhold': 5}; retained claims 0 |

Full tables: `logs/pilot_2026-10-31_qwen2.5-14b/pilot_summary.md`, `cost_log.csv`,
`profile.csv`; control arms in `logs/arms_2026-10-31_qwen2.5-14b/`; the expertise
extension in `logs/experts_2026-10-31_qwen2.5-14b/`. See `logs/README.md` for the
redaction applied to passages from licensed transcripts.

## The workflow (Appendix B)

```
masked window ─► R1 Reader ─► S1 Evidence skeptic ─► R2 Reader (one revision)        source stage
                                      │
                           record_interp = views.build_view(R2)   ← drops passage, declaration ledger, spans;
                                      │                              keeps items, excerpts, sanitized unresolved flags
                           [T1..T6 expertise agents, --with-experts]
                                      ▼
   J1 Judge ─► C1 Critic ─► J2 Judge ─► C2 Critic ─► A1 Adjudicator ─► measurement + process records   interpretation stage
```

| Role (prompt) | Sees | Does not see |
|---|---|---|
| Reader (`prompts/current/reader.txt`) | masked window with sentence IDs; in revision also R1 and the critique (arm D) or the self-check instruction (arm C) | codebook, culture labels |
| Evidence skeptic (`evidence_skeptic.txt`) | window, R1 | codebook, downstream outputs |
| Expertise agents (`expertise_agent.txt`) | interpretation view, one category definition | passage, ledger, each other |
| Judge (`judge.txt`) | view, codebook, assessments (or null in the five-role run); in arm B also the window | passage, ledger, identifiers |
| Interpretive critic (`interpretive_critic.txt`) | view, codebook, Judge claims; in round 2 its own C1 | passage, ledger |
| Adjudicator (`adjudicator.txt`) | view, codebook, J1, C1, J2, C2 | passage, identifiers, outcomes |

What the code enforces independently of the prompts (`pipeline/validate.py`, `pipeline/views.py`):

* every excerpt, declaration and skeptic quote is verbatim in the cited sentence (exact
  matching after whitespace and typographic normalization) and at most 25 words; the
  controller adds character spans to the record;
* the view is built by a whitelist, flag notes that reproduce passage text outside the
  excerpts are replaced by generic notes, and every interpretation-stage input is scanned
  for declaration text, span fields and passage n-grams before the call (a violation
  aborts the passage; arm B's deliberate exposure is logged as such);
* MISSING_ITEM flags target `none`, other flags target existing items; the Reader's reply
  answers every flag and carries absent/unclear information into `unresolved_flags`;
* claims cite view evidence, copy direction, origin and scope from the cited items and
  never widen them; episode-only claims must declare `generalized_from_event`; planned
  conduct cannot support an ongoing claim;
* the critic covers every supported claim; the adjudicator acts on every Judge claim,
  only narrows, keeps withheld claims out of the measurement record, accounts for
  objections, keeps category relevance and direction consistent with their claims and
  must escalate when a RESOLVABLE or UNDETERMINED limitation remains or completeness is
  uncertain;
* an output that fails validation is returned once with the error list; a second failure
  ends the passage with `output_state = invalid`.

## Repository map

```
README.md                  this file
codebook.json              six categories (Li et al. 2026 taxonomy, adapted), vocabularies, coding rules, provenance
config/model_pins.json     pinned model (tag, digest, runtime, context, decoding); config/Modelfile builds the served variant
prompts/current/           Appendix B prompts + arm-C self-check; prompts/earlier/ earlier drafts and the eleven-agent pack
schemas/                   JSON Schema for record, critique, record_interp, assessment, judgment, interpretive_critique,
                           measurement, process, adjudication (generated by pipeline/schemas.py)
pipeline/                  controller.py (eight or fourteen calls, arm switches, logging, retry), validate.py, views.py,
                           schemas.py, llm_client.py, windows.py, redact.py, costs.py, aggregate.py
run_workflow.py            CLI: demo | run | replay | windows | pilot-summary | redact | export-schemas
demo/inputs/               constructed passage (Appendix C), four public SEC-filed passages, synthetic LSEG transcript
demo/recorded/             recorded run of the constructed passage (offline replay)
logs/                      release copies of the pilot batches (see logs/README.md)
legacy_pilot/              May 2026 predecessor pilot (ten agents in one prompt): prompt, summary, scripts; per-call outputs withheld
validation/                paired_edit_templates.json, annotation_guidelines.md, controlled_vocabularies.json,
                           preregistration_draft.md, metrics.py, resampling.py
tests/                     38 unit tests (NER test needs the optional spaCy model)
tools/make_manifest.py     regenerates manifest.json (file hashes) and verification.json/.txt (software checks)
docs/                      workflow figure; the technical appendix (PDF)
```

## Data and reproducibility

* No licensed transcript text is redistributed. The twelve restricted pilot passages come
  from three LSEG StreetEvents transcripts (calls of 30 January 2026) and are released
  with the window redacted and only verified excerpts (at most 25 words each) visible.
* The four public passages are verbatim sentences from an earnings-call transcript filed
  with the SEC as an 8-K exhibit (ReposiTrak, Inc., accession 0001437749-26-004737,
  Exhibit 99.2); `demo/README.md` states which are contiguous.
* The constructed passage is the one in Technical Appendix C; the recorded run is real
  model output on that input, whereas the appendix's exchange is explanatory.
* Every call logs its template hash, rendered prompt, exact inputs, raw replies, parsed
  output, token counts and latency; decoding is temperature 0 with a fixed seed. Serving
  nondeterminism is not excluded; the preregistration plans three re-runs per arm.
* The legacy pilot (May 2026) used a hosted model and is kept for provenance only. Its per-call outputs
  quote the licensed transcripts at length and are withheld; `legacy_pilot/README.md` lists their fingerprints.

## Licence

Code and prompts: MIT (`LICENSE`). Legacy pipeline scripts in `legacy_pilot/` adapt the
replication kit of Li, Mai, Shen, Yang and Zhang (2026), Harvard Dataverse
doi:10.7910/DVN/SGHZJ8 (CC0 1.0), as noted there. Qwen2.5-14B-Instruct is used under the
Apache-2.0 licence.
