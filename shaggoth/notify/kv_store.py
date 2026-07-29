"""Cloudflare KV-backed push subscription store.

Subscriptions stored in KV survive server restarts and are visible across
any future instances.  Falls back silently to local file storage when
Cloudflare credentials are absent.

Required env vars:
    CLOUDFLARE_ACCOUNT_ID
    CLOUDFLARE_API_TOKEN

Optional:
    CLOUDFLARE_KV_NAMESPACE_ID  (defaults to the namespace created for Shaggoth)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from .push import SubscriptionStore, is_valid_subscription, subscription_key

_DEFAULT_NAMESPACE_ID = "18c863e25c74401594dbc464cb50970d"  # shaggoth-push-subscriptions
_KV_KEY = "push_subscriptions"


class KVSubscriptionStore(SubscriptionStore):
    """Push subscription store backed by Cloudflare KV, with local-file fallback."""

    def __init__(
        self,
        account_id: Optional[str] = None,
        api_token: Optional[str] = None,
        namespace_id: Optional[str] = None,
        fallback_path=None,
    ) -> None:
        self._account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID") or ""
        self._api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN") or ""
        self._namespace_id = (
            namespace_id
            or os.environ.get("CLOUDFLARE_KV_NAMESPACE_ID")
            or _DEFAULT_NAMESPACE_ID
        )
        # SubscriptionStore.__init__ calls _load(), so init fields first.
        super().__init__(path=fallback_path)

    @property
    def kv_configured(self) -> bool:
        return bool(self._account_id and self._api_token)

    def _kv_url(self) -> str:
        return (
            f"https://api.cloudflare.com/client/v4/accounts/{self._account_id}"
            f"/storage/kv/namespaces/{self._namespace_id}/values/{_KV_KEY}"
        )

    def _load(self) -> None:
        # Try KV first; fall back to the local file on any failure.
        if self.kv_configured:
            try:
                req = urllib.request.Request(
                    self._kv_url(),
                    headers={"Authorization": f"Bearer {self._api_token}"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                    if isinstance(data, list):
                        for item in data:
                            if is_valid_subscription(item):
                                self._subs[subscription_key(item)] = item
                return
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    print(f"[kv] load failed (HTTP {exc.code}), falling back to file")
            except Exception as exc:
                print(f"[kv] load failed ({exc}), falling back to file")

        # Fallback: use the parent's file-based load.
        super()._load()

    def _save(self) -> None:
        if self.kv_configured:
            try:
                payload = json.dumps(list(self._subs.values())).encode()
                req = urllib.request.Request(
                    self._kv_url(),
                    data=payload,
                    method="PUT",
                    headers={
                        "Authorization": f"Bearer {self._api_token}",
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp.read()
            except Exception as exc:
                print(f"[kv] save failed: {exc}")
                # Fall through to also write the local file as backup.

        # Always write the local file too (cheap, instant, offline-available).
        super()._save()
