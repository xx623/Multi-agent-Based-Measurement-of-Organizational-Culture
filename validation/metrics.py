"""Scoring functions for the validation protocol (Technical Appendix D.5, Table B3).

Inputs are final measurement records (``measurement.json``), process records and expert
reference labels in the same field structure. Standard library only.

Field scored -> metric (Table B3):
  categories.<cat>.relevance            -> relevance_exact_agreement, relevance_macro_f1
  categories.<cat>.direction            -> direction_agreement; pair_correct_relevant(field='direction')
  claims[].scope.{type,target,extent}   -> scope_agreement; pair_correct_relevant(field='scope_extent')
  all of the above jointly              -> pair_correct_irrelevant
  record.items vs reference items       -> evidence_completeness
  process.output_state                  -> decision_coverage, failure_rate
  relevance none / abstained vs ref     -> erroneous_exclusion
  process.escalate_to_human             -> escalation_rate
"""
from __future__ import annotations

import re
from typing import Iterable, Mapping

RELEVANCE = ["none", "weak", "moderate", "strong"]
RANK = {r: i for i, r in enumerate(RELEVANCE)}


# ── field extractors ──────────────────────────────────────────────────────────

def category_relevance(measurement: dict) -> dict[str, str]:
    return {cat: body["relevance"] for cat, body in measurement["categories"].items()}


def category_direction(measurement: dict) -> dict[str, str]:
    return {cat: body["direction"] for cat, body in measurement["categories"].items()}


def strongest_claim(measurement: dict, cat: str) -> dict | None:
    claims = measurement["categories"][cat]["claims"]
    return max(claims, key=lambda c: RANK.get(c["relevance"], 0)) if claims else None


def category_scope(measurement: dict) -> dict[str, dict | None]:
    out = {}
    for cat in measurement["categories"]:
        c = strongest_claim(measurement, cat)
        out[cat] = None if c is None else {"type": c["scope"]["type"], "target": _norm_target(c["scope"]["target"]),
                                           "extent": c["scope"]["extent"]}
    return out


def _norm_target(t: str) -> str:
    return re.sub(r"\s+", " ", str(t or "")).strip().lower()


def scored_fields(measurement: dict) -> dict[str, dict]:
    """Jointly scored fields per category: relevance, direction, scope of the strongest claim."""
    rel, dire, scope = category_relevance(measurement), category_direction(measurement), category_scope(measurement)
    return {cat: {"relevance": rel[cat], "direction": dire[cat], "scope": scope[cat]} for cat in rel}


# ── agreement with the expert reference ───────────────────────────────────────

def relevance_exact_agreement(pairs: Iterable[tuple[Mapping[str, str], Mapping[str, str]]]) -> float:
    hits = total = 0
    for ref, pred in pairs:
        for cat, r in ref.items():
            total += 1
            hits += int(pred.get(cat, "none") == r)
    return hits / total if total else float("nan")


def relevance_macro_f1(pairs: Iterable[tuple[Mapping[str, str], Mapping[str, str]]]) -> float:
    """Binary detection per category (relevance above none), F1 per category, macro-averaged."""
    tp: dict[str, int] = {}
    fp: dict[str, int] = {}
    fn: dict[str, int] = {}
    cats: set[str] = set()
    for ref, pred in pairs:
        for cat in set(ref) | set(pred):
            cats.add(cat)
            g = RANK.get(ref.get(cat, "none"), 0) > 0
            p = RANK.get(pred.get(cat, "none"), 0) > 0
            if g and p:
                tp[cat] = tp.get(cat, 0) + 1
            elif p:
                fp[cat] = fp.get(cat, 0) + 1
            elif g:
                fn[cat] = fn.get(cat, 0) + 1
    scores = []
    for cat in cats:
        denom = 2 * tp.get(cat, 0) + fp.get(cat, 0) + fn.get(cat, 0)
        scores.append(1.0 if denom == 0 else 2 * tp.get(cat, 0) / denom)
    return sum(scores) / len(scores) if scores else float("nan")


def direction_agreement(pairs: Iterable[tuple[dict, dict]], ref_relevance: Iterable[Mapping[str, str]] | None = None) -> float:
    """Exact agreement of category direction where the reference has relevance above none."""
    pairs = list(pairs)
    rels = list(ref_relevance) if ref_relevance is not None else [None] * len(pairs)
    hits = total = 0
    for (ref, pred), rel in zip(pairs, rels):
        for cat, d in ref.items():
            if rel is not None and RANK.get(rel.get(cat, "none"), 0) == 0:
                continue
            total += 1
            hits += int(pred.get(cat) == d)
    return hits / total if total else float("nan")


def scope_agreement(pairs: Iterable[tuple[Mapping[str, dict | None], Mapping[str, dict | None]]]) -> float:
    """All three scope fields must match, on categories where the reference has a claim."""
    hits = total = 0
    for ref, pred in pairs:
        for cat, s in ref.items():
            if s is None:
                continue
            total += 1
            p = pred.get(cat)
            hits += int(p is not None and p["type"] == s["type"] and p["extent"] == s["extent"]
                        and _norm_target(p["target"]) == _norm_target(s["target"]))
    return hits / total if total else float("nan")


# ── paired edits (D.1 scoring) ────────────────────────────────────────────────

def pair_correct_irrelevant(original: dict, edited: dict, reference: dict) -> bool:
    """Every scored field unchanged across the pair AND both equal to the reference."""
    return original == edited == reference


def pair_correct_relevant(original: dict, edited: dict, *, category: str, field: str,
                          expected_before: str, expected_after: str, reference_original: dict,
                          reference_edited: dict) -> bool:
    """The prespecified field changes in the prespecified direction and both match the reference."""
    def get(fields: dict, which: str):
        cell = fields[category]
        if which == "direction":
            return cell["direction"]
        if which.startswith("scope_"):
            return None if cell["scope"] is None else cell["scope"][which.split("_", 1)[1]]
        return cell[which]

    return (get(original, field) == expected_before and get(edited, field) == expected_after
            and original == reference_original and edited == reference_edited)


# ── coverage and failures ─────────────────────────────────────────────────────

def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", str(text).lower()))


def evidence_completeness(record_items: list[dict], reference_items: list[dict], min_overlap: float = 0.5) -> float:
    """Share of reference conduct items recovered: same sentence and >= 50% token overlap of excerpts."""
    if not reference_items:
        return float("nan")
    found = 0
    for ref in reference_items:
        rt = _tokens(ref["excerpt"])
        for it in record_items:
            if it.get("excerpt_sentence") == ref.get("excerpt_sentence") and rt:
                if len(rt & _tokens(it["excerpt"])) / len(rt) >= min_overlap:
                    found += 1
                    break
    return found / len(reference_items)


def decision_coverage(process_records: Iterable[dict], n_categories: int = 6) -> float:
    recs = list(process_records)
    if not recs:
        return float("nan")
    valid = sum(p.get("output_state") == "valid" for p in recs) * n_categories
    return valid / (len(recs) * n_categories)


def erroneous_exclusion(triples: Iterable[tuple[Mapping[str, str], Mapping[str, str], str]]) -> float:
    """Share of reference-relevant pairs decided none or abstained/invalid."""
    missed = total = 0
    for ref, pred, state in triples:
        for cat, r in ref.items():
            if RANK.get(r, 0) == 0:
                continue
            total += 1
            missed += int(state != "valid" or RANK.get(pred.get(cat, "none"), 0) == 0)
    return missed / total if total else float("nan")


def escalation_rate(process_records: Iterable[dict]) -> float:
    recs = list(process_records)
    return sum(bool(p.get("escalate_to_human")) for p in recs) / len(recs) if recs else float("nan")


def failure_rate(process_records: Iterable[dict]) -> float:
    recs = list(process_records)
    return sum(p.get("output_state") == "invalid" for p in recs) / len(recs) if recs else float("nan")
