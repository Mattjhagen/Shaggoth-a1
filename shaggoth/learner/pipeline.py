"""Self-learning pipeline — the brain's growth loop.

Orchestrates:
  1. Scraping new content from seed URLs
  2. Processing and cleaning text
  3. Training TinyGPT on accumulated corpus
  4. Tracking learning history and metrics
"""

from __future__ import annotations

import json
import time
import threading
from dataclasses import dataclass, asdict
from pathlib import Path

from ..config import DATA_DIR
from ..scraper.engine import ScraperEngine


@dataclass
class LearningSession:
    session_id: str
    started_at: float
    ended_at: float | None = None
    pages_scraped: int = 0
    words_learned: int = 0
    training_steps: int = 0
    loss_start: float = 0.0
    loss_end: float = 0.0
    model_path: str = ""
    status: str = "running"  # running | completed | failed
    error: str | None = None


class LearnerPipeline:
    """Manages the self-learning lifecycle: scrape → process → train → save."""

    def __init__(
        self,
        scraper: ScraperEngine | None = None,
        model_path: str | None = None,
    ):
        self.scraper = scraper or ScraperEngine()
        self.model_path = model_path or str(DATA_DIR / "tinygpt.pt")
        self.history_path = str(DATA_DIR / "learning_history.json")
        self._learning = False
        self._current_session: LearningSession | None = None
        self._lock = threading.Lock()
        self._load_history()

    def _load_history(self) -> None:
        path = Path(self.history_path)
        if path.exists():
            self._history: list[dict] = json.loads(path.read_text())
        else:
            self._history = []

    def _save_history(self) -> None:
        Path(self.history_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.history_path).write_text(json.dumps(self._history, indent=2))

    @property
    def is_learning(self) -> bool:
        return self._learning

    @property
    def current_session(self) -> LearningSession | None:
        return self._current_session

    def learn(
        self,
        urls: list[str] | None = None,
        crawl_depth: int = 1,
        max_pages: int = 20,
        training_steps: int = 1000,
        background: bool = True,
    ) -> LearningSession:
        """Run a full learn cycle: scrape → train → save.

        If background=True, runs in a daemon thread.
        """
        session = LearningSession(
            session_id=f"learn-{int(time.time())}",
            started_at=time.time(),
        )

        if background:
            t = threading.Thread(target=self._run_learn, args=(session, urls, crawl_depth, max_pages, training_steps), daemon=True)
            t.start()
        else:
            self._run_learn(session, urls, crawl_depth, max_pages, training_steps)

        return session

    def _run_learn(
        self,
        session: LearningSession,
        urls: list[str] | None,
        crawl_depth: int,
        max_pages: int,
        training_steps: int,
    ) -> None:
        with self._lock:
            if self._learning:
                session.status = "failed"
                session.error = "Already learning"
                return
            self._learning = True
            self._current_session = session

        try:
            # 1. Add URLs as seeds if provided
            if urls:
                self.scraper.add_seeds(urls)

            # 2. Crawl and scrape
            pages = self.scraper.crawl(max_pages=max_pages, depth=crawl_depth)
            session.pages_scraped = len(pages)

            # 3. Get combined corpus
            corpus = self.scraper.get_corpus_text()
            session.words_learned = len(corpus.split())

            if session.words_learned < 100:
                session.status = "completed"
                session.error = "Not enough text to train (need 100+ words)"
                return

            # 4. Train model (TinyGPT if torch available, else Markov)
            try:
                from ..models.tinygpt import TinyGPTModel, TORCH_AVAILABLE

                if TORCH_AVAILABLE:
                    model = TinyGPTModel()
                    model_file = Path(self.model_path)
                    if model_file.exists():
                        model.load(self.model_path)
                        print(f"[learner] Loaded existing model from {self.model_path}")
                    model.train(corpus, steps=training_steps, log_every=200)
                    model.save(self.model_path)
                    session.model_path = self.model_path
                    session.training_steps = training_steps
                else:
                    raise RuntimeError("torch not available")
            except Exception as exc:
                # Fall back to Markov for ANY TinyGPT failure, not just
                # RuntimeError. A corpus too small for the configured
                # block_size raises ValueError, which slipped past the old
                # `except RuntimeError` and failed the whole session -- after
                # the scrape had already succeeded. Losing 161k freshly
                # scraped words because the optional model is unavailable is
                # the wrong trade.
                print(f"[learner] TinyGPT unavailable ({exc}); training Markov instead")
                from ..models.markov import MarkovModel
                model = MarkovModel()
                model.train(corpus)
                markov_path = str(DATA_DIR / "markov_model.json")
                model.save(markov_path)
                session.model_path = markov_path
                session.training_steps = 0

            session.status = "completed"

        except Exception as exc:
            session.status = "failed"
            session.error = str(exc)[:500]

        finally:
            session.ended_at = time.time()
            self._history.append(asdict(session))
            self._save_history()
            self._learning = False
            self._current_session = None

    def active_model(self) -> tuple[str, str]:
        """The model actually on disk, as ``(kind, path)``.

        TinyGPT wins when present because the engine prefers it; otherwise
        the Markov model. ``("none", "")`` when neither exists.

        Reporting only ``self.model_path`` (always the TinyGPT path) made the
        dashboard show "TRAINED: No" while a 12 MB trained Markov model sat
        right next to it -- the model every reply was actually coming from.
        """
        tinygpt = Path(self.model_path)
        if tinygpt.exists():
            return "tinygpt", str(tinygpt)
        markov = DATA_DIR / "markov_model.json"
        if markov.exists():
            return "markov", str(markov)
        return "none", ""

    def status(self) -> dict:
        """Return current learning status."""
        model_kind, active_path = self.active_model()
        model_exists = bool(active_path)
        model_size = Path(active_path).stat().st_size if model_exists else 0
        return {
            "is_learning": self._learning,
            "current_session": asdict(self._current_session) if self._current_session else None,
            "model_exists": model_exists,
            "model_kind": model_kind,
            "model_size_bytes": model_size,
            "model_path": active_path or self.model_path,
            "total_sessions": len(self._history),
            "last_session": self._history[-1] if self._history else None,
            "scraper_stats": self.scraper.stats(),
        }

    def history(self, limit: int = 10) -> list[dict]:
        """Return recent learning sessions."""
        return self._history[-limit:]
