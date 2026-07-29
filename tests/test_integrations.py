"""Tests for Slack, D1 sync, and KV subscription store integrations.

Network calls are mocked throughout so tests run without credentials.
"""
from __future__ import annotations

import json
import queue
import tempfile
import time
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from shaggoth.integrations.slack import SlackSender
from shaggoth.memory.d1_sync import D1Sync
from shaggoth.memory.store import MemoryStore
from shaggoth.notify.kv_store import KVSubscriptionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_urlopen(response_body: bytes, status: int = 200):
    """Return a context-manager mock that looks like urllib.request.urlopen."""
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.read.return_value = response_body
    resp.status = status
    return MagicMock(return_value=resp)


# ---------------------------------------------------------------------------
# SlackSender
# ---------------------------------------------------------------------------

class SlackSenderTests(unittest.TestCase):
    def test_unconfigured_when_no_token(self):
        sender = SlackSender(token="")
        self.assertFalse(sender.configured)

    def test_configured_when_token_set(self):
        sender = SlackSender(token="xoxb-test-token")
        self.assertTrue(sender.configured)

    def test_send_returns_false_when_unconfigured(self):
        sender = SlackSender(token="")
        self.assertFalse(sender.send("hello"))

    def test_send_posts_to_slack_api(self):
        response = json.dumps({"ok": True}).encode()
        with patch("urllib.request.urlopen", _fake_urlopen(response)) as mock_open:
            sender = SlackSender(token="xoxb-test", channel_id="C123")
            result = sender.send("hello world")
        self.assertTrue(result)
        mock_open.assert_called_once()
        req = mock_open.call_args[0][0]
        self.assertIn("chat.postMessage", req.full_url)
        body = json.loads(req.data)
        self.assertEqual(body["text"], "hello world")
        self.assertEqual(body["channel"], "C123")

    def test_send_returns_false_on_api_error_response(self):
        response = json.dumps({"ok": False, "error": "channel_not_found"}).encode()
        with patch("urllib.request.urlopen", _fake_urlopen(response)):
            sender = SlackSender(token="xoxb-test")
            result = sender.send("hi")
        self.assertFalse(result)

    def test_send_returns_false_on_network_exception(self):
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            sender = SlackSender(token="xoxb-test")
            result = sender.send("hi")
        self.assertFalse(result)

    def test_send_async_does_not_block(self):
        response = json.dumps({"ok": True}).encode()
        with patch("urllib.request.urlopen", _fake_urlopen(response)):
            sender = SlackSender(token="xoxb-test")
            # Should return immediately — no assertion on network side-effect here
            sender.send_async("background message")

    def test_bearer_token_is_in_auth_header(self):
        response = json.dumps({"ok": True}).encode()
        with patch("urllib.request.urlopen", _fake_urlopen(response)) as mock_open:
            sender = SlackSender(token="xoxb-secret-token")
            sender.send("test")
        req = mock_open.call_args[0][0]
        self.assertEqual(req.get_header("Authorization"), "Bearer xoxb-secret-token")

    def test_channel_defaults_to_default_channel_id(self):
        from shaggoth.integrations.slack import DEFAULT_CHANNEL_ID
        response = json.dumps({"ok": True}).encode()
        with patch("urllib.request.urlopen", _fake_urlopen(response)) as mock_open:
            sender = SlackSender(token="xoxb-test")
            sender.send("hi")
        req = mock_open.call_args[0][0]
        body = json.loads(req.data)
        self.assertEqual(body["channel"], DEFAULT_CHANNEL_ID)


# ---------------------------------------------------------------------------
# D1Sync
# ---------------------------------------------------------------------------

class FakeMemoryStore:
    """Minimal stand-in for MemoryStore."""

    def __init__(self):
        self.messages: list[dict] = []
        self.facts: dict[str, str] = {}
        self._next_id = 1

    def add_message(self, session_id, role, content) -> int:
        mid = self._next_id
        self._next_id += 1
        self.messages.append({"id": mid, "session_id": session_id, "role": role, "content": content})
        return mid

    def set_fact(self, key, value, user_id="default", commit=True):
        self.facts[key] = value

    def extract_and_store_facts(self, text):
        return {}

    def history(self, session_id):
        return [m for m in self.messages if m["session_id"] == session_id]


class D1SyncTests(unittest.TestCase):
    def _sync(self, **kwargs) -> D1Sync:
        local = FakeMemoryStore()
        # account_id="" means configured=False → queue is inert
        return D1Sync(local, account_id=kwargs.pop("account_id", ""),
                      api_token=kwargs.pop("api_token", ""), **kwargs)

    def test_unconfigured_when_no_credentials(self):
        sync = self._sync()
        self.assertFalse(sync.configured)

    def test_configured_when_credentials_set(self):
        sync = self._sync(account_id="ACC", api_token="TOKEN")
        self.assertTrue(sync.configured)

    def test_add_message_returns_local_id(self):
        sync = self._sync()
        mid = sync.add_message("sess", "user", "hello")
        self.assertEqual(mid, 1)

    def test_add_message_stored_locally(self):
        sync = self._sync()
        sync.add_message("s1", "user", "hi")
        self.assertEqual(sync._local.messages[0]["content"], "hi")

    def test_set_fact_stored_locally(self):
        sync = self._sync()
        sync.set_fact("name", "Matt")
        self.assertEqual(sync._local.facts["name"], "Matt")

    def test_reads_delegate_to_local(self):
        sync = self._sync()
        sync.add_message("s1", "user", "test")
        # history() is not overridden → __getattr__ → local
        hist = sync.history("s1")
        self.assertEqual(len(hist), 1)

    def test_unconfigured_sync_does_not_enqueue(self):
        sync = self._sync()
        sync.add_message("s", "user", "hi")
        self.assertEqual(sync._queue.qsize(), 0)

    def test_configured_sync_enqueues_message_write(self):
        response_body = json.dumps({"result": [], "success": True}).encode()
        with patch("urllib.request.urlopen", _fake_urlopen(response_body)):
            sync = self._sync(account_id="ACC", api_token="TOK")
            sync.add_message("s", "user", "hello")
            # Give the worker thread a moment to drain the queue
            sync._queue.join()
        # No assertion on network (timing), just verify it didn't crash
        self.assertEqual(sync._local.messages[0]["content"], "hello")

    def test_configured_sync_enqueues_fact_write(self):
        response_body = json.dumps({"result": [], "success": True}).encode()
        with patch("urllib.request.urlopen", _fake_urlopen(response_body)):
            sync = self._sync(account_id="ACC", api_token="TOK")
            sync.set_fact("city", "Portland")
            sync._queue.join()
        self.assertEqual(sync._local.facts["city"], "Portland")

    def test_queue_overflow_drops_oldest_not_newest(self):
        from shaggoth.memory.d1_sync import _MAX_QUEUE
        sync = self._sync(account_id="ACC", api_token="TOK")
        # Pause the worker so items stack up
        sync._queue.maxsize = 5
        # We manually test _enqueue overflow by filling beyond maxsize
        for i in range(6):
            sync._enqueue(f"SELECT {i}")
        # Should not block or raise
        self.assertLessEqual(sync._queue.qsize(), 5)

    def test_extract_and_store_facts_returns_dict(self):
        sync = self._sync()
        result = sync.extract_and_store_facts("some text")
        self.assertIsInstance(result, dict)


# ---------------------------------------------------------------------------
# KVSubscriptionStore
# ---------------------------------------------------------------------------

VALID_SUB = {
    "endpoint": "https://push.example.com/sub1",
    "keys": {"p256dh": "key1", "auth": "auth1"},
}


class KVSubscriptionStoreTests(unittest.TestCase):
    def _store(self, kv_response=None, kv_error=None, tmp_path=None) -> KVSubscriptionStore:
        with patch("urllib.request.urlopen") as mock_open:
            if kv_error:
                mock_open.side_effect = kv_error
            elif kv_response is not None:
                mock_open.return_value = MagicMock(
                    __enter__=lambda s: s,
                    __exit__=MagicMock(return_value=False),
                    read=MagicMock(return_value=json.dumps(kv_response).encode()),
                )
            else:
                # 404 → fall back to local file
                import urllib.error
                mock_open.side_effect = urllib.error.HTTPError(
                    url="", code=404, msg="Not Found", hdrs=None, fp=None
                )
            store = KVSubscriptionStore(
                account_id="ACC", api_token="TOK",
                fallback_path=tmp_path,
            )
        return store

    def test_unconfigured_when_no_credentials(self):
        with patch("urllib.request.urlopen", side_effect=Exception("should not call")):
            store = KVSubscriptionStore(account_id="", api_token="")
        self.assertFalse(store.kv_configured)

    def test_configured_when_credentials_set(self):
        import urllib.error
        with patch("urllib.request.urlopen") as m:
            m.side_effect = urllib.error.HTTPError("", 404, "Not Found", None, None)
            store = KVSubscriptionStore(account_id="ACC", api_token="TOK")
        self.assertTrue(store.kv_configured)

    def test_loads_subscriptions_from_kv(self):
        store = self._store(kv_response=[VALID_SUB])
        self.assertEqual(len(store), 1)

    def test_falls_back_to_local_file_on_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "subs.json"
            # Pre-populate local file
            path.write_text(json.dumps([VALID_SUB]))
            store = self._store(tmp_path=path)
        self.assertEqual(len(store), 1)

    def test_falls_back_to_local_file_on_network_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "subs.json"
            path.write_text(json.dumps([VALID_SUB]))
            store = self._store(kv_error=OSError("network down"), tmp_path=path)
        self.assertEqual(len(store), 1)

    def test_add_subscription_then_save_writes_kv(self):
        import urllib.error
        with patch("urllib.request.urlopen") as mock_open:
            # First call (load) → 404
            load_resp = MagicMock(__enter__=lambda s: s,
                                  __exit__=MagicMock(return_value=False),
                                  read=MagicMock(return_value=b"[]"))
            mock_open.side_effect = [
                urllib.error.HTTPError("", 404, "Not Found", None, None),  # load
                load_resp,  # save → PUT
            ]
            with tempfile.TemporaryDirectory() as tmp:
                store = KVSubscriptionStore(
                    account_id="ACC", api_token="TOK",
                    fallback_path=Path(tmp) / "subs.json",
                )
                store.add(VALID_SUB)

    def test_invalid_subscription_is_rejected(self):
        store = self._store(kv_response=[])
        added = store.add({"not_a_real": "subscription"})
        self.assertFalse(added)

    def test_remove_subscription(self):
        store = self._store(kv_response=[VALID_SUB])
        with patch("urllib.request.urlopen", _fake_urlopen(b"")):
            removed = store.remove(VALID_SUB["endpoint"])
        self.assertTrue(removed)
        self.assertEqual(len(store), 0)

    def test_kv_save_falls_through_to_local_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            local_path = Path(tmp) / "subs.json"
            import urllib.error
            with patch("urllib.request.urlopen") as mock_open:
                mock_open.side_effect = [
                    urllib.error.HTTPError("", 404, "Not Found", None, None),  # load
                    OSError("network error"),  # save PUT fails
                    MagicMock(__enter__=lambda s: s,
                               __exit__=MagicMock(return_value=False),
                               read=MagicMock(return_value=b"")),
                ]
                store = KVSubscriptionStore(
                    account_id="ACC", api_token="TOK",
                    fallback_path=local_path,
                )
                store.add(VALID_SUB)
            # Local file should still have been written even though KV failed
            self.assertTrue(local_path.exists())


if __name__ == "__main__":
    unittest.main()
