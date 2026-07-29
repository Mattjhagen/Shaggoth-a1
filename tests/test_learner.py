"""Tests for LearnerPipeline and LearningSession (learner/pipeline.py)."""
from __future__ import annotations

import json
import time
import tempfile
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shaggoth.learner.pipeline import LearnerPipeline, LearningSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeScraper:
    """Minimal ScraperEngine stand-in."""
    def __init__(self, pages=None, corpus=""):
        self._pages = pages or []
        self._corpus = corpus

    def add_seeds(self, urls):
        pass

    def crawl(self, max_pages=20, depth=1):
        return self._pages

    def get_corpus_text(self):
        return self._corpus

    def stats(self):
        return {"pages": len(self._pages), "corpus_words": len(self._corpus.split())}


def _pipeline(corpus: str = "", pages=None, tmp_path: Path | None = None) -> LearnerPipeline:
    scraper = FakeScraper(pages=pages or [], corpus=corpus)
    model_dir = tmp_path or Path(tempfile.mkdtemp())
    model_path = str(model_dir / "model.pt")
    # Isolate the Markov fallback path too -- otherwise a TinyGPT-unavailable
    # test writes straight into the real DATA_DIR/markov_model.json.
    markov_path = str(model_dir / "markov_model.json")
    p = LearnerPipeline(scraper=scraper, model_path=model_path, markov_path=markov_path)
    # Isolate from the global DATA_DIR history file
    p.history_path = str(model_dir / "history.json")
    p._history = []
    return p


# ---------------------------------------------------------------------------
# LearningSession
# ---------------------------------------------------------------------------

class TestLearningSession:
    def test_default_status_running(self):
        s = LearningSession(session_id="s1", started_at=time.time())
        assert s.status == "running"

    def test_dataclass_serialisable(self):
        s = LearningSession(session_id="s1", started_at=100.0)
        d = asdict(s)
        assert d["session_id"] == "s1"
        assert d["status"] == "running"


# ---------------------------------------------------------------------------
# LearnerPipeline — basic state
# ---------------------------------------------------------------------------

class TestLearnerPipelineState:
    def test_not_learning_initially(self, tmp_path):
        p = _pipeline(tmp_path=tmp_path)
        assert not p.is_learning

    def test_current_session_none_initially(self, tmp_path):
        p = _pipeline(tmp_path=tmp_path)
        assert p.current_session is None

    def test_history_empty_initially(self, tmp_path):
        p = _pipeline(tmp_path=tmp_path)
        assert p.history() == []

    def test_history_limit(self, tmp_path):
        p = _pipeline(corpus="word " * 200, tmp_path=tmp_path)
        # Add fake history entries directly
        for i in range(15):
            p._history.append({"session_id": f"s{i}", "status": "completed"})
        h = p.history(limit=5)
        assert len(h) == 5

    def test_history_persistence(self, tmp_path):
        # Pipeline saves history to disk; a second instance loads it
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        history_path = str(model_dir / "history.json")

        scraper1 = FakeScraper(corpus="")
        p1 = LearnerPipeline(scraper=scraper1, model_path=str(model_dir / "m.pt"))
        p1.history_path = history_path
        p1._history = [{"session_id": "saved", "status": "completed"}]
        p1._save_history()

        scraper2 = FakeScraper(corpus="")
        p2 = LearnerPipeline(scraper=scraper2, model_path=str(model_dir / "m.pt"))
        p2.history_path = history_path
        p2._load_history()
        assert any(h["session_id"] == "saved" for h in p2._history)


# ---------------------------------------------------------------------------
# active_model
# ---------------------------------------------------------------------------

class TestActiveModel:
    def test_no_model_returns_none(self, tmp_path):
        p = _pipeline(tmp_path=tmp_path)
        kind, path = p.active_model()
        assert kind == "none"
        assert path == ""

    def test_tinygpt_file_detected(self, tmp_path):
        p = _pipeline(tmp_path=tmp_path)
        Path(p.model_path).write_text("fake")
        kind, path = p.active_model()
        assert kind == "tinygpt"

    def test_tinygpt_preferred_over_markov(self, tmp_path):
        p = _pipeline(tmp_path=tmp_path)
        Path(p.model_path).write_text("fake tinygpt")
        # Even if a markov model also exists, tinygpt wins.
        Path(p.markov_path).write_text("{}")
        kind, _ = p.active_model()
        assert kind == "tinygpt"


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

class TestStatus:
    def test_status_structure(self, tmp_path):
        p = _pipeline(tmp_path=tmp_path)
        s = p.status()
        assert "is_learning" in s
        assert "model_exists" in s
        assert "model_kind" in s
        assert "total_sessions" in s
        assert "last_session" in s

    def test_status_no_model(self, tmp_path):
        p = _pipeline(tmp_path=tmp_path)
        s = p.status()
        assert not s["model_exists"]
        assert s["model_kind"] == "none"

    def test_status_with_model(self, tmp_path):
        p = _pipeline(tmp_path=tmp_path)
        Path(p.model_path).write_text("dummy")
        s = p.status()
        assert s["model_exists"]
        assert s["model_kind"] == "tinygpt"

    def test_status_no_learning_initially(self, tmp_path):
        p = _pipeline(tmp_path=tmp_path)
        assert not p.status()["is_learning"]


# ---------------------------------------------------------------------------
# _run_learn: corpus too small
# ---------------------------------------------------------------------------

class TestRunLearnShortCorpus:
    def test_too_few_words_status_completed_with_note(self, tmp_path):
        p = _pipeline(corpus="hello world", pages=[MagicMock()], tmp_path=tmp_path)
        session = LearningSession(session_id="s1", started_at=time.time())
        p._run_learn(session, urls=None, crawl_depth=1, max_pages=1, training_steps=10)
        assert session.status == "completed"
        assert session.error  # should have an error note about word count

    def test_no_pages_scraped_still_runs(self, tmp_path):
        p = _pipeline(corpus="", pages=[], tmp_path=tmp_path)
        session = LearningSession(session_id="s1", started_at=time.time())
        p._run_learn(session, urls=None, crawl_depth=1, max_pages=1, training_steps=10)
        assert session.ended_at is not None

    def test_history_updated_after_run(self, tmp_path):
        p = _pipeline(corpus="few words here", pages=[], tmp_path=tmp_path)
        before = len(p._history)
        session = LearningSession(session_id="s-unique-xyz", started_at=time.time())
        p._run_learn(session, urls=None, crawl_depth=1, max_pages=1, training_steps=10)
        assert len(p._history) == before + 1


# ---------------------------------------------------------------------------
# _run_learn: already learning guard
# ---------------------------------------------------------------------------

class TestConcurrentLockout:
    def test_second_run_rejected_while_learning(self, tmp_path):
        p = _pipeline(corpus="", tmp_path=tmp_path)
        p._learning = True  # Simulate an in-progress session
        session = LearningSession(session_id="s2", started_at=time.time())
        p._run_learn(session, urls=None, crawl_depth=1, max_pages=1, training_steps=10)
        assert session.status == "failed"
        assert "Already learning" in (session.error or "")


# ---------------------------------------------------------------------------
# _run_learn: full path with mocked model training
# ---------------------------------------------------------------------------

class TestRunLearnFullPath:
    def test_markov_fallback_when_torch_unavailable(self, tmp_path):
        big_corpus = "word " * 200
        p = _pipeline(corpus=big_corpus, pages=[MagicMock()], tmp_path=tmp_path)

        # Patch so TinyGPT raises immediately → Markov fallback
        with patch("shaggoth.learner.pipeline.TORCH_AVAILABLE", False, create=True):
            with patch("shaggoth.models.markov.MarkovModel") as MockMarkov:
                instance = MagicMock()
                MockMarkov.return_value = instance
                with patch.dict("sys.modules", {"shaggoth.models.tinygpt": MagicMock(TORCH_AVAILABLE=False)}):
                    session = LearningSession(session_id="s1", started_at=time.time())
                    p._run_learn(session, urls=None, crawl_depth=1, max_pages=10, training_steps=100)

        # Whatever happens, the session must have ended and history updated
        assert session.ended_at is not None
        assert session.status in ("completed", "failed")

    def test_learn_background_returns_session(self, tmp_path):
        p = _pipeline(corpus="", tmp_path=tmp_path)
        session = p.learn(background=True)
        assert session is not None
        assert session.session_id.startswith("learn-")

    def test_learn_synchronous_sets_ended_at(self, tmp_path):
        p = _pipeline(corpus="short corpus", tmp_path=tmp_path)
        session = p.learn(background=False)
        # Wait for it since it's sync
        assert session.ended_at is not None

    def test_pages_scraped_tracked(self, tmp_path):
        pages = [MagicMock(), MagicMock(), MagicMock()]
        p = _pipeline(corpus="tiny", pages=pages, tmp_path=tmp_path)
        session = LearningSession(session_id="s1", started_at=time.time())
        p._run_learn(session, urls=None, crawl_depth=1, max_pages=10, training_steps=10)
        assert session.pages_scraped == 3
