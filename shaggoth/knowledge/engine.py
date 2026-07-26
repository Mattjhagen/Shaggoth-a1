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

    def query(self, text: str, limit: int = 3, min_score: float = 0.0) -> list[tuple[KnowledgeEntry, float]]:
        self.maybe_reload()
        query_words = set(extract_keywords(text))
        if not query_words or not self._entries:
            return []

        total = len(self._entries)
        scores: list[float] = [0.0] * total
        shared: list[set[str]] = [set() for _ in range(total)]

        for word in query_words:
            if word not in self._index:
                continue
            df = len(self._index[word])
            idf = math.log((1 + total) / (1 + df))
            for idx in self._index[word]:
                scores[idx] += idf
                shared[idx].add(word)

        results = [
            (self._entries[i], scores[i])
            for i in range(total)
            if scores[i] >= min_score
        ]
        results.sort(key=lambda x: (-x[1], -x[0].word_count))
        return results[:limit]

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
