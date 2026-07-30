from __future__ import annotations

import difflib
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


# Common English words that should not count as meaningful title tokens.
# Without this, "The History Of Modern Art" would match a query about "the
# history of gravity" on "the" and "history", inflating the title-boost score
# for an unrelated article.
_TITLE_STOPWORDS = frozenset({
    "the", "and", "for", "from", "with", "that", "this", "into",
    "about", "over", "under", "between", "through", "during", "before",
    "after", "above", "below", "more", "most", "other", "some", "any",
    "all", "each", "every", "many", "much", "very", "also", "just",
    "only", "its", "their", "our", "your", "his", "her", "who", "how",
    "what", "when", "where", "why", "which", "not", "but", "yet",
    "tell", "you", "your", "please", "about", "thing", "things",
    "something", "anything", "explain", "describe", "story", "stories",
    "talk", "know", "one", "some", "any", "new", "old", "now", "then",
    "good", "bad", "make", "like", "get",
    "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is",
    "it", "me", "my", "no", "of", "on", "or", "so", "to", "up", "us",
    "we",
})

# Titles that denote an index rather than a subject.
_DISAMBIGUATION_TOPIC = re.compile(r"\bdisambiguation\b", re.I)

# Chunk suffix: "Photosynthesis Part 2" is a continuation, not a standalone
# article. The base entry should rank above its chunks.
_CHUNK_SUFFIX = re.compile(r"\bparts?\s+\d+\s*$", re.I)


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

    # A chunk entry ("Photosynthesis Part 2") is a continuation, not the
    # canonical article. The base entry almost always contains the
    # definition and should rank above its fragments.
    _CHUNK_PENALTY = 0.85

    def _topic_tokens(self, entry: "KnowledgeEntry") -> set[str]:
        title = _CHUNK_SUFFIX.sub("", entry.topic).strip()
        return {
            t for t in re.split(r"[^a-z0-9]+", title.lower())
            if len(t) > 1 and t not in _TITLE_STOPWORDS
        }

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

        # Fuzzy fallback: if exact index matching found nothing, try to
        # match misspelled query words to known index keywords.
        if not candidates:
            index_keys = list(self._index.keys())
            fuzzy_words: set[str] = set()
            for qw in query_words:
                close = difflib.get_close_matches(qw, index_keys, n=1, cutoff=0.8)
                if close:
                    fuzzy_words.add(close[0])
                    candidates.update(self._index.get(close[0], ()))
            if fuzzy_words:
                query_words = query_words | fuzzy_words

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

            if _CHUNK_SUFFIX.search(entry.topic):
                score *= self._CHUNK_PENALTY

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
        topic = topic.replace("++", "-plus-plus").replace("#", "-sharp")
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
            {"topic": e.topic, "word_count": e.word_count, "path": e.path,
             "mtime": e.mtime}
            for e in self._entries
        ]

    def get_entry(self, topic: str) -> KnowledgeEntry | None:
        self.maybe_reload()
        for e in self._entries:
            if e.topic.lower() == topic.lower():
                return e
        return None
