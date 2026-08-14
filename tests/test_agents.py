"""The onboard crew: cadence, failure containment, and the two defaults that
protect the corpus (curator reports, trainer gates).

Everything here runs on fake clocks and fakes of the loops being wrapped. No
sleeping, no threads left running, no network, no filesystem outside tmpdirs.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from shaggoth.agents import (
    DEFAULT_AGENT_SETTINGS,
    CuratorAgent,
    GathererAgent,
    GraderAgent,
    ResearcherAgent,
    Supervisor,
    TrainerAgent,
    agents_enabled,
    build_crew,
)
from shaggoth.agents.base import Agent, AgentSkipped


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class CountingAgent(Agent):
    name = "counting"
    role = "counts"
    default_cadence_minutes = 10.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = 0

    def work(self) -> dict:
        self.calls += 1
        return {"calls": self.calls}


class ExplodingAgent(Agent):
    name = "exploding"
    default_cadence_minutes = 10.0

    def work(self) -> dict:
        raise RuntimeError("boom")


class SkippingAgent(Agent):
    name = "skipping"
    default_cadence_minutes = 10.0

    def work(self) -> dict:
        raise AgentSkipped("nothing queued")


# --------------------------------------------------------------------------
# base


class TestAgentBase(unittest.TestCase):
    def test_not_due_until_one_cadence_after_start(self):
        """The crew must not all fire the second the server comes up."""
        clock = FakeClock()
        agent = CountingAgent(clock=clock)
        self.assertFalse(agent.due())
        clock.advance(10 * 60 - 1)
        self.assertFalse(agent.due())
        clock.advance(1)
        self.assertTrue(agent.due())

    def test_run_records_and_reschedules(self):
        clock = FakeClock()
        agent = CountingAgent(clock=clock)
        clock.advance(10 * 60)
        report = agent.run()
        self.assertTrue(report.ran)
        self.assertEqual(report.detail, {"calls": 1})
        self.assertEqual(agent.stats.runs, 1)
        self.assertFalse(agent.due())

    def test_reschedule_measures_from_finish_not_from_due(self):
        """A long run must not come due again the instant it finishes."""
        clock = FakeClock()
        agent = CountingAgent(clock=clock)
        clock.advance(10 * 60)  # due

        class Slow(CountingAgent):
            def work(inner) -> dict:  # noqa: N805
                clock.advance(30 * 60)  # runs for three cadences
                return {}

        slow = Slow(clock=clock)
        slow._next_due = clock.now
        slow.run()
        self.assertFalse(slow.due())
        self.assertAlmostEqual(slow.due_in(), 10 * 60, places=3)

    def test_failure_is_contained_and_counted(self):
        clock = FakeClock()
        agent = ExplodingAgent(clock=clock)
        clock.advance(10 * 60)
        report = agent.run()  # must not raise
        self.assertFalse(report.ran)
        self.assertIn("boom", report.error)
        self.assertEqual(agent.stats.failures, 1)
        self.assertEqual(agent.stats.runs, 0)
        # And it is still scheduled: one bad turn does not retire an agent.
        self.assertGreater(agent.due_in(), 0)

    def test_skip_is_not_a_failure(self):
        clock = FakeClock()
        agent = SkippingAgent(clock=clock)
        clock.advance(10 * 60)
        report = agent.run()
        self.assertTrue(report.skipped)
        self.assertEqual(agent.stats.skips, 1)
        self.assertEqual(agent.stats.failures, 0)
        self.assertEqual(agent.stats.runs, 0)
        self.assertEqual(agent.stats.last_skip_reason, "nothing queued")

    def test_cadence_is_clamped_off_zero(self):
        """A zero cadence in settings.json must not busy-loop the supervisor."""
        agent = CountingAgent(cadence_minutes=0)
        self.assertGreaterEqual(agent.cadence_seconds, 60.0)

    def test_disabled_agent_is_never_due(self):
        clock = FakeClock()
        agent = CountingAgent(enabled=False, clock=clock)
        clock.advance(10 * 60 * 5)
        self.assertFalse(agent.due())

    def test_status_is_json_safe(self):
        import json

        agent = CountingAgent()
        json.dumps(agent.status())  # must not raise


# --------------------------------------------------------------------------
# supervisor


class TestSupervisor(unittest.TestCase):
    def test_tick_runs_at_most_one_agent(self):
        """Two due agents must not work simultaneously -- that is the point."""
        clock = FakeClock()
        a = CountingAgent(clock=clock)
        b = CountingAgent(clock=clock)
        b.name = "counting-b"
        sup = Supervisor([a, b], clock=clock)
        clock.advance(10 * 60)

        self.assertEqual(len(sup.due_agents()), 2)
        reports = sup.tick()
        self.assertEqual(len(reports), 1)
        self.assertEqual((a.calls, b.calls), (1, 0))
        reports = sup.tick()
        self.assertEqual((a.calls, b.calls), (1, 1))

    def test_registration_order_is_priority(self):
        clock = FakeClock()
        first = CountingAgent(clock=clock)
        first.name = "first"
        second = CountingAgent(clock=clock)
        second.name = "second"
        sup = Supervisor([first, second], clock=clock)
        clock.advance(10 * 60)
        self.assertEqual(sup.tick()[0].name, "first")

    def test_tick_with_nothing_due(self):
        clock = FakeClock()
        sup = Supervisor([CountingAgent(clock=clock)], clock=clock)
        self.assertEqual(sup.tick(), [])

    def test_run_now_ignores_cadence(self):
        clock = FakeClock()
        agent = CountingAgent(clock=clock)
        sup = Supervisor([agent], clock=clock)
        self.assertFalse(agent.due())
        reports = sup.run_now("counting")
        self.assertEqual(len(reports), 1)
        self.assertEqual(agent.calls, 1)

    def test_run_now_unknown_agent(self):
        sup = Supervisor([CountingAgent()])
        with self.assertRaises(KeyError):
            sup.run_now("nope")

    def test_run_now_all_skips_disabled(self):
        clock = FakeClock()
        on = CountingAgent(clock=clock)
        off = CountingAgent(enabled=False, clock=clock)
        off.name = "off"
        sup = Supervisor([on, off], clock=clock)
        sup.run_now()
        self.assertEqual((on.calls, off.calls), (1, 0))

    def test_a_broken_agent_does_not_stop_the_crew(self):
        clock = FakeClock()
        boom = ExplodingAgent(clock=clock)
        ok = CountingAgent(clock=clock)
        sup = Supervisor([boom, ok], clock=clock)
        clock.advance(10 * 60)
        sup.tick()
        sup.tick()
        self.assertEqual(ok.calls, 1)
        self.assertEqual(boom.stats.failures, 1)

    def test_history_is_bounded(self):
        clock = FakeClock()
        agent = CountingAgent(clock=clock)
        sup = Supervisor([agent], clock=clock)
        for _ in range(250):
            sup.run_now("counting")
        self.assertLessEqual(len(sup._history), 200)

    def test_status_is_json_safe(self):
        import json

        sup = Supervisor([CountingAgent()])
        json.dumps(sup.status())


# --------------------------------------------------------------------------
# the crew


class FakeCuriosity:
    def __init__(self):
        self.is_running = False


class FakeSchedulerConfig:
    enabled = True


class FakeScheduler:
    def __init__(self):
        self.config = FakeSchedulerConfig()
        self.curiosity = FakeCuriosity()
        self.cycles = 0

    def run_cycle(self):
        self.cycles += 1

    def status(self):
        return {"buffered_messages": 0}


class FakeTeacher:
    model = "fake-teacher"

    def __init__(self, ok=True):
        self.ok = ok

    def available(self):
        return self.ok


class FakeCritic:
    max_load = 1e9  # never "busy", so the test is about the agent not the box

    def __init__(self, teacher):
        self.teacher = teacher
        self.batches = 0

    def run_batch(self, limit=None):
        self.batches += 1
        return {"judged": 2, "limit": limit}


class TestResearcherAgent(unittest.TestCase):
    def test_runs_one_cycle(self):
        sched = FakeScheduler()
        agent = ResearcherAgent(sched)
        report = agent.run()
        self.assertTrue(report.ran)
        self.assertEqual(sched.cycles, 1)

    def test_does_not_start_the_scheduler_thread(self):
        """Double-driving the scheduler is the bug this design exists to avoid."""
        sched = FakeScheduler()
        sched.start = lambda: self.fail("agent must not start the scheduler")
        ResearcherAgent(sched).run()

    def test_skips_when_a_research_episode_is_running(self):
        sched = FakeScheduler()
        sched.curiosity.is_running = True
        report = ResearcherAgent(sched).run()
        self.assertTrue(report.skipped)
        self.assertEqual(sched.cycles, 0)

    def test_skips_when_scheduler_disabled(self):
        sched = FakeScheduler()
        sched.config.enabled = False
        self.assertTrue(ResearcherAgent(sched).run().skipped)

    def test_skips_without_a_scheduler(self):
        self.assertTrue(ResearcherAgent(None).run().skipped)


class TestGraderAgent(unittest.TestCase):
    def test_runs_a_batch(self):
        critic = FakeCritic(FakeTeacher(ok=True))
        report = GraderAgent(critic, batch=4).run()
        self.assertTrue(report.ran)
        self.assertEqual(critic.batches, 1)
        self.assertEqual(report.detail["limit"], 4)

    def test_skips_when_teacher_unavailable(self):
        critic = FakeCritic(FakeTeacher(ok=False))
        report = GraderAgent(critic).run()
        self.assertTrue(report.skipped)
        self.assertIn("fake-teacher", report.reason)
        self.assertEqual(critic.batches, 0)

    def test_skips_without_a_critic(self):
        self.assertTrue(GraderAgent(None).run().skipped)


class FakeEntry:
    def __init__(self, topic, path, word_count=100, content="the sky is blue"):
        self.topic = topic
        self.path = path
        self.word_count = word_count
        self.content = content


class FakeKnowledge:
    def __init__(self, entries, directory):
        self._entries = list(entries)
        self.directory = Path(directory)
        self.reloads = 0

    def maybe_reload(self):
        self.reloads += 1
        return False


class TestCuratorAgent(unittest.TestCase):
    def _dup_corpus(self, tmp):
        knowledge_dir = Path(tmp) / "knowledge"
        knowledge_dir.mkdir()
        honest = knowledge_dir / "the-sky-blue.md"
        dupe = knowledge_dir / "why-is-the-sky-blue.md"
        honest.write_text("real entry", encoding="utf-8")
        dupe.write_text("query-named duplicate", encoding="utf-8")
        entries = [
            FakeEntry("The Sky Blue", str(honest), word_count=900),
            FakeEntry("Why Is The Sky Blue", str(dupe), word_count=100),
        ]
        return FakeKnowledge(entries, knowledge_dir), honest, dupe

    def test_reports_without_touching_files_by_default(self):
        with TemporaryDirectory() as tmp:
            knowledge, honest, dupe = self._dup_corpus(tmp)
            report = CuratorAgent(knowledge).run()
            self.assertTrue(report.ran)
            self.assertFalse(report.detail["applied"])
            self.assertEqual(report.detail["duplicate_subjects"], 1)
            self.assertEqual(report.detail["files"], 1)
            # The whole point of the default: nothing moved.
            self.assertTrue(honest.exists())
            self.assertTrue(dupe.exists())

    def test_apply_quarantines_the_question_named_variant(self):
        with TemporaryDirectory() as tmp:
            knowledge, honest, dupe = self._dup_corpus(tmp)
            report = CuratorAgent(knowledge, apply=True).run()
            self.assertTrue(report.detail["applied"])
            self.assertEqual(report.detail["moved"], 1)
            self.assertTrue(honest.exists(), "the honest entry must survive")
            self.assertFalse(dupe.exists())
            # Moved, never deleted -- the run has to be undoable.
            quarantined = Path(report.detail["quarantine_dir"]) / dupe.name
            self.assertTrue(quarantined.exists())
            self.assertEqual(quarantined.read_text(encoding="utf-8"),
                             "query-named duplicate")

    def test_skips_a_clean_corpus(self):
        with TemporaryDirectory() as tmp:
            knowledge = FakeKnowledge(
                [FakeEntry("Photosynthesis", str(Path(tmp) / "photosynthesis.md"))],
                tmp,
            )
            report = CuratorAgent(knowledge).run()
            self.assertTrue(report.skipped)
            self.assertIn("clean", report.reason)

    def test_skips_an_empty_corpus(self):
        with TemporaryDirectory() as tmp:
            self.assertTrue(CuratorAgent(FakeKnowledge([], tmp)).run().skipped)


class FakePage:
    def __init__(self, text):
        self.text = text


class FakeScraper:
    def __init__(self, seeds=1, pages=2):
        self._seeds = seeds
        self._pages = pages
        self.crawls = 0
        self.corpus = "the sky is blue " * 100

    def get_unscraped_seeds(self, limit=20):
        return ["http://example.com"] * min(limit, self._seeds)

    def crawl(self, max_pages=10, depth=1):
        self.crawls += 1
        return [FakePage("word " * 50) for _ in range(self._pages)]

    def get_corpus_text(self, min_words=50):
        return self.corpus


class TestGathererAgent(unittest.TestCase):
    def test_crawls_when_seeds_are_queued(self):
        scraper = FakeScraper(seeds=3, pages=2)
        report = GathererAgent(scraper, max_pages=5).run()
        self.assertTrue(report.ran)
        self.assertEqual(report.detail["pages"], 2)
        self.assertEqual(report.detail["words"], 100)

    def test_skips_with_no_seeds(self):
        scraper = FakeScraper(seeds=0)
        report = GathererAgent(scraper).run()
        self.assertTrue(report.skipped)
        self.assertEqual(scraper.crawls, 0)

    def test_skips_without_a_scraper(self):
        self.assertTrue(GathererAgent(None).run().skipped)


class FakeGenModel:
    """A model whose generated text is controllable, for the coherence gate."""

    def __init__(self, output="the sky is blue and water is wet " * 6):
        self.output = output

    def generate(self, prompt="", max_tokens=60):
        return self.output


class FakeEngine:
    def __init__(self, knowledge=None, model=None):
        self.knowledge = knowledge
        self.model = model


class TestTrainerAgent(unittest.TestCase):
    def _engine(self, tmp, words=8000, model=None):
        text = "the sky is blue and water is wet and the sun is bright "
        repeats = max(1, words // len(text.split()))
        entries = [
            FakeEntry("Corpus", str(Path(tmp) / "c.md"), content=text * repeats)
        ]
        return FakeEngine(FakeKnowledge(entries, tmp), model=model)

    def test_skips_when_the_corpus_is_too_small(self):
        with TemporaryDirectory() as tmp:
            engine = self._engine(tmp, words=10)
            report = TrainerAgent(engine, min_words=5000).run()
            self.assertTrue(report.skipped)
            self.assertIn("too small", report.reason)

    def test_promotes_a_coherent_candidate_and_writes_atomically(self):
        with TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "markov_model.json")
            engine = self._engine(tmp)
            report = TrainerAgent(engine, markov_path=path, min_words=100).run()
            self.assertTrue(report.ran, report.error)
            self.assertTrue(report.detail["promoted"], report.detail)
            self.assertTrue(Path(path).exists())
            # No candidate file left behind -- os.replace, not two writes.
            self.assertFalse(Path(path + ".candidate").exists())
            self.assertTrue(report.detail["swapped_live_model"])

    def test_rejects_an_incoherent_candidate_and_keeps_the_live_model(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "markov_model.json"
            path.write_text("LIVE MODEL", encoding="utf-8")
            engine = self._engine(tmp)
            live = object()
            engine.model = live

            agent = TrainerAgent(engine, markov_path=str(path), min_words=100)
            from shaggoth.models import promote as promote_mod

            original = promote_mod.coherence_report
            try:
                promote_mod.coherence_report = lambda model, vocab, **kw: type(
                    "R", (), {"passed": False, "reason": "emitted only 0 words",
                              "known_word_ratio": 0.0}
                )()
                report = agent.run()
            finally:
                promote_mod.coherence_report = original

            self.assertTrue(report.ran)
            self.assertFalse(report.detail["promoted"])
            self.assertIn("REJECT", report.detail["reason"])
            # The live model file and the live model object are both untouched.
            self.assertEqual(path.read_text(encoding="utf-8"), "LIVE MODEL")
            self.assertIs(engine.model, live)

    def test_rejects_a_candidate_that_regressed_against_live(self):
        """A candidate that got worse must lose, even though it passes the gate."""
        from shaggoth.models import promote as promote_mod
        from shaggoth.models.markov import MarkovModel

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "markov_model.json"
            path.write_text("LIVE MODEL", encoding="utf-8")
            engine = self._engine(tmp)
            live = MarkovModel()
            live.train("the sky is blue and water is wet")
            engine.model = live

            def fake_report(model, vocab, **kw):
                ratio = 0.60 if model is not live else 0.99
                return type(
                    "R", (), {"passed": True, "reason": "ok", "known_word_ratio": ratio}
                )()

            original = promote_mod.coherence_report
            try:
                promote_mod.coherence_report = fake_report
                report = TrainerAgent(
                    engine, markov_path=str(path), min_words=100
                ).run()
            finally:
                promote_mod.coherence_report = original

            self.assertFalse(report.detail["promoted"])
            self.assertIn("regressed", report.detail["reason"])
            self.assertEqual(path.read_text(encoding="utf-8"), "LIVE MODEL")
            self.assertIs(engine.model, live)

    def test_does_not_downgrade_a_non_markov_live_model(self):
        """Promoting Markov over a GPT-class model would be a silent downgrade."""
        with TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "markov_model.json")
            engine = self._engine(tmp)
            gpt = FakeGenModel()
            engine.model = gpt
            report = TrainerAgent(engine, markov_path=path, min_words=100).run()
            self.assertTrue(report.detail["promoted"])
            self.assertFalse(report.detail["swapped_live_model"])
            self.assertIs(engine.model, gpt)
            self.assertTrue(Path(path).exists(), "still saved for later use")


# --------------------------------------------------------------------------
# wiring


class TestBuildCrew(unittest.TestCase):
    def test_disabled_by_default(self):
        self.assertFalse(agents_enabled({}))
        self.assertFalse(agents_enabled(None))
        self.assertFalse(DEFAULT_AGENT_SETTINGS["enabled"])

    def test_enabled_by_settings(self):
        self.assertTrue(agents_enabled({"agents": {"enabled": True}}))

    def test_crew_order_is_the_documented_priority(self):
        sup = build_crew(FakeEngine())
        self.assertEqual(
            [a.name for a in sup.agents],
            ["researcher", "grader", "curator", "gatherer", "trainer"],
        )

    def test_every_agent_is_registered_even_with_nothing_to_wrap(self):
        """An absent agent is indistinguishable from one that was never built."""
        sup = build_crew(FakeEngine())
        for report in sup.run_now():
            self.assertFalse(report.ran)
            self.assertTrue(report.skipped or report.error)
        self.assertEqual(len(sup.status()["agents"]), 5)

    def test_per_agent_settings_override_defaults(self):
        settings = {
            "agents": {
                "enabled": True,
                "grader": {"enabled": False, "cadence_minutes": 30},
                "curator": {"enabled": True, "cadence_minutes": 60, "apply": True},
            }
        }
        sup = build_crew(FakeEngine(), settings=settings)
        grader = sup.get("grader")
        self.assertFalse(grader.enabled)
        self.assertEqual(grader.cadence_seconds, 30 * 60)
        self.assertTrue(sup.get("curator").apply)
        # Untouched agents keep their defaults.
        self.assertEqual(sup.get("researcher").cadence_seconds, 15 * 60)

    def test_partial_override_does_not_drop_sibling_keys(self):
        """{"curator": {"cadence_minutes": 5}} must not lose the apply default."""
        sup = build_crew(
            FakeEngine(),
            settings={"agents": {"enabled": True, "curator": {"cadence_minutes": 5}}},
        )
        curator = sup.get("curator")
        self.assertEqual(curator.cadence_seconds, 5 * 60)
        self.assertFalse(curator.apply)

    def test_trainer_gets_the_configured_markov_path(self):
        sup = build_crew(FakeEngine(), settings={"markov_model_path": "/tmp/m.json"})
        self.assertEqual(sup.get("trainer").markov_path, "/tmp/m.json")


class TestSupervisorThread(unittest.TestCase):
    def test_start_and_stop_are_clean(self):
        agent = CountingAgent(cadence_minutes=1)
        sup = Supervisor([agent], tick_seconds=0.01)
        sup.start()
        self.assertTrue(sup.running)
        sup.start()  # idempotent
        sup.stop()
        self.assertFalse(sup.running)


if __name__ == "__main__":
    unittest.main()
