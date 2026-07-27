"""Retrieval ranking: the right article must win.

These build a small corpus on disk and assert the ordering directly, so a
regression shows up as a ranking failure rather than as a strange answer
three layers downstream.
"""
from __future__ import annotations

import pytest

from shaggoth.knowledge.engine import KnowledgeBase


@pytest.fixture
def kb(tmp_path):
    base = KnowledgeBase(tmp_path)

    base.add_entry(
        "Evolution",
        "Evolution is the change in the heritable characteristics of "
        "biological populations over successive generations. Evolution "
        "occurs when evolutionary processes such as natural selection and "
        "genetic drift act on genetic variation. " + ("evolution biology " * 300),
    )
    base.add_entry(
        "Evolution Disambiguation",
        "Evolution may refer to evolution in biology, Evolution a 2001 "
        "comedy film, or Evolution an album. If an internal link "
        "incorrectly led you here, you may wish to change the link.",
    )
    base.add_entry(
        "Machine Learning",
        "Machine learning is a field of study in artificial intelligence "
        "concerned with statistical algorithms that learn from data. "
        + ("machine learning model training " * 200),
    )
    base.add_entry(
        "Asia Asia Album",
        "Asia is the debut studio album by the rock band Asia, released in "
        "1982. The album topped the charts. " + ("album band rock " * 400),
    )
    return base


def _top(kb, query):
    results = kb.query(query, limit=5, min_score=0.0)
    assert results, f"no results for {query!r}"
    return results[0][0].topic


def test_real_article_beats_its_disambiguation_page(kb):
    """The observed bug: 'what is evolution' returned the index page."""
    assert _top(kb, "what is evolution") == "Evolution"


def test_disambiguation_page_is_penalised_not_removed(kb):
    """Still reachable when it is genuinely what was asked for."""
    topics = [e.topic for e, _ in kb.query("evolution disambiguation", limit=5)]
    assert "Evolution Disambiguation" in topics


def test_title_match_beats_incidental_body_mentions(kb):
    assert _top(kb, "what is machine learning") == "Machine Learning"


def test_query_with_no_match_returns_nothing(kb):
    assert kb.query("xylophone tessellation", limit=5, min_score=0.0) == []


def test_scores_are_normalised_and_ordered(kb):
    results = kb.query("what is evolution", limit=5, min_score=0.0)
    scores = [s for _, s in results]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == pytest.approx(1.0)
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_min_score_filters_weak_hits(kb):
    loose = kb.query("what is evolution", limit=5, min_score=0.0)
    strict = kb.query("what is evolution", limit=5, min_score=0.9)
    assert len(strict) <= len(loose)
    assert all(s >= 0.9 for _, s in strict)


# --------------------------------------------------------------------------
# Relevance: title match, plus a narrow body route for long documents
# --------------------------------------------------------------------------


def test_title_overlap_is_relevant():
    from shaggoth.dialogue.engine import knowledge_is_relevant

    assert knowledge_is_relevant("Photosynthesis", "what is photosynthesis")


def test_unrelated_title_is_not_relevant():
    from shaggoth.dialogue.engine import knowledge_is_relevant

    assert not knowledge_is_relevant("Brokeback Mountain", "what is photosynthesis")


def test_a_name_buried_in_the_body_is_reachable():
    """A character is discussed in chapters whose titles never name them."""
    from shaggoth.dialogue.engine import knowledge_is_relevant

    body = "The hearing began. Ellie Finch took the stand and did not blink."
    assert knowledge_is_relevant("Chapter 23: The Hearing", "who is Ellie Finch", body)


def test_a_single_common_word_cannot_match_on_the_body_alone():
    """Two content words minimum, or half the corpus would qualify."""
    from shaggoth.dialogue.engine import knowledge_is_relevant

    body = "the system optimised everything it touched"
    assert not knowledge_is_relevant("Chapter 4", "what is system", body)


def test_body_route_requires_every_content_word():
    from shaggoth.dialogue.engine import knowledge_is_relevant

    body = "Ellie Finch took the stand."
    assert not knowledge_is_relevant("Chapter 23", "who is Marcus Okonkwo", body)


def test_body_route_is_off_without_content():
    from shaggoth.dialogue.engine import knowledge_is_relevant

    assert not knowledge_is_relevant("Chapter 23", "who is Ellie Finch")
