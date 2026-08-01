"""The agent contract: one unit of work, one cadence, one place to fail.

Every loop this package wraps already existed -- the curiosity scheduler, the
critic, the dedup planner, the scraper, the promotion gate. What did not exist
was a single place to ask "what is training this thing right now, when did it
last run, and did it work". That is all an :class:`Agent` is.

Two rules shape the base class, both learned from the loops it wraps:

1. **run() never raises.** Every background loop in this codebase already
   carries a comment about why a dead thread is worse than a broken one: from
   outside, a thread that died looks exactly like a thread that is idle, and
   the daemon goes on answering requests while silently never learning again.
   An agent that throws would take the supervisor's tick thread with it and
   stop the whole crew, so failures are caught, counted and exposed in
   :meth:`status`.

2. **An agent wraps a unit of work, never a thread.** ``run()`` performs one
   cycle; it must not call ``start()`` on the loop underneath. If it did, that
   loop's own timer and the supervisor's cadence would both fire and the work
   would happen twice -- twice the research, twice the load, and a status
   surface that reports half of what is actually happening.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


class AgentSkipped(Exception):
    """Raised by :meth:`Agent.work` when there was nothing to do.

    A skip is not a failure. The gatherer with no unscraped seeds and the
    grader with no local teacher are both working correctly; counting them as
    errors would make a healthy crew look broken and bury the real failures.
    """


@dataclass
class AgentStats:
    runs: int = 0
    failures: int = 0
    skips: int = 0
    last_run: float = 0.0
    last_skip_reason: str = ""
    last_error: str = ""
    last_detail: dict = field(default_factory=dict)
    seconds_spent: float = 0.0

    def as_dict(self) -> dict:
        return {
            "runs": self.runs,
            "failures": self.failures,
            "skips": self.skips,
            "last_run": self.last_run,
            "last_skip_reason": self.last_skip_reason,
            "last_error": self.last_error,
            "last_detail": self.last_detail,
            "seconds_spent": round(self.seconds_spent, 1),
            "avg_seconds": (
                round(self.seconds_spent / self.runs, 1) if self.runs else 0.0
            ),
        }


@dataclass
class AgentReport:
    """What one :meth:`Agent.run` did. Returned, and also recorded in stats."""

    name: str
    ran: bool
    skipped: bool = False
    reason: str = ""
    detail: dict = field(default_factory=dict)
    error: str = ""
    seconds: float = 0.0

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "ran": self.ran,
            "skipped": self.skipped,
            "reason": self.reason,
            "detail": self.detail,
            "error": self.error,
            "seconds": round(self.seconds, 2),
        }


class Agent:
    """One onboard trainer. Subclasses implement :meth:`work`.

    ``cadence_minutes`` is how often the supervisor should offer it a turn.
    The first turn comes one full cadence *after* start, never at start: five
    agents all firing in the same second the server comes up is the load spike
    this design exists to avoid, and it would land while the process is still
    warming its knowledge index.
    """

    #: Stable identifier, used as the key in ``/agents`` and in settings.
    name = "agent"
    #: One line, shown in the GUI and the API. Say what it trains, not how.
    role = ""
    default_cadence_minutes = 15.0

    def __init__(
        self,
        cadence_minutes: float | None = None,
        enabled: bool = True,
        clock=time.time,
    ) -> None:
        cadence = (
            self.default_cadence_minutes if cadence_minutes is None else cadence_minutes
        )
        # A zero or negative cadence would busy-loop the supervisor's tick
        # thread against this one agent. Clamp rather than raise: a bad number
        # in settings.json should degrade, not refuse to boot the server.
        self.cadence_seconds = max(60.0, float(cadence) * 60.0)
        self.enabled = bool(enabled)
        self._clock = clock
        self.stats = AgentStats()
        self._next_due = self._clock() + self.cadence_seconds

    # -- scheduling ----------------------------------------------------------

    def due(self, now: float | None = None) -> bool:
        now = self._clock() if now is None else now
        return self.enabled and now >= self._next_due

    def due_in(self, now: float | None = None) -> float:
        now = self._clock() if now is None else now
        return max(0.0, self._next_due - now)

    def reschedule(self, now: float | None = None) -> None:
        """Push the next turn one cadence out from *now*, not from the due time.

        Measuring from now means a long run does not immediately become due
        again the moment it finishes. The trainer takes minutes; scheduling
        from the old due time would hand it back-to-back turns and starve the
        rest of the crew.
        """
        now = self._clock() if now is None else now
        self._next_due = now + self.cadence_seconds

    # -- work ----------------------------------------------------------------

    def work(self) -> dict:
        """Do one unit of work. Return a JSON-safe dict describing it.

        Raise :class:`AgentSkipped` when there is nothing to do.
        """
        raise NotImplementedError

    def run(self) -> AgentReport:
        """One turn. Records stats, reschedules, and never raises."""
        started = self._clock()
        try:
            detail = self.work() or {}
        except AgentSkipped as exc:
            reason = str(exc) or "nothing to do"
            self.stats.skips += 1
            self.stats.last_skip_reason = reason
            self.reschedule()
            return AgentReport(
                name=self.name,
                ran=False,
                skipped=True,
                reason=reason,
                seconds=self._clock() - started,
            )
        except Exception as exc:  # noqa: BLE001 -- see module docstring, rule 1
            elapsed = self._clock() - started
            self.stats.failures += 1
            self.stats.last_error = f"{type(exc).__name__}: {exc}"[:200]
            self.stats.seconds_spent += elapsed
            self.reschedule()
            print(f"[agents] {self.name} failed: {exc}")
            return AgentReport(
                name=self.name,
                ran=False,
                error=self.stats.last_error,
                seconds=elapsed,
            )

        elapsed = self._clock() - started
        self.stats.runs += 1
        self.stats.last_run = self._clock()
        self.stats.last_detail = detail
        self.stats.seconds_spent += elapsed
        self.reschedule()
        return AgentReport(name=self.name, ran=True, detail=detail, seconds=elapsed)

    # -- reporting -----------------------------------------------------------

    def status(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "enabled": self.enabled,
            "cadence_minutes": round(self.cadence_seconds / 60.0, 2),
            "due_in_seconds": round(self.due_in(), 1),
            **self.stats.as_dict(),
        }
