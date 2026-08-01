"""One thread, one crew, one status surface.

**Why a single tick thread and not one per agent.** Each loop this package
wraps used to own its own timer. Five timers on a box where the critic already
stands down above load 6.0 means five agents can wake in the same second with
nothing arbitrating between them -- and a whole session of this project's
history went into root-causing 85% idle CPU. The supervisor ticks once a
second, takes at most one due agent per tick, and runs it to completion before
looking at the next. Agents therefore never overlap each other, and the
cadences are a lower bound on how often an agent runs, not a promise.

**Ordering is registration order, and it is a priority.** When several agents
come due in the same tick the earliest-registered one goes first. The default
crew is ordered researcher, grader, curator, gatherer, trainer: learn, then
judge what was learned, then clean up, then fetch more, then retrain on the
result.
"""

from __future__ import annotations

import threading
import time


class Supervisor:
    """Owns a crew of :class:`~.base.Agent` and gives each a turn when due."""

    #: How often the tick thread wakes to look for due agents. Short enough
    #: that a cadence is honoured to the second, long enough to be free.
    TICK_SECONDS = 1.0

    def __init__(self, agents=None, tick_seconds: float | None = None, clock=time.time):
        self.agents = list(agents or [])
        self.tick_seconds = self.TICK_SECONDS if tick_seconds is None else tick_seconds
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._history: list[dict] = []
        self._lock = threading.Lock()
        self.started_at: float = 0.0

    # -- crew ----------------------------------------------------------------

    def add(self, agent) -> None:
        self.agents.append(agent)

    def get(self, name: str):
        for agent in self.agents:
            if agent.name == name:
                return agent
        return None

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self.started_at = self._clock()
        self._thread = threading.Thread(
            target=self._run, name="shaggoth-agents", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # -- work ----------------------------------------------------------------

    def due_agents(self, now: float | None = None) -> list:
        now = self._clock() if now is None else now
        return [a for a in self.agents if a.due(now)]

    def tick(self) -> list:
        """Run at most one due agent. Returns the reports it produced.

        One per tick, not all of them: running the whole due set in a single
        tick is how five agents end up working at once, which is the thing the
        single thread exists to prevent.
        """
        due = self.due_agents()
        if not due:
            return []
        report = due[0].run()
        self._record(report)
        return [report]

    def run_now(self, name: str | None = None) -> list:
        """Run one named agent, or every enabled agent, ignoring cadence.

        Used by ``POST /agents/run``. Cadences are still reset afterwards by
        :meth:`~.base.Agent.run`, so a manual run pushes the next scheduled
        turn out rather than doubling up with it.
        """
        if name is not None:
            agent = self.get(name)
            if agent is None:
                raise KeyError(name)
            report = agent.run()
            self._record(report)
            return [report]

        reports = []
        for agent in self.agents:
            if not agent.enabled:
                continue
            report = agent.run()
            self._record(report)
            reports.append(report)
        return reports

    def _record(self, report) -> None:
        with self._lock:
            self._history.append({"at": self._clock(), **report.as_dict()})
            if len(self._history) > 200:
                del self._history[:-100]

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001
                # Agent.run() already swallows its own failures, so reaching
                # here means the supervisor itself broke. Still must not kill
                # the thread: a dead supervisor looks exactly like an idle one.
                print(f"[agents] supervisor tick failed: {exc}")
            self._stop.wait(self.tick_seconds)

    # -- reporting -----------------------------------------------------------

    def history(self, limit: int = 20) -> list:
        with self._lock:
            return list(self._history[-limit:])

    def status(self) -> dict:
        return {
            "running": self.running,
            "started_at": self.started_at,
            "uptime_seconds": (
                round(self._clock() - self.started_at, 1) if self.started_at else 0.0
            ),
            "agents": [a.status() for a in self.agents],
            "enabled_count": sum(1 for a in self.agents if a.enabled),
            "recent": self.history(10),
        }
