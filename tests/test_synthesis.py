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
    _stem_match,
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


def test_synthesize_preserves_acronyms():
    result = _synthesize([
        "DNA is deoxyribonucleic acid.",
        "DNA carries the genetic instructions for life.",
    ])
    assert "DNA" in result
    assert "dNA" not in result


def test_synthesize_preserves_proper_nouns():
    result = _synthesize([
        "Gravity was first described mathematically.",
        "Einstein proposed general relativity in 1915.",
    ])
    assert "Einstein" in result
    assert "einstein" not in result


def test_stem_match_rejects_photosynthesis_photography():
    assert not _stem_match("photosynthesis", "photography")


def test_stem_match_rejects_gravity_gravel():
    assert not _stem_match("gravity", "gravel")


def test_stem_match_accepts_gravity_gravitational():
    assert _stem_match("gravity", "gravitational")


def test_stem_match_accepts_computing_computer():
    assert _stem_match("computing", "computer")


def test_summarizer_keeps_pronoun_continuation():
    content = (
        "Photosynthesis is the process by which plants convert light energy "
        "into chemical energy. It occurs primarily in the chloroplasts of "
        "plant cells. Photosynthesis requires carbon dioxide and water."
    )
    summary, _ = summarize_entry_scored(content, "Photosynthesis")
    assert "chloroplasts" in summary or "chemical energy" in summary


def test_clean_sentences_accepts_long_encyclopedia_leads():
    from shaggoth.dialogue.engine import _clean_sentences
    long_lead = (
        "Photosynthesis is a system of biological processes by which "
        "photosynthetic organisms convert light energy into chemical energy "
        "that can later be released to fuel the organism's activities, and "
        "involves a complex set of reactions that include the absorption of "
        "light by proteins containing chlorophylls, the transfer of that energy "
        "to molecular reaction centers, the production of adenosine triphosphate "
        "and the reduction of carbon dioxide to organic compounds by a sequence "
        "of chemical reactions known collectively as the Calvin cycle, which "
        "takes place in the stroma of the chloroplast and represents the "
        "primary pathway by which inorganic carbon enters the biological world."
    )
    assert len(long_lead) > 400
    sentences = _clean_sentences(long_lead)
    assert sentences, "long encyclopedia lead should not be rejected"


def test_clean_sentences_still_rejects_very_long_garbage():
    from shaggoth.dialogue.engine import _clean_sentences
    garbage = "word " * 200
    sentences = _clean_sentences(garbage)
    assert not sentences, "900-char wall of noise should be rejected"


# -- _DEFINING_VERB expansion tests ------------------------------------------

def test_defining_verb_recognises_comprised_of():
    from shaggoth.dialogue.engine import _DEFINING_VERB
    assert _DEFINING_VERB.search("An atom is comprised of protons and neutrons.")


def test_defining_verb_recognises_includes():
    from shaggoth.dialogue.engine import _DEFINING_VERB
    assert _DEFINING_VERB.search("The solar system includes eight major planets.")


def test_defining_verb_recognises_contains():
    from shaggoth.dialogue.engine import _DEFINING_VERB
    assert _DEFINING_VERB.search("A cell contains a nucleus and cytoplasm.")


# -- _stem_match short-word inflection tests ----------------------------------

def test_stem_match_gene_genes():
    assert _stem_match("gene", "genes")


def test_stem_match_gene_genetic_rejects():
    assert not _stem_match("gene", "genetic")


def test_stem_match_cell_cells():
    assert _stem_match("cell", "cells")


def test_stem_match_ice_iced():
    assert _stem_match("ice", "iced")


def test_stem_match_short_unrelated_rejects():
    assert not _stem_match("ice", "idea")


# -- Abbreviation-aware sentence splitting tests -----------------------------

def test_clean_sentences_preserves_dr_abbreviation():
    from shaggoth.dialogue.engine import _clean_sentences
    text = "Dr. Smith discovered the element. It was a breakthrough."
    sentences = _clean_sentences(text)
    assert any("Dr." in s and "Smith" in s for s in sentences), \
        f"Dr. Smith should stay in one sentence, got: {sentences}"


def test_clean_sentences_preserves_jan_abbreviation():
    from shaggoth.dialogue.engine import _clean_sentences
    text = "The event took place on Jan. 15 in the city hall. It was well attended."
    sentences = _clean_sentences(text)
    assert any("Jan." in s and "15" in s for s in sentences), \
        f"Jan. should not split the sentence, got: {sentences}"


def test_body_discusses_abbreviation_no_false_split():
    from shaggoth.dialogue.engine import _body_discusses
    text = "Dr. Watson assisted Holmes in solving the mystery of the missing jewels."
    assert _body_discusses(text, {"watson", "holmes"}), \
        "Co-occurrence should work across abbreviation dots"


def test_body_discusses_still_splits_real_sentences():
    from shaggoth.dialogue.engine import _body_discusses
    text = "Gravity pulls objects down. Light travels in straight lines."
    assert not _body_discusses(text, {"gravity", "light"}), \
        "Words in different sentences should not co-occur"
