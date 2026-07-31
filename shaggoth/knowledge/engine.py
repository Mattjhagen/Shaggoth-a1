from __future__ import annotations

import math
import re
import threading
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


# Titles that denote an index rather than a subject.
_DISAMBIGUATION_TOPIC = re.compile(r"\bdisambiguation\b", re.I)


class KnowledgeBase:
    def __init__(self, directory: str | Path | None = None):
        self.directory = Path(directory) if directory else DEFAULT_KNOWLEDGE_DIR
        self.directory.mkdir(parents=True, exist_ok=True)
        self._entries: list[KnowledgeEntry] = []
        self._index: dict[str, list[int]] = {}
        self._last_scan: float = 0
        self._last_check: float = 0
        # _index holds positions into _entries, so the two must be swapped
        # together and read as one snapshot. Held only around the swap and the
        # snapshot read -- never around the scan itself, which does file I/O.
        self._swap_lock = threading.Lock()
        self._scan()

    def _scan(self) -> None:
        entries: list[KnowledgeEntry] = []
        for fpath in sorted(self.directory.glob("*")):
            if fpath.suffix.lower() not in (".md", ".txt", ".text"):
                continue
            content = fpath.read_text(encoding="utf-8", errors="replace").strip()
            if not content:
                continue
            # Collapse runs of separators: "aeroponics---wikipedia" would
            # otherwise become the topic "Aeroponics   Wikipedia", whose
            # extra blanks break title matching.
            topic = " ".join(
                fpath.stem.replace("-", " ").replace("_", " ").split()
            ).title()
            keywords = extract_keywords(content)
            entries.append(KnowledgeEntry(
                topic=topic,
                content=content,
                path=str(fpath),
                word_count=len(content.split()),
                keywords=keywords,
                mtime=fpath.stat().st_mtime,
            ))
        index: dict[str, list[int]] = {}
        for i, entry in enumerate(entries):
            for kw in set(entry.keywords):
                index.setdefault(kw, []).append(i)
        # Publish both at once. Assigning _entries first left a window where a
        # concurrent query() could pair the new entry list with the stale index
        # (or an index still being filled), and index into it out of range.
        with self._swap_lock:
            self._entries = entries
            self._index = index
        self._last_scan = time.time()

    def _snapshot(self) -> tuple[list[KnowledgeEntry], dict[str, list[int]]]:
        """The current entries and index as a matched pair."""
        with self._swap_lock:
            return self._entries, self._index

    # Statting every file in the corpus costs ~13ms at 800 entries, and one
    # /curiosity/status triggers four such checks (once directly, three more
    # via FreshnessTracker) -- ~50ms of pure duplicate work per request.
    # Re-statting the directory more often than this cannot surface anything
    # a caller would act on; a new file is simply picked up a tick later.
    _RELOAD_CHECK_INTERVAL = 2.0

    def maybe_reload(self) -> bool:
        now = time.time()
        if now - self._last_check < self._RELOAD_CHECK_INTERVAL:
            return False
        self._last_check = now
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

    # Awarded when every word of the title is accounted for by the query --
    # i.e. the article is *about exactly what was asked*, with no extra
    # qualifier. Title overlap alone could not separate "Evolution" from
    # "Evolution Sabrina Carpenter Album": both contain the single query word
    # "evolution", so both earned the same boost, and the shorter-article
    # tie-break then handed the answer to the pop album. The same tie sent
    # "what is quantum mechanics" to "Interpretations Of Quantum Mechanics"
    # and "what is chemistry" to "Bioorganic Chemistry".
    _EXACT_TITLE_BOOST = 10.0

    # A disambiguation page should lose a tie against a real article on the
    # subject: "Evolution Disambiguation" was beating "Evolution" because both
    # matched the title equally and the shorter-article tie-break (right for
    # real articles) handed the win to the index page.
    #
    # The penalty is deliberately mild rather than disqualifying. These pages
    # open with a compact, accurate gloss ("DNA, or deoxyribonucleic acid, is a
    # molecule that carries genetic information"), which is sometimes the best
    # definition in the whole corpus -- particularly where the seeded article
    # under that title turned out to be about something else entirely.
    _DISAMBIGUATION_PENALTY = 0.75

    def _topic_tokens(self, entry: "KnowledgeEntry") -> set[str]:
        return {t for t in re.split(r"[^a-z0-9]+", entry.topic.lower()) if len(t) > 2}

    def query(self, text: str, limit: int = 3, min_score: float = 0.0) -> list[tuple[KnowledgeEntry, float]]:
        """Rank knowledge entries against ``text`` using BM25 + title boost.

        Returns ``(entry, score)`` pairs sorted best-first. Scores are
        normalized to roughly 0..1 so ``min_score`` behaves like a confidence
        threshold and stays comparable as the corpus grows.
        """
        self.maybe_reload()
        # One matched (entries, index) pair for the whole ranking pass: a
        # reload landing mid-query must not shift the positions in _index out
        # from under the _entries list they point into.
        entries, index = self._snapshot()
        query_words = set(extract_keywords(text))
        if not query_words or not entries:
            return []

        total = len(entries)
        avg_len = sum(e.word_count for e in entries) / total or 1.0

        # Only documents containing at least one query term can score.
        candidates: set[int] = set()
        for word in query_words:
            candidates.update(index.get(word, ()))

        # Title matches count even when the body never repeats the phrase.
        title_hits: dict[int, int] = {}
        for idx, entry in enumerate(entries):
            overlap = len(query_words & self._topic_tokens(entry))
            if overlap:
                title_hits[idx] = overlap
                candidates.add(idx)

        if not candidates:
            return []

        results: list[tuple[KnowledgeEntry, float]] = []
        for idx in candidates:
            entry = entries[idx]
            # Term frequencies from the pre-extracted keyword list.
            tf_counts: dict[str, int] = {}
            for kw in entry.keywords:
                if kw in query_words:
                    tf_counts[kw] = tf_counts.get(kw, 0) + 1

            doc_len = entry.word_count or 1
            score = 0.0
            for word, tf in tf_counts.items():
                df = len(index.get(word, ()))
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

                # Dilute by the qualifiers the query never mentioned, then
                # reward a title with none left over. "Evolution" beats
                # "Evolution Sabrina Carpenter Album" for the query
                # "evolution"; asking about the album still surfaces it,
                # because then those words are in the query too.
                leftover = len(self._topic_tokens(entry) - query_words)
                if leftover:
                    score -= self._TITLE_BOOST * (
                        leftover / (leftover + overlap)
                    ) * 0.5
                else:
                    score += self._EXACT_TITLE_BOOST

            if _DISAMBIGUATION_TOPIC.search(entry.topic):
                score *= self._DISAMBIGUATION_PENALTY

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
        fpath = self.directory / f"{self.slug_for(topic)}.md"
        fpath.write_text(content, encoding="utf-8")
        self._scan()
        return fpath

    @staticmethod
    def slug_for(topic: str) -> str:
        """Filename stem for a topic.

        The stem is the only record of the topic -- :meth:`_scan` reads it
        back and title-cases it -- so a malformed slug becomes a malformed
        topic permanently. A leading hyphen survived ``.strip()`` and produced
        the entry " Algebra"; the title "Aeroponics - Wikipedia" collapsed to
        "aeroponics---wikipedia" and came back as "Aeroponics   Wikipedia".
        Both broke title matching in retrieval.
        """
        slug = re.sub(r"[^a-zA-Z0-9\s-]", " ", topic).lower()
        slug = re.sub(r"[\s-]+", "-", slug).strip("-")
        return slug or "untitled"

    def remove_entry(self, topic: str) -> bool:
        fpath = self.directory / f"{self.slug_for(topic)}.md"
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
