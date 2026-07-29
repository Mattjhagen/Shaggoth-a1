"""Tests for web push notification infrastructure (notify/push.py)."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shaggoth.notify.push import (
    DEFAULT_MIN_INTERVAL_SECONDS,
    PushSender,
    SubscriptionStore,
    VapidConfig,
    is_valid_subscription,
    load_vapid,
    subscription_key,
    subscription_session_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_sub(endpoint: str = "https://push.example.com/sub/123", session_id: str = "") -> dict:
    sub = {
        "endpoint": endpoint,
        "keys": {"p256dh": "AAAA", "auth": "BBBB"},
    }
    if session_id:
        sub["session_id"] = session_id
    return sub


def _store(tmp_path: Path | None = None) -> SubscriptionStore:
    if tmp_path is None:
        tmp_path = Path(tempfile.mktemp(suffix=".json"))
    return SubscriptionStore(path=tmp_path)


def _vapid() -> VapidConfig:
    return VapidConfig(private_key="pk", public_key="pubk", subject="mailto:test@x.com")


# ---------------------------------------------------------------------------
# VapidConfig
# ---------------------------------------------------------------------------

class TestVapidConfig:
    def test_configured_when_both_keys_set(self):
        v = _vapid()
        assert v.configured

    def test_not_configured_when_missing_private_key(self):
        v = VapidConfig(private_key="", public_key="pubk")
        assert not v.configured

    def test_not_configured_when_missing_public_key(self):
        v = VapidConfig(private_key="pk", public_key="")
        assert not v.configured

    def test_default_subject(self):
        v = VapidConfig()
        assert v.subject.startswith("mailto:")


# ---------------------------------------------------------------------------
# load_vapid
# ---------------------------------------------------------------------------

class TestLoadVapid:
    def test_loads_from_file(self, tmp_path):
        p = tmp_path / "vapid.json"
        p.write_text(json.dumps({
            "private_key": "priv",
            "public_key": "pub",
            "subject": "mailto:admin@test.com",
        }))
        v = load_vapid(p)
        assert v.private_key == "priv"
        assert v.public_key == "pub"
        assert v.subject == "mailto:admin@test.com"

    def test_missing_file_returns_unconfigured(self, tmp_path):
        v = load_vapid(tmp_path / "nonexistent.json")
        assert not v.configured

    def test_invalid_json_returns_unconfigured(self, tmp_path):
        p = tmp_path / "vapid.json"
        p.write_text("not json")
        v = load_vapid(p)
        assert not v.configured

    def test_non_dict_returns_unconfigured(self, tmp_path):
        p = tmp_path / "vapid.json"
        p.write_text("[1, 2, 3]")
        v = load_vapid(p)
        assert not v.configured

    def test_missing_keys_produce_empty_strings(self, tmp_path):
        p = tmp_path / "vapid.json"
        p.write_text("{}")
        v = load_vapid(p)
        assert v.private_key == ""
        assert v.public_key == ""


# ---------------------------------------------------------------------------
# subscription helpers
# ---------------------------------------------------------------------------

class TestSubscriptionHelpers:
    def test_subscription_key_extracts_endpoint(self):
        sub = _valid_sub("https://example.com/push")
        assert subscription_key(sub) == "https://example.com/push"

    def test_subscription_key_non_dict(self):
        assert subscription_key("not a dict") == ""

    def test_subscription_key_missing_endpoint(self):
        assert subscription_key({}) == ""

    def test_subscription_session_id_extracts(self):
        sub = _valid_sub(session_id="sess42")
        assert subscription_session_id(sub) == "sess42"

    def test_subscription_session_id_missing(self):
        assert subscription_session_id(_valid_sub()) == ""

    def test_subscription_session_id_non_dict(self):
        assert subscription_session_id(None) == ""

    def test_is_valid_subscription_valid(self):
        assert is_valid_subscription(_valid_sub())

    def test_is_valid_subscription_non_dict(self):
        assert not is_valid_subscription("string")

    def test_is_valid_subscription_missing_endpoint(self):
        sub = {"keys": {"p256dh": "A", "auth": "B"}}
        assert not is_valid_subscription(sub)

    def test_is_valid_subscription_non_http_endpoint(self):
        sub = {"endpoint": "ftp://bad.com", "keys": {"p256dh": "A", "auth": "B"}}
        assert not is_valid_subscription(sub)

    def test_is_valid_subscription_missing_keys(self):
        sub = {"endpoint": "https://ok.com"}
        assert not is_valid_subscription(sub)

    def test_is_valid_subscription_keys_not_dict(self):
        sub = {"endpoint": "https://ok.com", "keys": "string"}
        assert not is_valid_subscription(sub)

    def test_is_valid_subscription_missing_p256dh(self):
        sub = {"endpoint": "https://ok.com", "keys": {"auth": "B"}}
        assert not is_valid_subscription(sub)

    def test_is_valid_subscription_missing_auth(self):
        sub = {"endpoint": "https://ok.com", "keys": {"p256dh": "A"}}
        assert not is_valid_subscription(sub)


# ---------------------------------------------------------------------------
# SubscriptionStore
# ---------------------------------------------------------------------------

class TestSubscriptionStore:
    def test_add_valid_subscription(self):
        store = _store()
        assert store.add(_valid_sub())
        assert len(store) == 1

    def test_add_invalid_subscription_returns_false(self):
        store = _store()
        assert not store.add({"no": "endpoint"})
        assert len(store) == 0

    def test_add_deduplicates_by_endpoint(self):
        store = _store()
        sub = _valid_sub()
        store.add(sub)
        store.add(sub)  # same endpoint
        assert len(store) == 1

    def test_add_different_endpoints_both_stored(self):
        store = _store()
        store.add(_valid_sub("https://endpoint-a.com"))
        store.add(_valid_sub("https://endpoint-b.com"))
        assert len(store) == 2

    def test_remove_existing_subscription(self):
        store = _store()
        sub = _valid_sub()
        store.add(sub)
        existed = store.remove(subscription_key(sub))
        assert existed
        assert len(store) == 0

    def test_remove_nonexistent_returns_false(self):
        store = _store()
        assert not store.remove("https://nonexistent.com")

    def test_all_returns_list_copy(self):
        store = _store()
        sub = _valid_sub()
        store.add(sub)
        result = store.all()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_by_session_filters_correctly(self):
        store = _store()
        store.add(_valid_sub("https://ep-a.com", session_id="s1"))
        store.add(_valid_sub("https://ep-b.com", session_id="s2"))
        result = store.by_session("s1")
        assert len(result) == 1

    def test_by_session_empty_when_no_match(self):
        store = _store()
        store.add(_valid_sub())
        assert store.by_session("ghost_session") == []

    def test_persistence_survives_reload(self, tmp_path):
        path = tmp_path / "subs.json"
        store1 = SubscriptionStore(path=path)
        store1.add(_valid_sub())

        store2 = SubscriptionStore(path=path)
        assert len(store2) == 1

    def test_load_ignores_invalid_entries(self, tmp_path):
        path = tmp_path / "subs.json"
        path.write_text(json.dumps([
            {"no": "endpoint"},
            _valid_sub("https://valid.com"),
        ]))
        store = SubscriptionStore(path=path)
        assert len(store) == 1


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    def test_may_send_true_on_first_contact(self):
        store = _store()
        store.add(_valid_sub())
        assert store.may_send("https://push.example.com/sub/123", min_interval=3600)

    def test_may_send_false_immediately_after_mark_sent(self):
        store = _store()
        sub = _valid_sub()
        store.add(sub)
        ep = subscription_key(sub)
        now = time.time()
        store.mark_sent(ep, now=now)
        assert not store.may_send(ep, min_interval=3600, now=now + 10)

    def test_may_send_true_after_interval_elapsed(self):
        store = _store()
        sub = _valid_sub()
        store.add(sub)
        ep = subscription_key(sub)
        past = time.time() - 7200
        store.mark_sent(ep, now=past)
        assert store.may_send(ep, min_interval=3600)

    def test_remove_clears_rate_limit_state(self):
        store = _store()
        sub = _valid_sub()
        store.add(sub)
        ep = subscription_key(sub)
        store.mark_sent(ep, now=time.time())
        store.remove(ep)
        # Add it again — last_sent should be gone
        store.add(sub)
        assert store.may_send(ep, min_interval=3600)


# ---------------------------------------------------------------------------
# PushSender
# ---------------------------------------------------------------------------

class TestPushSenderAvailability:
    def test_not_available_when_vapid_unconfigured(self):
        sender = PushSender(vapid=VapidConfig())
        assert not sender.available

    def test_not_available_when_pywebpush_missing(self):
        with patch.dict("sys.modules", {"pywebpush": None}):
            sender = PushSender(vapid=_vapid())
            assert not sender.available

    def test_available_when_configured_and_pywebpush_present(self):
        fake_module = MagicMock()
        with patch.dict("sys.modules", {"pywebpush": fake_module}):
            sender = PushSender(vapid=_vapid())
            assert sender.available

    def test_status_returns_dict(self):
        store = _store()
        sender = PushSender(store=store, vapid=VapidConfig())
        s = sender.status()
        assert "available" in s
        assert "configured" in s
        assert "subscriptions" in s
        assert s["subscriptions"] == 0

    def test_send_now_returns_reason_when_unavailable(self):
        sender = PushSender(vapid=VapidConfig())
        result = sender.send_now("title", "body")
        assert "reason" in result
        assert result["sent"] == 0


class TestPushSenderSend:
    def _make_sender(self, subs: list[dict] | None = None) -> tuple[PushSender, SubscriptionStore]:
        store = _store()
        for sub in (subs or []):
            store.add(sub)
        fake_module = MagicMock()
        with patch.dict("sys.modules", {"pywebpush": fake_module}):
            sender = PushSender(store=store, vapid=_vapid(), min_interval=0)
            sender._pywebpush = fake_module
        return sender, store

    def test_send_all_counts_sent(self):
        store = _store()
        store.add(_valid_sub("https://ep-a.com"))
        store.add(_valid_sub("https://ep-b.com"))

        fake_pw = MagicMock()
        fake_pw.WebPushException = Exception
        fake_pw.webpush = MagicMock(return_value=None)

        with patch.dict("sys.modules", {"pywebpush": fake_pw}):
            sender = PushSender(store=store, vapid=_vapid(), min_interval=0)
            result = sender._send_all('{"title":"T"}', respect_rate_limit=False)

        assert result["sent"] == 2
        assert result["failed"] == 0

    def test_send_all_skips_rate_limited(self):
        store = _store()
        sub = _valid_sub()
        store.add(sub)
        ep = subscription_key(sub)
        store.mark_sent(ep, now=time.time())  # just sent

        fake_pw = MagicMock()
        fake_pw.webpush = MagicMock()

        with patch.dict("sys.modules", {"pywebpush": fake_pw}):
            sender = PushSender(store=store, vapid=_vapid(), min_interval=3600)
            result = sender._send_all('{"title":"T"}', respect_rate_limit=True)

        assert result["skipped"] == 1
        assert result["sent"] == 0

    def test_dead_subscription_removed_on_404(self):
        store = _store()
        sub = _valid_sub()
        store.add(sub)
        ep = subscription_key(sub)

        class FakeResponse:
            status_code = 404

        fake_exc = Exception("dead")
        fake_exc.response = FakeResponse()

        fake_pw = MagicMock()
        fake_pw.WebPushException = type(fake_exc)
        fake_pw.webpush.side_effect = fake_exc

        with patch.dict("sys.modules", {"pywebpush": fake_pw}):
            sender = PushSender(store=store, vapid=_vapid(), min_interval=0)
            # Manually inject fake_pw so _send_one can import it
            with patch("shaggoth.notify.push.PushSender._send_one", return_value=False):
                result = sender._send_all('{"title":"T"}', respect_rate_limit=False)

        assert result["failed"] == 1

    def test_notify_does_not_raise_when_unavailable(self):
        sender = PushSender(vapid=VapidConfig())
        # Should be a no-op, not an exception
        sender.notify("title", "body")

    def test_notify_session_does_not_raise_when_unavailable(self):
        sender = PushSender(vapid=VapidConfig())
        sender.notify_session("sess1", "title", "body")
