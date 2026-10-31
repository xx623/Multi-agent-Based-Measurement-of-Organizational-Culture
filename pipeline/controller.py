"""Controller for the five-role prototype, with the expertise-agent stage as an opt-in extension.

Call sequence (Technical Appendix B; eight calls, or fourteen with ``--with-experts``)::

    R1 Reader (initial) -> S1 Evidence skeptic -> R2 Reader (one revision)
    -> record_interp = views.build_view(R2)           # the only object that crosses the boundary
    -> [T1..T6 expertise agents, optional]
    -> J1 Judge -> C1 Interpretive critic -> J2 Judge -> C2 Interpretive critic -> A1 Adjudicator

Information boundaries are enforced in the inputs, not by instruction: interpretation
calls receive ``record_interp`` (no passage, no declaration ledger, no spans) and every
interpretation input is scanned by ``views.leak_report`` before the call; a violation
aborts the passage. Control arm B deliberately adds the masked window to the Judge's
input and is logged as such.

Arm switches (budget-matched contrasts, Appendix D.2): ``isolation`` (A on / B off),
``evidence_inquiry`` (D on / C off: the critique is generated and logged but the Reader
re-reads with the generic self-check instruction), ``interpretive_inquiry`` (F on / E off:
J2 gets no challenge and C2 reassesses J1).

Every call logs the rendered prompt, the exact input objects, every raw reply, the parsed
output, token counts and latency, and all validation attempts. An output that fails
validation is returned once to the model with the error list; a second failure ends the
passage with ``output_state = invalid``. The passage summary is derived from these files by
``summary.derive_summary``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import validate as V
from . import views
from .costs import cost_for
from .llm_client import Backend, DryRunStop
from .schemas import category_names, load_codebook, skeleton
from .summary import derive_summary

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts" / "current"
USER_TURN = "Proceed as instructed above. Return only the JSON object."
PLACEHOLDER = re.compile(r"\{\{([^{}]+)\}\}")
MAX_TOKENS = {"R1": 3000, "S1": 1500, "R2": 3500, "T": 1500, "J1": 2500, "C1": 2000, "J2": 3000, "C2": 2000,
              "A1": 5000}
TEMPLATES = {"reader": "reader.txt", "skeptic": "evidence_skeptic.txt", "selfcheck": "reader_selfcheck.txt",
             "expert": "expertise_agent.txt", "judge": "judge.txt", "critic": "interpretive_critic.txt",
             "adjudicator": "adjudicator.txt"}
GENERATED = ("calls", "final")
GENERATED_FILES = ("log.jsonl", "summary.json", "record_initial.json", "record_revised.json", "record_interp.json")


@dataclass(frozen=True)
class ArmConfig:
    isolation: bool = True
    evidence_inquiry: bool = True
    interpretive_inquiry: bool = True

    @property
    def label(self) -> str:
        return ("A" if self.isolation else "B") + ("D" if self.evidence_inquiry else "C") + \
            ("F" if self.interpretive_inquiry else "E")

    def as_dict(self) -> dict:
        return dict(dataclasses.asdict(self), label=self.label)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_source_window(window: dict) -> str:
    lines = []
    for u in window["units"]:
        role = u.get("speaker_role", "unknown")
        wrole = str(u.get("window_role", "focus")).upper()
        lines.append(f"[{u['sid']}] ({role}, {wrole}) {u['text']}")
    return "\n".join(lines)


def _fmt(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, indent=2)
    return str(v)


def render_template(template: str, values: dict[str, Any]) -> str:
    """One-pass substitution of {{placeholders}}; text inside values is never re-expanded."""
    found = set(PLACEHOLDER.findall(template))
    missing = found - set(values)
    if missing:
        raise KeyError(f"no value for placeholders {sorted(missing)}")
    return PLACEHOLDER.sub(lambda m: _fmt(values[m.group(1)]), template)


class WorkflowRunner:
    def __init__(self, backend: Backend, run_dir: Path, arms: ArmConfig = ArmConfig(), *,
                 with_experts: bool = False, max_validation_retries: int = 1,
                 progress: Callable[[str], None] | None = None, root: Path = ROOT):
        self.backend = backend
        self.run_dir = Path(run_dir)
        self.arms = arms
        self.with_experts = with_experts
        self.max_validation_retries = max_validation_retries
        self.progress = progress or (lambda msg: None)
        self.root = Path(root)
        self.codebook = load_codebook(self.root)
        self.vocab = self.codebook["vocabularies"]
        self.categories = category_names(self.codebook)
        self.codebook_for_prompt = {"target": self.codebook["target"],
                                    "categories": self.codebook["categories"],
                                    "vocabularies": {k: v for k, v in self.vocab.items()},
                                    "coding_rules": self.codebook["coding_rules"]}
        self.templates = {k: (self.root / "prompts" / "current" / f).read_text(encoding="utf-8-sig")
                          for k, f in TEMPLATES.items()}
        self.call_no = 0
        self.log: list[dict] = []
        self.boundary_violations: list[dict] = []

    # ── one logged, validated call ─────────────────────────────────────────────

    def _call(self, output_id: str, template_key: str, values: dict[str, Any],
              validator: Callable[[Any], tuple[list[str], list[str]]], max_tokens: int,
              boundary_check: tuple[dict, dict] | None = None, extra_sub: dict[str, str] | None = None) -> dict:
        self.call_no += 1
        template = self.templates[template_key]
        for k, v in (extra_sub or {}).items():
            template = template.replace(k, v)
        prompt = render_template(template, values)
        prefix = f"{self.call_no:02d}_{output_id}"
        calls_dir = self.run_dir / "calls"
        calls_dir.mkdir(parents=True, exist_ok=True)
        (calls_dir / f"{prefix}.prompt.txt").write_text(prompt, encoding="utf-8")
        (calls_dir / f"{prefix}.inputs.json").write_text(
            json.dumps({k: v for k, v in values.items() if k != "output_schema"}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        if boundary_check is not None:
            record, window = boundary_check
            problems = views.leak_report({k: v for k, v in values.items() if k not in ("output_schema", "codebook")},
                                         record, window)
            if problems:
                self.boundary_violations.append({"call": output_id, "problems": problems})
                raise V.ValidationFailure([f"{output_id}: boundary violation in inputs: {p}" for p in problems])
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": USER_TURN}]
        attempts: list[dict] = []
        parsed: Any = None
        started = time.perf_counter()
        for attempt in range(1, self.max_validation_retries + 2):
            tag = output_id if attempt == 1 else f"{output_id}#{attempt}"
            self.progress(f"call {self.call_no:02d} {output_id} attempt {attempt}")
            result = self.backend.complete(messages, tag, max_tokens=max_tokens)
            (calls_dir / f"{prefix}.attempt{attempt}.raw.txt").write_text(result.text, encoding="utf-8")
            warnings: list[str] = []
            try:
                parsed = V.parse_json_text(result.text)
                errors, warnings = validator(parsed)
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                parsed, errors = None, [f"unparseable or malformed JSON: {exc}"]
            attempts.append({"attempt": attempt, "meta": result.meta, "errors": errors, "warnings": warnings})
            if not errors:
                break
            messages = messages + [
                {"role": "assistant", "content": result.text},
                {"role": "user", "content": "Your previous output failed validation:\n- " + "\n- ".join(errors)
                 + "\nReturn a corrected JSON object only."}]
        meta_last = attempts[-1]["meta"]
        cost, basis = cost_for(meta_last.get("model") or self.backend.params.get("model", ""),
                               meta_last.get("input_tokens"), meta_last.get("output_tokens"))
        entry = {"call": self.call_no, "output_id": output_id, "template": TEMPLATES[template_key],
                 "prompt_sha256": sha256_text(prompt), "prompt_chars": len(prompt),
                 "backend": self.backend.name, "backend_params": self.backend.params, "attempts": attempts,
                 "wall_s": round(time.perf_counter() - started, 3), "arm": self.arms.label,
                 "cost_usd": cost, "cost_basis": basis}
        self.log.append(entry)
        (calls_dir / f"{prefix}.meta.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2),
                                                      encoding="utf-8")
        with (self.run_dir / "log.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if attempts[-1]["errors"]:
            raise V.ValidationFailure([f"{output_id}: {e}" for e in attempts[-1]["errors"]])
        (calls_dir / f"{prefix}.output.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2),
                                                        encoding="utf-8")
        return parsed

    # ── full run ───────────────────────────────────────────────────────────────

    def _reset_run_dir(self) -> None:
        """Remove artifacts of an earlier run in the same directory so that no stale file is summarised."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        for name in GENERATED:
            shutil.rmtree(self.run_dir / name, ignore_errors=True)
        for name in GENERATED_FILES:
            path = self.run_dir / name
            if path.exists():
                path.unlink()

    def run(self, source_input: dict) -> dict:
        passage_id = source_input["passage_id"]
        window = source_input["source_window"]
        for i, u in enumerate(window["units"], 1):
            u.setdefault("sid", f"S{i}")
        self._reset_run_dir()
        config = {"passage_id": passage_id, "arms": self.arms.as_dict(), "with_experts": self.with_experts,
                  "backend": self.backend.name, "backend_params": self.backend.params,
                  "codebook_version": self.codebook.get("version"),
                  "template_sha256": {TEMPLATES[k]: sha256_text(v) for k, v in self.templates.items()},
                  "license": source_input.get("license", source_input.get("provenance", {}).get("license")),
                  "group_key": source_input.get("group_key")}
        (self.run_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.run_dir / "input.json").write_text(json.dumps(source_input, ensure_ascii=False, indent=2),
                                                 encoding="utf-8")
        started = time.perf_counter()
        try:
            self._run(source_input, passage_id, window)
        except DryRunStop as stop:
            summary = {"passage_id": passage_id, "status": "dry_run_stopped_before_model_call",
                       "stopped_at": str(stop), "calls_rendered": self.call_no}
            (self.run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            return summary
        except V.ValidationFailure as exc:
            failed = exc.errors[0].split(":")[0] if exc.errors else "?"
            process = {"passage_id": passage_id, "actions": [], "unresolved_objections": [],
                       "escalate_to_human": True, "output_state": "invalid", "failed_call": failed,
                       "errors": exc.errors}
            (self.run_dir / "final").mkdir(exist_ok=True)
            (self.run_dir / "final" / "process.json").write_text(json.dumps(process, indent=2), encoding="utf-8")
        summary = derive_summary(self.run_dir)
        summary["wall_s"] = round(time.perf_counter() - started, 1)
        (self.run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                                   encoding="utf-8")
        return summary

    def _run(self, source_input: dict, passage_id: str, window: dict) -> None:
        window_text = render_source_window(window)
        vocab = self.vocab
        # Source stage -----------------------------------------------------------
        r1 = self._call("R1", "reader", {
            "passage_id": passage_id, "phase": "initial", "source_window": window_text,
            "previous_record": None, "revision_input": None, "output_schema": skeleton("record", self.codebook),
        }, lambda o: V.validate_record(o, passage_id=passage_id, phase="initial", window=window, vocab=vocab),
            MAX_TOKENS["R1"])
        V.attach_spans(r1, window)
        s1 = self._call("S1", "skeptic", {
            "passage_id": passage_id, "source_window": window_text, "reader_record": r1,
            "output_schema": skeleton("critique", self.codebook),
        }, lambda o: V.validate_critique(o, passage_id=passage_id, window=window, record=r1, vocab=vocab),
            MAX_TOKENS["S1"])
        if self.arms.evidence_inquiry:
            revision_input: Any = s1
            r2_validator = lambda o: V.validate_record(o, passage_id=passage_id, phase="revision", window=window,  # noqa: E731
                                                       vocab=vocab, previous=r1, critique=s1)
        else:
            revision_input = self.templates["selfcheck"]
            r2_validator = lambda o: V.validate_record(o, passage_id=passage_id, phase="revision", window=window,  # noqa: E731
                                                       vocab=vocab, previous=r1, critique=None, selfcheck=True)
        r2 = self._call("R2", "reader", {
            "passage_id": passage_id, "phase": "revision", "source_window": window_text,
            "previous_record": r1, "revision_input": revision_input,
            "output_schema": skeleton("record", self.codebook),
        }, r2_validator, MAX_TOKENS["R2"])
        V.attach_spans(r2, window)
        (self.run_dir / "record_initial.json").write_text(json.dumps(r1, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.run_dir / "record_revised.json").write_text(json.dumps(r2, ensure_ascii=False, indent=2), encoding="utf-8")
        # Boundary ---------------------------------------------------------------
        view = views.build_view(r2, window)
        (self.run_dir / "record_interp.json").write_text(json.dumps(view, ensure_ascii=False, indent=2),
                                                         encoding="utf-8")
        boundary = (r2, window) if self.arms.isolation else None
        # Expertise agents (optional) -------------------------------------------
        assessments: Any = None
        if self.with_experts:
            assessments = []
            for i, cat in enumerate(self.codebook["categories"], 1):
                out = self._call(f"T{i}", "expert", {
                    "passage_id": passage_id, "record_interp": view,
                    "output_schema": skeleton("assessment", self.codebook),
                }, lambda o, name=cat["name"]: V.validate_assessment(o, passage_id=passage_id, category=name,
                                                                     view=view, vocab=vocab),
                    MAX_TOKENS["T"], boundary_check=boundary,
                    extra_sub={"{CATEGORY}": cat["name"], "{DEFINITION}": cat["definition"],
                               "{INDICATORS}": cat["indicators"], "{NON_QUALIFYING}": cat["non_qualifying"]})
                assessments.append(out)
        # Interpretation stage ---------------------------------------------------
        full_window = window_text if not self.arms.isolation else "withheld in this arm"
        j1 = self._call("J1", "judge", {
            "passage_id": passage_id, "round": 1, "record_interp": view, "codebook": self.codebook_for_prompt,
            "assessments": assessments, "full_masked_window": full_window, "previous_claims": None,
            "critic_challenge": None, "output_schema": skeleton("judgment", self.codebook),
        }, lambda o: V.validate_judgment(o, passage_id=passage_id, round_no=1, view=view,
                                         categories=self.categories, vocab=vocab),
            MAX_TOKENS["J1"], boundary_check=boundary)
        c1 = self._call("C1", "critic", {
            "passage_id": passage_id, "round": 1, "record_interp": view, "codebook": self.codebook_for_prompt,
            "assessments": assessments, "judge_claims": j1, "prior_critique": None,
            "output_schema": skeleton("interpretive_critique", self.codebook),
        }, lambda o: V.validate_interpretive_critique(o, passage_id=passage_id, round_no=1, judgment=j1,
                                                      view=view, vocab=vocab),
            MAX_TOKENS["C1"], boundary_check=(r2, window))
        challenge = c1 if self.arms.interpretive_inquiry else None
        j2 = self._call("J2", "judge", {
            "passage_id": passage_id, "round": 2, "record_interp": view, "codebook": self.codebook_for_prompt,
            "assessments": assessments, "full_masked_window": full_window, "previous_claims": j1,
            "critic_challenge": challenge, "output_schema": skeleton("judgment", self.codebook),
        }, lambda o: V.validate_judgment(o, passage_id=passage_id, round_no=2, view=view,
                                         categories=self.categories, vocab=vocab, critique=challenge),
            MAX_TOKENS["J2"], boundary_check=boundary)
        under_review = j2 if self.arms.interpretive_inquiry else j1
        c2 = self._call("C2", "critic", {
            "passage_id": passage_id, "round": 2, "record_interp": view, "codebook": self.codebook_for_prompt,
            "assessments": assessments, "judge_claims": under_review, "prior_critique": c1,
            "output_schema": skeleton("interpretive_critique", self.codebook),
        }, lambda o: V.validate_interpretive_critique(o, passage_id=passage_id, round_no=2, judgment=under_review,
                                                      view=view, vocab=vocab, prior=c1, prior_judgment=j1),
            MAX_TOKENS["C2"], boundary_check=(r2, window))
        a1 = self._call("A1", "adjudicator", {
            "passage_id": passage_id, "record_interp": view, "codebook": self.codebook_for_prompt,
            "judge_round1": j1, "critic_round1": c1, "judge_round2": j2, "critic_round2": c2,
            "output_schema": skeleton("adjudication", self.codebook),
        }, lambda o: V.validate_adjudication(o, passage_id=passage_id, view=view, judgment2=j2, critique1=c1,
                                             critique2=c2, categories=self.categories, vocab=vocab),
            MAX_TOKENS["A1"], boundary_check=(r2, window))
        final = self.run_dir / "final"
        final.mkdir(exist_ok=True)
        (final / "measurement.json").write_text(json.dumps(a1["measurement"], ensure_ascii=False, indent=2),
                                                encoding="utf-8")
        (final / "process.json").write_text(json.dumps(a1["process"], ensure_ascii=False, indent=2), encoding="utf-8")
