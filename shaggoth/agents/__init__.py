"""Onboard AI agents that train Shaggoth while it runs.

The crew is **off by default**. ``settings["agents"]["enabled"]`` must be true
before :func:`build_crew` returns anything the server will start, so an
existing deployment picks up this module and behaves exactly as it did before.
Turning it on is a deliberate act, because these agents consume the same CPU
that answers chat.
"""

from __future__ import annotations

from .base import Agent, AgentReport, AgentSkipped, AgentStats
from .crew import (
    CuratorAgent,
    GathererAgent,
    GraderAgent,
    ResearcherAgent,
    TrainerAgent,
)
from .supervisor import Supervisor

__all__ = [
    "Agent",
    "AgentReport",
    "AgentSkipped",
    "AgentStats",
    "CuratorAgent",
    "GathererAgent",
    "GraderAgent",
    "ResearcherAgent",
    "TrainerAgent",
    "Supervisor",
    "DEFAULT_AGENT_SETTINGS",
    "agents_enabled",
    "build_crew",
]


#: Cadences chosen to match the loops being wrapped: the curiosity scheduler
#: already ran every 15 minutes and the critic idled 5 minutes between
#: batches, so the researcher and grader keep the behaviour a running box
#: already has. Curator and gatherer are hourly; the trainer is nightly
#: because retraining reads the whole corpus.
DEFAULT_AGENT_SETTINGS: dict = {
    "enabled": False,
    "researcher": {"enabled": True, "cadence_minutes": 15},
    "grader": {"enabled": True, "cadence_minutes": 5},
    # apply=False: the curator reports duplicates and moves nothing until
    # someone opts in. See CuratorAgent for why that default is not timidity.
    "curator": {"enabled": True, "cadence_minutes": 60, "apply": False},
    "gatherer": {"enabled": True, "cadence_minutes": 60, "max_pages": 5},
    "trainer": {"enabled": True, "cadence_minutes": 1440},
}


def _config(settings: dict | None, name: str) -> dict:
    """Merged per-agent config: defaults, overlaid with settings.json."""
    merged = dict(DEFAULT_AGENT_SETTINGS[name])
    section = (settings or {}).get("agents") or {}
    override = section.get(name)
    if isinstance(override, dict):
        merged.update(override)
    return merged


def agents_enabled(settings: dict | None) -> bool:
    section = (settings or {}).get("agents") or {}
    return bool(section.get("enabled", DEFAULT_AGENT_SETTINGS["enabled"]))


def build_crew(
    engine,
    scheduler=None,
    critic=None,
    scraper=None,
    settings: dict | None = None,
) -> Supervisor:
    """Assemble the crew in priority order.

    Every agent is registered even when the thing it wraps is missing. An
    agent that is absent from ``/agents`` is indistinguishable from one that
    was never built; one that is present and reporting ``skips`` with the
    reason ``"no scraper"`` tells you what is actually wrong.
    """
    knowledge = getattr(engine, "knowledge", None)
    markov_path = (settings or {}).get("markov_model_path")

    researcher_cfg = _config(settings, "researcher")
    grader_cfg = _config(settings, "grader")
    curator_cfg = _config(settings, "curator")
    gatherer_cfg = _config(settings, "gatherer")
    trainer_cfg = _config(settings, "trainer")

    return Supervisor(
        [
            ResearcherAgent(
                scheduler,
                enabled=researcher_cfg["enabled"],
                cadence_minutes=researcher_cfg["cadence_minutes"],
            ),
            GraderAgent(
                critic,
                enabled=grader_cfg["enabled"],
                cadence_minutes=grader_cfg["cadence_minutes"],
            ),
            CuratorAgent(
                knowledge,
                apply=curator_cfg["apply"],
                enabled=curator_cfg["enabled"],
                cadence_minutes=curator_cfg["cadence_minutes"],
            ),
            GathererAgent(
                scraper,
                max_pages=gatherer_cfg["max_pages"],
                enabled=gatherer_cfg["enabled"],
                cadence_minutes=gatherer_cfg["cadence_minutes"],
            ),
            TrainerAgent(
                engine,
                scraper=scraper,
                markov_path=markov_path,
                enabled=trainer_cfg["enabled"],
                cadence_minutes=trainer_cfg["cadence_minutes"],
            ),
        ]
    )
