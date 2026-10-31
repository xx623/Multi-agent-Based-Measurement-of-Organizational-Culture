"""Release-safe copies of run logs for passages from licensed transcripts (Appendix F).

Released logs may contain source text only as the verified excerpts of at most 25 words.
For a passage whose input carries ``license: restricted`` this module copies the run
directory and (1) replaces the rendered source window in the Reader and skeptic calls
with a placeholder carrying its sentence count and SHA-256, and (2) blanks any run of six
or more consecutive passage words that appears anywhere else in the logs and is not
inside a verified excerpt, and (3) replaces identifiers that the masking table missed,
such as a firm abbreviation, with their placeholders. Those terms come from a private list
kept outside the repository ({call_id: {term: placeholder}}); REDACTION.json records only
how many replacements were made, never the terms. Public and constructed passages are
copied unchanged.
Interpretation-stage inputs (record_interp onwards) are released in full; they are the
objects whose boundary a reviewer should check.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from .validate import normalize_text, verified_quote_ngrams

NGRAM = 6
WORD = re.compile(r"[A-Za-z0-9']+")


def _ngrams(text: str) -> set[tuple[str, ...]]:
    toks = [t.lower() for t in WORD.findall(normalize_text(text))]
    return {tuple(toks[i:i + NGRAM]) for i in range(0, max(0, len(toks) - NGRAM + 1))}


def scrub(text: str, passage_ngrams: set, excerpt_ngrams: set) -> tuple[str, int]:
    """Blank passage n-grams that are not excerpt n-grams; returns (text, tokens_blanked)."""
    tokens = list(WORD.finditer(text))
    lowered = [t.group(0).lower() for t in tokens]
    marked = [False] * len(tokens)
    for i in range(0, max(0, len(tokens) - NGRAM + 1)):
        gram = tuple(lowered[i:i + NGRAM])
        if gram in passage_ngrams and gram not in excerpt_ngrams:
            for j in range(i, i + NGRAM):
                marked[j] = True
    if not any(marked):
        return text, 0
    out, last = [], 0
    for t, m in zip(tokens, marked):
        if m:
            out.append(text[last:t.start()])
            out.append("█" * min(len(t.group(0)), 3))
            last = t.end()
    out.append(text[last:])
    return "".join(out), sum(marked)


def window_placeholder(window: dict) -> str:
    text = "\n".join(u["text"] for u in window["units"])
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return (f"[SOURCE WINDOW REDACTED: licensed transcript; {len(window['units'])} sentences; "
            f"sha256 {digest[:16]}...; sentence IDs {window['units'][0]['sid']}-{window['units'][-1]['sid']}]")


def _rendered_line(u: dict) -> str:
    return f"[{u['sid']}] ({u.get('speaker_role', 'unknown')}, {str(u.get('window_role', 'focus')).upper()}) {u['text']}"


def load_private_terms(path: str | Path) -> dict[str, dict[str, str]]:
    """Read the private term list {call_id: {term: placeholder}}; keep the file outside the repository."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
            isinstance(terms, dict) and all(isinstance(k, str) and isinstance(v, str) and k for k, v in terms.items())
            for terms in data.values()):
        raise ValueError("private terms must be a JSON object {call_id: {term: placeholder}}")
    return data


def mask_private_terms(dest: Path, terms: dict[str, str]) -> tuple[int, int]:
    """Replace whole-word, case-sensitive occurrences of each term in the text files under dest.

    Returns (replacements, files changed).
    """
    if not terms:
        return 0, 0
    alternation = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    pattern = re.compile(r"(?<![A-Za-z0-9])(" + alternation + r")(?![A-Za-z0-9])")
    replaced = changed = 0
    for path in sorted(Path(dest).rglob("*")):
        if path.is_dir() or path.suffix not in (".txt", ".json", ".jsonl"):
            continue
        text = path.read_text(encoding="utf-8")
        new, n = pattern.subn(lambda m: terms[m.group(1)], text)
        if n:
            path.write_text(new, encoding="utf-8")
            replaced += n
            changed += 1
    return replaced, changed


def redact_run_dir(run_dir: Path, dest: Path, private_terms: dict[str, dict[str, str]] | None = None) -> dict:
    run_dir, dest = Path(run_dir), Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(run_dir, dest)
    source_input = json.loads((run_dir / "input.json").read_text(encoding="utf-8"))
    license_tag = source_input.get("license") or source_input.get("provenance", {}).get("license")
    report = {"passage_id": source_input["passage_id"], "license": license_tag, "redacted": False,
              "tokens_blanked": 0, "files_touched": 0}
    if license_tag != "restricted":
        return report
    window = source_input["source_window"]
    record = {}
    if (run_dir / "record_revised.json").exists():
        record = json.loads((run_dir / "record_revised.json").read_text(encoding="utf-8"))
    excerpt_ngrams: set = verified_quote_ngrams(record, window) if record else set()
    passage_ngrams = _ngrams("\n".join(u["text"] for u in window["units"]))
    placeholder = window_placeholder(window)
    redacted_input = dict(source_input)
    redacted_input["source_window"] = {
        "units": [{"sid": u["sid"], "speaker_role": u.get("speaker_role"), "window_role": u.get("window_role"),
                   "text": "[redacted]"} for u in window["units"]],
        "placeholder": placeholder}
    (dest / "input.json").write_text(json.dumps(redacted_input, ensure_ascii=False, indent=2), encoding="utf-8")
    rendered_lines = [_rendered_line(u) for u in window["units"]]
    block = "\n".join(rendered_lines)
    multi = re.compile("(?:" + re.escape(placeholder) + r"\s*){2,}")
    for path in dest.rglob("*"):
        if path.is_dir() or path.suffix not in (".txt", ".json", ".jsonl") or path.name == "input.json":
            continue
        text = path.read_text(encoding="utf-8")
        original = text
        for candidate in [block, json.dumps(block, ensure_ascii=False)[1:-1]]:
            text = text.replace(candidate, placeholder)
        for line in rendered_lines:
            text = text.replace(line, placeholder)
            text = text.replace(json.dumps(line, ensure_ascii=False)[1:-1], placeholder)
        for u in window["units"]:
            text = text.replace(u["text"], placeholder)
            text = text.replace(json.dumps(u["text"], ensure_ascii=False)[1:-1], placeholder)
        text = multi.sub(placeholder + "\n", text)
        text, n = scrub(text, passage_ngrams, excerpt_ngrams)
        if text != original:
            path.write_text(text, encoding="utf-8")
            report["files_touched"] += 1
            report["tokens_blanked"] += n
    # after scrubbing, so that the passage n-grams still match the logged text
    call_terms = (private_terms or {}).get(str(source_input["passage_id"]).split(":")[0], {})
    report["private_terms_replaced"], report["files_touched_by_private_terms"] = mask_private_terms(dest, call_terms)
    report["redacted"] = True
    (dest / "REDACTION.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def redact_batch(batch_dir: Path, dest_dir: Path,
                 private_terms: dict[str, dict[str, str]] | None = None) -> list[dict]:
    batch_dir, dest_dir = Path(batch_dir), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for rd in sorted(p for p in batch_dir.iterdir() if p.is_dir() and (p / "input.json").exists()):
        reports.append(redact_run_dir(rd, dest_dir / rd.name, private_terms))
    for name in ("batch_summary.json", "cost_log.csv", "pilot_summary.json", "pilot_summary.md", "profile.csv"):
        if (batch_dir / name).exists():
            shutil.copy2(batch_dir / name, dest_dir / name)
    (dest_dir / "REDACTION_REPORT.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    return reports
