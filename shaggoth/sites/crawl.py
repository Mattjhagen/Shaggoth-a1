"""Bounded, gated crawl of a tenant's own domain.

The gate is the point of the whole verification module: an unverified site is
refused here, with no override parameter. A debug flag that skips the check
would turn this box back into a crawl-on-demand proxy, so there isn't one --
the only way past :func:`crawl_site` is a site whose ownership was proven.

Everything a crawl fetches lands in that site's own KnowledgeBase and nowhere
else. Nothing here touches the general corpus.
"""

from __future__ import annotations

import hashlib
import re
import time
import urllib.parse
from dataclasses import asdict, dataclass, field

from ..scraper.engine import ScraperEngine
from .registry import SiteRegistry

#: Conservative ceilings. A marketing site is a few dozen pages; anything
#: hitting these limits wants a conversation, not a bigger default.
MAX_PAGES = 25
MAX_DEPTH = 2
MAX_TOTAL_BYTES = 5 * 1024 * 1024
MAX_PAGE_BYTES = 512 * 1024
MAX_WALL_SECONDS = 300

_HREF = re.compile(r'href=["\']([^"\'#]+)', re.I)
_NON_HTML = re.compile(
    r"\.(pdf|zip|gz|tar|png|jpe?g|gif|svg|webp|ico|mp4|mp3|wav|avi|mov|css|js|"
    r"woff2?|ttf|eot|xml|rss|json|csv|xlsx?|docx?|pptx?)$",
    re.I,
)


class CrawlNotPermitted(PermissionError):
    """Raised when a crawl is attempted for a site that is not verified."""


@dataclass
class PageResult:
    url: str
    status: str          # "fetched" | "skipped"
    reason: str = ""     # why it was skipped
    words: int = 0
    bytes: int = 0


@dataclass
class CrawlReport:
    site_id: str
    domain: str
    started_at: float
    finished_at: float = 0.0
    pages_fetched: int = 0
    pages_skipped: int = 0
    bytes_total: int = 0
    stopped_reason: str = "completed"
    pages: list[PageResult] = field(default_factory=list)

    def as_dict(self) -> dict:
        out = asdict(self)
        out["duration_seconds"] = round(self.finished_at - self.started_at, 2)
        return out

    def _add(self, result: PageResult) -> None:
        self.pages.append(result)
        if result.status == "fetched":
            self.pages_fetched += 1
            self.bytes_total += result.bytes
        else:
            self.pages_skipped += 1


def _same_site(url: str, domain: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host == domain or host.endswith("." + domain)


def crawl_site(
    registry: SiteRegistry,
    site_id: str,
    *,
    max_pages: int = MAX_PAGES,
    max_depth: int = MAX_DEPTH,
    max_total_bytes: int = MAX_TOTAL_BYTES,
    max_wall_seconds: int = MAX_WALL_SECONDS,
    scraper: ScraperEngine | None = None,
) -> CrawlReport:
    """Crawl a verified site into its own corpus.

    Raises :class:`CrawlNotPermitted` unless the site's ownership has been
    verified. There is deliberately no parameter that bypasses this.
    """
    record = registry.get(site_id)
    if record is None:
        raise CrawlNotPermitted(f"no such site: {site_id!r}")
    if not record.verified:
        raise CrawlNotPermitted(
            f"{record.domain} is {record.status}, not verified. Prove ownership "
            f"before crawling it."
        )

    scraper = scraper or ScraperEngine()
    kb = registry.knowledge_base(site_id)
    report = CrawlReport(site_id=site_id, domain=record.domain, started_at=time.time())

    start = time.monotonic()
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    queue: list[tuple[str, int]] = [(f"https://{record.domain}/", 0)]

    while queue:
        if report.pages_fetched >= max_pages:
            report.stopped_reason = f"page limit reached ({max_pages})"
            break
        if report.bytes_total >= max_total_bytes:
            report.stopped_reason = f"byte limit reached ({max_total_bytes})"
            break
        if time.monotonic() - start > max_wall_seconds:
            report.stopped_reason = f"time limit reached ({max_wall_seconds}s)"
            break

        url, depth = queue.pop(0)
        url, _, _ = url.partition("#")
        if url in seen_urls:
            continue
        seen_urls.add(url)

        if not _same_site(url, record.domain):
            report._add(PageResult(url, "skipped", "off-domain"))
            continue
        if _NON_HTML.search(urllib.parse.urlsplit(url).path or ""):
            report._add(PageResult(url, "skipped", "non-HTML"))
            continue
        if scraper.respect_robots and not scraper.robots_allows(url):
            # Checked here as well as inside fetch_page, so the report can say
            # *why* rather than just recording a failure.
            report._add(PageResult(url, "skipped", "robots.txt disallow"))
            continue

        page = scraper.fetch_page(url)
        if page is None or not page.text.strip():
            report._add(PageResult(url, "skipped", "fetch failed or empty"))
            continue

        body = page.text.strip()
        size = len(body.encode("utf-8"))
        if size > MAX_PAGE_BYTES:
            report._add(PageResult(url, "skipped", "too large", bytes=size))
            continue

        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if digest in seen_hashes:
            report._add(PageResult(url, "skipped", "duplicate content"))
            continue
        seen_hashes.add(digest)

        title = (page.title or url).strip() or url
        kb.add_entry(title, body)
        report._add(PageResult(
            url, "fetched", words=page.word_count or len(body.split()), bytes=size
        ))

        if depth < max_depth:
            for href in _HREF.findall(scraper._last_html or ""):
                nxt = urllib.parse.urljoin(url, href)
                if nxt.startswith(("http://", "https://")) and nxt not in seen_urls:
                    queue.append((nxt, depth + 1))

    report.finished_at = time.time()
    registry.update(
        site_id,
        last_crawl_at=report.finished_at,
        pages_indexed=report.pages_fetched,
    )
    return report
