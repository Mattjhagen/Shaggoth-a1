"""One crawl at a time per site, run off the request thread.

A crawl is bounded at 25 pages and every fetch is paced at 1s per origin, so
a synchronous crawl endpoint would hold the connection open for the better
part of a minute -- longer than some proxies in front of this box will wait.
A client timeout would then look like a failed crawl when the crawl actually
succeeded, and the caller's obvious response is to retry, which starts a
second crawl of the same host. So POST starts a job and GET reports on it.

The concurrency caps are the other half of that. One job per site (refused,
not queued) means a retry loop cannot multiply into concurrent fetches of one
customer's server; a global cap means N tenants cannot together saturate this
box's uplink.

The verification gate is checked *here*, synchronously, before a thread is
started -- so an unverified site gets a 4xx rather than a 202 followed by a
job that fails out of band. :func:`~shaggoth.sites.crawl.crawl_site` checks it
again inside the thread. That duplication is deliberate: the library-level
check is the real gate and must hold on its own, and this one exists only so
the HTTP response can be honest.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .crawl import CrawlNotPermitted, crawl_site
from .registry import SiteRegistry

#: How many crawls may run across all tenants at once.
MAX_CONCURRENT_CRAWLS = 2

#: Finished jobs are kept this long so a caller that polls slowly still sees
#: its result. Without an expiry the map is a small permanent leak.
JOB_RETENTION_SECONDS = 3600.0


class CrawlAlreadyRunning(RuntimeError):
    """A crawl for this site (or too many crawls overall) is already going."""


@dataclass
class CrawlJob:
    site_id: str
    domain: str
    state: str = "running"          # running | done | failed
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    error: str = ""
    report: dict[str, Any] | None = None

    @property
    def running(self) -> bool:
        return self.state == "running"

    def as_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "domain": self.domain,
            "state": self.state,
            "started_at": self.started_at,
            "finished_at": self.finished_at or None,
            "error": self.error,
            "report": self.report,
        }


class CrawlJobs:
    """Tracks the in-flight and most recent crawl for each site."""

    def __init__(self, runner: Callable[..., Any] = crawl_site):
        # Injectable so tests do not have to reach the network to exercise
        # the gate, the concurrency caps or the job lifecycle.
        self._runner = runner
        self._lock = threading.Lock()
        self._jobs: dict[str, CrawlJob] = {}

    # ------------------------------------------------------------- lookup

    def get(self, site_id: str) -> CrawlJob | None:
        with self._lock:
            return self._jobs.get(site_id)

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for job in self._jobs.values() if job.running)

    def _reap(self, now: float) -> None:
        """Drop finished jobs nobody is going to poll for. Caller holds lock."""
        for site_id, job in list(self._jobs.items()):
            if not job.running and job.finished_at < now - JOB_RETENTION_SECONDS:
                self._jobs.pop(site_id, None)

    # -------------------------------------------------------------- start

    def start(self, registry: SiteRegistry, site_id: str, **bounds: Any) -> CrawlJob:
        """Begin a crawl, or explain why not.

        Raises :class:`~shaggoth.sites.crawl.CrawlNotPermitted` for an unknown
        or unverified site and :class:`CrawlAlreadyRunning` when a slot is not
        free. Both are raised before any thread exists, so the caller can turn
        them straight into a status code.
        """
        record = registry.get(site_id)
        if record is None:
            raise CrawlNotPermitted(f"no such site: {site_id!r}")
        if not record.verified:
            raise CrawlNotPermitted(
                f"{record.domain} is {record.status}, not verified. Prove "
                f"ownership before crawling it."
            )

        now = time.time()
        with self._lock:
            self._reap(now)
            existing = self._jobs.get(site_id)
            if existing is not None and existing.running:
                raise CrawlAlreadyRunning(
                    f"a crawl of {record.domain} is already running"
                )
            if sum(1 for j in self._jobs.values() if j.running) >= MAX_CONCURRENT_CRAWLS:
                raise CrawlAlreadyRunning(
                    f"the server is already running {MAX_CONCURRENT_CRAWLS} "
                    f"crawls; try again shortly"
                )
            # The slot is claimed while the lock is held, so two simultaneous
            # POSTs cannot both see a free slot and both start.
            job = CrawlJob(site_id=site_id, domain=record.domain, started_at=now)
            self._jobs[site_id] = job

        thread = threading.Thread(
            target=self._run,
            args=(registry, site_id, job, bounds),
            name=f"crawl-{site_id}",
            daemon=True,
        )
        thread.start()
        return job

    def _run(self, registry: SiteRegistry, site_id: str, job: CrawlJob,
             bounds: dict[str, Any]) -> None:
        try:
            report = self._runner(registry, site_id, **bounds)
        except CrawlNotPermitted as exc:
            # Only reachable if the site was un-verified between the check
            # above and now. Recorded rather than swallowed.
            job.error = str(exc)
            job.state = "failed"
        except Exception as exc:  # noqa: BLE001 - a job must always terminate
            job.error = f"{type(exc).__name__}: {exc}"
            job.state = "failed"
        else:
            job.report = report.as_dict() if hasattr(report, "as_dict") else report
            job.state = "done"
        finally:
            job.finished_at = time.time()
