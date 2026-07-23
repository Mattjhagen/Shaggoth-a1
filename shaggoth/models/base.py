"""Common interface every Shaggoth language model implements.

The dialogue engine only talks to this interface, so models are swappable:
the stdlib Markov model today, TinyGPT once trained on the R510, or any
future model (including a remote one) tomorrow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LanguageModel(ABC):
    name: str = "base"

    @abstractmethod
    def train(self, text: str) -> None:
        """Learn from a corpus of text."""

    @abstractmethod
    def generate(self, prompt: str = "", max_tokens: int = 60) -> str:
        """Produce a continuation for ``prompt``."""

    @abstractmethod
    def save(self, path: str) -> None: ...

    @abstractmethod
    def load(self, path: str) -> None: ...

    def is_trained(self) -> bool:
        return True
