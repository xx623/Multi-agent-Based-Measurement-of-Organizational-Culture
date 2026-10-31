"""Model back-ends for the controller.

* ``OpenAICompatibleBackend`` talks to any server that speaks the OpenAI chat API: a local
  Ollama or vLLM instance serving the pinned open-weight model (the configuration used
  for the prototype runs) or a hosted provider for robustness checks. Credentials and
  endpoints come from arguments or environment variables; nothing is stored in the repo.
* ``ReplayBackend`` serves recorded outputs (``NN_<ID>.output.json`` from a run directory
  or ``<ID>.json`` fixtures), so a recorded run can be replayed through the controller
  and validators without a model.
* ``DryBackend`` renders the first prompt and stops.
* ``CachingBackend`` keys on the SHA-256 of the rendered messages and decoding parameters,
  so shared calls of a budget-matched contrast are generated once and reused.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CallResult:
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


class DryRunStop(Exception):
    pass


def messages_digest(messages: list[dict[str, str]], params: dict[str, Any]) -> str:
    payload = json.dumps({"messages": messages, "params": params}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Backend:
    name = "abstract"
    params: dict[str, Any] = {}

    def complete(self, messages: list[dict[str, str]], tag: str, max_tokens: int | None = None) -> CallResult:
        raise NotImplementedError


class DryBackend(Backend):
    name = "dry"

    def complete(self, messages, tag, max_tokens=None):
        raise DryRunStop(tag)


class ReplayBackend(Backend):
    name = "replay"

    def __init__(self, fixtures_dir: str | os.PathLike):
        self.dir = Path(fixtures_dir)
        if not self.dir.is_dir():
            raise FileNotFoundError(f"fixtures directory not found: {self.dir}")
        self.params = {"fixtures": str(self.dir)}

    def complete(self, messages, tag, max_tokens=None):
        output_id = tag.split("#")[0]
        candidates = [self.dir / f"{output_id}.json"] + sorted(self.dir.glob(f"*_{output_id}.output.json"))
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            raise FileNotFoundError(f"no recorded output for call {output_id} in {self.dir}")
        return CallResult(text=path.read_text(encoding="utf-8"),
                          meta={"backend": self.name, "fixture": str(path), "input_tokens": None,
                                "output_tokens": None, "latency_s": 0.0})


class OpenAICompatibleBackend(Backend):
    name = "openai_compatible"

    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None,
                 temperature: float = 0.0, seed: int | None = 12345, max_tokens: int = 4096,
                 json_mode: bool = True, timeout: float = 900.0, max_retries: int = 2):
        try:
            import openai  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise ImportError("pip install 'openai>=1.0' to use the OpenAI-compatible back-end") from exc
        self.model = model or os.environ.get("LLM_MODEL")
        if not self.model:
            raise ValueError("model not given and LLM_MODEL not set")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL") or None
        key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "local"
        import openai
        self._client = openai.OpenAI(base_url=self.base_url, api_key=key, timeout=timeout, max_retries=max_retries)
        self.temperature, self.seed, self.max_tokens, self.json_mode = temperature, seed, max_tokens, json_mode
        self.params = {"model": self.model, "temperature": temperature, "seed": seed, "max_tokens": max_tokens,
                       "json_mode": json_mode, "base_url": self.base_url or "default"}

    def complete(self, messages, tag, max_tokens=None):
        kwargs: dict[str, Any] = dict(model=self.model, messages=messages, temperature=self.temperature,
                                      max_tokens=max_tokens or self.max_tokens)
        if self.seed is not None:
            kwargs["seed"] = self.seed
        if self.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        start = time.perf_counter()
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                response = self._client.chat.completions.create(**kwargs)
                break
            except Exception as exc:  # transport errors: back off and retry
                last_exc = exc
                time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError(f"model call {tag} failed after 3 transport attempts: {last_exc}")
        latency = time.perf_counter() - start
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        meta = {"backend": self.name, "model": getattr(response, "model", self.model),
                "latency_s": round(latency, 3),
                "input_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
                "output_tokens": getattr(usage, "completion_tokens", None) if usage else None,
                "finish_reason": getattr(choice, "finish_reason", None),
                "system_fingerprint": getattr(response, "system_fingerprint", None)}
        return CallResult(text=choice.message.content or "", meta=meta)


class CachingBackend(Backend):
    def __init__(self, inner: Backend, cache_dir: str | os.PathLike):
        self.inner, self.name, self.params = inner, inner.name, inner.params
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def complete(self, messages, tag, max_tokens=None):
        key = messages_digest(messages, dict(self.inner.params, max_tokens=max_tokens))
        path = self.dir / f"{key}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            meta = dict(data["meta"], cached=True)
            return CallResult(text=data["text"], meta=meta)
        result = self.inner.complete(messages, tag, max_tokens)
        path.write_text(json.dumps({"text": result.text, "meta": result.meta}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        result.meta["cached"] = False
        return result


def make_backend(kind: str, *, fixtures: str | None = None, cache_dir: str | None = None, **kw: Any) -> Backend:
    if kind == "dry":
        backend: Backend = DryBackend()
    elif kind == "replay":
        if not fixtures:
            raise ValueError("replay back-end needs --fixtures")
        backend = ReplayBackend(fixtures)
    elif kind in ("openai", "openai_compatible"):
        backend = OpenAICompatibleBackend(**kw)
    else:
        raise ValueError(f"unknown back-end {kind!r}")
    if cache_dir and kind not in ("dry", "replay"):
        backend = CachingBackend(backend, cache_dir)
    return backend
