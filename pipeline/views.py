"""Construct the interpretation-stage input view (Technical Appendix B.0).

``record_interp`` is derived from the revised Reader record by removing the passage, the
context window, the declaration ledger and the character spans of excerpts, and by
keeping (i) the conduct items with their fields and verified excerpt text and (ii) a
sanitized list of unresolved source objections: flag type, affected evidence IDs, a
one-line note with no passage text beyond the verified excerpts, the Reader's
``source_states`` marking, and a passage-level ``completeness_uncertain`` indicator that
is true whenever a MISSING_ITEM flag remains unresolved.

The restriction is enforced in the inputs: ``leak_report`` scans any object destined for
an interpretation call and reports declaration text, span fields or passage n-grams that
are not inside a verified quote (an excerpt, or another Reader field that is itself a
verbatim provenance-checked quote of at most 25 words).
"""
from __future__ import annotations

import json
from typing import Any

from .schemas import VIEW_ITEM_FIELDS
from .validate import excerpt_ngrams, grams, normalize_text, passage_ngrams, verified_quote_ngrams


def generic_note(flag_type: str, source_states: str) -> str:
    desc = {
        "UNSUPPORTED_CLAIM": "an item was flagged as going beyond the passage",
        "OMITTED_QUALIFIER": "a condition, hedge or scope limit may be missing from an item",
        "IGNORED_COUNTEREVIDENCE": "the window may contain a statement cutting against an item",
        "SCOPE_OR_STATUS_ERROR": "timing, status, scope, direction, origin or content type of an item was questioned",
        "WEAK_EXCERPT": "an excerpt may not support the item it is attached to",
        "MISSING_ITEM": "a reported conduct item may be missing from the record",
    }.get(flag_type, "a source objection remains")
    return f"{desc}; the Reader marked the information as {source_states} in the passage."


def sanitize_note(note: str, flag_type: str, source_states: str, passage: set, allowed: set) -> str:
    """Keep the Reader's one-line note unless it reproduces passage text outside the verified quotes."""
    note = " ".join(str(note or "").split())
    if not note:
        return generic_note(flag_type, source_states)
    if (grams(note) & passage) - allowed:
        return generic_note(flag_type, source_states)
    return note[:300]


def build_view(record: dict, window: dict) -> dict:
    passage = passage_ngrams(window)
    allowed = excerpt_ngrams(record)   # notes are held to the excerpt-only standard (B.0)
    ids = {it["id"] for it in record.get("items", [])}
    items = []
    for it in record.get("items", []):
        view_item = {k: it[k] for k in VIEW_ITEM_FIELDS}
        view_item["scope"] = {"type": it["scope"]["type"], "target": it["scope"]["target"],
                              "extent": it["scope"]["extent"]}
        items.append(view_item)
    unresolved = []
    for f in record.get("unresolved_flags", []):
        target = f.get("target_item")
        unresolved.append({
            "type": f["type"],
            "evidence_ids": [target] if target in ids else [],
            "source_states": f["source_states"],
            "note": sanitize_note(f.get("note", ""), f["type"], f["source_states"], passage, allowed),
        })
    return {
        "passage_id": record["passage_id"],
        "items": items,
        "unresolved": unresolved,
        "completeness_uncertain": any(u["type"] == "MISSING_ITEM" for u in unresolved),
    }


def _strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def leak_report(obj: Any, record: dict, window: dict) -> list[str]:
    """Return a list of boundary violations found in ``obj`` (empty when clean)."""
    problems = []
    text = json.dumps(obj, ensure_ascii=False)
    norm_text = normalize_text(text).lower()
    allowed = verified_quote_ngrams(record, window)
    passage = passage_ngrams(window)
    quoted = []
    for it in record.get("items", []):
        quoted.append(normalize_text(it.get("excerpt", "")).lower())
        for q in it.get("qualifications") or []:
            quoted.append(normalize_text(q).lower())
        for k in ("actor", "conduct", "timing"):
            quoted.append(normalize_text(it.get(k, "")).lower())
    for d in record.get("declarations", []):
        decl = normalize_text(d.get("text", "")).lower().strip(" .")
        inside_quote = any(decl and decl in q for q in quoted if q)
        if decl and decl in norm_text and not inside_quote:
            problems.append(f"declaration text present: {d['text'][:40]!r}")
    for key in ("excerpt_span", "excerpt_sentence", "declarations", "source_window", "flag_responses"):
        if f'"{key}"' in text:
            problems.append(f"field {key} present")
    for s in _strings(obj):
        leaked = (grams(s) & passage) - allowed
        if leaked:
            problems.append(f"passage text outside verified quotes: {' '.join(next(iter(leaked)))!r}")
            break
    return problems
