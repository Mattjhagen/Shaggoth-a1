"""Cross-entry synthesis for definitional answers.

A plain "what is X" answer used to stop at the first matching article, even
when the source was split into "X", "X Part 2", "X Part 3" knowledge entries.
`pull_cross_entry_fact` adds one supporting fact from a genuine continuation
of the same source; it must NOT reach into an unrelated entry that merely
shares a title word ("Gravity" vs "Gravity Falls"), the same trap
`knowledge_is_relevant` exists to avoid elsewhere.
"""
from __future__ import annotations

from shaggoth.dialogue.engine import (
    _is_list_debris,
    _synthesize,
    _topic_tokens_for,
    pull_cross_entry_fact,
    summarize_entry_scored,
)
from shaggoth.knowledge.engine import KnowledgeEntry


def _entry(topic: str, content: str) -> tuple[KnowledgeEntry, float]:
    return (
        KnowledgeEntry(
            topic=topic, content=content, path="", word_count=len(content.split()),
            keywords=[], mtime=0,
        ),
        1.0,
    )


def test_pulls_fact_from_same_source_continuation():
    primary = _entry(
        "Gravity",
        "Gravity is the force that draws material objects towards each other.",
    )
    continuation = _entry(
        "Gravity Part 2",
        "Gravity also governs the orbits of planets around stars in every "
        "known solar system.",
    )
    result = pull_cross_entry_fact(
        "Gravity", _topic_tokens_for("Gravity"), [primary, continuation], primary[0].content,
    )
    assert result is not None
    sentence, source_topic = result
    assert source_topic == "Gravity Part 2"
    assert "orbits of planets" in sentence


def test_does_not_pull_from_title_overlapping_unrelated_entry():
    # "Gravity Falls" merely shares the word "gravity" -- it is not a
    # continuation of the Gravity article and must never be used as a source
    # of supporting fact for a physics question.
    primary = _entry(
        "Gravity",
        "Gravity is the force that draws material objects towards each other.",
    )
    unrelated = _entry(
        "Gravity Falls",
        "Gravity Falls is an animated television series created by Alex Hirsch.",
    )
    result = pull_cross_entry_fact(
        "Gravity", _topic_tokens_for("Gravity"), [primary, unrelated], primary[0].content,
    )
    assert result is None


def test_does_not_pull_from_same_title_different_subject():
    # "Dna" here stands in for the historical bug: a knowledge entry titled
    # "Dna" that is actually about an unrelated manga, not the molecule.
    # Different base_topic than the disambiguation entry -- must be rejected.
    primary = _entry(
        "Dna Disambiguation",
        "DNA, or deoxyribonucleic acid, is a molecule that carries genetic information.",
    )
    manga = _entry(
        "Dna",
        "DNA squared is a manga about a family whose members each have a "
        "hundred children with unusual charisma.",
    )
    result = pull_cross_entry_fact(
        "Dna Disambiguation", _topic_tokens_for("Dna Disambiguation"),
        [primary, manga], primary[0].content,
    )
    assert result is None


def test_rejects_caption_like_sentences():
    primary = _entry(
        "Photosynthesis",
        "Photosynthesis is the process by which plants convert light into energy.",
    )
    continuation = _entry(
        "Photosynthesis Part 1",
        "Composite image showing the global distribution of photosynthesis "
        "across oceans and continents.",
    )
    result = pull_cross_entry_fact(
        "Photosynthesis", _topic_tokens_for("Photosynthesis"),
        [primary, continuation], primary[0].content,
    )
    assert result is None


def test_is_list_debris_catches_captions():
    assert _is_list_debris("Diagram showing the water cycle in detail.")
    assert _is_list_debris("Schematic of a gravitational field around a mass.")
    assert not _is_list_debris(
        "Gravity is a fundamental interaction between massive objects."
    )


def test_synthesize_varies_the_join():
    seen = {
        _synthesize([
            "Photosynthesis is a biological process.",
            "It occurs in plants, algae, and some bacteria.",
        ])
        for _ in range(50)
    }
    # The lead sentence never changes; the join around the second one does.
    assert all(s.startswith("Photosynthesis is a biological process.") for s in seen)
    assert len(seen) > 1


def test_synthesize_leaves_single_sentence_untouched():
    assert _synthesize(["Just one sentence."]) == "Just one sentence."
    assert _synthesize([]) == ""


def test_summarize_entry_scored_still_returns_definition_flag():
    content = (
        "Aeroponics is the process of cultivating plants in an air or mist "
        "environment. It eliminates the need for soil or an aggregate medium "
        "entirely, which is its defining feature."
    )
    summary, is_definition = summarize_entry_scored(content, "Aeroponics")
    assert is_definition
    assert summary.startswith("Aeroponics is the process")
