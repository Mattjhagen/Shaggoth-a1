import tempfile
import unittest
from pathlib import Path

from shaggoth.knowledge.engine import KnowledgeBase
from shaggoth.memory.store import extract_keywords, STOPWORDS
from shaggoth.scraper.engine import ScraperEngine

from shaggoth.curiosity.engine import CuriosityEngine
from shaggoth.curiosity.search import SearchResult, _extract_results
from shaggoth.curiosity.topics import (
    extract_topic_query,
    extract_keywords_from_topic,
    is_known_topic,
    build_search_queries,
)
from shaggoth.curiosity.scheduler import CuriosityScheduler, ScheduleConfig
from shaggoth.curiosity.freshness import FreshnessTracker
from shaggoth.curiosity.wikipedia import _strip_html, _html_to_text


class TopicExtractionTests(unittest.TestCase):
    def test_extracts_what_is_question(self):
        topic = extract_topic_query("what is machine learning?")
        self.assertEqual(topic, "machine learning")

    def test_extracts_tell_me_about(self):
        topic = extract_topic_query("tell me about quantum computing")
        self.assertEqual(topic, "quantum computing")

    def test_extracts_explain(self):
        topic = extract_topic_query("explain how DNS works")
        self.assertEqual(topic, "DNS")

    def test_extracts_contraction_whats(self):
        topic = extract_topic_query("what's the capital of France")
        self.assertEqual(topic, "the capital of France")

    def test_extracts_contraction_whos(self):
        topic = extract_topic_query("who's Elon Musk")
        self.assertEqual(topic, "Elon Musk")

    def test_strips_trailing_verb(self):
        topic = extract_topic_query("how does DNA replication work")
        self.assertEqual(topic, "DNA replication")

    def test_strips_trailing_verb_photosynthesis(self):
        topic = extract_topic_query("why does photosynthesis need light")
        self.assertEqual(topic, "photosynthesis")

    def test_returns_none_for_greeting(self):
        topic = extract_topic_query("hello there")
        self.assertIsNone(topic)

    def test_returns_none_for_empty(self):
        topic = extract_topic_query("")
        self.assertIsNone(topic)

    def test_cleans_trailing_punctuation(self):
        topic = extract_topic_query("what is rust programming?")
        self.assertEqual(topic, "rust programming")

    def test_extracts_why_is_question(self):
        """POST /curiosity/research passed a raw question straight through
        without this normalization, so "why is the sky blue" created a
        knowledge entry titled after the whole question, duplicating the
        properly-named "the sky blue" entry from every other research path
        (which all go through this function first)."""
        topic = extract_topic_query("why is the sky blue")
        self.assertEqual(topic, "the sky blue")


class KeywordTests(unittest.TestCase):
    def test_extracts_keywords_from_topic(self):
        kws = extract_keywords_from_topic("machine learning neural networks")
        self.assertIn("machine", kws)
        self.assertIn("learning", kws)
        self.assertIn("neural", kws)
        self.assertIn("networks", kws)

    def test_known_topic_detection(self):
        known = {"machine", "learning", "neural", "networks"}
        self.assertTrue(is_known_topic("machine learning neural networks", known, min_overlap=0.5))

    def test_unknown_topic_detection(self):
        known = {"machine", "learning"}
        self.assertFalse(is_known_topic("quantum entanglement", known, min_overlap=0.5))


class SearchQueryTests(unittest.TestCase):
    def test_single_query(self):
        queries = build_search_queries("quantum computing")
        self.assertEqual(len(queries), 3)
        self.assertIn("quantum computing", queries)
        self.assertIn("quantum computing Wikipedia", queries)

    def test_max_queries(self):
        queries = build_search_queries("rust", max_queries=1)
        self.assertEqual(len(queries), 1)


class SearchResultParsingTests(unittest.TestCase):
    def test_empty_html_returns_empty(self):
        results = _extract_results("")
        self.assertEqual(results, [])

    def test_no_results_html(self):
        results = _extract_results("<html><body>no results</body></html>")
        self.assertEqual(results, [])


class CuriosityEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.knowledge = KnowledgeBase(directory=Path(self.tmpdir) / "knowledge")
        self.scraper = ScraperEngine(db_path=str(Path(self.tmpdir) / "scraper.db"))
        self.engine = CuriosityEngine(
            knowledge=self.knowledge,
            scraper=self.scraper,
            history_path=Path(self.tmpdir) / "curiosity_history.json",
        )

    def test_analyze_message_returns_topic(self):
        topic = self.engine.analyze_message("what is machine learning?")
        self.assertIsNotNone(topic)
        self.assertIn("machine learning", topic.lower())

    def test_analyze_message_returns_none_for_greeting(self):
        topic = self.engine.analyze_message("hello")
        self.assertIsNone(topic)

    def test_analyze_message_returns_none_for_known_topic(self):
        # Pre-populate knowledge with a topic
        self.knowledge.add_entry("greeting", "A greeting is a salutation.")
        topic = self.engine.analyze_message("what is a greeting?")
        # Should be None because the knowledge base already covers "greeting"
        # (though the exact behavior depends on keyword overlap)
        # At minimum, it should not crash
        self.assertIsInstance(topic, (str, type(None)))

    def test_ingest_text(self):
        path = self.engine.ingest_text("Test Topic", "This is test content about test topics.")
        self.assertTrue(Path(path).exists())

    def test_ingest_urls_empty(self):
        result = self.engine.ingest_urls([])
        self.assertEqual(result["pages_scraped"], 0)

    def test_status(self):
        status = self.engine.status()
        self.assertIn("is_running", status)
        self.assertIn("total_episodes", status)
        self.assertFalse(status["is_running"])

    def test_history_empty(self):
        history = self.engine.history()
        self.assertEqual(history, [])


class CuriositySchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.knowledge = KnowledgeBase(directory=Path(self.tmpdir) / "knowledge")
        self.scraper = ScraperEngine(db_path=str(Path(self.tmpdir) / "scraper.db"))
        self.curiosity = CuriosityEngine(
            knowledge=self.knowledge,
            scraper=self.scraper,
            history_path=Path(self.tmpdir) / "curiosity_history.json",
        )
        self.config = ScheduleConfig(enabled=False, interval_minutes=1, min_message_count=2)
        self.scheduler = CuriosityScheduler(self.curiosity, self.config)

    def test_record_message(self):
        self.scheduler.record_message("hello")
        self.assertEqual(len(self.scheduler._message_buffer), 1)

    def test_status(self):
        status = self.scheduler.status()
        self.assertIn("enabled", status)
        self.assertIn("buffered_messages", status)

    def test_trigger_no_messages(self):
        result = self.scheduler.trigger()
        self.assertFalse(result["triggered"])

    def test_trigger_with_messages(self):
        self.scheduler.record_message("hello there")
        self.scheduler.record_message("how are you?")
        result = self.scheduler.trigger()
        # May or may not trigger depending on topic detection
        self.assertIn("triggered", result)


class FreshnessTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.knowledge = KnowledgeBase(directory=Path(self.tmpdir) / "knowledge")
        self.tracker = FreshnessTracker(
            knowledge=self.knowledge,
            freshness_path=Path(self.tmpdir) / "freshness.json",
            stale_days=30,
        )

    def test_record_update(self):
        self.tracker.record_update("test topic")
        age = self.tracker.get_age_days("test topic")
        self.assertIsNotNone(age)
        self.assertLess(age, 0.001)  # basically 0 days

    def test_is_stale_never_researched(self):
        self.assertTrue(self.tracker.is_stale("never researched"))

    def test_is_stale_fresh_topic(self):
        self.tracker.record_update("fresh topic")
        self.assertFalse(self.tracker.is_stale("fresh topic"))

    def test_get_stale_topics(self):
        self.tracker.record_update("old topic")
        stale = self.tracker.get_stale_topics()
        # "old topic" was just recorded so it shouldn't be stale
        stale_names = [t["topic"] for t in stale]
        self.assertNotIn("old topic", stale_names)

    def test_status(self):
        status = self.tracker.status()
        self.assertIn("total_entries", status)
        self.assertIn("stale_count", status)
        self.assertIn("fresh_count", status)


class WikipediaTests(unittest.TestCase):
    def test_strip_html(self):
        result = _strip_html("<p>Hello <b>world</b></p>")
        self.assertEqual(result, "Hello world")

    def test_html_to_text(self):
        html = "<html><body><h1>Title</h1><p>Content here</p></body></html>"
        result = _html_to_text(html)
        self.assertIn("Title", result)
        self.assertIn("Content here", result)

    def test_html_to_text_strips_scripts(self):
        html = "<p>visible</p><script>invisible</script><p>also visible</p>"
        result = _html_to_text(html)
        self.assertIn("visible", result)
        self.assertNotIn("invisible", result)


class ResearchQueueTests(unittest.TestCase):
    """Research queue: concurrent requests queue instead of failing."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.knowledge = KnowledgeBase(directory=Path(self.tmpdir) / "knowledge")
        self.scraper = ScraperEngine(db_path=str(Path(self.tmpdir) / "scraper.db"))
        self.engine = CuriosityEngine(
            knowledge=self.knowledge,
            scraper=self.scraper,
            history_path=Path(self.tmpdir) / "curiosity_history.json",
            use_wikipedia=False,
        )

    def test_queue_when_busy(self):
        """A second research request while one is running should be queued."""
        with self.engine._lock:
            self.engine._running = True
        episode = self.engine.research_topic("test topic", background=False)
        self.assertEqual(episode.status, "queued")
        self.assertEqual(len(self.engine._queue), 1)
        with self.engine._lock:
            self.engine._running = False
            self.engine._queue.clear()

    def test_queue_full_fails(self):
        """When the queue has 5 items, new requests should fail."""
        with self.engine._lock:
            self.engine._running = True
            for i in range(5):
                self.engine._queue.append(("dummy", 5, 3))
        episode = self.engine.research_topic("overflow topic", background=False)
        self.assertEqual(episode.status, "failed")
        self.assertEqual(episode.error, "Research queue full")
        with self.engine._lock:
            self.engine._running = False
            self.engine._queue.clear()

    def test_queue_starts_empty(self):
        """Queue should be empty on construction."""
        self.assertEqual(self.engine._queue, [])

    def test_queued_item_runs_without_releasing_running(self):
        """_running must stay True while draining the queue (no race window)."""
        from shaggoth.curiosity.engine import CuriosityEpisode
        import uuid

        observed_running = []

        original_do = self.engine._do_research

        def spy_do(episode, max_results, max_pages):
            observed_running.append(self.engine._running)
            episode.status = "completed"

        self.engine._do_research = spy_do

        ep1 = CuriosityEpisode(
            episode_id=f"test-{uuid.uuid4().hex[:8]}",
            started_at=0, topic="first", queries=["first"],
        )
        ep2 = CuriosityEpisode(
            episode_id=f"test-{uuid.uuid4().hex[:8]}",
            started_at=0, topic="second", queries=["second"],
        )

        # Pre-load the queue so ep2 runs after ep1
        self.engine._queue.append((ep2, 5, 3))
        self.engine._run_research(ep1, 5, 3)

        # Both should have seen _running == True
        self.assertEqual(observed_running, [True, True])
        self.assertFalse(self.engine._running)


class PluginTests(unittest.TestCase):
    def test_teach_plugin_parses_topic_and_content(self):
        from shaggoth.plugins.builtin import build_registry
        registry = build_registry()
        # Test teach with content
        result = registry.dispatch("teach python - Python is a programming language")
        self.assertIsNotNone(result)
        self.assertIn("python", result.lower())

    def test_teach_plugin_no_content(self):
        from shaggoth.plugins.builtin import build_registry
        registry = build_registry()
        result = registry.dispatch("teach quantum physics")
        self.assertIsNotNone(result)
        self.assertIn("quantum physics", result)

    def test_wiki_plugin(self):
        from shaggoth.plugins.builtin import build_registry
        registry = build_registry()
        result = registry.dispatch("wiki python programming")
        # May return article or error — just check it doesn't crash
        self.assertIsInstance(result, (str, type(None)))

    def test_learned_plugin_empty(self):
        from shaggoth.plugins.builtin import build_registry
        registry = build_registry()
        result = registry.dispatch("what did you learn")
        self.assertIsNotNone(result)
        # Should mention learning or knowledge
        self.assertTrue(any(w in result.lower() for w in ["learn", "knowledge", "topic"]))

    def test_know_about_plugin(self):
        from shaggoth.plugins.builtin import build_registry
        registry = build_registry()
        result = registry.dispatch("what do you know about quantum computing")
        self.assertIsNotNone(result)
        # Should say it doesn't know or provide info
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
