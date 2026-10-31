"""Build masked passage windows from earnings-call transcripts (Technical Appendix A.2, A.3).

Input formats: LSEG StreetEvents plain-text transcripts, or a JSON list of turns
``[{"speaker", "role", "section", "text"}, ...]`` from any other parser.

Masking is deterministic: names come from the transcript's own participant list, the
employers named there, the subject company in the title line and the ticker in the file
name, plus common first-name short forms and an optional ``--mask-terms`` JSON file
(``{"PRODUCT": [...], "LOCATION": [...], "COMPANY": [...], "PERSON": [...]}``). With
``--ner spacy`` a named-entity pass (spaCy ``en_core_web_sm``) adds PERSON, ORG,
GPE/LOC/FAC and PRODUCT entities. Each entity maps to a typed, numbered placeholder stable
within a transcript. Dates and amounts are retained (A.3). The placeholder table is
written to a private folder and must not be published with the windows.

Windows: executive prepared remarks are cut into passages of ``k`` sentences with ``w``
context sentences on either side; Q&A answers keep the preceding analyst question as
context. Every unit carries a window-local sentence ID (S1, S2, ...) that excerpts cite,
and a stable source reference ``<call_key>:t<turn>:s<sentence>``.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DASH_RULE = re.compile(r"^-{10,}\s*$")
EQ_RULE = re.compile(r"^={10,}\s*$")
HEADER = re.compile(r"^(?P<head>.+?)\s+\[(?P<n>\d+)\]\s*$")
PARTICIPANT = re.compile(r"^\s*\*\s+(?P<name>.+?)\s*$")
TITLE_LINE = re.compile(r"^(?:Q[1-4]\s+\d{4}|(?:Full|Half)\s+Year\s+\d{4}|\w+\s+\d{4})\s+(?P<company>.+?)\s+"
                        r"(?:Earnings|Results|Conference)\b", re.I)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[“])")
BOILERPLATE_MARKERS = ("forward-looking statements", "safe harbor", "safe harbour", "being recorded",
                       "turn the call over", "turn the conference over", "non-gaap", "reconciliation to gaap")
NICKNAMES = {
    "Douglas": ["Doug"], "Michael": ["Mike"], "Daniel": ["Dan", "Danny"], "David": ["Dave"],
    "Robert": ["Bob", "Rob", "Bobby"], "William": ["Bill", "Will", "Billy"], "James": ["Jim", "Jimmy"],
    "Thomas": ["Tom", "Tommy"], "Christopher": ["Chris"], "Matthew": ["Matt"], "Steven": ["Steve"],
    "Stephen": ["Steve"], "Jeffrey": ["Jeff"], "Richard": ["Rich", "Rick", "Dick"], "Anthony": ["Tony"],
    "Andrew": ["Andy", "Drew"], "Edward": ["Ed", "Eddie"], "Benjamin": ["Ben"], "Alexander": ["Alex"],
    "Nicholas": ["Nick"], "Patrick": ["Pat"], "Joseph": ["Joe"], "Samuel": ["Sam"], "Gregory": ["Greg"],
    "Kenneth": ["Ken"], "Elizabeth": ["Liz", "Beth"], "Katherine": ["Kate", "Katie"], "Jennifer": ["Jen"],
    "Timothy": ["Tim"], "Jonathan": ["Jon"], "Charles": ["Charlie", "Chuck"], "Peter": ["Pete"],
    "Lawrence": ["Larry"], "Ronald": ["Ron"], "Donald": ["Don"], "Raymond": ["Ray"], "Frederick": ["Fred"],
    "Theodore": ["Ted"], "Randall": ["Randy"], "Randolph": ["Randy"],
}
COMPANY_SUFFIXES = (" Inc", " Inc.", " Corp", " Corp.", " Corporation", " Co", " Co.", " Ltd", " Ltd.", " plc",
                    " PLC", " LLC", " N.V.", " NV", " SA", " S.A.", " AG", " SE", " Holdings", " Group", " Company",
                    " Limited", " Incorporated", " LP", " L.P.", " Bancorp")
NER_KEEP = {"EDI", "SaaS", "AI", "GAAP", "EBITDA", "FDA", "SEC", "EPA", "OSHA", "FTC", "IRS", "US", "U.S.", "UK",
            "EU", "ESG", "IT", "R&D", "COVID", "COVID-19", "CEO", "CFO", "COO", "Q1", "Q2", "Q3", "Q4"}
NER_MAP = {"PERSON": "PERSON", "ORG": "COMPANY", "GPE": "LOCATION", "LOC": "LOCATION", "FAC": "LOCATION",
           "PRODUCT": "PRODUCT"}


@dataclass
class Turn:
    index: int
    speaker: str
    affiliation: str
    role: str
    section: str
    text: str


@dataclass
class Transcript:
    call_key: str
    title: str
    company: str
    ticker: str
    corporate: list[tuple[str, str]] = field(default_factory=list)
    conference: list[tuple[str, str]] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)


# ── parsing ────────────────────────────────────────────────────────────────────

def parse_lseg_transcript(text: str, call_key: str, ticker: str = "") -> Transcript:
    lines = text.splitlines()
    title, company = "", ""
    for line in lines[:40]:
        m = TITLE_LINE.match(line.strip())
        if m:
            title, company = line.strip(), m.group("company").strip()
            break
    tr = Transcript(call_key=call_key, title=title, company=company, ticker=ticker)
    section, block = "", ""
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        low = stripped.lower()
        if EQ_RULE.match(stripped):
            i += 1
            continue
        if low in ("corporate participants", "conference call participants"):
            block = "corporate" if low.startswith("corporate") else "conference"
            i += 1
            continue
        if low in ("presentation", "q-and-a", "questions and answers"):
            section = "presentation" if low == "presentation" else "qa"
            block = ""
            i += 1
            continue
        if block:
            pm = PARTICIPANT.match(line)
            if pm:
                name, affil = pm.group("name").strip(), ""
                if i + 1 < n and lines[i + 1].startswith("   ") and not PARTICIPANT.match(lines[i + 1]):
                    affil = lines[i + 1].strip()
                    i += 1
                (tr.corporate if block == "corporate" else tr.conference).append((name, affil))
            i += 1
            continue
        hm = HEADER.match(stripped)
        if hm and i + 1 < n and DASH_RULE.match(lines[i + 1].strip()):
            head = hm.group("head").strip()
            speaker, _, affil = head.partition(",")
            speaker, affil = speaker.strip(), affil.strip()
            i += 2
            body: list[str] = []
            while i < n:
                nxt = lines[i].strip()
                if DASH_RULE.match(nxt) and i + 1 < n and HEADER.match(lines[i + 1].strip()):
                    i += 1
                    break
                if EQ_RULE.match(nxt) or nxt.lower() in ("presentation", "q-and-a"):
                    break
                body.append(lines[i])
                i += 1
            tr.turns.append(Turn(index=len(tr.turns), speaker=speaker, affiliation=affil,
                                 role=_role(speaker, affil, tr), section=section or "presentation",
                                 text=" ".join(" ".join(body).split())))
            continue
        i += 1
    if not tr.company and tr.corporate:
        tr.company = tr.corporate[0][1].split(" - ")[0].strip()
    return tr


def _role(speaker: str, affil: str, tr: Transcript) -> str:
    if speaker.lower() == "operator":
        return "operator"
    if any(speaker == name for name, _ in tr.corporate):
        return "executive"
    if any(speaker == name for name, _ in tr.conference):
        return "analyst"
    if "analyst" in affil.lower():
        return "analyst"
    return "unknown"


def load_turns_json(path: Path, call_key: str, company: str = "", ticker: str = "") -> Transcript:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tr = Transcript(call_key=call_key, title="", company=company, ticker=ticker)
    for k, t in enumerate(data):
        tr.turns.append(Turn(index=k, speaker=t.get("speaker", ""), affiliation=t.get("affiliation", ""),
                             role=t.get("role", "unknown"), section=t.get("section", "presentation"),
                             text=" ".join(str(t.get("text", "")).split())))
        if t.get("role") == "executive" and t.get("speaker"):
            tr.corporate.append((t["speaker"], t.get("affiliation", "")))
        elif t.get("role") == "analyst" and t.get("speaker"):
            tr.conference.append((t["speaker"], t.get("affiliation", "")))
    return tr


# ── masking ────────────────────────────────────────────────────────────────────

class Masker:
    def __init__(self):
        self.table: dict[str, str] = {}
        self.counters: dict[str, int] = {}
        self.entity_ids: dict[tuple[str, str], str] = {}

    def add(self, etype: str, canonical: str, surfaces: list[str] | None = None) -> str:
        canonical = canonical.strip()
        if not canonical:
            return ""
        key = (etype, canonical)
        if key not in self.entity_ids:
            self.counters[etype] = self.counters.get(etype, 0) + 1
            self.entity_ids[key] = f"[{etype}_{self.counters[etype]:03d}]"
        ph = self.entity_ids[key]
        for s in [canonical] + list(surfaces or []):
            s = s.strip()
            if len(s) >= 3 and s not in self.table:
                self.table[s] = ph
        return ph

    def add_person(self, full_name: str) -> None:
        parts = [p for p in re.split(r"\s+", full_name.strip()) if p]
        if not parts:
            return
        surfaces = []
        first, last = parts[0], parts[-1]
        if len(first) >= 3 and not first.endswith("."):
            surfaces.append(first)
            surfaces.extend(NICKNAMES.get(first, []))
        if len(last) >= 3 and last != first:
            surfaces.append(last)
        self.add("PERSON", full_name, surfaces)

    def add_company(self, name: str) -> None:
        name = name.strip()
        if not name:
            return
        surfaces = []
        base = name
        for suf in COMPANY_SUFFIXES:
            if base.endswith(suf):
                base = base[: -len(suf)].strip()
        if base and base != name and len(base) >= 3:
            surfaces.append(base)
        self.add("COMPANY", name, surfaces)

    def pattern(self) -> re.Pattern | None:
        if not self.table:
            return None
        terms = sorted(self.table, key=len, reverse=True)
        return re.compile(r"(?<![\w\[])(" + "|".join(re.escape(t) for t in terms) + r")(?![\w\]])")

    def mask(self, text: str) -> str:
        pat = self.pattern()
        return text if not pat else pat.sub(lambda m: self.table[m.group(1)], text)


def build_masker(tr: Transcript, extra_terms: dict[str, list[str]] | None = None) -> Masker:
    m = Masker()
    if tr.company:
        m.add_company(tr.company)
    for _, affil in tr.corporate:
        comp = affil.split(" - ")[0].strip()
        if comp:
            m.add_company(comp)
    for name, _ in tr.corporate:
        m.add_person(name)
    for name, affil in tr.conference:
        if name.lower() != "operator":
            m.add_person(name)
        comp = affil.split(" - ")[0].strip()
        if comp and comp.lower() != "analyst":
            m.add_company(comp)
    if tr.ticker:
        m.add("TICKER", tr.ticker)
    for etype, terms in (extra_terms or {}).items():
        if etype.lower() == "note":
            continue
        for t in terms:
            if etype == "PERSON":
                m.add_person(t)
            elif etype == "COMPANY":
                m.add_company(t)
            else:
                m.add(etype.upper(), t)
    return m


def add_ner_entities(masker: Masker, texts: list[str], model: str = "en_core_web_sm") -> int:
    """Add spaCy entities to the masker (PERSON, ORG, GPE/LOC/FAC, PRODUCT). Returns count added."""
    import spacy  # optional dependency
    nlp = spacy.load(model)
    added = 0
    for doc in nlp.pipe(texts, batch_size=16):
        for ent in doc.ents:
            etype = NER_MAP.get(ent.label_)
            surface = ent.text.strip().strip(".,;:")
            if not etype or len(surface) < 3 or surface in NER_KEEP or surface.isupper() and len(surface) <= 5:
                continue
            if surface.startswith("[") or surface in masker.table or re.fullmatch(r"[\d.,%$]+", surface):
                continue
            if etype == "PERSON":
                masker.add_person(surface)
            elif etype == "COMPANY":
                masker.add_company(surface)
            else:
                masker.add(etype, surface)
            added += 1
    return added


# ── windows ────────────────────────────────────────────────────────────────────

def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def is_boilerplate(turn: Turn, min_words: int = 25) -> bool:
    if turn.role == "operator":
        return True
    words = len(turn.text.split())
    if words < min_words:
        return True
    low = turn.text.lower()
    hits = sum(marker in low for marker in BOILERPLATE_MARKERS)
    return hits >= 2 and words < 220


def build_windows(tr: Transcript, masker: Masker, sentences_per_passage: int = 8, context: int = 2,
                  min_words: int = 25, license_tag: str = "restricted") -> list[dict]:
    windows: list[dict] = []
    masked: dict[int, list[str]] = {t.index: split_sentences(masker.mask(t.text)) for t in tr.turns}

    def units(turn_idx: int, start: int, end: int, role: str, window_role: str) -> list[dict]:
        return [{"source_ref": f"{tr.call_key}:t{turn_idx}:s{s + 1}", "speaker_role": role,
                 "window_role": window_role, "text": masked[turn_idx][s]} for s in range(start, end)]

    prev_turn: Turn | None = None
    for t in tr.turns:
        if t.role != "executive" or is_boilerplate(t, min_words):
            prev_turn = t
            continue
        sents = masked[t.index]
        k = max(1, sentences_per_passage)
        for start in range(0, len(sents), k):
            end = min(len(sents), start + k)
            if end - start < 2 and start > 0:
                windows[-1]["source_window"]["units"].extend(units(t.index, start, end, t.role, "focus"))
                continue
            w_units: list[dict] = []
            if t.section == "qa" and prev_turn is not None and prev_turn.role == "analyst":
                w_units.extend(units(prev_turn.index, 0, len(masked[prev_turn.index]), "analyst", "context"))
            c0 = max(0, start - context)
            w_units.extend(units(t.index, c0, start, t.role, "context"))
            w_units.extend(units(t.index, start, end, t.role, "focus"))
            w_units.extend(units(t.index, end, min(len(sents), end + context), t.role, "context"))
            wid = len(windows) + 1
            windows.append({"passage_id": f"{tr.call_key}:w{wid:03d}", "group_key": tr.call_key,
                            "license": license_tag, "source_window": {"units": w_units},
                            "provenance": {"turn_index": t.index, "section": t.section,
                                           "focus_sentences": [start + 1, end], "speaker_role": t.role,
                                           "license": license_tag}})
        prev_turn = t
    for w in windows:
        for i, u in enumerate(w["source_window"]["units"], 1):
            u["sid"] = f"S{i}"
    return windows


def opaque_key(call_id: str, salt: str = "") -> str:
    return "C" + hashlib.sha256((salt + call_id).encode("utf-8")).hexdigest()[:10]


def ticker_from_filename(name: str) -> str:
    m = re.match(r"^\d{4}-[A-Za-z]{3}-\d{2}-(?P<ticker>[A-Za-z0-9_.^]+?)-\d+-Transcript", name)
    return m.group("ticker").split(".")[0] if m else ""


def build_from_transcript(path: Path, out_dir: Path, *, sentences_per_passage: int = 8, context: int = 2,
                          mask_terms: Path | None = None, keep_ids: bool = False, salt: str = "",
                          turns_json: bool = False, ner: str | None = None,
                          license_tag: str = "restricted") -> dict:
    path = Path(path)
    call_id = path.stem.replace("-Transcript", "")
    call_key = call_id if keep_ids else opaque_key(call_id, salt)
    ticker = ticker_from_filename(path.name)
    if turns_json:
        tr = load_turns_json(path, call_key, ticker=ticker)
    else:
        tr = parse_lseg_transcript(path.read_text(encoding="utf-8", errors="replace"), call_key, ticker)
    extra = json.loads(Path(mask_terms).read_text(encoding="utf-8")) if mask_terms else None
    masker = build_masker(tr, extra)
    ner_added = 0
    if ner:
        ner_added = add_ner_entities(masker, [t.text for t in tr.turns], model="en_core_web_sm" if ner == "spacy" else ner)
    windows = build_windows(tr, masker, sentences_per_passage, context, license_tag=license_tag)
    out_dir = Path(out_dir)
    (out_dir / "windows").mkdir(parents=True, exist_ok=True)
    (out_dir / "private").mkdir(parents=True, exist_ok=True)
    for w in windows:
        (out_dir / "windows" / f"{w['passage_id'].replace(':', '_')}.json").write_text(
            json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "private" / f"{call_key}_masking_table.json").write_text(json.dumps({
        "call_id": call_id, "call_key": call_key, "title": tr.title, "company": tr.company, "ticker": tr.ticker,
        "placeholders": masker.table, "ner_entities_added": ner_added,
        "note": "Private: links placeholders to real names. Do not publish with the windows."},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return {"call_id": call_id, "call_key": call_key, "turns": len(tr.turns),
            "executive_turns": sum(t.role == "executive" for t in tr.turns), "windows": len(windows),
            "masked_terms": len(masker.table), "ner_entities_added": ner_added, "out_dir": str(out_dir)}
