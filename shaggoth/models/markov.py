"""Word-level Markov chain language model — the Phase-1 generative core.

This is the same family of statistical language model that powered early
text generation research (Shannon, 1948): predict the next word from the
previous ``order`` words. It trains in milliseconds on a CPU, needs no
dependencies, and is fully inspectable — which makes it the right *first*
model for a homegrown platform. TinyGPT (models/tinygpt.py) is its
transformer successor once the R510 is set up for training.
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from pathlib import Path

from .base import LanguageModel

_TOKEN_RE = re.compile(r"[\w'\-]+|[.,!?;:]")

START = "<s>"
END = "</s>"


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def detokenize(tokens: list[str]) -> str:
    out: list[str] = []
    for tok in tokens:
        if tok in {".", ",", "!", "?", ";", ":"} and out:
            out[-1] += tok
        else:
            out.append(tok)
    text = " ".join(out)
    # Capitalize sentence starts.
    return re.sub(
        r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text
    )


class MarkovModel(LanguageModel):
    name = "markov"

    def __init__(self, order: int = 2, seed: int | None = None):
        self.order = order
        self.table: dict[tuple[str, ...], dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self.rng = random.Random(seed)

    def train(self, text: str) -> None:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            tokens = tokenize(sentence)
            if len(tokens) < 2:
                continue
            padded = [START] * self.order + tokens + [END]
            for i in range(len(padded) - self.order):
                context = tuple(padded[i : i + self.order])
                nxt = padded[i + self.order]
                self.table[context][nxt] += 1

    def is_trained(self) -> bool:
        return bool(self.table)

    def _sample(self, context: tuple[str, ...]) -> str | None:
        choices = self.table.get(context)
        if not choices:
            return None
        words = list(choices.keys())
        weights = list(choices.values())
        return self.rng.choices(words, weights=weights, k=1)[0]

    def generate(self, prompt: str = "", max_tokens: int = 60) -> str:
        """Continue from the prompt's tail if that context was seen; otherwise
        try to start from a context containing a prompt keyword; otherwise
        start a fresh sentence."""
        context: tuple[str, ...] | None = None
        prompt_tokens = tokenize(prompt.lower())

        if len(prompt_tokens) >= self.order:
            tail = tuple(prompt_tokens[-self.order :])
            if tail in self.table:
                context = tail
        if context is None and prompt_tokens:
            keywords = set(prompt_tokens)
            candidates = [c for c in self.table if keywords & set(c)]
            if candidates:
                context = self.rng.choice(candidates)
        if context is None:
            context = tuple([START] * self.order)

        out: list[str] = [t for t in context if t not in (START, END)]
        for _ in range(max_tokens):
            nxt = self._sample(context)
            if nxt is None or nxt == END:
                break
            out.append(nxt)
            context = (*context[1:], nxt)
        return detokenize(out)

    # ------------------------------------------------------- persistence
    def save(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            "order": self.order,
            "table": {" ".join(k): dict(v) for k, v in self.table.items()},
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(serializable, fh)

    def load(self, path: str) -> None:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.order = data["order"]
        self.table = defaultdict(lambda: defaultdict(int))
        for key, counts in data["table"].items():
            self.table[tuple(key.split(" "))] = defaultdict(int, counts)
