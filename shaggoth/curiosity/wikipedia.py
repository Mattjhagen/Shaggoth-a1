"""Wikipedia as a knowledge source — no API key required.

Fetches article content via the Wikipedia REST API (action=query)
and extracts clean text for ingestion into the knowledge base.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class WikiArticle:
    title: str
    pageid: int
    url: str
    extract: str
    word_count: int


def search_wikipedia(query: str, max_results: int = 5) -> list[dict]:
    """Search Wikipedia for articles matching the query.

    Returns list of {"title": ..., "pageid": ..., "snippet": ...}.
    """
    params = urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": str(max_results),
        "format": "json",
    })
    url = f"https://en.wikipedia.org/w/api.php?{params}"

    req = urllib.request.Request(url, headers={
        "User-Agent": "Shaggoth/0.1 (self-learning bot; +https://github.com/Mattjhagen/Shaggoth-a1)",
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return []

    results = data.get("query", {}).get("search", [])
    return [
        {"title": r["title"], "pageid": r["pageid"], "snippet": _strip_html(r.get("snippet", ""))}
        for r in results
    ]


def fetch_article(title: str, max_chars: int = 15000) -> WikiArticle | None:
    """Fetch a Wikipedia article's plain text extract.

    Uses the parse API to get the full article text.
    """
    params = urllib.parse.urlencode({
        "action": "parse",
        "page": title,
        "prop": "text",
        "format": "json",
    })
    url = f"https://en.wikipedia.org/w/api.php?{params}"

    req = urllib.request.Request(url, headers={
        "User-Agent": "Shaggoth/0.1 (self-learning bot; +https://github.com/Mattjhagen/Shaggoth-a1)",
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None

    parse = data.get("parse")
    if not parse:
        return None

    pageid = parse.get("pageid", 0)
    html = parse.get("text", {}).get("*", "")
    text = _html_to_text(html)

    # Truncate if too long
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "..."

    article_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"

    return WikiArticle(
        title=parse.get("title", title),
        pageid=pageid,
        url=article_url,
        extract=text,
        word_count=len(text.split()),
    )


def fetch_summary(title: str) -> str | None:
    """Fetch a short summary of a Wikipedia article via the REST summary endpoint."""
    encoded = urllib.parse.quote(title.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"

    req = urllib.request.Request(url, headers={
        "User-Agent": "Shaggoth/0.1 (self-learning bot)",
        "Accept": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None

    return data.get("extract")


def learn_topic_from_wikipedia(topic: str, max_articles: int = 3) -> list[WikiArticle]:
    """Search Wikipedia for a topic and fetch the top articles.

    Returns list of WikiArticle objects with full text.
    """
    results = search_wikipedia(topic, max_results=max_articles)
    articles: list[WikiArticle] = []

    for result in results:
        article = fetch_article(result["title"])
        if article and article.word_count >= 50:
            articles.append(article)

    return articles


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _html_to_text(html: str) -> str:
    """Convert HTML to clean plain text."""
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    html = re.sub(r"<(?:br|hr|p|div|h[1-6]|li|tr|blockquote)[^>]*>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
