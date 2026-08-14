"""Cloudflare D1 background sync for Shaggoth's conversation memory.

Wraps MemoryStore: all reads go to local SQLite (fast, always available),
all writes are mirrored to D1 asynchronously so the conversation history
is accessible from the cloud and survives if the local disk is ever wiped.

Required env vars:
    CLOUDFLARE_ACCOUNT_ID
    CLOUDFLARE_API_TOKEN

Optional:
    CLOUDFLARE_D1_DATABASE_ID  (defaults to shaggoth-memory database)
"""
from __future__ import annotations

import json
import queue
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

_DEFAULT_DATABASE_ID = "02e06c82-4187-4116-a0a1-0e5a0ea7b276"  # shaggoth-memory

#: If the sync queue grows past this, oldest items are silently dropped.
_MAX_QUEUE = 500


class D1Sync:
    """Mirrors MemoryStore writes to Cloudflare D1 in the background.

    This is deliberately thin: reads always go local. D1 is write-through
    cloud backup — useful for visibility and disaster recovery, not for
    serving live queries.
    """

    def __init__(
        self,
        local_store,
        account_id: Optional[str] = None,
        api_token: Optional[str] = None,
        database_id: Optional[str] = None,
    ) -> None:
        import os
        self._local = local_store
        self._account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID") or ""
        self._api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN") or ""
        self._database_id = (
            database_id
            or os.environ.get("CLOUDFLARE_D1_DATABASE_ID")
            or _DEFAULT_DATABASE_ID
        )
        self._queue: queue.Queue = queue.Queue(maxsize=_MAX_QUEUE)
        self._thread = threading.Thread(
            target=self._worker, name="shaggoth-d1-sync", daemon=True
        )
        self._thread.start()
        self._ensure_remote_schema()

    @property
    def configured(self) -> bool:
        return bool(self._account_id and self._api_token)

    # ----------------------------------------------------------------- D1 I/O

    def _d1_query(self, sql: str, params: list | None = None) -> None:
        url = (
            f"https://api.cloudflare.com/client/v4/accounts/{self._account_id}"
            f"/d1/database/{self._database_id}/query"
        )
        payload = json.dumps({"sql": sql, "params": params or []}).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()

    def _enqueue(self, sql: str, params: list | None = None) -> None:
        if not self.configured:
            return
        try:
            self._queue.put_nowait((sql, params))
        except queue.Full:
            # Drop the oldest item and retry once — we'd rather lose an old
            # write than block the calling thread.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait((sql, params))
            except queue.Empty:
                pass

    def _ensure_remote_schema(self) -> None:
        """Enqueue idempotent DDL so the remote D1 schema matches local."""
        if not self.configured:
            return
        creates = [
            "CREATE TABLE IF NOT EXISTS messages ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "session_id TEXT NOT NULL, role TEXT NOT NULL, "
            "content TEXT NOT NULL, ts REAL NOT NULL)",

            "CREATE TABLE IF NOT EXISTS facts ("
            "key TEXT NOT NULL, value TEXT NOT NULL, "
            "user_id TEXT NOT NULL DEFAULT 'default', "
            "ts REAL NOT NULL, "
            "confidence REAL NOT NULL DEFAULT 0.5, "
            "source TEXT NOT NULL DEFAULT 'pattern', "
            "PRIMARY KEY (key, user_id))",

            "CREATE TABLE IF NOT EXISTS preferences ("
            "user_id TEXT NOT NULL DEFAULT 'default', "
            "category TEXT NOT NULL, key TEXT NOT NULL, "
            "value TEXT NOT NULL, "
            "confidence REAL NOT NULL DEFAULT 0.5, "
            "source TEXT NOT NULL DEFAULT 'inferred', "
            "ts REAL NOT NULL, "
            "PRIMARY KEY (user_id, category, key))",

            "CREATE TABLE IF NOT EXISTS projects ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id TEXT NOT NULL DEFAULT 'default', "
            "name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', "
            "status TEXT NOT NULL DEFAULT 'active', "
            "ts_created REAL NOT NULL, ts_updated REAL NOT NULL, "
            "UNIQUE(user_id, name))",
        ]
        for ddl in creates:
            self._enqueue(ddl)

        # If facts table existed before confidence/source were added,
        # CREATE TABLE IF NOT EXISTS is a no-op and the columns are missing.
        # D1 has no IF NOT EXISTS for ALTER TABLE, so the worker silently
        # drops the "duplicate column" error on the second run.
        alters = [
            "ALTER TABLE facts ADD COLUMN confidence REAL NOT NULL DEFAULT 0.5",
            "ALTER TABLE facts ADD COLUMN source TEXT NOT NULL DEFAULT 'pattern'",
            "ALTER TABLE preferences ADD COLUMN confidence REAL NOT NULL DEFAULT 0.5",
            "ALTER TABLE preferences ADD COLUMN source TEXT NOT NULL DEFAULT 'inferred'",
        ]
        for ddl in alters:
            self._enqueue(ddl)

    def _worker(self) -> None:
        while True:
            sql, params = self._queue.get()
            try:
                self._d1_query(sql, params)
            except Exception as exc:
                msg = str(exc)
                for secret in (self._api_token, self._account_id, self._database_id):
                    if secret:
                        msg = msg.replace(secret, "[REDACTED]")
                print(f"[d1] sync failed: {type(exc).__name__}: {msg}")
            finally:
                self._queue.task_done()

    # --------------------------------------------------------- write intercepts

    def add_message(self, session_id: str, role: str, content: str) -> int:
        mid = self._local.add_message(session_id, role, content)
        self._enqueue(
            "INSERT INTO messages (session_id, role, content, ts) VALUES (?, ?, ?, ?)",
            [session_id, role, content, time.time()],
        )
        return mid

    def set_fact(self, key: str, value: str, user_id: str = "default",
                 commit: bool = True, *, confidence: float = 0.5,
                 source: str = "pattern") -> None:
        self._local.set_fact(key, value, user_id=user_id, commit=commit,
                             confidence=confidence, source=source)
        self._enqueue(
            "INSERT INTO facts (key, value, user_id, ts, confidence, source) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(key, user_id) DO UPDATE SET "
            "value = excluded.value, ts = excluded.ts, "
            "confidence = excluded.confidence, source = excluded.source",
            [key, value, user_id, time.time(), confidence, source],
        )

    def extract_and_store_facts(self, text: str) -> dict:
        found = self._local.extract_and_store_facts(text)
        for key, value in found.items():
            confidence = 0.9 if key == "name" else 0.7
            self._enqueue(
                "INSERT INTO facts (key, value, user_id, ts, confidence, source) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key, user_id) DO UPDATE SET "
                "value = excluded.value, ts = excluded.ts, "
                "confidence = excluded.confidence, source = excluded.source",
                [key, value, "default", time.time(), confidence, "pattern"],
            )
        return found

    def set_preference(
        self, category: str, key: str, value: str,
        user_id: str = "default", *,
        confidence: float = 0.5, source: str = "inferred",
    ) -> None:
        self._local.set_preference(
            category, key, value, user_id=user_id,
            confidence=confidence, source=source,
        )
        self._enqueue(
            "INSERT INTO preferences (user_id, category, key, value, confidence, source, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, category, key) DO UPDATE SET "
            "value = excluded.value, confidence = excluded.confidence, "
            "source = excluded.source, ts = excluded.ts",
            [user_id, category, key, value, confidence, source, time.time()],
        )

    def add_project(
        self, name: str, description: str = "",
        user_id: str = "default",
    ) -> int:
        pid = self._local.add_project(name, description, user_id=user_id)
        now = time.time()
        if description:
            self._enqueue(
                "INSERT INTO projects (user_id, name, description, status, ts_created, ts_updated) "
                "VALUES (?, ?, ?, 'active', ?, ?) "
                "ON CONFLICT(user_id, name) DO UPDATE SET "
                "description = excluded.description, ts_updated = excluded.ts_updated",
                [user_id, name, description, now, now],
            )
        else:
            self._enqueue(
                "INSERT INTO projects (user_id, name, description, status, ts_created, ts_updated) "
                "VALUES (?, ?, ?, 'active', ?, ?) "
                "ON CONFLICT(user_id, name) DO UPDATE SET "
                "ts_updated = excluded.ts_updated",
                [user_id, name, description, now, now],
            )
        return pid

    def update_project(
        self, name: str, *, description: str | None = None,
        status: str | None = None, user_id: str = "default",
    ) -> bool:
        result = self._local.update_project(
            name, description=description, status=status, user_id=user_id,
        )
        sets = []
        params: list = []
        if description is not None:
            sets.append("description = ?")
            params.append(description)
        if status is not None:
            sets.append("status = ?")
            params.append(status)
        if sets:
            sets.append("ts_updated = ?")
            params.append(time.time())
            params.extend([user_id, name])
            self._enqueue(
                f"UPDATE projects SET {', '.join(sets)} "
                "WHERE user_id = ? AND name = ?",
                params,
            )
        return result

    # --------------------------------------------------------- read delegation

    def __getattr__(self, name: str):
        return getattr(self._local, name)
