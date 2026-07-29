"""Slack integration: post messages from Shaggoth to a Slack channel.

Set SLACK_BOT_TOKEN (xoxb-...) to enable.  SLACK_CHANNEL_ID overrides the
default #shaggoth channel created for this deployment.

Usage:
    sender = SlackSender()
    if sender.configured:
        sender.send("I just read about aeroponics.")
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request

#: Default channel created for this deployment.
DEFAULT_CHANNEL_ID = "C0BLD1P9TC5"  # #shaggoth


class SlackSender:
    """Posts text messages to a Slack channel via the Web API."""

    def __init__(
        self,
        token: str | None = None,
        channel_id: str | None = None,
    ) -> None:
        self._token = token or os.environ.get("SLACK_BOT_TOKEN") or ""
        self._channel = (
            channel_id
            or os.environ.get("SLACK_CHANNEL_ID")
            or DEFAULT_CHANNEL_ID
        )

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def send(self, text: str) -> bool:
        """Post ``text`` to the Slack channel. Returns True on success."""
        if not self.configured:
            return False
        try:
            payload = json.dumps(
                {"channel": self._channel, "text": text}
            ).encode()
            req = urllib.request.Request(
                "https://slack.com/api/chat.postMessage",
                data=payload,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if not result.get("ok"):
                    print(f"[slack] API error: {result.get('error')}")
                return bool(result.get("ok"))
        except Exception as exc:
            print(f"[slack] send failed: {exc}")
            return False

    def send_async(self, text: str) -> None:
        """Fire-and-forget send on a daemon thread."""
        threading.Thread(
            target=self.send, args=(text,), name="shaggoth-slack", daemon=True
        ).start()
