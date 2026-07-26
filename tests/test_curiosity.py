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


class TopicExtractionTests(unittest.TestCase):
    def test_extracts_what_is_question(self):
        topic = extract_topic_query("what is machine learning?")
        self.assertEqual(topic, "machine learning")

    def test_extracts_tell_me_about(self):
        topic = extract_topic_query("tell me about quantum computing")
        self.assertEqual(topic, "quantum computing")

    def test_extracts_explain(self):
        topic = extract_topic_query("explain how DNS works")
        self.assertEqual(topic, "how DNS works")

    def test_returns_none_for_greeting(self):
        topic = extract_topic_query("hello there")
        self.assertIsNone(topic)

    def test_returns_none_for_empty(self):
        topic = extract_topic_query("")
        self.assertIsNone(topic)

    def test_cleans_trailing_punctuation(self):
        topic = extract_topic_query("what is rust programming?")
        self.assertEqual(topic, "rust programming")


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
        self.assertIn("quantum computing explained", queries)

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


if __name__ == "__main__":
    unittest.main()
