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

    def _worker(self) -> None:
        while True:
            sql, params = self._queue.get()
            try:
                self._d1_query(sql, params)
            except Exception as exc:
                print(f"[d1] sync failed: {exc}")
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
                 commit: bool = True) -> None:
        self._local.set_fact(key, value, user_id=user_id, commit=commit)
        self._enqueue(
            "INSERT INTO facts (key, value, user_id, ts) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key, user_id) DO UPDATE SET "
            "value = excluded.value, ts = excluded.ts",
            [key, value, user_id, time.time()],
        )

    def extract_and_store_facts(self, text: str) -> dict:
        found = self._local.extract_and_store_facts(text)
        for key, value in found.items():
            self._enqueue(
                "INSERT INTO facts (key, value, user_id, ts) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(key, user_id) DO UPDATE SET "
                "value = excluded.value, ts = excluded.ts",
                [key, value, "default", time.time()],
            )
        return found

    # --------------------------------------------------------- read delegation

    def __getattr__(self, name: str):
        return getattr(self._local, name)
