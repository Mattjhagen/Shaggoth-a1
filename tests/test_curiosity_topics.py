"""Chunk names must never be treated as subjects, and "do I know this?"
must not degrade as the corpus grows.

Both bugs here were found by watching the knowledge base grow on its own:

* ``ingest_text`` names a slice "Aeroponic Farming (part 2)". ``add_entry``
  strips the parentheses, so the next scan reads it back as the plain topic
  "Aeroponic Farming Part 2" -- indistinguishable from a real article title.
  ``refresh_stale`` then researched that literal string, chunked *that*, and
  wrote "Aeroponic Farming Part 1 Part 1". On a 15-minute timer, forever.

* ``analyze_message`` asked whether 60% of a topic's words appeared anywhere
  in a union of every keyword in the corpus. At 368 entries that set held
  44,149 words, so every real phrase looked already-known and
  conversation-driven curiosity silently stopped firing -- and got more wrong
  the more Shaggoth learned.
"""
from __future__ import annotations

import pytest

from shaggoth.curiosity.topics import (
    base_topic,
    canonical_subject,
    is_chunk_topic,
    is_question_topic,
    strip_question_prefix,
)


# --------------------------------------------------------------------------
# Chunk names
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "topic,expected",
    [
        ("Aeroponic Farming Part 2", "Aeroponic Farming"),
        ("Aeroponic Farming (part 2)", "Aeroponic Farming"),
        ("Aeroponic Farming part 10", "Aeroponic Farming"),
        ("Aeroponic Farming Parts 3", "Aeroponic Farming"),
    ],
)
def test_base_topic_strips_a_chunk_suffix(topic, expected):
    assert base_topic(topic) == expected


def test_base_topic_unwinds_stacked_suffixes():
    """The observed corruption: one suffix added per refresh cycle."""
    assert base_topic("Aeroponic Farming Part 1 Part 1 Part 1") == "Aeroponic Farming"


def test_base_topic_leaves_real_titles_alone():
    for title in (
        "Machine Learning",
        "Photosynthesis",
        "The Gentle Conquest Chapter 22: The Book",
        "Part of a Whole",          # "Part" not in trailing position
        "Quantum Mechanics",
    ):
        assert base_topic(title) == title


def test_base_topic_handles_degenerate_input():
    assert base_topic("") == ""
    assert base_topic(None) == ""
    assert base_topic("Part 1") == ""


def test_is_chunk_topic():
    assert is_chunk_topic("Aeroponic Farming Part 2")
    assert not is_chunk_topic("Aeroponic Farming")
    assert not is_chunk_topic("Machine Learning")


# --------------------------------------------------------------------------
# strip_question_prefix / canonical_subject: AGENTS.md §NN
#
# "why is the sky blue" bypassing extract_topic_query stores an entry titled
# after the whole question, duplicating the properly-named "the sky blue"
# entry -- and, scored on title match alone, can outrank it.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "topic,expected",
    [
        ("Why Is The Sky Blue", "The Sky Blue"),
        ("What Is Machine Learning", "Machine Learning"),
        ("How Does Aeroponic Farming Work", "Aeroponic Farming Work"),
        ("Who Is Ada Lovelace", "Ada Lovelace"),
        ("Define Photosynthesis", "Photosynthesis"),
        ("Definition Of Osmosis", "Osmosis"),
        ("Tell Me About Gravity", "Gravity"),
        ("Explain Quantum Mechanics", "Quantum Mechanics"),
    ],
)
def test_strip_question_prefix(topic, expected):
    assert strip_question_prefix(topic) == expected


def test_strip_question_prefix_leaves_real_titles_alone():
    for title in ("Machine Learning", "Photosynthesis", "Quantum Mechanics"):
        assert strip_question_prefix(title) == title


def test_strip_question_prefix_unwinds_double_processing():
    assert strip_question_prefix("What Is Why Is Gravity") == "Gravity"


def test_strip_question_prefix_handles_degenerate_input():
    assert strip_question_prefix("") == ""
    assert strip_question_prefix(None) == ""


def test_is_question_topic():
    assert is_question_topic("Why Is The Sky Blue")
    assert not is_question_topic("The Sky Blue")
    assert not is_question_topic("Machine Learning")


def test_canonical_subject_unifies_both_acquisition_paths():
    """The exact duplicate pair from AGENTS.md §NN: same subject, one named
    properly, one named after the raw question that produced it."""
    assert (
        canonical_subject("Why Is The Sky Blue Part 1")
        == canonical_subject("The Sky Blue Part 2")
        == "The Sky Blue"
    )


def test_canonical_subject_leaves_real_titles_alone():
    assert canonical_subject("Photosynthesis") == "Photosynthesis"


# --------------------------------------------------------------------------
# refresh_stale must collapse and dedupe
# --------------------------------------------------------------------------


class FakeFreshness:
    def __init__(self, topics):
        self._topics = [{"topic": t} for t in topics]

    def get_stale_topics(self):
        return list(self._topics)


class RecordingEngine:
    """Minimal stand-in exercising the real refresh_stale/research_topic."""

    def __init__(self, stale):
        from shaggoth.curiosity.engine import CuriosityEngine

        self.researched = []
        self._engine = CuriosityEngine.__new__(CuriosityEngine)
        self._engine._running = False
        self._engine.freshness = FakeFreshness(stale)
        self._engine.research_topic = lambda topic, **kw: self.researched.append(topic)

    def refresh(self, max_topics=3):
        from shaggoth.curiosity.engine import CuriosityEngine

        return CuriosityEngine.refresh_stale(self._engine, max_topics=max_topics)


def test_refresh_stale_researches_the_subject_not_the_chunk():
    eng = RecordingEngine(["Aeroponic Farming Part 1"])
    eng.refresh()
    assert eng.researched == ["Aeroponic Farming"]


def test_refresh_stale_deduplicates_chunks_of_one_article():
    eng = RecordingEngine([
        "Aeroponic Farming Part 1",
        "Aeroponic Farming Part 2",
        "Aeroponic Farming Part 3",
    ])
    result = eng.refresh()
    assert eng.researched == ["Aeroponic Farming"]
    assert result["stale_found"] == 3
    assert result["stale_subjects"] == 1


def test_refresh_stale_still_honours_the_cap():
    eng = RecordingEngine(["Alpha", "Beta", "Gamma", "Delta"])
    eng.refresh(max_topics=2)
    assert eng.researched == ["Alpha", "Beta"]


def test_refresh_stale_reports_nothing_to_do():
    eng = RecordingEngine([])
    assert eng.refresh() == {"stale_found": 0, "stale_subjects": 0, "refreshed": 0}


# --------------------------------------------------------------------------
# knows_topic: retrieval, not a bag of every word in the corpus
# --------------------------------------------------------------------------


class FakeEntry:
    def __init__(self, topic):
        self.topic = topic


class FakeKnowledge:
    def __init__(self, topics):
        self._topics = topics

    def query(self, text, limit=5, min_score=0.0):
        return [(FakeEntry(t), 1.0) for t in self._topics[:limit]]


def _engine_with(topics):
    from shaggoth.curiosity.engine import CuriosityEngine

    engine = CuriosityEngine.__new__(CuriosityEngine)
    engine.knowledge = FakeKnowledge(topics)
    return engine


def test_a_matching_title_counts_as_known():
    engine = _engine_with(["Photosynthesis"])
    assert engine.knows_topic("photosynthesis")


def test_an_unrelated_top_hit_does_not_count_as_known():
    """The regression: any phrase looked known because its words existed
    *somewhere* in the corpus."""
    engine = _engine_with(["Brokeback Mountain", "Gravity", "Hydroponics"])
    assert not engine.knows_topic("mycelium networks")
    assert not engine.knows_topic("quantum entanglement")


def test_partial_title_overlap_is_not_enough():
    engine = _engine_with(["Quantum Mechanics"])
    assert not engine.knows_topic("quantum entanglement")


def test_a_chunked_article_still_counts_as_knowing_its_subject():
    engine = _engine_with(["Aeroponic Farming Part 2"])
    assert engine.knows_topic("aeroponic farming")


def test_analyze_message_returns_unknown_topics():
    engine = _engine_with(["Gravity"])
    assert engine.analyze_message("what is mycelium networks") == "mycelium networks"


def test_analyze_message_stays_quiet_about_known_topics():
    engine = _engine_with(["Gravity"])
    assert engine.analyze_message("what is gravity") is None


def test_analyze_message_ignores_non_questions():
    engine = _engine_with([])
    assert engine.analyze_message("hi there") is None
    assert engine.analyze_message("") is None
