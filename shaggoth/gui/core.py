"""Tk-free GUI controller. Pure logic, no import of tkinter, so it runs and
tests on headless boxes (this project's dev box has no ``tkinter`` module at
all). The tkinter shell in :mod:`.tk` is a thin view over this controller.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class Turn:
    """One user message plus the reply it produced."""

    user: str
    text: str
    source: str = "pattern"
    mode: str = "no_drift"
    blocked: bool = False
    reasoning: list = field(default_factory=list)
    entries_used: list = field(default_factory=list)
    new_facts: dict = field(default_factory=dict)


class GUIController:
    """Stateful chat controller for the desktop GUI.

    One instance wraps one :class:`DialogueEngine` and owns a chat session.
    The view layer calls :meth:`send` for each user turn and re-renders from
    :attr:`turns`; nothing here touches the screen.
    """

    def __init__(
        self,
        engine,
        session_id: str | None = None,
        bot_name: str | None = None,
        supervisor=None,
    ):
        self.engine = engine
        self.session_id = session_id or f"gui-{uuid.uuid4().hex[:8]}"
        self.bot_name = bot_name or getattr(engine, "bot_name", "Shaggoth")
        self.turns: list[Turn] = []
        #: Optional :class:`~shaggoth.agents.Supervisor`. The desktop app runs
        #: the crew in-process when settings enable it, which is what makes
        #: the GUI a place the model trains rather than only a place it talks.
        self.supervisor = supervisor

    # -- conversation --------------------------------------------------------

    def send(self, text: str, mode: str | None = None) -> Turn:
        """Run one user turn through the engine and record it."""
        text = (text or "").strip()
        if not text:
            raise ValueError("empty message")
        reply = self.engine.respond(text, session_id=self.session_id, mode=mode)
        turn = Turn(
            user=text,
            text=reply.text,
            source=reply.source,
            mode=getattr(reply, "mode", mode or "no_drift"),
            blocked=reply.blocked,
            reasoning=list(getattr(reply, "reasoning", []) or []),
            entries_used=list(getattr(reply, "entries_used", []) or []),
            new_facts=dict(getattr(reply, "new_facts", {}) or {}),
        )
        self.turns.append(turn)
        return turn

    def reset(self) -> None:
        """Start a fresh conversation (new session id, empty transcript)."""
        self.session_id = f"gui-{uuid.uuid4().hex[:8]}"
        self.turns = []

    # -- status --------------------------------------------------------------

    def status(self) -> dict:
        """Machine-readable status for the view's status bar."""
        model = getattr(self.engine, "model", None)
        knowledge = getattr(self.engine, "knowledge", None)
        if knowledge is not None and hasattr(knowledge, "maybe_reload"):
            try:
                knowledge.maybe_reload()
            except Exception:  # noqa: BLE001 — status must never raise
                pass
            entries = len(getattr(knowledge, "_entries", []) or [])
        else:
            entries = 0
        model_name = type(model).__name__ if model is not None else "none"
        provider = getattr(model, "provider", "") if model is not None else ""
        configured = getattr(model, "configured", False) if model is not None else False
        return {
            "bot_name": self.bot_name,
            "model": model_name,
            "provider": provider,
            "model_configured": bool(configured),
            "knowledge_entries": entries,
            "session_id": self.session_id,
            "turns": len(self.turns),
            "agents": self.agents_status(),
        }

    def agents_status(self) -> dict:
        """What the onboard crew is doing, for the training panel.

        Never raises and never blocks: this is called from the view's refresh
        timer, so an exception here would take the window down on a tick that
        exists only to update a label.
        """
        if self.supervisor is None:
            return {"enabled": False, "running": False, "agents": []}
        try:
            status = self.supervisor.status()
        except Exception:  # noqa: BLE001 — status must never raise
            return {"enabled": True, "running": False, "agents": []}
        return {"enabled": True, **status}

    def agent_lines(self) -> list[str]:
        """One human-readable line per agent, for the training panel."""
        status = self.agents_status()
        if not status.get("enabled"):
            return ["agents: off (set agents.enabled in config/settings.json)"]
        lines = []
        for agent in status.get("agents", []):
            state = "on" if agent["enabled"] else "off"
            detail = f"{agent['runs']} runs"
            if agent["failures"]:
                detail += f", {agent['failures']} failed"
            if agent["skips"]:
                detail += f", {agent['skips']} skipped"
            lines.append(
                f"{agent['name']:<10} {state:<3} every {agent['cadence_minutes']:g}m "
                f"· next in {agent['due_in_seconds']:.0f}s · {detail}"
            )
        return lines or ["no agents registered"]

    def greeting(self) -> str:
        """A fresh opening line assembled from live system state."""
        from ..dialogue.engine import compose_greeting

        status = self.status()
        return compose_greeting(knowledge_count=status["knowledge_entries"])
