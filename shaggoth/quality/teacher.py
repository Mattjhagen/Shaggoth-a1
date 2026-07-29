"""A model used to judge Shaggoth's answers.

One model training another, with the teacher kept strictly offline: it never
sits in the request path. A user's question is always answered by Shaggoth's
own retrieval; the teacher works between conversations, manufacturing the
judgement signal that otherwise only arrives when a human notices something
is wrong.

Local, via the ollama already on this box, BY DEFAULT, for two reasons.
Shaggoth exists to be self-hosted with no corporate handlers -- routing its
self-improvement through someone else's API would quietly make it a wrapper.
And measured on this hardware a hosted round-trip is not even the slow part:

    qwen2.5-coder:7b   ~20 s per judgement   (warm, 2.3 tok/s)
    gemma4:12b         ~62 s per judgement   (warm, 0.9 tok/s, empty replies)

The 7B model is three times faster *and* answered correctly where the 12B
returned nothing, so it is the default despite being smaller. Re-measure
before changing that: the ranking is hardware-specific, not general.

``AnthropicTeacher`` and ``OpenRouterTeacher`` below are a deliberate,
recorded exception to "local by default" -- an explicit opt-in
(``SHAGGOTH_TEACHER_PROVIDER=anthropic`` or ``openrouter``), not a change to
what ``build_teacher()`` picks when nothing is set. See AGENTS.md for the
decision and why it does not silently become the default.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11434
DEFAULT_MODEL = "qwen2.5-coder:7b"

#: One judgement takes ~20 s warm on Ollama/CPU. This is a ceiling for a
#: stuck call, not a target -- the loop is bounded by its own cadence, not
#: by this. Cloud teachers use their own, shorter default (see below).
DEFAULT_TIMEOUT = 180.0

#: Cloud APIs don't carry the ~20s CPU-bound cost Ollama does; a stuck call
#: here means a hung connection, not a slow model, so a much shorter ceiling
#: is appropriate.
DEFAULT_CLOUD_TIMEOUT = 60.0

#: Verdicts are one word. Generating more is wasted time (and, for cloud
#: teachers, money).
MAX_TOKENS = 8

GOOD, WEAK, BAD = "good", "weak", "bad"

_VERDICT = re.compile(r"\b(good|weak|bad)\b", re.I)

PROMPT = """You are grading an encyclopedia assistant.

Question: {question}
Answer given: {answer}

Does the answer actually address the question? Consider only whether it is on
topic and responsive -- not whether it is well written.

Reply with exactly one word: good, weak, or bad."""


@dataclass
class TeacherVerdict:
    verdict: str
    raw: str = ""
    seconds: float = 0.0
    model: str = ""

    @property
    def usable(self) -> bool:
        return self.verdict in (GOOD, WEAK, BAD)

    @property
    def negative(self) -> bool:
        """Whether this should count against the entry that produced it."""
        return self.verdict == BAD


class _JudgeMixin:
    """Shared grading logic for any teacher backend.

    A subclass provides ``self.model`` and a ``_generate(prompt, max_tokens)
    -> (text, seconds, error)`` method; prompt-building, truncation, and
    verdict parsing live here once so every backend is graded the same way
    and a new one is just a new ``_generate``.
    """

    model: str

    def _generate(self, prompt: str, max_tokens: int = MAX_TOKENS) -> tuple:
        raise NotImplementedError

    def judge(self, question: str, answer: str) -> TeacherVerdict:
        """Grade one answer. An unusable reply is reported, never guessed at."""
        question = (question or "").strip()
        answer = (answer or "").strip()
        if not question or not answer:
            return TeacherVerdict(verdict="", model=self.model)

        # Long inputs are truncated: the judgement is about topicality, not
        # a full re-read, and every backend pays either CPU or token cost
        # proportional to input length.
        raw, seconds, error = self._generate(
            PROMPT.format(question=question[:300], answer=answer[:600])
        )
        if error:
            print(f"[teacher] {error}")
            return TeacherVerdict(verdict="", raw=error, seconds=seconds, model=self.model)

        match = _VERDICT.search(raw)
        return TeacherVerdict(
            verdict=match.group(1).lower() if match else "",
            raw=raw.strip()[:200],
            seconds=seconds,
            model=self.model,
        )


class Teacher(_JudgeMixin):
    """Thin ollama client. Never raises into a caller."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.model = model
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout

    def available(self) -> bool:
        """Whether the configured model is actually loaded and listable."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5) as r:
                data = json.loads(r.read().decode())
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return False
        names = {m.get("name", "") for m in (data.get("models") or [])}
        return self.model in names

    def _generate(self, prompt: str, max_tokens: int = MAX_TOKENS) -> tuple:
        body = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0},
        }).encode()
        request = urllib.request.Request(
            f"{self.base_url}/api/generate", data=body,
            headers={"Content-Type": "application/json"},
        )
        started = time.time()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as r:
                data = json.loads(r.read().decode())
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            return "", time.time() - started, str(exc)
        return str(data.get("response") or ""), time.time() - started, ""


DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicTeacher(_JudgeMixin):
    """Judges answers via the Anthropic Messages API.

    Cloud, not local -- see the module docstring for why Ollama stays the
    default and this is an explicit opt-in instead.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        timeout: float = DEFAULT_CLOUD_TIMEOUT,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or ""
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        """Whether an API key is configured.

        Does not verify it authenticates or that the model name is valid --
        that would spend a request on every status check. A bad key surfaces
        instead as an unusable verdict with the HTTP error recorded, the
        first time ``judge`` actually runs.
        """
        return bool(self.api_key)

    def _generate(self, prompt: str, max_tokens: int = MAX_TOKENS) -> tuple:
        if not self.api_key:
            return "", 0.0, "ANTHROPIC_API_KEY not set"
        body = json.dumps({
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        request = urllib.request.Request(
            _ANTHROPIC_API_URL, data=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
        )
        started = time.time()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200]
            return "", time.time() - started, f"HTTP {exc.code}: {detail}"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            return "", time.time() - started, str(exc)
        text = "".join(
            block.get("text", "")
            for block in (data.get("content") or [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        return text, time.time() - started, ""


DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"
_OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterTeacher(_JudgeMixin):
    """Judges answers via OpenRouter's OpenAI-compatible chat completions API.

    Cloud, not local -- see the module docstring for why Ollama stays the
    default and this is an explicit opt-in instead. Defaults to a different
    underlying model than ``AnthropicTeacher`` so the two are actually
    distinct options rather than two paths to the same judge.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_OPENROUTER_MODEL,
        timeout: float = DEFAULT_CLOUD_TIMEOUT,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY") or ""
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        """Whether an API key is configured (see AnthropicTeacher.available)."""
        return bool(self.api_key)

    def _generate(self, prompt: str, max_tokens: int = MAX_TOKENS) -> tuple:
        if not self.api_key:
            return "", 0.0, "OPENROUTER_API_KEY not set"
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
        }).encode()
        request = urllib.request.Request(
            _OPENROUTER_API_URL, data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        started = time.time()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200]
            return "", time.time() - started, f"HTTP {exc.code}: {detail}"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            return "", time.time() - started, str(exc)
        choices = data.get("choices") or []
        text = ""
        if choices:
            text = (choices[0].get("message") or {}).get("content") or ""
        return text, time.time() - started, ""


#: Substrings that mark a failure as "this provider is exhausted right now",
#: not "this judgement failed" -- 429/quota/rate-limit/billing errors should
#: move on to the next teacher; a malformed response or a timeout should not
#: (those aren't evidence the *provider* is out, just that this call was bad).
_EXHAUSTED = re.compile(r"\b(429|insufficient_quota|rate.?limit|quota|billing)\b", re.I)


def _looks_exhausted(error: str) -> bool:
    return bool(_EXHAUSTED.search(error or ""))


class FallbackTeacher(_JudgeMixin):
    """Tries each teacher in order, moving on when one looks exhausted.

    "Exhausted" is judged from the error text (see ``_looks_exhausted``) --
    HTTP 429 / quota / rate-limit / billing. Once a teacher trips that, this
    stays advanced past it for the rest of the process's life; a fresh
    process (e.g. a service restart) starts back at the front of the chain,
    so topping up credits and restarting is what un-sticks it. A teacher that
    fails for some other reason (bad JSON, a timeout) is retried next call --
    that is not evidence it is out of credits.

    ``model`` always reflects whichever backend most recently actually
    produced (or attempted) a verdict, so a caller or a log line can tell who
    graded a given answer.
    """

    def __init__(self, teachers: list) -> None:
        if not teachers:
            raise ValueError("FallbackTeacher needs at least one teacher")
        self._teachers = list(teachers)
        self._index = 0
        self.model = self._teachers[0].model

    def available(self) -> bool:
        return any(t.available() for t in self._teachers[self._index:])

    def _advance(self, reason: str) -> None:
        exhausted = self._teachers[self._index].model
        self._index += 1
        remaining = self._teachers[self._index:]
        nxt = remaining[0].model if remaining else None
        print(
            f"[teacher] {exhausted} looks exhausted ({reason})"
            + (f"; falling back to {nxt}" if nxt else "; no teachers left")
        )

    def _generate(self, prompt: str, max_tokens: int = MAX_TOKENS) -> tuple:
        text, seconds, error = "", 0.0, "no teacher configured"
        while self._index < len(self._teachers):
            teacher = self._teachers[self._index]
            if not teacher.available():
                self._advance("not available")
                continue
            text, seconds, error = teacher._generate(prompt, max_tokens)
            self.model = teacher.model
            if not error or not _looks_exhausted(error):
                return text, seconds, error
            self._advance(error)
        return text, seconds, error


_PROVIDERS = {
    "ollama": Teacher,
    "anthropic": AnthropicTeacher,
    "openrouter": OpenRouterTeacher,
}

#: Provider names that mean "cascade through the cloud options, local last".
_AUTO_PROVIDERS = ("auto", "fallback", "cascade")

#: Priority order for the auto chain: strongest cloud judge first, cheaper
#: cloud backup second, local Ollama always last as the free, always-on
#: safety net that never runs out of credits.
_AUTO_ORDER = ("anthropic", "openrouter", "ollama")


def _build_single(provider: str):
    cls = _PROVIDERS.get(provider)
    if cls is None:
        return None
    if cls is AnthropicTeacher:
        model = os.environ.get("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
        return AnthropicTeacher(model=model)
    if cls is OpenRouterTeacher:
        model = os.environ.get("OPENROUTER_MODEL") or DEFAULT_OPENROUTER_MODEL
        return OpenRouterTeacher(model=model)
    return Teacher()


def build_teacher(provider: Optional[str] = None):
    """Construct the configured Teacher implementation.

    ``provider`` is ``SHAGGOTH_TEACHER_PROVIDER`` (env) or the explicit
    argument, defaulting to ``"ollama"`` -- the module docstring explains why
    that stays the default. ``"anthropic"`` and ``"openrouter"`` are explicit
    single-provider opt-ins; each reads its own API key from the environment
    (``ANTHROPIC_API_KEY`` / ``OPENROUTER_API_KEY``) and its own model
    override (``ANTHROPIC_MODEL`` / ``OPENROUTER_MODEL``).

    ``"auto"`` (also ``"fallback"``/``"cascade"``) builds a
    :class:`FallbackTeacher` over Anthropic, then OpenRouter, then local
    Ollama -- whichever of the cloud two have a key configured, plus Ollama
    always, so grading never fully stops even if every cloud key is out of
    credits or unset.
    """
    provider = (provider or os.environ.get("SHAGGOTH_TEACHER_PROVIDER") or "ollama").strip().lower()

    if provider in _AUTO_PROVIDERS:
        chain = []
        for name in _AUTO_ORDER:
            teacher = _build_single(name)
            if teacher is not None and (name == "ollama" or teacher.available()):
                chain.append(teacher)
        return FallbackTeacher(chain)

    teacher = _build_single(provider)
    if teacher is None:
        print(f"[teacher] unknown SHAGGOTH_TEACHER_PROVIDER={provider!r}, falling back to ollama")
        return Teacher()
    return teacher
