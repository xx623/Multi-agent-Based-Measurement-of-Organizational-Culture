# Demo inputs and recorded runs

`make demo` (or `python run_workflow.py demo`) runs the five-role pipeline on every passage
in `inputs/` with the pinned local model (`config/model_pins.json`) and writes new logs
under `runs/`. `make replay` re-runs the recorded constructed-passage run offline through
the controller and validators (no model needed).

## inputs/

| File | Source | Licence | Text status |
|---|---|---|---|
| `constructed_appendix_c.json` | The constructed passage of Technical Appendix C | synthetic | author-written; no real firm |
| `public_trak_2026q2_w001.json` | US SEC EDGAR, Form 8-K of ReposiTrak, Inc. (CIK 50471), accession 0001437749-26-004737, Exhibit 99.2 (earnings-call transcript, call of 2026-02-17) | public record | five consecutive sentences of the CEO's prepared remarks, verbatim |
| `public_trak_2026q2_w002.json` | same exhibit | public record | two consecutive Q&A exchanges, verbatim; the CFO's first name masked as `[PERSON_002]` |
| `public_trak_2026q2_w003.json` | same exhibit | public record | four verbatim sentences of the CFO's remarks on milestones since 2020, selected from one block; intervening sentences omitted (not contiguous) |
| `public_trak_2026q2_w004.json` | same exhibit | public record | six verbatim sentences of the CEO's remarks on supplier data accuracy, in original order, intervening sentences omitted (not contiguous) |
| `synthetic_transcript_lseg.txt`, `synthetic_mask_terms.json` | author-constructed transcript in LSEG StreetEvents layout | synthetic | input for `make windows-demo` (parsing, masking, windowing) |

Passage files are plain JSON: `passage_id`, `group_key`, `license`, a `source_window` with
numbered sentence units (`sid`, `speaker_role`, `window_role` focus/context, `text`) and a
`provenance` block that is never passed to any prompt. To run the pipeline on a complete
public transcript, save the exhibit as text, then
`python run_workflow.py windows --transcript <file> --out-dir work/<name> --license public`
and `python run_workflow.py run --input work/<name>/windows`.

Masking policy for the public passages: names of the firm, people, products and
counterparties are replaced by typed placeholders; regulators and generic acronyms (FDA,
EDI, SaaS, GAAP) are kept. The SEC exhibit states that the transcript was prepared by a
transcription vendor and may contain errors.

## recorded/

`DEMO-C_001/`: the complete recorded run of the constructed passage with the pinned model
(prompts, raw replies, parsed outputs, interpretation view, final measurement and process
records). It is the input of `make replay` and of the verification step in
`tools/make_manifest.py`. The same run is part of the pilot batch in `logs/`.
