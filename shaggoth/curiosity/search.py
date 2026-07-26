"""Web search via DuckDuckGo HTML — no API key required.

Uses only stdlib (urllib + regex) to query DuckDuckGo's HTML interface
and extract result URLs and snippets.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str


def _extract_results(html: str) -> list[SearchResult]:
    """Parse DuckDuckGo HTML search results."""
    results: list[SearchResult] = []

    # DuckDuckGo wraps results in <a> tags with class "result__a"
    # and snippets in <a class="result__snippet">
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        r'.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    for match in pattern.finditer(html):
        url = match.group(1).strip()
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()

        # DuckDuckGo wraps URLs in redirect links — extract the actual URL
        if "uddg=" in url:
            actual = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
            url = actual

        if url.startswith("http") and title:
            results.append(SearchResult(url=url, title=title, snippet=snippet))

    return results[:10]


def search_web(query: str, max_results: int = 5) -> list[SearchResult]:
    """Search DuckDuckGo for the given query and return results.

    Returns up to ``max_results`` SearchResult objects.
    """
    params = urllib.parse.urlencode({"q": query, "t": "shaggoth", "ia": "web"})
    url = f"https://html.duckduckgo.com/html/?{params}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; Shaggoth/0.1; "
                "+https://github.com/Mattjhagen/Shaggoth-a1)"
            ),
            "Accept": "text/html",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError):
        return []

    results = _extract_results(html)
    return results[:max_results]
