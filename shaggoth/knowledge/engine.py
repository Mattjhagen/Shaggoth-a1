from __future__ import annotations

import difflib
import math
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import DATA_DIR
from ..memory.store import STOPWORDS, extract_keywords

DEFAULT_KNOWLEDGE_DIR = DATA_DIR / "knowledge"

# Chunking parameters. Articles longer than _CHUNK_THRESHOLD words are split
# into overlapping windows so BM25 can score specific sections rather than
# diluting term frequency across thousands of words.
_CHUNK_THRESHOLD = 800   # words — below this, one chunk = full article
_CHUNK_SIZE = 500        # words per chunk
_CHUNK_OVERLAP = 100     # words shared between consecutive chunks


def chunk_content(
    text: str,
    chunk_size: int = _CHUNK_SIZE,
    overlap: int = _CHUNK_OVERLAP,
    threshold: int = _CHUNK_THRESHOLD,
) -> list[str]:
    """Split text into overlapping chunks of roughly *chunk_size* words.

    Returns a single-element list (the full text) when the article is short
    enough that chunking would add cost without value.
    """
    words = text.split()
    if len(words) <= threshold:
        return [text]

    step = chunk_size - overlap
    if step <= 0:
        step = max(chunk_size, 1)

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start += step
    return chunks


@dataclass
class KnowledgeEntry:
    topic: str
    content: str
    path: str
    word_count: int
    keywords: list[str]
    mtime: float
    chunks: list[str] = field(default_factory=list)
    chunk_keywords: list[list[str]] = field(default_factory=list)


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
        self._last_check: float = 0
        self._known_paths: set[str] = set()
        # _index holds positions into _entries, so the two must be swapped
        # together and read as one snapshot. Held only around the swap and the
        # snapshot read -- never around the scan itself, which does file I/O.
        self._swap_lock = threading.Lock()
        # Serialise add_entry/remove_entry so concurrent callers cannot
        # interleave file writes with _scan() calls.
        self._write_lock = threading.Lock()
        self._scan()

    def _scan(self) -> None:
        scan_start = time.time()
        entries: list[KnowledgeEntry] = []
        # Every path this scan *considered*, including files skipped for being
        # empty. maybe_reload() compares against this, so it has to record what
        # was on disk rather than what produced an entry -- otherwise an empty
        # file would look like a deletion on every check and rescan forever.
        seen: set[str] = set()
        for fpath in sorted(self.directory.glob("*")):
            if fpath.suffix.lower() not in (".md", ".txt", ".text"):
                continue
            seen.add(str(fpath))
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace").strip()
            except FileNotFoundError:
                # Deleted between the glob and the read.
                seen.discard(str(fpath))
                continue
            if not content:
                continue
            try:
                mtime = fpath.stat().st_mtime
            except FileNotFoundError:
                seen.discard(str(fpath))
                continue
            # Collapse runs of separators: "aeroponics---wikipedia" would
            # otherwise become the topic "Aeroponics   Wikipedia", whose
            # extra blanks break title matching.
            topic = " ".join(
                fpath.stem.replace("-", " ").replace("_", " ").split()
            ).title()
            keywords = extract_keywords(content)
            chunks = chunk_content(content)
            chunk_kw = (
                [extract_keywords(c) for c in chunks]
                if len(chunks) > 1
                else [keywords]
            )
            entries.append(KnowledgeEntry(
                topic=topic,
                content=content,
                path=str(fpath),
                word_count=len(content.split()),
                keywords=keywords,
                mtime=mtime,
                chunks=chunks,
                chunk_keywords=chunk_kw,
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
            self._known_paths = seen
        self._last_scan = scan_start

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
        with self._swap_lock:
            if now - self._last_check < self._RELOAD_CHECK_INTERVAL:
                return False
            self._last_check = now
        # Compare the whole path set, not just mtimes. Iterating only the files
        # that still exist can never observe a deletion, so a removed entry
        # used to stay queryable until the process restarted -- and it only
        # ever disappeared by accident, when some *other* file was written and
        # forced a full rescan.
        current: set[str] = set()
        newest = 0.0
        for fpath in self.directory.glob("*"):
            if fpath.suffix.lower() not in (".md", ".txt", ".text"):
                continue
            current.add(str(fpath))
            try:
                mtime = fpath.stat().st_mtime
            except FileNotFoundError:
                # Deleted underneath us; the set comparison catches it.
                current.discard(str(fpath))
                continue
            if mtime > newest:
                newest = mtime
        if current != self._known_paths or newest > self._last_scan:
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

    # Reranker blending weight. After BM25 retrieves candidates, a second
    # pass scores each entry's best-matching chunk for keyword density and
    # concentration. The final score is a weighted blend of the two.
    _RERANK_BM25_WEIGHT = 0.75
    _RERANK_CHUNK_WEIGHT = 0.25

    def query(self, text: str, limit: int = 3, min_score: float = 0.0) -> list[tuple[KnowledgeEntry, float]]:
        """Rank knowledge entries against ``text`` using BM25 + title boost.

        After BM25 scoring, a chunk-level reranker rescores each candidate
        by measuring keyword density within the best-matching content chunk.
        This lifts entries where query terms are concentrated in one section
        over entries where they are scattered across thousands of words.

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
        avg_len = sum(e.word_count for e in entries) / (total or 1)

        # Only documents containing at least one query term can score.
        candidates: set[int] = set()
        for word in query_words:
            candidates.update(index.get(word, ()))

        # Fuzzy fallback: if exact index matching found nothing, try to
        # match misspelled query words to known index keywords.
        if not candidates:
            index_keys = list(index.keys())
            fuzzy_words: set[str] = set()
            for qw in query_words:
                close = difflib.get_close_matches(qw, index_keys, n=1, cutoff=0.8)
                if close:
                    fuzzy_words.add(close[0])
                    candidates.update(index.get(close[0], ()))
            if fuzzy_words:
                query_words = query_words | fuzzy_words

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
        # Track structural penalty per entry so the reranker can apply it to
        # the chunk_rel component too -- otherwise a high-density disambiguation
        # page can claw back its penalty through the unpenalized chunk score.
        penalties: dict[str, float] = {}
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
                title_add = self._TITLE_BOOST * (overlap / len(query_words))

                # Dilute by the qualifiers the query never mentioned, then
                # reward a title with none left over. "Evolution" beats
                # "Evolution Sabrina Carpenter Album" for the query
                # "evolution"; asking about the album still surfaces it,
                # because then those words are in the query too.
                # Clamped to 0 so a long title never pushes an otherwise
                # matching entry below zero and drops it from results.
                leftover = len(self._topic_tokens(entry) - query_words)
                if leftover:
                    title_sub = self._TITLE_BOOST * (
                        leftover / (leftover + overlap)
                    ) * 0.5
                    score += max(0.0, title_add - title_sub)
                else:
                    score += title_add + self._EXACT_TITLE_BOOST

            penalty = 1.0
            if _DISAMBIGUATION_TOPIC.search(entry.topic):
                score *= self._DISAMBIGUATION_PENALTY
                penalty *= self._DISAMBIGUATION_PENALTY

            if _CHUNK_SUFFIX.search(entry.topic):
                score *= self._CHUNK_PENALTY
                penalty *= self._CHUNK_PENALTY

            if score > 0:
                results.append((entry, score))
                if penalty != 1.0:
                    penalties[entry.topic] = penalty

        if not results:
            return []

        # --- Rerank pass: blend BM25 with chunk-level keyword density ---
        best_bm25 = max(s for _, s in results) or 1.0
        reranked: list[tuple[KnowledgeEntry, float]] = []
        for entry, bm25_raw in results:
            bm25_norm = bm25_raw / best_bm25
            chunk_rel = self._chunk_relevance(entry, query_words)
            # Apply structural penalties to chunk_rel so a disambiguation page
            # with dense, high-relevance content cannot recover the penalty
            # it already received on the BM25 side through an unpenalized
            # chunk_rel contribution.
            if entry.topic in penalties:
                chunk_rel *= penalties[entry.topic]
            combined = (
                self._RERANK_BM25_WEIGHT * bm25_norm
                + self._RERANK_CHUNK_WEIGHT * chunk_rel
            )
            reranked.append((entry, combined))

        # Filter by absolute combined score before normalization so min_score
        # actually rejects weak single-match results (without this, a lone match
        # always normalizes to 1.0 and trivially passes any threshold).
        reranked = [(e, s) for e, s in reranked if s >= min_score]
        if not reranked:
            return []
        # Normalize the survivors to 0..1 against the best combined hit.
        best = max(s for _, s in reranked) or 1.0
        normalized = [(e, s / best) for e, s in reranked]
        # Tie-break toward the SHORTER, more focused article.
        normalized.sort(key=lambda x: (-x[1], x[0].word_count))
        return normalized[:limit]

    # ------------------------------------------------------------------
    # Chunk-level reranker
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk_relevance(entry: KnowledgeEntry, query_words: set[str]) -> float:
        """Score how well the entry's best chunk covers the query keywords.

        Returns 0..1 — the blend of keyword *density* (what fraction of
        query terms appear in the chunk) and *concentration* (query terms
        as a fraction of the chunk's total keywords).
        """
        chunks = entry.chunks if entry.chunks else [entry.content]
        chunk_kws = entry.chunk_keywords if entry.chunk_keywords else None

        best = 0.0
        for i, chunk in enumerate(chunks):
            if chunk_kws and i < len(chunk_kws):
                kw_set = set(chunk_kws[i])
            else:
                kw_set = set(extract_keywords(chunk))

            overlap = len(query_words & kw_set)
            if not overlap:
                continue

            density = overlap / max(len(query_words), 1)
            concentration = overlap / max(len(kw_set), 1)
            score = 0.6 * density + 0.4 * concentration
            best = max(best, score)

        return best

    def best_chunks(
        self,
        entry: KnowledgeEntry,
        query: str,
        max_chunks: int = 2,
    ) -> str:
        """Return the most query-relevant chunk(s) from *entry*.

        When the entry is short or unchunked, returns the full content.
        Otherwise scores each chunk by keyword overlap with the query and
        returns the top *max_chunks*, reassembled in their original order
        so the prose reads sequentially.
        """
        if not entry.chunks or len(entry.chunks) <= 1:
            return entry.content

        query_words = set(extract_keywords(query))
        if not query_words:
            return entry.content

        scored: list[tuple[float, int]] = []
        for i, chunk in enumerate(entry.chunks):
            if entry.chunk_keywords and i < len(entry.chunk_keywords):
                kw_set = set(entry.chunk_keywords[i])
            else:
                kw_set = set(extract_keywords(chunk))
            overlap = len(query_words & kw_set)
            scored.append((overlap, i))

        scored.sort(key=lambda x: -x[0])
        positive = [(s, i) for s, i in scored if s > 0]
        selected = positive[:max_chunks] if positive else scored[:max_chunks]
        best_indices = sorted(idx for _, idx in selected)
        # Strip duplicated overlap words when consecutive chunks are selected.
        # chunk_content() produces overlapping windows; naively joining adjacent
        # chunks would repeat the shared words.  Detect the overlap by finding
        # the longest suffix of the previous chunk that equals the prefix of the
        # current one, then strip that prefix from the current chunk.
        parts: list[str] = []
        for k, idx in enumerate(best_indices):
            chunk = entry.chunks[idx]
            if k > 0 and best_indices[k] == best_indices[k - 1] + 1 and parts:
                prev_words = parts[-1].split()
                next_words = chunk.split()
                for n in range(min(len(prev_words), len(next_words)), 0, -1):
                    if prev_words[-n:] == next_words[:n]:
                        chunk = " ".join(next_words[n:])
                        break
            if chunk.strip():
                parts.append(chunk)
        return "\n\n".join(parts)

    def add_entry(self, topic: str, content: str) -> Path:
        with self._write_lock:
            fpath = self.directory / f"{self.slug_for(topic)}.md"
            fd, tmp = tempfile.mkstemp(dir=str(self.directory), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(content)
                os.replace(tmp, fpath)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
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
        with self._write_lock:
            fpath = self.directory / f"{self.slug_for(topic)}.md"
            if fpath.exists():
                fpath.unlink()
                self._scan()
                return True
        return False

    def list_entries(self) -> list[dict[str, Any]]:
        self.maybe_reload()
        entries, _ = self._snapshot()
        return [
            {"topic": e.topic, "word_count": e.word_count, "path": e.path,
             "mtime": e.mtime}
            for e in entries
        ]

    def get_entry(self, topic: str) -> KnowledgeEntry | None:
        self.maybe_reload()
        entries, _ = self._snapshot()
        for e in entries:
            if e.topic.lower() == topic.lower():
                return e
        return None
