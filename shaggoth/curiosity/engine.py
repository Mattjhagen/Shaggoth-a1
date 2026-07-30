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
    base_topic,
    build_search_queries,
    extract_keywords_from_topic,
    extract_topic_query,
    is_chunk_topic,
    is_known_topic,
    strip_question_prefix,
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
        self._queue: list[tuple[CuriosityEpisode, int, int]] = []
        self._history: list[dict] = self._load_history()
        self._completion_hooks: list = []

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

    def analyze_message(self, text: str) -> str | None:
        """Analyze a user message and return a topic to research, or None.

        Only returns a topic if it is NOT already well covered.

        "Covered" is decided by *retrieval*, not by a bag of every word in the
        corpus. The old check unioned the keywords of every entry -- 44,149
        words across 368 documents -- and asked whether 60% of the topic's
        words appeared anywhere in that bag. Any real English phrase does, so
        it answered "already known" to everything and conversation-driven
        curiosity silently stopped working. Worse, it got *more* wrong the more
        Shaggoth learned.

        Having an article whose title matches is the honest test.
        """
        topic = extract_topic_query(text)
        if not topic:
            return None
        return None if self.knows_topic(topic) else topic

    def knows_topic(self, topic: str) -> bool:
        """True when an entry actually *about* ``topic`` already exists."""
        wanted = {
            w for w in extract_keywords_from_topic(topic) if len(w) > 2
        }
        if not wanted:
            return False
        for entry, _score in self.knowledge.query(topic, limit=5, min_score=0.25):
            title_words = set(
                extract_keywords_from_topic(base_topic(entry.topic))
            )
            # Every meaningful word of the request is in the article's title.
            if wanted <= title_words:
                return True
        return False

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

        # Never research a chunk name. It is a slice of an existing entry, not
        # a subject, and researching it writes a new entry whose name is one
        # suffix longer -- the loop that filled the knowledge base with
        # "... Part 1 Part 1 Part 1".
        #
        # Nor a raw question. Every caller is supposed to have already
        # reduced a question to its subject (extract_topic_query), but that
        # was a per-call-site convention, not an invariant -- one endpoint
        # forgot, and stored "Why Is The Sky Blue" as a title next to the
        # honest "The Sky Blue" (AGENTS.md §NN). Stripping the interrogative
        # lead-in here too means the storage layer itself cannot produce that
        # duplicate, regardless of what a future caller forgets to do first.
        topic = strip_question_prefix(base_topic(topic)) or topic

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
                if len(self._queue) < 5:
                    self._queue.append((episode, max_results, max_pages))
                    episode.status = "queued"
                else:
                    episode.status = "failed"
                    episode.error = "Research queue full"
                return
            self._running = True
            self._current_episode = episode

        while True:
            try:
                self._do_research(episode, max_results, max_pages)
            except Exception as exc:
                episode.status = "failed"
                episode.error = str(exc)[:500]
            finally:
                episode.ended_at = time.time()
                self._history.append(asdict(episode))
                self._save_history()
                self._fire_completion(episode)

            with self._lock:
                if self._queue:
                    episode, max_results, max_pages = self._queue.pop(0)
                    episode.status = "running"
                    self._current_episode = episode
                else:
                    self._running = False
                    self._current_episode = None
                    break

    def _do_research(
        self,
        episode: CuriosityEpisode,
        max_results: int,
        max_pages: int,
    ) -> None:
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

    def on_episode_complete(self, callback) -> None:
        """Register a callback fired after each research episode ends.

        Used to deliver deferred answers the moment the knowledge to answer
        them exists, rather than having anything poll for it.
        """
        self._completion_hooks.append(callback)

    def _fire_completion(self, episode) -> None:
        # Runs on the research thread. A misbehaving hook must not corrupt the
        # episode record or stop the next cycle, so each is isolated.
        for hook in getattr(self, "_completion_hooks", []):
            try:
                hook(episode)
            except Exception as exc:  # noqa: BLE001
                print(f"[curiosity] completion hook failed: {exc}")

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
        """Re-research stale knowledge entries.

        Chunk names are collapsed to the subject they came from and
        deduplicated, so refreshing "Aeroponic Farming Part 2" re-researches
        *aeroponic farming*.

        Researching the chunk name literally is what produced
        "Aeroponic Farming Part 1 Part 1", then "... Part 1 Part 1 Part 1" --
        each refresh chunked the previous chunk's name and wrote new entries,
        so the knowledge base grew without bound on a 15-minute timer.
        """
        stale = self.freshness.get_stale_topics()

        subjects: list[str] = []
        for item in stale:
            subject = strip_question_prefix(base_topic(item.get("topic", ""))).strip()
            if subject and subject not in subjects:
                subjects.append(subject)

        refreshed = 0
        for subject in subjects[:max_topics]:
            if self._running:
                break
            self.research_topic(subject, background=False)
            refreshed += 1
        return {
            "stale_found": len(stale),
            "stale_subjects": len(subjects),
            "refreshed": refreshed,
        }

    # -------------------------------------------------------- status

    def status(self) -> dict:
        ep = self._current_episode  # capture once; avoids TOCTOU with finishing threads
        return {
            "is_running": self._running,
            "current_episode": asdict(ep) if ep else None,
            "total_episodes": len(self._history),
            "last_episode": self._history[-1] if self._history else None,
            "knowledge_entries": len(self.knowledge.list_entries()),
            "scraper_stats": self.scraper.stats(),
            "freshness": self.freshness.status(),
        }

    def history(self, limit: int = 10) -> list[dict]:
        return self._history[-limit:]
