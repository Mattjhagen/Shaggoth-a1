"""Web push: how Shaggoth says something without being asked first.

Two pieces:

* :class:`SubscriptionStore` -- the browsers that have agreed to hear from it,
  persisted as JSON so they survive a restart.
* :class:`PushSender` -- delivery, on a background thread, best-effort.

**Nothing here may raise into a caller.** Sends are triggered from the request
handler and from the curiosity scheduler's thread; a dead phone, an expired
subscription, or a missing dependency must never take down a chat reply or
kill the learning loop. Failures are logged and the offending subscription is
dropped when the push service says it is gone.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..config import CONFIG_DIR, DATA_DIR

VAPID_PATH = CONFIG_DIR / "vapid.json"
SUBSCRIPTIONS_PATH = DATA_DIR / "push_subscriptions.json"

#: A push service returns these once a subscription is permanently dead --
#: the browser was uninstalled, or the user revoked permission. Anything else
#: (network blip, 5xx) is transient and the subscription is kept.
_DEAD_STATUSES = (404, 410)

#: Notifications are rate-limited per subscription. Shaggoth researches on a
#: 15-minute timer and would otherwise buzz a phone all night.
DEFAULT_MIN_INTERVAL_SECONDS = 3600.0


@dataclass
class VapidConfig:
    private_key: str = ""
    public_key: str = ""
    subject: str = "mailto:admin@localhost"

    @property
    def configured(self) -> bool:
        return bool(self.private_key and self.public_key)


def load_vapid(path: Optional[Path] = None) -> VapidConfig:
    """Read the VAPID keypair, or return an unconfigured stub.

    Missing keys disable push rather than crashing the server: this is an
    optional feature and a fresh checkout has no keys.
    """
    path = Path(path) if path else VAPID_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return VapidConfig()
    if not isinstance(data, dict):
        return VapidConfig()
    return VapidConfig(
        private_key=str(data.get("private_key") or ""),
        public_key=str(data.get("public_key") or ""),
        subject=str(data.get("subject") or "mailto:admin@localhost"),
    )


def subscription_key(subscription: dict) -> str:
    """Stable identity for a subscription: its endpoint URL."""
    if not isinstance(subscription, dict):
        return ""
    return str(subscription.get("endpoint") or "")


def is_valid_subscription(subscription: Any) -> bool:
    """Whether a payload has the shape the Push API actually produces."""
    if not isinstance(subscription, dict):
        return False
    if not subscription_key(subscription).startswith(("http://", "https://")):
        return False
    keys = subscription.get("keys")
    return isinstance(keys, dict) and bool(keys.get("p256dh")) and bool(keys.get("auth"))


class SubscriptionStore:
    """The set of browsers that have opted in, persisted to disk."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else SUBSCRIPTIONS_PATH
        self._lock = threading.Lock()
        self._subs: dict[str, dict] = {}
        self._last_sent: dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(raw, list):
            for item in raw:
                if is_valid_subscription(item):
                    self._subs[subscription_key(item)] = item

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(list(self._subs.values()), indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass  # Losing the file is not worth failing a request over.

    def add(self, subscription: dict) -> bool:
        """Register a browser. Returns False for a malformed payload."""
        if not is_valid_subscription(subscription):
            return False
        with self._lock:
            # Keyed by endpoint, so re-subscribing replaces rather than
            # duplicates -- browsers re-issue the same endpoint on every load.
            self._subs[subscription_key(subscription)] = subscription
            self._save()
        return True

    def remove(self, endpoint: str) -> bool:
        with self._lock:
            existed = self._subs.pop(endpoint, None) is not None
            self._last_sent.pop(endpoint, None)
            if existed:
                self._save()
        return existed

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._subs.values())

    def __len__(self) -> int:
        with self._lock:
            return len(self._subs)

    # -- rate limiting ----------------------------------------------------

    def may_send(self, endpoint: str, min_interval: float, now: Optional[float] = None) -> bool:
        """Whether this subscription is due another notification."""
        now = time.time() if now is None else now
        with self._lock:
            last = self._last_sent.get(endpoint)
        return last is None or (now - last) >= min_interval

    def mark_sent(self, endpoint: str, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self._last_sent[endpoint] = now


class PushSender:
    """Delivers notifications, off the calling thread, best-effort."""

    def __init__(
        self,
        store: Optional[SubscriptionStore] = None,
        vapid: Optional[VapidConfig] = None,
        min_interval: float = DEFAULT_MIN_INTERVAL_SECONDS,
    ) -> None:
        self.store = store or SubscriptionStore()
        self.vapid = vapid or load_vapid()
        self.min_interval = min_interval

    @property
    def available(self) -> bool:
        """True when push can actually be sent.

        Requires both a VAPID keypair and the optional ``pywebpush``
        dependency. Absent either, everything here degrades to a no-op.
        """
        if not self.vapid.configured:
            return False
        try:
            import pywebpush  # noqa: F401
        except ImportError:
            return False
        return True

    def status(self) -> dict:
        return {
            "available": self.available,
            "configured": self.vapid.configured,
            "public_key": self.vapid.public_key,
            "subscriptions": len(self.store),
            "min_interval_seconds": self.min_interval,
        }

    # -- sending ----------------------------------------------------------

    def notify(self, title: str, body: str, url: str = "/", tag: str = "shaggoth",
               respect_rate_limit: bool = True) -> None:
        """Fire and forget. Returns immediately."""
        if not self.available:
            return
        payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
        thread = threading.Thread(
            target=self._send_all,
            args=(payload, respect_rate_limit),
            name="shaggoth-push",
            daemon=True,
        )
        thread.start()

    def send_now(self, title: str, body: str, url: str = "/", tag: str = "shaggoth",
                 respect_rate_limit: bool = False) -> dict:
        """Synchronous send, for the manual test endpoint. Never raises."""
        if not self.available:
            return {"sent": 0, "failed": 0, "reason": "push not configured"}
        payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
        return self._send_all(payload, respect_rate_limit)

    def _send_all(self, payload: str, respect_rate_limit: bool) -> dict:
        sent = failed = skipped = 0
        for subscription in self.store.all():
            endpoint = subscription_key(subscription)
            if respect_rate_limit and not self.store.may_send(endpoint, self.min_interval):
                skipped += 1
                continue
            if self._send_one(subscription, payload):
                self.store.mark_sent(endpoint)
                sent += 1
            else:
                failed += 1
        return {"sent": sent, "failed": failed, "skipped": skipped}

    def _send_one(self, subscription: dict, payload: str) -> bool:
        from pywebpush import WebPushException, webpush

        try:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=self.vapid.private_key,
                vapid_claims={"sub": self.vapid.subject},
                timeout=10,
            )
            return True
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in _DEAD_STATUSES:
                # The browser is gone for good. Drop it rather than retrying
                # forever on every future notification.
                self.store.remove(subscription_key(subscription))
                print(f"[push] dropped dead subscription ({status})")
            else:
                print(f"[push] send failed: {exc}")
            return False
        except Exception as exc:  # noqa: BLE001
            print(f"[push] send error: {exc}")
            return False
