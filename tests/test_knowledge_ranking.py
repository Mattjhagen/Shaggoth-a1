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


def test_body_discusses_cleans_citations():
    from shaggoth.dialogue.engine import _body_discusses

    content = "Ellie Finch [1] published a [citation needed] seminal paper."
    assert _body_discusses(content, {"ellie", "finch"})


def test_body_discusses_ignores_noise_sentences():
    from shaggoth.dialogue.engine import _body_discusses

    content = "This article has multiple issues. Ellie Finch is a character."
    assert _body_discusses(content, {"ellie", "finch"})
    assert not _body_discusses(
        "This article has multiple issues with Ellie Finch references.",
        {"ellie", "finch"},
    )


# --------------------------------------------------------------------------
# Slugs: the filename stem IS the topic, so a bad slug is a permanent bad topic
# --------------------------------------------------------------------------


def test_slug_strips_leading_and_trailing_separators():
    """A leading hyphen survived .strip() and produced the topic " Algebra"."""
    assert KnowledgeBase.slug_for("- Algebra") == "algebra"
    assert KnowledgeBase.slug_for("Algebra -") == "algebra"


def test_slug_collapses_separator_runs():
    """"Aeroponics - Wikipedia" came back as "Aeroponics   Wikipedia"."""
    assert KnowledgeBase.slug_for("Aeroponics - Wikipedia") == "aeroponics-wikipedia"
    assert KnowledgeBase.slug_for("A   B") == "a-b"


def test_slug_drops_punctuation_without_welding_words_together():
    assert KnowledgeBase.slug_for("Rock & Roll") == "rock-roll"


# --------------------------------------------------------------------------
# Fuzzy matching: typos should still find the right article
# --------------------------------------------------------------------------


def test_typo_still_finds_article(tmp_path):
    kb = KnowledgeBase(tmp_path)
    kb.add_entry("Photosynthesis", "Photosynthesis is the process by which plants convert light. " * 20)
    results = kb.query("photosythesis", limit=3, min_score=0.0)
    assert results, "typo 'photosythesis' should fuzzy-match 'photosynthesis'"
    assert results[0][0].topic == "Photosynthesis"


def test_fuzzy_does_not_match_unrelated(tmp_path):
    kb = KnowledgeBase(tmp_path)
    kb.add_entry("Gravity", "Gravity is a fundamental force. " * 20)
    results = kb.query("xyzzyfoob", limit=3, min_score=0.0)
    assert not results, "garbage query should not fuzzy-match anything"


def test_exact_match_still_preferred_over_fuzzy(tmp_path):
    kb = KnowledgeBase(tmp_path)
    kb.add_entry("Evolution", "Evolution is the change in heritable characteristics. " * 20)
    kb.add_entry("Evaluation", "Evaluation is the process of assessing something. " * 20)
    results = kb.query("evolution", limit=3, min_score=0.0)
    assert results[0][0].topic == "Evolution"


def test_acronym_query_finds_article(tmp_path):
    """Two-letter acronyms like AI should match knowledge entries."""
    kb = KnowledgeBase(tmp_path)
    kb.add_entry("AI", "AI is the simulation of human intelligence by machines. " * 20)
    results = kb.query("what is AI", limit=3, min_score=0.0)
    assert results, "AI query should find the AI article"
    assert results[0][0].topic.lower() == "ai"


def test_acronym_keyword_extraction():
    """extract_keywords should capture uppercase 2-letter acronyms."""
    from shaggoth.memory.store import extract_keywords
    kw = extract_keywords("What is AI and how does it relate to UK policy?")
    assert "ai" in kw
    assert "uk" in kw


def test_slug_never_returns_empty():
    assert KnowledgeBase.slug_for("!!!") == "untitled"
    assert KnowledgeBase.slug_for("") == "untitled"


def test_slug_distinguishes_c_variants():
    assert KnowledgeBase.slug_for("C++") != KnowledgeBase.slug_for("C")
    assert KnowledgeBase.slug_for("C#") != KnowledgeBase.slug_for("C")
    assert KnowledgeBase.slug_for("C++") != KnowledgeBase.slug_for("C#")
    assert KnowledgeBase.slug_for("C#") == "c-sharp"
    assert KnowledgeBase.slug_for("C++") == "c-plus-plus"


def test_added_topic_round_trips_cleanly(tmp_path):
    base = KnowledgeBase(tmp_path)
    base.add_entry("Aeroponics - Wikipedia", "Aeroponics is soil-free cultivation. " * 30)
    topics = [e["topic"] for e in base.list_entries()]
    assert "Aeroponics Wikipedia" in topics
    assert all(t == t.strip() and "  " not in t for t in topics)


def test_remove_entry_finds_what_add_entry_wrote(tmp_path):
    base = KnowledgeBase(tmp_path)
    base.add_entry("- Algebra", "Algebra is a branch of mathematics. " * 30)
    assert base.remove_entry("- Algebra")
    assert base.list_entries() == []


# --------------------------------------------------------------------------
# Chunk fragments: base article must rank above its part-N continuations
# --------------------------------------------------------------------------


def test_base_article_beats_its_chunks(tmp_path):
    """'Photosynthesis' must rank above 'Photosynthesis Part 2'."""
    kb = KnowledgeBase(tmp_path)
    kb.add_entry(
        "Photosynthesis",
        "Photosynthesis is a biological process used by plants to convert "
        "light energy into chemical energy. " + ("photosynthesis plants " * 200),
    )
    kb.add_entry(
        "Photosynthesis Part 2",
        "Photosynthesis in cyanobacteria uses similar mechanisms. "
        + ("photosynthesis cyanobacteria " * 200),
    )
    kb.add_entry(
        "Photosynthesis Part 3",
        "The evolution of photosynthesis changed Earth's atmosphere. "
        + ("photosynthesis evolution " * 200),
    )
    results = kb.query("what is photosynthesis", limit=5)
    assert results[0][0].topic == "Photosynthesis"


def test_chunks_are_still_reachable(tmp_path):
    """Chunks should rank lower, not disappear."""
    kb = KnowledgeBase(tmp_path)
    kb.add_entry("DNA", "DNA is the molecule. " + ("dna genetics " * 200))
    kb.add_entry("DNA Part 2", "DNA replication. " + ("dna replication " * 200))
    results = kb.query("what is dna", limit=5)
    topics = [e.topic.lower() for e, _ in results]
    assert any("part" in t for t in topics)


def test_chunk_title_tokens_exclude_part_suffix(tmp_path):
    """'Part 2' should not count as title overlap against the query."""
    kb = KnowledgeBase(tmp_path)
    kb.add_entry("Gravity Part 2", "Gravity is a force. " + ("gravity " * 200))
    tokens = kb._topic_tokens(kb._entries[0])
    assert "part" not in tokens


# --------------------------------------------------------------------------
# Relevance: 2-letter acronyms must not be dropped
# --------------------------------------------------------------------------


def test_two_letter_acronym_is_relevant():
    from shaggoth.dialogue.engine import knowledge_is_relevant

    assert knowledge_is_relevant("AI", "what is AI")


def test_two_letter_acronym_topic_tokens():
    from shaggoth.dialogue.engine import _topic_tokens_for

    tokens = _topic_tokens_for("AI")
    assert "ai" in tokens


def test_short_stopwords_excluded_from_topic_tokens():
    from shaggoth.dialogue.engine import _topic_tokens_for

    tokens = _topic_tokens_for("History of Art")
    assert "of" not in tokens
    assert "history" in tokens
    assert "art" in tokens
