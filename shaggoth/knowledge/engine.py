from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import DATA_DIR
from ..memory.store import STOPWORDS, extract_keywords

DEFAULT_KNOWLEDGE_DIR = DATA_DIR / "knowledge"


@dataclass
class KnowledgeEntry:
    topic: str
    content: str
    path: str
    word_count: int
    keywords: list[str]
    mtime: float


class KnowledgeBase:
    def __init__(self, directory: str | Path | None = None):
        self.directory = Path(directory) if directory else DEFAULT_KNOWLEDGE_DIR
        self.directory.mkdir(parents=True, exist_ok=True)
        self._entries: list[KnowledgeEntry] = []
        self._index: dict[str, list[int]] = {}
        self._last_scan: float = 0
        self._scan()

    def _scan(self) -> None:
        entries: list[KnowledgeEntry] = []
        for fpath in sorted(self.directory.glob("*")):
            if fpath.suffix.lower() not in (".md", ".txt", ".text"):
                continue
            content = fpath.read_text(encoding="utf-8", errors="replace").strip()
            if not content:
                continue
            topic = fpath.stem.replace("-", " ").replace("_", " ").title()
            keywords = extract_keywords(content)
            entries.append(KnowledgeEntry(
                topic=topic,
                content=content,
                path=str(fpath),
                word_count=len(content.split()),
                keywords=keywords,
                mtime=fpath.stat().st_mtime,
            ))
        self._entries = entries
        self._index = {}
        for i, entry in enumerate(entries):
            for kw in set(entry.keywords):
                self._index.setdefault(kw, []).append(i)
        self._last_scan = time.time()

    def maybe_reload(self) -> bool:
        needs_reload = False
        for fpath in self.directory.glob("*"):
            if fpath.suffix.lower() in (".md", ".txt", ".text"):
                if fpath.stat().st_mtime > self._last_scan:
                    needs_reload = True
                    break
        if needs_reload:
            self._scan()
            return True
        return False

    # BM25 tuning. k1 controls how fast term frequency saturates; b controls
    # how strongly long documents are penalized. These are the standard
    # defaults and behave well on encyclopedic text.
    _BM25_K1 = 1.5
    _BM25_B = 0.75
    # A title match is the strongest signal available here: every article is
    # named after its subject, so "machine learning" should beat any article
    # that merely mentions the phrase in passing.
    _TITLE_BOOST = 8.0

    def _topic_tokens(self, entry: "KnowledgeEntry") -> set[str]:
        return {t for t in re.split(r"[^a-z0-9]+", entry.topic.lower()) if len(t) > 2}

    def query(self, text: str, limit: int = 3, min_score: float = 0.0) -> list[tuple[KnowledgeEntry, float]]:
        """Rank knowledge entries against ``text`` using BM25 + title boost.

        Returns ``(entry, score)`` pairs sorted best-first. Scores are
        normalized to roughly 0..1 so ``min_score`` behaves like a confidence
        threshold and stays comparable as the corpus grows.
        """
        self.maybe_reload()
        query_words = set(extract_keywords(text))
        if not query_words or not self._entries:
            return []

        total = len(self._entries)
        avg_len = sum(e.word_count for e in self._entries) / total or 1.0

        # Only documents containing at least one query term can score.
        candidates: set[int] = set()
        for word in query_words:
            candidates.update(self._index.get(word, ()))

        # Title matches count even when the body never repeats the phrase.
        title_hits: dict[int, int] = {}
        for idx, entry in enumerate(self._entries):
            overlap = len(query_words & self._topic_tokens(entry))
            if overlap:
                title_hits[idx] = overlap
                candidates.add(idx)

        if not candidates:
            return []

        results: list[tuple[KnowledgeEntry, float]] = []
        for idx in candidates:
            entry = self._entries[idx]
            # Term frequencies from the pre-extracted keyword list.
            tf_counts: dict[str, int] = {}
            for kw in entry.keywords:
                if kw in query_words:
                    tf_counts[kw] = tf_counts.get(kw, 0) + 1

            doc_len = entry.word_count or 1
            score = 0.0
            for word, tf in tf_counts.items():
                df = len(self._index.get(word, ()))
                idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
                denom = tf + self._BM25_K1 * (
                    1 - self._BM25_B + self._BM25_B * doc_len / avg_len
                )
                score += idf * (tf * (self._BM25_K1 + 1)) / (denom or 1.0)

            overlap = title_hits.get(idx, 0)
            if overlap:
                # Scale with how much of the query the title accounts for, so
                # an exact title match dominates a single incidental word.
                score += self._TITLE_BOOST * (overlap / len(query_words))

            if score > 0:
                results.append((entry, score))

        if not results:
            return []

        # Normalize to 0..1 against the best hit so min_score is a stable
        # confidence threshold rather than a corpus-size-dependent magnitude.
        best = max(s for _, s in results) or 1.0
        normalized = [(e, s / best) for e, s in results if (s / best) >= min_score]
        # Tie-break toward the SHORTER, more focused article -- the opposite of
        # the previous behaviour, which surfaced sprawling omnibus pages.
        normalized.sort(key=lambda x: (-x[1], x[0].word_count))
        return normalized[:limit]

    def add_entry(self, topic: str, content: str) -> Path:
        safe_name = re.sub(r"[^a-zA-Z0-9\s-]", "", topic).strip().lower()
        safe_name = re.sub(r"\s+", "-", safe_name)
        fpath = self.directory / f"{safe_name}.md"
        fpath.write_text(content, encoding="utf-8")
        self._scan()
        return fpath

    def remove_entry(self, topic: str) -> bool:
        safe_name = re.sub(r"[^a-zA-Z0-9\s-]", "", topic).strip().lower()
        safe_name = re.sub(r"\s+", "-", safe_name)
        fpath = self.directory / f"{safe_name}.md"
        if fpath.exists():
            fpath.unlink()
            self._scan()
            return True
        return False

    def list_entries(self) -> list[dict[str, Any]]:
        self.maybe_reload()
        return [
            {"topic": e.topic, "word_count": e.word_count, "path": e.path}
            for e in self._entries
        ]

    def get_entry(self, topic: str) -> KnowledgeEntry | None:
        self.maybe_reload()
        for e in self._entries:
            if e.topic.lower() == topic.lower():
                return e
        return None
