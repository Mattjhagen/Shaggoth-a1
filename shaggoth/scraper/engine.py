"""Web scraper engine — fetches URLs, extracts clean text, stores for training.

Uses only stdlib (urllib + regex) so no extra deps are needed.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, asdict
from pathlib import Path

#: Sent on every request the scraper makes.
#:
#: A descriptive, contactable agent string is the minimum courtesy for a bot
#: that crawls other people's servers, and several hosts enforce it. Reddit in
#: particular returns "429/403 Blocked" to generic or absent agents no matter
#: what the endpoint is -- which is what the scraper's `HTTP Error 403:
#: Blocked` failures were.
USER_AGENT = (
    "ShaggothBot/0.1 (+https://ai.relayapp.pro; self-hosted research bot; "
    "contact: https://github.com/Mattjhagen/Shaggoth-a1/issues)"
)

#: How long a parsed robots.txt is trusted before being re-fetched.
ROBOTS_TTL_SECONDS = 3600


def _clean_text(text: str) -> str:
    """Collapse whitespace, strip control chars, normalize."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _html_to_text(html: str) -> str:
    """Extract visible text from HTML using regex. Robust against complex pages."""
    # Remove script, style, noscript blocks entirely
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<noscript[^>]*>.*?</noscript>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    # Replace block elements with newlines for paragraph breaks
    html = re.sub(r"<(?:br|hr|p|div|h[1-6]|li|tr|blockquote)[^>]*>", "\n", html, flags=re.IGNORECASE)
    # Strip all remaining tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    return _clean_text(text)


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return _clean_text(m.group(1)) if m else ""


def _extract_links(html: str, base_url: str) -> list[str]:
    """Pull all http/https href values, resolving relative URLs against base_url."""
    links = []
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE):
        href = m.group(1)
        full = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(full)
        if parsed.scheme in ("http", "https"):
            links.append(full)
    return links


@dataclass
class ScrapedPage:
    url: str
    title: str
    text: str
    word_count: int
    scraped_at: float
    content_hash: str


class ScraperEngine:
    """Fetches web pages, extracts clean text, stores in SQLite for training."""

    def __init__(self, db_path: str | None = None, respect_robots: bool = True):
        self.db_path = db_path or str(Path.home() / ".shaggoth" / "scraper.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        #: Honour robots.txt. Settable for tests; leave it on in production.
        self.respect_robots = respect_robots
        #: origin -> (RobotFileParser | None, fetched_at)
        self._robots_cache: dict[str, tuple] = {}
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS pages (
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    text TEXT,
                    word_count INTEGER,
                    scraped_at REAL,
                    content_hash TEXT
                );
                CREATE TABLE IF NOT EXISTS scrape_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    status TEXT,
                    message TEXT,
                    ts REAL
                );
                CREATE TABLE IF NOT EXISTS seeds (
                    url TEXT PRIMARY KEY,
                    added_at REAL,
                    scraped INTEGER DEFAULT 0
                );
            """)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def add_seed(self, url: str) -> None:
        """Add a URL to the seed list for future crawling."""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seeds (url, added_at) VALUES (?, ?)",
                (url, time.time()),
            )

    def add_seeds(self, urls: list[str]) -> int:
        """Add multiple seed URLs. Returns count added."""
        added = 0
        with self._conn() as conn:
            for url in urls:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO seeds (url, added_at) VALUES (?, ?)",
                    (url.strip(), time.time()),
                )
                if cur.rowcount > 0:
                    added += 1
        return added

    def get_unscraped_seeds(self, limit: int = 20) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT url FROM seeds WHERE scraped = 0 ORDER BY added_at LIMIT ?",
                (limit,),
            ).fetchall()
        return [r[0] for r in rows]

    def robots_allows(self, url: str, timeout: int = 10) -> bool:
        """Whether ``robots.txt`` permits :data:`USER_AGENT` to fetch ``url``.

        Parsed files are cached per-origin for :data:`ROBOTS_TTL_SECONDS` so a
        crawl does not re-request robots.txt once per page.

        Fails **open**: a site with no robots.txt, or one that cannot be
        reached, is treated as allowed -- that is what the standard specifies,
        and refusing to crawl on a transient network error would silently stall
        learning. A robots.txt that is fetched and *does* disallow the path is
        always honoured.
        """
        try:
            parts = urllib.parse.urlsplit(url)
        except ValueError:
            return True
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return True

        origin = f"{parts.scheme}://{parts.netloc}"
        now = time.time()
        cached = self._robots_cache.get(origin)
        if cached is None or now - cached[1] > ROBOTS_TTL_SECONDS:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(origin + "/robots.txt")
            try:
                request = urllib.request.Request(
                    origin + "/robots.txt", headers={"User-Agent": USER_AGENT}
                )
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    parser.parse(
                        response.read().decode("utf-8", errors="replace").splitlines()
                    )
            except Exception:
                # No robots.txt, or unreachable. Allowed by default.
                parser = None
            self._robots_cache[origin] = (parser, now)
            cached = self._robots_cache[origin]

        parser = cached[0]
        if parser is None:
            return True
        try:
            return parser.can_fetch(USER_AGENT, url)
        except Exception:
            return True

    def fetch_page(self, url: str, timeout: int = 15) -> ScrapedPage | None:
        """Fetch a single URL, extract clean text, store in DB.

        Refuses anything ``robots.txt`` disallows. The refusal is logged like
        any other failure so a blocked seed is visible in the scraper stats
        rather than silently absent.
        """
        if self.respect_robots and not self.robots_allows(url):
            self._log(url, "error", "blocked by robots.txt")
            return None
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,text/plain,application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                content_type = resp.headers.get("Content-Type", "")
                if "html" in content_type or "xhtml" in content_type:
                    html = raw.decode("utf-8", errors="replace")
                    title = _extract_title(html)
                    text = _html_to_text(html)
                else:
                    title = url.split("/")[-1] or url
                    text = raw.decode("utf-8", errors="replace")
                    text = _clean_text(text)

            content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
            page = ScrapedPage(
                url=url,
                title=title,
                text=text,
                word_count=len(text.split()),
                scraped_at=time.time(),
                content_hash=content_hash,
            )
            self._store_page(page)
            self._log(url, "ok", f"{page.word_count} words")
            return page

        except Exception as exc:
            self._log(url, "error", str(exc)[:200])
            return None

    def _store_page(self, page: ScrapedPage) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO pages
                   (url, title, text, word_count, scraped_at, content_hash)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (page.url, page.title, page.text, page.word_count, page.scraped_at, page.content_hash),
            )
            conn.execute(
                "UPDATE seeds SET scraped = 1 WHERE url = ?",
                (page.url,),
            )

    def _log(self, url: str, status: str, message: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO scrape_log (url, status, message, ts) VALUES (?, ?, ?, ?)",
                (url, status, message, time.time()),
            )

    def crawl(self, max_pages: int = 10, depth: int = 1) -> list[ScrapedPage]:
        """BFS crawl starting from unscraped seeds. Returns scraped pages."""
        scraped: list[ScrapedPage] = []
        queue = self.get_unscraped_seeds(limit=max_pages)
        visited = set()

        for _ in range(depth):
            next_queue = []
            for url in queue:
                if url in visited:
                    continue
                visited.add(url)
                page = self.fetch_page(url)
                if page:
                    scraped.append(page)
                    if len(scraped) >= max_pages:
                        break
                    # discover more links from the page
                    try:
                        req = urllib.request.Request(
                            url,
                            headers={"User-Agent": USER_AGENT},
                        )
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            html = resp.read().decode("utf-8", errors="replace")
                        links = _extract_links(html, url)
                        for link in links[:20]:
                            if link not in visited:
                                self.add_seed(link)
                                next_queue.append(link)
                    except Exception:
                        pass
            queue = next_queue[:max_pages - len(scraped)]

        return scraped

    def get_corpus_text(self, min_words: int = 50) -> str:
        """Combine all scraped text into a single training corpus string."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT text FROM pages WHERE word_count >= ? ORDER BY scraped_at",
                (min_words,),
            ).fetchall()
        return "\n\n".join(r[0] for r in rows)

    def stats(self) -> dict:
        """Return scraper statistics."""
        with self._conn() as conn:
            pages = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            total_words = conn.execute("SELECT COALESCE(SUM(word_count), 0) FROM pages").fetchone()[0]
            seeds = conn.execute("SELECT COUNT(*) FROM seeds").fetchone()[0]
            scraped_seeds = conn.execute("SELECT COUNT(*) FROM seeds WHERE scraped = 1").fetchone()[0]
            errors = conn.execute(
                "SELECT COUNT(*) FROM scrape_log WHERE status = 'error'"
            ).fetchone()[0]
            last_error = conn.execute(
                "SELECT message FROM scrape_log WHERE status = 'error' ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        return {
            "pages_stored": pages,
            "total_words": total_words,
            "seeds_total": seeds,
            "seeds_scraped": scraped_seeds,
            "seeds_pending": seeds - scraped_seeds,
            "errors": errors,
            "last_error": last_error[0] if last_error else None,
        }

    def recent_logs(self, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT url, status, message, ts FROM scrape_log ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"url": r[0], "status": r[1], "message": r[2], "ts": r[3]}
            for r in rows
        ]
