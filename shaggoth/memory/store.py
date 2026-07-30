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
    they're he's she's it's that's what's who's there's here's we'll we've
    they'll they've i've i'd you'd we'd they'd don't doesn't didn't won't
    wouldn't can't couldn't shouldn't haven't hasn't hadn't isn't aren't
    wasn't weren't ain't let's
    says said told tell asked one two three time day today yesterday tomorrow
    thing things stuff way ways make made need needs new now still even ever never
    much many lot bit good great nice cool right left back well much
    feel feeling feelings felt happy sad angry tired bored excited stressed
    anxious depressed nervous frustrated lonely scared sick hungry sleepy fine
    terrible awful wonderful amazing fantastic horrible better worse
    thank thanks thankyou thx sorry apologize goodbye farewell seeya cya
    bruh dude man bro dang damn yooo meh hmmm hmmmm ugh sigh bleh pfft stfu
    wait hold whoa cool crazy wild hilarious funny weird strange dumb smart
    stupid suck sucks lame boring true false real same never mind forget
    whatever nvm idc care nothing changed help helping whats""".split()
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT 'default',
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
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT 'default',
    ts REAL NOT NULL,
    PRIMARY KEY (key, user_id)
);
CREATE INDEX IF NOT EXISTS idx_facts_user ON facts(user_id);
CREATE TABLE IF NOT EXISTS session_summaries (
    session_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    through_message_id INTEGER NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    ts REAL NOT NULL
);
"""

# Pattern → fact key. First capture group becomes the value.
FACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)\bmy name is ([A-Z][a-zA-Z\-]+)"), "name"),
    (re.compile(r"(?i)\bcall me ([A-Z][a-zA-Z\-]+)"), "name"),
    (re.compile(r"(?i)\bi (?:really )?(?:like|love|enjoy) ([a-zA-Z][\w\s\-]{2,20}?)(?:[.,!?]|$)"), "likes"),
    (re.compile(r"(?i)\bi work (?:as|at|on) ([a-zA-Z][\w\s\-]{2,30}?)(?:[.,!?]|$)"), "work"),
    (re.compile(r"(?i)\bi live in ([a-zA-Z][\w\s\-]{2,30}?)(?:[.,!?]|$)"), "location"),
    (re.compile(r"(?i)\bi(?:'m| am) building ([a-zA-Z][\w\s\-]{2,30}?)(?:[.,!?]|$)"), "project"),
]

_NOT_A_LOCATION = frozenset({
    "fear", "pain", "hope", "denial", "sin", "peace", "harmony", "chaos",
    "darkness", "silence", "shame", "disgrace", "poverty", "luxury",
    "constant", "a world", "the moment", "the past", "the present",
})


def extract_keywords(text: str) -> list[str]:
    # Normalize iOS/smart curly quotes so contractions tokenize correctly.
    text = text.replace("‘", "'").replace("’", "'")
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
                if key == "location" and value.lower() in _NOT_A_LOCATION:
                    continue
                found[key] = value
                self.set_fact(key, value, commit=False)
        if found:
            self.db.commit()
        return found

    def set_fact(self, key: str, value: str, user_id: str = "default",
                 commit: bool = True) -> None:
        """Store or update a durable fact.

        The single place that knows the `facts` schema. Two call sites
        previously inlined this SQL with `ON CONFLICT(key)`, but the table is
        keyed on `(key, user_id)` -- a partial conflict target matches no
        constraint, so SQLite raised and fact storage crashed on every freshly
        created database. Databases created before `user_id` existed have
        `key` alone as the primary key and kept working, which is why the bug
        stayed hidden in production while failing every test run.
        """
        self.db.execute(
            "INSERT INTO facts (key, value, user_id, ts) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key, user_id) DO UPDATE SET "
            "value = excluded.value, ts = excluded.ts",
            (key, value, user_id, time.time()),
        )
        if commit:
            self.db.commit()

    # ----------------------------------------------------------- reading
    def get_fact(self, key: str, user_id: str = "default") -> str | None:
        row = self.db.execute(
            "SELECT value FROM facts WHERE key = ? AND user_id = ?", (key, user_id)
        ).fetchone()
        return row[0] if row else None

    def all_facts(self, user_id: str = "default") -> dict[str, str]:
        return dict(
            self.db.execute(
                "SELECT key, value FROM facts WHERE user_id = ?", (user_id,)
            ).fetchall()
        )

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

    # ------------------------------------------- conversation context

    #: Turns kept verbatim. Older ones are folded into the summary.
    RECENT_TURNS = 8

    #: Compaction runs once a session passes this many messages.
    COMPACT_AFTER = 40

    def conversation_context(
        self, session_id: str, recent_turns: int | None = None
    ) -> dict:
        """What Shaggoth should have in mind for this conversation.

        Returns the last few turns verbatim, a compacted summary of everything
        before them, and the subjects that have come up. Every reply used to
        be computed from the current message alone, so "has it been a bit"
        or "why?" had nothing to refer back to.
        """
        recent_turns = self.RECENT_TURNS if recent_turns is None else recent_turns
        rows = self.db.execute(
            "SELECT id, role, content, ts FROM messages WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, max(0, recent_turns) * 2),
        ).fetchall()
        recent = [
            {"id": r[0], "role": r[1], "content": r[2], "ts": r[3]}
            for r in reversed(rows)
        ]

        total = self.db.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
        ).fetchone()[0]

        summary_row = self.db.execute(
            "SELECT summary, message_count FROM session_summaries WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        last_user = next(
            (m["content"] for m in reversed(recent) if m["role"] == "user"), ""
        )
        return {
            "session_id": session_id,
            "message_count": total,
            "recent": recent,
            "summary": summary_row[0] if summary_row else "",
            "summarized_messages": summary_row[1] if summary_row else 0,
            "topics": self.session_topics(session_id),
            "last_user_message": last_user,
        }

    def session_topics(self, session_id: str, limit: int = 8) -> list[str]:
        """The subjects this conversation keeps coming back to.

        Ranked by how often a keyword appears across the session's messages,
        which is a decent proxy for what it has been about.
        """
        rows = self.db.execute(
            "SELECT k.word, COUNT(*) AS n FROM keywords k "
            "JOIN messages m ON m.id = k.message_id "
            "WHERE m.session_id = ? AND m.role = 'user' "
            "GROUP BY k.word ORDER BY n DESC, k.word ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [r[0] for r in rows]

    def compact_session(self, session_id: str, keep_recent: int | None = None) -> str:
        """Fold older turns into a stored summary, so long chats stay usable.

        The summary is *extractive*: the subjects raised, the facts learned,
        and a couple of representative questions. There is no model here that
        could paraphrase honestly, and an invented paraphrase in long-term
        memory is worse than a plain list of what was discussed.

        Idempotent -- re-running only extends the summary if new messages have
        accumulated past the last compaction point.
        """
        keep_recent = self.RECENT_TURNS * 2 if keep_recent is None else keep_recent

        total = self.db.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        if total <= keep_recent:
            return ""

        cutoff_row = self.db.execute(
            "SELECT id FROM messages WHERE session_id = ? ORDER BY id DESC "
            "LIMIT 1 OFFSET ?",
            (session_id, keep_recent - 1),
        ).fetchone()
        if not cutoff_row:
            return ""
        cutoff = cutoff_row[0]

        existing = self.db.execute(
            "SELECT summary, through_message_id FROM session_summaries "
            "WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if existing and existing[1] >= cutoff:
            return existing[0]  # nothing new to fold in

        older = self.db.execute(
            "SELECT role, content FROM messages WHERE session_id = ? AND id < ? "
            "ORDER BY id ASC",
            (session_id, cutoff),
        ).fetchall()
        if not older:
            return existing[0] if existing else ""

        questions = [c for role, c in older if role == "user"]
        counts: dict[str, int] = {}
        for question in questions:
            for word in set(extract_keywords(question)):
                counts[word] = counts.get(word, 0) + 1
        subjects = [
            w for w, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ][:10]

        parts = [f"Earlier in this conversation ({len(older)} messages)."]
        if subjects:
            parts.append("Subjects raised: " + ", ".join(subjects) + ".")
        if questions:
            sample = [q.strip() for q in questions if len(q.strip()) > 8][:3]
            if sample:
                parts.append("They asked about: " + "; ".join(sample) + ".")
        facts = self.all_facts()
        if facts:
            parts.append(
                "Known about them: "
                + "; ".join(f"{k.replace('_', ' ')} = {v}" for k, v in facts.items())
                + "."
            )
        summary = " ".join(parts)

        self.db.execute(
            "INSERT INTO session_summaries "
            "(session_id, summary, through_message_id, message_count, ts) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET "
            "summary = excluded.summary, "
            "through_message_id = excluded.through_message_id, "
            "message_count = excluded.message_count, ts = excluded.ts",
            (session_id, summary, cutoff, len(older), time.time()),
        )
        self.db.commit()
        return summary

    def maybe_compact(self, session_id: str) -> str:
        """Compact only once a session is long enough to need it."""
        total = self.db.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        if total < self.COMPACT_AFTER:
            return ""
        return self.compact_session(session_id)

    def proactive_messages_after(
        self, session_id: str, since_id: int = 0, limit: int = 20
    ) -> list[dict]:
        """Assistant messages stored after ``since_id`` for a session.

        Used by the proactive polling endpoint so the server doesn't access
        the SQLite connection directly.
        """
        rows = self.db.execute(
            "SELECT id, content, ts FROM messages "
            "WHERE session_id = ? AND role = 'assistant' AND id > ? "
            "ORDER BY id ASC LIMIT ?",
            (session_id, since_id, limit),
        ).fetchall()
        return [{"id": r[0], "text": r[1], "ts": r[2]} for r in rows]

    def close(self) -> None:
        self.db.close()
