"""Core curiosity engine — the drive to learn.

Detects knowledge gaps, searches the web, scrapes content, and feeds
learned facts into the knowledge base. Runs autonomously on a background
thread or on-demand via API/CLI.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from ..config import DATA_DIR
from ..knowledge.engine import KnowledgeBase
from ..memory.store import extract_keywords, STOPWORDS
from ..scraper.engine import ScraperEngine
from .search import search_web, SearchResult
from .topics import (
    extract_topic_query,
    extract_keywords_from_topic,
    is_known_topic,
    build_search_queries,
)
from .wikipedia import learn_topic_from_wikipedia, WikiArticle
from .freshness import FreshnessTracker

HISTORY_PATH = DATA_DIR / "curiosity_history.json"


@dataclass
class CuriosityEpisode:
    """Record of a single curiosity-driven research session."""
    episode_id: str
    started_at: float
    topic: str
    queries: list[str]
    urls_found: int = 0
    pages_scraped: int = 0
    words_learned: int = 0
    knowledge_entries: int = 0
    ended_at: float | None = None
    status: str = "running"  # running | completed | failed
    error: str | None = None


class CuriosityEngine:
    """Autonomous knowledge acquisition engine.

    Flow:
        1. User says something → detect if it mentions an unknown topic
        2. If unknown → search the web for relevant pages
        3. Scrape the top results → extract clean text
        4. Summarize and store in the knowledge base
        5. Optionally crawl related pages for deeper knowledge
    """

    def __init__(
        self,
        knowledge: KnowledgeBase | None = None,
        scraper: ScraperEngine | None = None,
        history_path: str | Path | None = None,
        use_wikipedia: bool = True,
    ):
        self.knowledge = knowledge or KnowledgeBase()
        self.scraper = scraper or ScraperEngine()
        self.history_path = Path(history_path) if history_path else HISTORY_PATH
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.use_wikipedia = use_wikipedia
        self.freshness = FreshnessTracker(knowledge=self.knowledge)
        self._running = False
        self._current_episode: CuriosityEpisode | None = None
        self._lock = threading.Lock()
        self._history: list[dict] = self._load_history()

    def _load_history(self) -> list[dict]:
        if self.history_path.exists():
            try:
                return json.loads(self.history_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save_history(self) -> None:
        self.history_path.write_text(
            json.dumps(self._history, indent=2), encoding="utf-8"
        )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_episode(self) -> CuriosityEpisode | None:
        return self._current_episode

    # --------------------------------------------------------- core logic

    def _get_known_keywords(self) -> set[str]:
        """Build a set of all keywords currently in the knowledge base."""
        all_kw: set[str] = set()
        for entry in self.knowledge.list_entries():
            all_kw.update(entry.get("keywords", []))
        # Also pull from raw knowledge content
        for entry in self.knowledge._entries:
            all_kw.update(entry.keywords)
        return all_kw

    def analyze_message(self, text: str) -> str | None:
        """Analyze a user message and return a topic to research, or None.

        Only returns a topic if it's NOT already well-known.
        """
        topic = extract_topic_query(text)
        if not topic:
            return None

        known = self._get_known_keywords()
        if is_known_topic(topic, known, min_overlap=0.6):
            return None

        return topic

    def research_topic(
        self,
        topic: str,
        max_results: int = 5,
        max_pages: int = 3,
        background: bool = False,
    ) -> CuriosityEpisode:
        """Research a topic: search → scrape → store.

        If background=True, runs in a daemon thread.
        """
        import uuid
        episode = CuriosityEpisode(
            episode_id=f"curiosity-{uuid.uuid4().hex[:8]}",
            started_at=time.time(),
            topic=topic,
            queries=build_search_queries(topic),
        )

        if background:
            t = threading.Thread(
                target=self._run_research,
                args=(episode, max_results, max_pages),
                daemon=True,
            )
            t.start()
        else:
            self._run_research(episode, max_results, max_pages)

        return episode

    def _run_research(
        self,
        episode: CuriosityEpisode,
        max_results: int,
        max_pages: int,
    ) -> None:
        with self._lock:
            if self._running:
                episode.status = "failed"
                episode.error = "Already researching"
                return
            self._running = True
            self._current_episode = episode

        try:
            scraped_text_parts: list[str] = []

            # 0. Try Wikipedia first (more reliable, structured content)
            if self.use_wikipedia:
                try:
                    wiki_articles = learn_topic_from_wikipedia(episode.topic, max_articles=2)
                    for article in wiki_articles:
                        if article.word_count >= 50:
                            scraped_text_parts.append(article.extract)
                            episode.pages_scraped += 1
                            episode.urls_found += 1
                except Exception:
                    pass  # Wikipedia is optional, fall through to web search

            # 1. Search the web for each query
            all_results: list[SearchResult] = []
            for query in episode.queries:
                results = search_web(query, max_results=max_results)
                all_results.extend(results)
                episode.urls_found += len(results)

            # Deduplicate by URL
            seen_urls: set[str] = set()
            unique_results: list[SearchResult] = []
            for r in all_results:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    unique_results.append(r)

            # 2. Scrape top pages
            for result in unique_results[:max_pages]:
                page = self.scraper.fetch_page(result.url)
                if page and page.word_count >= 50:
                    scraped_text_parts.append(page.text)
                    episode.pages_scraped += 1

            if not scraped_text_parts:
                episode.status = "completed"
                episode.error = "No usable content found"
                return

            # 3. Combine and store in knowledge base
            combined = "\n\n".join(scraped_text_parts)
            episode.words_learned = len(combined.split())

            # Chunk into knowledge entries if very long
            entries = self._chunk_and_store(episode.topic, combined)
            episode.knowledge_entries = len(entries)

            # 4. Record freshness
            self.freshness.record_update(episode.topic)

            episode.status = "completed"

        except Exception as exc:
            episode.status = "failed"
            episode.error = str(exc)[:500]

        finally:
            episode.ended_at = time.time()
            self._history.append(asdict(episode))
            self._save_history()
            self._running = False
            self._current_episode = None

    def _chunk_and_store(self, topic: str, text: str) -> list[str]:
        """Split text into knowledge-sized chunks and store each.

        Returns list of file paths created.
        """
        paths: list[str] = []
        # Split into ~2000-word chunks
        words = text.split()
        chunk_size = 2000

        if len(words) <= chunk_size:
            path = self.knowledge.add_entry(topic, text)
            paths.append(str(path))
            return paths

        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i : i + chunk_size])
            subtopic = f"{topic} (part {i // chunk_size + 1})"
            path = self.knowledge.add_entry(subtopic, chunk)
            paths.append(str(path))

        return paths

    # -------------------------------------------------------- manual add

    def ingest_text(self, topic: str, text: str) -> str:
        """Directly ingest text into the knowledge base under a topic."""
        path = self.knowledge.add_entry(topic, text)
        return str(path)

    def ingest_urls(self, urls: list[str], max_pages: int = 5) -> dict:
        """Scrape and ingest content from specific URLs."""
        scraped = 0
        words = 0
        for url in urls[:max_pages]:
            page = self.scraper.fetch_page(url)
            if page and page.word_count >= 50:
                title = page.title or url.split("/")[-1]
                self.knowledge.add_entry(title, page.text)
                scraped += 1
                words += page.word_count
        return {"pages_scraped": scraped, "words_learned": words}

    def ingest_wikipedia(self, topic: str, max_articles: int = 3) -> dict:
        """Fetch and ingest Wikipedia articles about a topic."""
        articles = learn_topic_from_wikipedia(topic, max_articles=max_articles)
        words = 0
        for article in articles:
            self.knowledge.add_entry(article.title, article.extract)
            self.freshness.record_update(article.title)
            words += article.word_count
        return {"articles": len(articles), "words_learned": words}

    def refresh_stale(self, max_topics: int = 3) -> dict:
        """Re-research stale knowledge entries."""
        stale = self.freshness.get_stale_topics()
        refreshed = 0
        for item in stale[:max_topics]:
            if self._running:
                break
            self.research_topic(item["topic"], background=False)
            refreshed += 1
        return {"stale_found": len(stale), "refreshed": refreshed}

    # -------------------------------------------------------- status

    def status(self) -> dict:
        return {
            "is_running": self._running,
            "current_episode": asdict(self._current_episode) if self._current_episode else None,
            "total_episodes": len(self._history),
            "last_episode": self._history[-1] if self._history else None,
            "knowledge_entries": len(self.knowledge.list_entries()),
            "scraper_stats": self.scraper.stats(),
            "freshness": self.freshness.status(),
        }

    def history(self, limit: int = 10) -> list[dict]:
        return self._history[-limit:]
