"""JSON Schema (draft 2020-12) for every object in Technical Appendix B.7, generated from
the codebook vocabularies so that prompts, validators and schema files cannot drift,
plus the compact skeletons rendered into the prompts' OUTPUT FORMAT blocks.

Objects: record (Reader R1/R2), critique (Evidence skeptic), record_interp (the
interpretation view built by ``views.py``), assessment (expertise agents), judgment
(Judge J1/J2), interpretive_critique (critic C1/C2), measurement and process (the two
adjudicator records, returned together as ``adjudication``).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFT = "https://json-schema.org/draft/2020-12/schema"

VIEW_ITEM_FIELDS = ["id", "actor", "conduct", "timing", "status", "content_type", "direction",
                    "origin", "scope", "qualifications", "excerpt"]


def load_codebook(root: Path = ROOT) -> dict:
    return json.loads((root / "codebook.json").read_text(encoding="utf-8"))


def category_names(codebook: dict) -> list[str]:
    return [c["name"] for c in codebook["categories"]]


def _obj(props: dict, required, extra: bool = False) -> dict:
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": extra}


def _str(nonblank: bool = True) -> dict:
    return {"type": "string", "minLength": 1} if nonblank else {"type": "string"}


def _arr(items: dict, min_items: int = 0) -> dict:
    return {"type": "array", "items": items, "minItems": min_items}


def _enum(values) -> dict:
    return {"type": "string", "enum": list(values)}


def _ids() -> dict:
    return _arr(_str())


def scope_schema(v: dict) -> dict:
    return _obj({"type": _enum(v["scope_type"]), "target": _str(), "extent": _enum(v["scope_extent"])},
                ["type", "target", "extent"])


def item_schema(v: dict, *, with_sentence: bool, with_span: bool) -> dict:
    props = {"id": _str(), "actor": _str(), "conduct": _str(), "timing": _str(), "status": _enum(v["status"]),
             "content_type": _enum(v["content_type"]), "direction": _enum(v["direction"]),
             "origin": _enum(v["origin"]), "scope": scope_schema(v), "qualifications": _arr(_str()),
             "excerpt": _str()}
    required = list(props)
    if with_sentence:
        props["excerpt_sentence"] = _str()
        required.append("excerpt_sentence")
    if with_span:
        props["excerpt_span"] = _obj({"sentence": _str(), "start": {"type": "integer"}, "end": {"type": "integer"}},
                                     ["sentence", "start", "end"])
    return _obj(props, required)


def record_schema(v: dict) -> dict:
    declaration = _obj({"id": _str(), "text": _str(), "sentence": _str()}, ["id", "text", "sentence"])
    flag = _obj({"flag_id": _str(), "type": _enum(v["flag_types"]), "target_item": _str(),
                 "source_states": _enum(v["source_states"]), "note": _str()},
                ["flag_id", "type", "target_item", "source_states", "note"])
    response = _obj({"flag_id": _str(), "action": _enum(v["flag_response_actions"]),
                     "source_states": _enum(v["source_states"]), "reason": _str()},
                    ["flag_id", "action", "source_states", "reason"])
    body = _obj({"passage_id": _str(), "items": _arr(item_schema(v, with_sentence=True, with_span=True)),
                 "declarations": _arr(declaration), "unresolved_flags": _arr(flag),
                 "flag_responses": _arr(response), "removed_item_ids": _ids()},
                ["passage_id", "items", "declarations", "unresolved_flags", "flag_responses", "removed_item_ids"])
    return {"$schema": DRAFT, "$id": "record.schema.json", "title": "Reader record (R1, R2)", **body}


def critique_schema(v: dict) -> dict:
    flag = _obj({"id": _str(), "type": _enum(v["flag_types"]), "target_item": _str(), "sentences": _arr(_str(), 1),
                 "question": _str()}, ["id", "type", "target_item", "sentences", "question"])
    body = _obj({"passage_id": _str(), "flags": _arr(flag), "complete_and_supported": {"type": "boolean"}},
                ["passage_id", "flags", "complete_and_supported"])
    return {"$schema": DRAFT, "$id": "critique.schema.json", "title": "Evidence skeptic critique (S1)", **body}


def record_interp_schema(v: dict) -> dict:
    unresolved = _obj({"type": _enum(v["flag_types"]), "evidence_ids": _ids(),
                       "source_states": _enum(v["source_states"]), "note": _str()},
                      ["type", "evidence_ids", "source_states", "note"])
    body = _obj({"passage_id": _str(), "items": _arr(item_schema(v, with_sentence=False, with_span=False)),
                 "unresolved": _arr(unresolved), "completeness_uncertain": {"type": "boolean"}},
                ["passage_id", "items", "unresolved", "completeness_uncertain"])
    return {"$schema": DRAFT, "$id": "record_interp.schema.json",
            "title": "Interpretation view (derived; no declarations, spans or passage text)", **body}


def assessment_schema(v: dict, categories: list[str]) -> dict:
    entry = _obj({"evidence_ids": _ids(), "relevance": _enum(v["relevance"]), "direction": _enum(v["direction"]),
                  "origin": _enum(v["origin"]), "scope": scope_schema(v), "reasons_for": _arr(_str()),
                  "reasons_against": _arr(_str()), "unresolved": _arr(_str())},
                 ["evidence_ids", "relevance", "direction", "origin", "scope", "reasons_for", "reasons_against",
                  "unresolved"])
    body = _obj({"passage_id": _str(), "category": _enum(categories), "entries": _arr(entry)},
                ["passage_id", "category", "entries"])
    return {"$schema": DRAFT, "$id": "assessment.schema.json", "title": "Expertise agent assessment (T1-T6)", **body}


def judgment_schema(v: dict, categories: list[str]) -> dict:
    claim = _obj({"id": _str(), "category": _enum(categories), "status": _enum(v["claim_status"]),
                  "evidence_ids": _ids(), "conduct": _str(), "content_type": _enum(v["content_type"]),
                  "direction": _enum(v["direction"]), "origin": _enum(v["origin"]), "scope": scope_schema(v),
                  "conduct_status": _enum(v["status"]), "generalized_from_event": {"type": "boolean"}},
                 ["id", "category", "status", "evidence_ids", "conduct", "content_type", "direction", "origin",
                  "scope", "conduct_status", "generalized_from_event"])
    response = _obj({"objection_id": _str(), "action": _enum(v["objection_response_actions"]),
                     "evidence_ids": _ids(), "reason": _str()}, ["objection_id", "action", "evidence_ids", "reason"])
    body = _obj({"passage_id": _str(), "round": {"type": "integer", "enum": [1, 2]}, "claims": _arr(claim),
                 "completeness_uncertain_affects": _ids(), "strongest_objection": _str(),
                 "objection_responses": _arr(response)},
                ["passage_id", "round", "claims", "completeness_uncertain_affects", "strongest_objection",
                 "objection_responses"])
    return {"$schema": DRAFT, "$id": "judgment.schema.json", "title": "Judge claims (J1, J2)", **body}


def interpretive_critique_schema(v: dict) -> dict:
    objection = _obj({"id": _str(), "claim_ref": _str(), "criterion": _enum(sorted(v["critic_criteria"])),
                      "evidence_ids": _ids(), "reason": _str(), "narrowest_claim": _str()},
                     ["id", "claim_ref", "criterion", "evidence_ids", "reason", "narrowest_claim"])
    accepted = _obj({"claim_ref": _str(), "reason": _str()}, ["claim_ref", "reason"])
    body = _obj({"passage_id": _str(), "round": {"type": "integer", "enum": [1, 2]}, "objections": _arr(objection),
                 "accepted_claims": _arr(accepted), "resolved_objection_ids": _ids()},
                ["passage_id", "round", "objections", "accepted_claims", "resolved_objection_ids"])
    return {"$schema": DRAFT, "$id": "interpretive_critique.schema.json",
            "title": "Interpretive critic challenge / reassessment (C1, C2)", **body}


def measurement_schema(v: dict, categories: list[str]) -> dict:
    limitation = _obj({"text": _str(), "kind": _enum(v["limitation_kinds"])}, ["text", "kind"])
    claim = _obj({"claim_ref": _str(), "relevance": _enum(v["relevance"]), "conduct": _str(),
                  "content_type": _enum(v["content_type"]), "direction": _enum(v["direction"]),
                  "origin": _enum(v["origin"]), "scope": scope_schema(v), "conduct_status": _enum(v["status"]),
                  "evidence_for": _ids(), "evidence_against": _ids(), "limitations": _arr(limitation)},
                 ["claim_ref", "relevance", "conduct", "content_type", "direction", "origin", "scope",
                  "conduct_status", "evidence_for", "evidence_against", "limitations"])
    category = _obj({"relevance": _enum(v["relevance"]), "direction": _enum(v["category_direction"]),
                     "claims": _arr(claim)}, ["relevance", "direction", "claims"])
    cats = _obj({name: category for name in categories}, categories)
    body = _obj({"passage_id": _str(), "categories": cats}, ["passage_id", "categories"])
    return {"$schema": DRAFT, "$id": "measurement.schema.json", "title": "Final measurement record (A1)", **body}


def process_schema(v: dict) -> dict:
    action = _obj({"claim_ref": _str(), "action": _enum(v["adjudication_actions"])}, ["claim_ref", "action"])
    body = _obj({"passage_id": _str(), "actions": _arr(action), "unresolved_objections": _ids(),
                 "escalate_to_human": {"type": "boolean"}, "output_state": _enum(["valid", "abstained"]),
                 "abstention_reason": _str(False)},
                ["passage_id", "actions", "unresolved_objections", "escalate_to_human", "output_state"])
    return {"$schema": DRAFT, "$id": "process.schema.json", "title": "Adjudication process record (A1)", **body}


def adjudication_schema(v: dict, categories: list[str]) -> dict:
    m, p = measurement_schema(v, categories), process_schema(v)
    for s in (m, p):
        for k in ("$schema", "$id", "title"):
            s.pop(k, None)
    body = _obj({"passage_id": _str(), "measurement": m, "process": p}, ["passage_id", "measurement", "process"])
    return {"$schema": DRAFT, "$id": "adjudication.schema.json", "title": "Adjudicator reply (measurement + process)",
            **body}


def all_schemas(codebook: dict) -> dict[str, dict]:
    v, cats = codebook["vocabularies"], category_names(codebook)
    return {
        "record.schema.json": record_schema(v),
        "critique.schema.json": critique_schema(v),
        "record_interp.schema.json": record_interp_schema(v),
        "assessment.schema.json": assessment_schema(v, cats),
        "judgment.schema.json": judgment_schema(v, cats),
        "interpretive_critique.schema.json": interpretive_critique_schema(v),
        "measurement.schema.json": measurement_schema(v, cats),
        "process.schema.json": process_schema(v),
        "adjudication.schema.json": adjudication_schema(v, cats),
    }


def export(out_dir: Path, codebook: dict) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, schema in all_schemas(codebook).items():
        path = out_dir / name
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


# ── skeletons rendered into prompts ───────────────────────────────────────────

def _j(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def skeleton(name: str, codebook: dict) -> str:
    v = codebook["vocabularies"]
    cats = category_names(codebook)
    pipe = lambda key: " | ".join(v[key])  # noqa: E731
    scope = {"type": pipe("scope_type"), "target": "<unit, team or role named, verbatim or placeholder; Not stated>",
             "extent": pipe("scope_extent")}
    if name == "record":
        return _j({"passage_id": "<as given>",
                   "items": [{"id": "E1", "actor": "<placeholder or role>", "conduct": "<reported conduct>",
                              "timing": "<as stated or Not stated>", "status": pipe("status"),
                              "content_type": pipe("content_type"), "direction": pipe("direction"),
                              "origin": pipe("origin"), "scope": scope, "qualifications": ["<as stated>"],
                              "excerpt": "<verbatim, at most 25 words>", "excerpt_sentence": "S2"}],
                   "declarations": [{"id": "D1", "text": "<verbatim value statement>", "sentence": "S1"}],
                   "unresolved_flags": [{"flag_id": "F1", "type": pipe("flag_types"), "target_item": "E1 or none",
                                         "source_states": pipe("source_states"), "note": "<one line>"}],
                   "flag_responses": [{"flag_id": "F1", "action": pipe("flag_response_actions"),
                                       "source_states": pipe("source_states"), "reason": "<cite sentence IDs>"}],
                   "removed_item_ids": []})
    if name == "critique":
        return _j({"passage_id": "<as given>",
                   "flags": [{"id": "F1", "type": pipe("flag_types"), "target_item": "E1 or none",
                              "sentences": ["S2"], "question": "<one targeted question>"}],
                   "complete_and_supported": False})
    if name == "assessment":
        return _j({"passage_id": "<as given>", "category": "<category name>",
                   "entries": [{"evidence_ids": ["E2"], "relevance": pipe("relevance"), "direction": pipe("direction"),
                                "origin": pipe("origin"), "scope": scope, "reasons_for": ["E2: <one sentence>"],
                                "reasons_against": ["<one sentence or empty>"], "unresolved": ["<limit or empty>"]}]})
    if name == "judgment":
        return _j({"passage_id": "<as given>", "round": 1,
                   "claims": [{"id": "K1", "category": " | ".join(cats), "status": pipe("claim_status"),
                               "evidence_ids": ["E2"], "conduct": "<reported conduct>",
                               "content_type": pipe("content_type"), "direction": pipe("direction"),
                               "origin": pipe("origin"), "scope": scope, "conduct_status": pipe("status"),
                               "generalized_from_event": False}],
                   "completeness_uncertain_affects": [], "strongest_objection": "<one sentence>",
                   "objection_responses": [{"objection_id": "O1", "action": pipe("objection_response_actions"),
                                            "evidence_ids": ["E2"], "reason": "<one sentence>"}]})
    if name == "interpretive_critique":
        return _j({"passage_id": "<as given>", "round": 1,
                   "objections": [{"id": "O1", "claim_ref": "K1", "criterion": "a | b | c | d | e | f | g",
                                   "evidence_ids": ["E2"], "reason": "<precise gap>",
                                   "narrowest_claim": "<narrowest claim the view supports, or withhold>"}],
                   "accepted_claims": [{"claim_ref": "K2", "reason": "<why no objection is warranted>"}],
                   "resolved_objection_ids": []})
    if name == "adjudication":
        claim = {"claim_ref": "K1", "relevance": pipe("relevance"), "conduct": "<reported conduct>",
                 "content_type": pipe("content_type"), "direction": pipe("direction"), "origin": pipe("origin"),
                 "scope": scope, "conduct_status": pipe("status"), "evidence_for": ["E2"], "evidence_against": [],
                 "limitations": [{"text": "<limitation>", "kind": pipe("limitation_kinds")}]}
        categories = {cats[0]: {"relevance": pipe("relevance"), "direction": pipe("category_direction"),
                                "claims": [claim]}}
        for c in cats[1:]:
            categories[c] = {"relevance": "none", "direction": "none", "claims": []}
        return _j({"passage_id": "<as given>",
                   "measurement": {"passage_id": "<as given>", "categories": categories},
                   "process": {"passage_id": "<as given>",
                               "actions": [{"claim_ref": "K1", "action": pipe("adjudication_actions")}],
                               "unresolved_objections": [], "escalate_to_human": False,
                               "output_state": "valid | abstained", "abstention_reason": ""}})
    raise KeyError(name)
