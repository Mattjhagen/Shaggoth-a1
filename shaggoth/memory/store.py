"""Persistent conversational memory.

Three capabilities, all backed by a single SQLite database:

1. **Transcript** — every message (user and assistant) is stored per session.
2. **Facts** — lightweight information extraction pulls durable facts out of
   user messages ("my name is Matt" → ``name: Matt``) so later replies can use
   them.
3. **Topic recall** — every message is keyword-indexed. Given a new message,
   :meth:`MemoryStore.recall` finds past messages from *other* sessions (or
   much earlier in this one) that share rare keywords, scored with a TF-IDF
   style weighting. The dialogue engine uses this to trigger topic callbacks:
   "last time we talked about your homelab…".

The keyword approach is deliberately simple and inspectable — Phase 1 favors
mechanisms you can read end-to-end. Embedding-based recall is a Phase 1+
upgrade (see docs/ROADMAP.md) and slots in behind the same interface.
"""

from __future__ import annotations

import math
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z'\-]{2,}")

# Common words that carry no topical signal.
STOPWORDS = frozenset(
    """the and for you your are was were with that this what when where which who how
    why not don can could would should have has had but they them then than there
    here his her she him its it's about just like really very know think want going
    got get did does doing yes yeah okay too also because been being will may might
    from into onto over under out off all any some more most other such only own
    same our ours their theirs mine me my myself you'll i'll i'm you're we're
    let's says said told tell asked one two three time day today yesterday tomorrow
    thing things stuff way ways make made need needs new now still even ever never
    much many lot bit good great nice cool right left back well much""".split()
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS keywords (
    message_id INTEGER NOT NULL REFERENCES messages(id),
    word TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_keywords_word ON keywords(word);
CREATE TABLE IF NOT EXISTS facts (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    ts REAL NOT NULL
);
"""

# Pattern → fact key. First capture group becomes the value.
FACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)\bmy name is ([A-Z][a-zA-Z\-]+)"), "name"),
    (re.compile(r"(?i)\bcall me ([A-Z][a-zA-Z\-]+)"), "name"),
    (re.compile(r"(?i)\bi (?:really )?(?:like|love|enjoy) ([a-zA-Z][\w\s\-]{2,40}?)(?:[.,!?]|$)"), "likes"),
    (re.compile(r"(?i)\bi work (?:as|at|on) ([a-zA-Z][\w\s\-]{2,40}?)(?:[.,!?]|$)"), "work"),
    (re.compile(r"(?i)\bi live in ([a-zA-Z][\w\s\-]{2,40}?)(?:[.,!?]|$)"), "location"),
    (re.compile(r"(?i)\bi(?:'m| am) building ([a-zA-Z][\w\s\-]{2,40}?)(?:[.,!?]|$)"), "project"),
]


def extract_keywords(text: str) -> list[str]:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    return [w for w in words if w not in STOPWORDS]


@dataclass
class Recall:
    """A past message surfaced as topically related to the current one."""

    message_id: int
    session_id: str
    content: str
    ts: float
    score: float
    shared_words: list[str]


class MemoryStore:
    def __init__(self, db_path: str | Path = ":memory:"):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ----------------------------------------------------------- writing
    def add_message(self, session_id: str, role: str, content: str) -> int:
        cur = self.db.execute(
            "INSERT INTO messages (session_id, role, content, ts) VALUES (?, ?, ?, ?)",
            (session_id, role, content, time.time()),
        )
        message_id = cur.lastrowid
        # Index unique keywords only, to keep scoring about overlap not repetition.
        for word in set(extract_keywords(content)):
            self.db.execute(
                "INSERT INTO keywords (message_id, word) VALUES (?, ?)", (message_id, word)
            )
        self.db.commit()
        return int(message_id)

    def extract_and_store_facts(self, text: str) -> dict[str, str]:
        """Pull durable facts out of a user message; returns any new facts."""
        found: dict[str, str] = {}
        for pattern, key in FACT_PATTERNS:
            match = pattern.search(text)
            if match:
                value = match.group(1).strip()
                found[key] = value
                self.db.execute(
                    "INSERT INTO facts (key, value, ts) VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, ts = excluded.ts",
                    (key, value, time.time()),
                )
        if found:
            self.db.commit()
        return found

    # ----------------------------------------------------------- reading
    def get_fact(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM facts WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def all_facts(self) -> dict[str, str]:
        return dict(self.db.execute("SELECT key, value FROM facts").fetchall())

    def history(self, session_id: str, limit: int = 50) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, role, content, ts FROM messages WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [
            {"id": r[0], "role": r[1], "content": r[2], "ts": r[3]} for r in reversed(rows)
        ]

    def recall(
        self,
        text: str,
        current_session: str,
        limit: int = 3,
        min_score: float = 0.0,
    ) -> list[Recall]:
        """Find past *user* messages topically related to ``text``.

        Scoring: for each shared keyword, add its inverse document frequency —
        rare shared words (e.g. "homelab") count far more than common ones.
        Messages from the current session's recent turns are excluded so we
        recall *past* conversations, not the one in progress.
        """
        query_words = set(extract_keywords(text))
        if not query_words:
            return []

        total_msgs = self.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] or 1
        placeholders = ",".join("?" for _ in query_words)
        rows = self.db.execute(
            f"""
            SELECT k.word, m.id, m.session_id, m.content, m.ts
            FROM keywords k JOIN messages m ON m.id = k.message_id
            WHERE k.word IN ({placeholders})
              AND m.role = 'user'
              AND m.session_id != ?
            """,
            (*query_words, current_session),
        ).fetchall()

        # Document frequency per word (over all indexed messages).
        by_message: dict[int, dict] = {}
        df: dict[str, int] = {}
        for word, *_ in rows:
            df[word] = df.get(word, 0) + 1
        for word, mid, session_id, content, ts in rows:
            idf = math.log((1 + total_msgs) / (1 + df[word]))
            entry = by_message.setdefault(
                mid,
                {"session_id": session_id, "content": content, "ts": ts,
                 "score": 0.0, "words": []},
            )
            entry["score"] += idf
            entry["words"].append(word)

        results = [
            Recall(mid, e["session_id"], e["content"], e["ts"], e["score"], sorted(e["words"]))
            for mid, e in by_message.items()
            if e["score"] >= min_score
        ]
        results.sort(key=lambda r: (-r.score, -r.ts))
        return results[:limit]

    def close(self) -> None:
        self.db.close()
