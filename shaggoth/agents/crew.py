"""The five onboard agents.

None of these implement training from scratch -- every one wraps a loop that
already existed and already had its edge cases beaten out of it on this
hardware. What they add is a shared cadence, a shared status surface, and a
consistent answer to "what happens when there is nothing to do" (an
:class:`~.base.AgentSkipped`, not a silent no-op that reads as success).

Two of them are deliberately conservative by default:

* the **curator** reports what it would quarantine and moves nothing unless
  ``apply=True``. The corpus is the product; an agent that prunes it
  unattended on a cadence is one bad heuristic away from deleting the thing
  it was hired to protect.
* the **trainer** promotes nothing that fails the coherence gate, and never
  promotes on a first run with no live model to compare against.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..quality.critic import DEFAULT_MAX_LOAD, machine_busy
from .base import Agent, AgentSkipped


class ResearcherAgent(Agent):
    """Turns conversation into knowledge: one curiosity cycle per turn.

    Wraps :class:`~shaggoth.curiosity.scheduler.CuriosityScheduler`, whose
    cycle already prioritises correctly -- topics from real messages first,
    then the feedback repair queue, then the stalest entry, then proactive
    exploration -- so this agent deliberately adds no policy of its own.
    """

    name = "researcher"
    role = "turns conversations into researched knowledge entries"
    default_cadence_minutes = 15.0

    def __init__(self, scheduler, **kwargs):
        super().__init__(**kwargs)
        self.scheduler = scheduler

    def work(self) -> dict:
        if self.scheduler is None:
            raise AgentSkipped("no curiosity scheduler")
        if not getattr(self.scheduler.config, "enabled", True):
            raise AgentSkipped("curiosity scheduler disabled in config")
        if getattr(self.scheduler.curiosity, "is_running", False):
            raise AgentSkipped("a research episode is already running")

        before = self.scheduler.status().get("buffered_messages", 0)
        self.scheduler.run_cycle()
        after = self.scheduler.status().get("buffered_messages", 0)
        return {"buffered_before": before, "buffered_after": after}


class GraderAgent(Agent):
    """Grades Shaggoth's own past answers and files the bad ones as feedback.

    Wraps :class:`~shaggoth.quality.critic.CriticLoop`. The batch is bounded
    by the critic itself and it stands down above a load threshold, so this
    agent's only job is to offer it a turn and report what came back.
    """

    name = "grader"
    role = "self-grades past answers and queues the bad ones for repair"
    default_cadence_minutes = 5.0

    def __init__(self, critic, batch: int | None = None, **kwargs):
        super().__init__(**kwargs)
        self.critic = critic
        self.batch = batch

    def work(self) -> dict:
        if self.critic is None:
            raise AgentSkipped("no critic loop")
        teacher = getattr(self.critic, "teacher", None)
        if teacher is None or not teacher.available():
            model = getattr(teacher, "model", "teacher")
            raise AgentSkipped(f"{model} not available")
        if machine_busy(getattr(self.critic, "max_load", DEFAULT_MAX_LOAD)):
            raise AgentSkipped("machine busy")
        return self.critic.run_batch(limit=self.batch)


class CuratorAgent(Agent):
    """Keeps the corpus clean: finds duplicate title variants of one subject.

    Reports by default. ``apply=True`` moves the losing variants into a
    quarantine directory beside the knowledge dir -- moved, never deleted, so
    a bad call is undone by moving them back.
    """

    name = "curator"
    role = "finds duplicate knowledge entries and quarantines them on request"
    default_cadence_minutes = 60.0

    def __init__(self, knowledge, apply: bool = False, quarantine_dir=None, **kwargs):
        super().__init__(**kwargs)
        self.knowledge = knowledge
        self.apply = bool(apply)
        self.quarantine_dir = quarantine_dir

    def _quarantine_dir(self) -> Path:
        from ..knowledge.dedupe import QUARANTINE_DIRNAME

        if self.quarantine_dir is not None:
            return Path(self.quarantine_dir)
        return Path(self.knowledge.directory).parent / QUARANTINE_DIRNAME

    def work(self) -> dict:
        from ..knowledge.dedupe import plan_dedup, plan_summary, quarantine

        if self.knowledge is None:
            raise AgentSkipped("no knowledge base")
        self.knowledge.maybe_reload()
        entries = list(self.knowledge._entries)
        if not entries:
            raise AgentSkipped("empty corpus")

        plan = plan_dedup(entries)
        summary = plan_summary(plan)
        summary["entries"] = len(entries)
        summary["applied"] = False
        if not plan:
            raise AgentSkipped(f"corpus clean ({len(entries)} entries)")

        if self.apply:
            moved = quarantine(plan, self._quarantine_dir())
            summary["applied"] = True
            summary["moved"] = len(moved)
            summary["quarantine_dir"] = str(self._quarantine_dir())
            # The corpus changed underneath the live index; the reload is what
            # makes the removal visible to answering, and maybe_reload only
            # notices deletions because of the fix in engine.py.
            self.knowledge.maybe_reload()
        return summary


class GathererAgent(Agent):
    """Reads crawl-permissive sources that are already queued as seeds.

    Deliberately does not choose what to read. Seeds arrive from the learner,
    from ``/scrape/url`` and from tenant crawls, all of which are already
    gated on robots.txt and paced per origin by the scraper.
    """

    name = "gatherer"
    role = "crawls queued crawl-permissive sources into the corpus"
    default_cadence_minutes = 60.0

    def __init__(self, scraper, max_pages: int = 5, depth: int = 1, **kwargs):
        super().__init__(**kwargs)
        self.scraper = scraper
        self.max_pages = max_pages
        self.depth = depth

    def work(self) -> dict:
        if self.scraper is None:
            raise AgentSkipped("no scraper")
        if machine_busy():
            raise AgentSkipped("machine busy")
        if not self.scraper.get_unscraped_seeds(1):
            raise AgentSkipped("no unscraped seeds")

        pages = self.scraper.crawl(max_pages=self.max_pages, depth=self.depth)
        return {
            "pages": len(pages),
            "words": sum(len((p.text or "").split()) for p in pages),
        }


class TrainerAgent(Agent):
    """Retrains the Markov model and promotes it only if it stays coherent.

    The gate is :func:`shaggoth.models.promote.coherence_report` plus a
    no-regression check against the live model. It is **not** the full
    coherence+perplexity gate used for TinyGPT: ``models/eval.py``'s
    perplexity needs a tokenizer and a block size, both of which are TinyGPT
    concepts a Markov chain has no equivalent for. Retraining TinyGPT stays in
    ``scripts/retrain_tinygpt.py``, where torch is a prerequisite rather than
    something a background agent silently depends on.

    Promotion swaps ``engine.model`` to the already-trained candidate object
    rather than reloading the live model in place. Reloading mutates a model
    that request threads are generating from; rebinding the attribute is a
    single reference assignment and a request either gets the whole old model
    or the whole new one.
    """

    name = "trainer"
    role = "retrains the Markov model behind a coherence gate"
    default_cadence_minutes = 24 * 60.0

    #: A candidate may be this much worse than live on known-word ratio before
    #: it is rejected as a regression. Small, because the ratio is stable
    #: between runs on the same corpus and a real drop means the corpus got
    #: dirtier, which is a curator problem and not something to promote past.
    REGRESSION_TOLERANCE = 0.02

    def __init__(self, engine, scraper=None, markov_path: str | None = None, min_words: int = 5000, **kwargs):
        super().__init__(**kwargs)
        self.engine = engine
        self.scraper = scraper
        self.markov_path = markov_path
        self.min_words = min_words

    def corpus(self) -> str:
        """Everything the model is allowed to learn language from.

        Scraped pages plus the knowledge corpus. The knowledge entries matter
        here: they are the text answers are actually built from, so a model
        trained without them generates in a register the rest of the system
        never uses.
        """
        parts: list[str] = []
        if self.scraper is not None:
            try:
                parts.append(self.scraper.get_corpus_text())
            except Exception as exc:  # noqa: BLE001 -- a missing scrape db is not fatal
                print(f"[agents] trainer: scraper corpus unavailable ({exc})")
        knowledge = getattr(self.engine, "knowledge", None)
        if knowledge is not None:
            knowledge.maybe_reload()
            parts.extend(e.content for e in knowledge._entries)
        return "\n\n".join(p for p in parts if p)

    def work(self) -> dict:
        from ..models.markov import MarkovModel
        from ..models.promote import coherence_report, corpus_vocabulary

        if machine_busy():
            raise AgentSkipped("machine busy")

        corpus = self.corpus()
        words = len(corpus.split())
        if words < self.min_words:
            raise AgentSkipped(f"corpus too small to retrain ({words} words)")

        candidate = MarkovModel()
        candidate.train(corpus)
        vocab = corpus_vocabulary(corpus)
        report = coherence_report(candidate, vocab)

        result = {
            "corpus_words": words,
            "candidate_known_word_ratio": report.known_word_ratio,
            "promoted": False,
        }

        if not report.passed:
            result["reason"] = f"REJECT: {report.reason}"
            return result

        live = getattr(self.engine, "model", None)
        if isinstance(live, MarkovModel):
            live_report = coherence_report(live, vocab)
            result["live_known_word_ratio"] = live_report.known_word_ratio
            if (
                report.known_word_ratio
                < live_report.known_word_ratio - self.REGRESSION_TOLERANCE
            ):
                result["reason"] = (
                    f"REJECT: known-word ratio {report.known_word_ratio:.3f} "
                    f"regressed from live {live_report.known_word_ratio:.3f}"
                )
                return result

        path = self.markov_path
        if path:
            # Write beside the target and rename, so a crash mid-write cannot
            # leave a truncated model where the live one used to be.
            tmp = f"{path}.candidate"
            candidate.save(tmp)
            os.replace(tmp, path)
            result["path"] = path

        if live is None or isinstance(live, MarkovModel):
            self.engine.model = candidate
            result["swapped_live_model"] = True
        else:
            # A GPT-class or cloud model is answering; the Markov model is not
            # on the live path and replacing it would be a silent downgrade.
            result["swapped_live_model"] = False
            result["reason"] = "saved but not swapped: a non-Markov model is live"

        result["promoted"] = True
        result["reason"] = result.get("reason") or f"PROMOTE: {report.reason}"
        return result
