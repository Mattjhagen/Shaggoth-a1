"""A local model used to judge Shaggoth's answers.

One model training another, with the teacher kept strictly offline: it never
sits in the request path. A user's question is always answered by Shaggoth's
own retrieval; the teacher works between conversations, manufacturing the
judgement signal that otherwise only arrives when a human notices something
is wrong.

Local, via the ollama already on this box, for two reasons. Shaggoth exists to
be self-hosted with no corporate handlers -- routing its self-improvement
through someone else's API would quietly make it a wrapper. And measured on
this hardware a hosted round-trip is not even the slow part:

    qwen2.5-coder:7b   ~20 s per judgement   (warm, 2.3 tok/s)
    gemma4:12b         ~62 s per judgement   (warm, 0.9 tok/s, empty replies)

The 7B model is three times faster *and* answered correctly where the 12B
returned nothing, so it is the default despite being smaller. Re-measure
before changing that: the ranking is hardware-specific, not general.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11434
DEFAULT_MODEL = "qwen2.5-coder:7b"

#: One judgement takes ~20 s warm. This is a ceiling for a stuck call, not a
#: target -- the loop is bounded by its own cadence, not by this.
DEFAULT_TIMEOUT = 180.0

#: Verdicts are one word. Generating more is wasted time on a CPU.
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


class Teacher:
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

    def judge(self, question: str, answer: str) -> TeacherVerdict:
        """Grade one answer. An unusable reply is reported, never guessed at."""
        question = (question or "").strip()
        answer = (answer or "").strip()
        if not question or not answer:
            return TeacherVerdict(verdict="", model=self.model)

        # Long answers are truncated: the judgement is about topicality, and
        # prompt evaluation is the dominant cost on CPU (~19 s of the ~20 s).
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
