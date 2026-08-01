"""Multi-step reasoning: questions one lookup cannot answer.

The baseline this was written against: asked "what is the difference between
aeroponics and hydroponics", Shaggoth returned the hydroponics article and
never mentioned aeroponics. It could retrieve; it could not compare.
"""
from __future__ import annotations

import pytest

from shaggoth.dialogue.reasoning import (
    Intent,
    Reasoner,
    classify,
    split_subjects,
    subject_of,
)


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question", [
    "what is the difference between aeroponics and hydroponics",
    "how is aeroponics different from hydroponics",
    "aeroponics versus hydroponics",
    "aeroponics vs hydroponics",
    "compare aeroponics to hydroponics",
    "compare cats and dogs",
    "how does X relate to Y",
    "how does X hold up against Y",
    "how does X stack up against Y",
])
def test_comparison_questions(question):
    assert classify(question) == Intent.COMPARE


@pytest.mark.parametrize("question", [
    "how are aeroponics and hydroponics similar",
    "what do aeroponics and hydroponics have in common",
    "what is the relationship between light and photosynthesis",
])
def test_contrast_questions(question):
    assert classify(question) == Intent.CONTRAST


@pytest.mark.parametrize("question", [
    "why does photosynthesis need light",
    "what causes gravity",
    "how does a river work",
    "how is steel made",
    "how are vaccines produced",
    "how do earthquakes happen",
    "how can I fix a leaky faucet",
    "what is the process of photosynthesis",
    "what happens when water boils",
    "what is the cause of inflation",
    "how can I protect against phishing",
])
def test_causal_questions(question):
    assert classify(question) == Intent.CAUSAL


@pytest.mark.parametrize("question", [
    "what are the types of cryptography",
    "what kinds of algae exist",
    "give me examples of programming languages",
])
def test_enumerating_questions(question):
    assert classify(question) == Intent.ENUMERATE


def test_plain_definitions_are_left_to_retrieval():
    assert classify("what is photosynthesis") == Intent.DEFINE
    assert classify("tell me about gravity") == Intent.DEFINE


def test_a_comparison_beginning_with_why_is_still_a_comparison():
    """Order matters: 'why is X different from Y' is not a causal question."""
    assert classify("why is aeroponics different from hydroponics") == Intent.COMPARE


# --------------------------------------------------------------------------
# Subject extraction
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    ("what is the difference between aeroponics and hydroponics",
     ["aeroponics", "hydroponics"]),
    ("aeroponics versus hydroponics", ["aeroponics", "hydroponics"]),
    ("aeroponics vs hydroponics", ["aeroponics", "hydroponics"]),
    ("what do aeroponics and hydroponics have in common",
     ["aeroponics", "hydroponics"]),
])
def test_split_subjects(question, expected):
    assert split_subjects(question) == expected


def test_split_subjects_strips_the_how_are_lead_in():
    """Every group of the old lead-in was optional, so it matched the empty
    string and left "how are aeroponics" as a subject."""
    assert split_subjects("how are aeroponics and hydroponics similar") == [
        "aeroponics", "hydroponics"
    ]


def test_split_subjects_refuses_to_guess_at_one():
    assert split_subjects("what is photosynthesis") == []
    assert split_subjects("") == []


def test_split_subjects_short_acronyms():
    """Two-letter acronyms like AI and ML should be valid comparison subjects."""
    assert split_subjects("AI vs ML") == ["AI", "ML"]


def test_subject_of_drops_the_trailing_verb_phrase():
    """The subject is what to look up; the rest is what to look for."""
    assert subject_of("why does photosynthesis need light") == "photosynthesis"
    assert subject_of("what causes gravity") == "gravity"
    assert subject_of("what are the types of cryptography") == "cryptography"
    assert subject_of("how does a river work") == "a river"


@pytest.mark.parametrize("question,expected", [
    ("how is steel made", "steel"),
    ("how are vaccines produced", "vaccines"),
    ("how do earthquakes happen", "earthquakes"),
    ("how can I fix a leaky faucet", "I fix a leaky faucet"),
    ("what is the process of photosynthesis", "photosynthesis"),
    ("what is the cause of inflation", "inflation"),
    ("what happens when water boils", "when water boils"),
])
def test_subject_of_new_causal_patterns(question, expected):
    assert subject_of(question) == expected


# --------------------------------------------------------------------------
# The reasoner
# --------------------------------------------------------------------------


class FakeEntry:
    def __init__(self, topic, content):
        self.topic = topic
        self.content = content


class FakeKnowledge:
    def __init__(self, entries):
        self.entries = entries

    def query(self, text, limit=5, min_score=0.0):
        words = {w for w in text.lower().split() if len(w) > 3}
        hits = [
            e for e in self.entries
            if words & {w for w in e.topic.lower().split()}
        ]
        return [(e, 1.0) for e in hits[:limit]]


def _reasoner(entries):
    return Reasoner(
        FakeKnowledge(entries),
        summarize=lambda content, topic: (content, True),
        sentences=lambda content: [s.strip() + "." for s in content.split(".") if s.strip()],
    )


AERO = FakeEntry("Aeroponics", "Aeroponics grows plants in air or mist without soil.")
HYDRO = FakeEntry("Hydroponics", "Hydroponics grows plants in water without soil.")
PHOTO = FakeEntry(
    "Photosynthesis",
    "Photosynthesis converts light into chemical energy. "
    "It requires light because chlorophyll absorbs photons to drive the reaction. "
    "The oxygen is a byproduct.",
)
CRYPTO = FakeEntry(
    "Cryptography",
    "Cryptography secures communication. "
    "Cryptography includes symmetric-key cryptography and public-key cryptography. "
    "It is very old.",
)


def test_comparison_uses_both_entries():
    """The bug: it answered with one article and ignored the other."""
    result = _reasoner([AERO, HYDRO]).reason(
        "what is the difference between aeroponics and hydroponics"
    )
    assert result is not None
    assert "Aeroponics" in result.answer
    assert "Hydroponics" in result.answer
    assert set(result.entries_used) == {"Aeroponics", "Hydroponics"}


def test_comparison_records_its_steps():
    result = _reasoner([AERO, HYDRO]).reason("aeroponics vs hydroponics")
    trace = " ".join(result.trace)
    assert "compare" in trace
    assert "aeroponics" in trace and "hydroponics" in trace


def test_a_half_known_comparison_says_so():
    """Answering about one side and calling it a comparison would be a lie."""
    result = _reasoner([AERO]).reason(
        "what is the difference between aeroponics and hydroponics"
    )
    assert result is not None
    assert "only know one half" in result.answer.lower()
    assert "hydroponics" in result.answer.lower()


def test_an_entirely_unknown_comparison_declines():
    assert _reasoner([]).reason("difference between alpha and beta") is None


def test_causal_questions_get_explanations_not_definitions():
    result = _reasoner([PHOTO]).reason("why does photosynthesis need light")
    assert result is not None
    assert "because" in result.answer.lower()
    assert result.intent == Intent.CAUSAL


def test_enumerating_questions_get_the_list_sentence():
    result = _reasoner([CRYPTO]).reason("what are the types of cryptography")
    assert result is not None
    assert "includes" in result.answer.lower()
    assert result.intent == Intent.ENUMERATE


def test_topic_words_includes_3_char_terms():
    from shaggoth.dialogue.reasoning import _topic_words
    words = _topic_words("DNA and RNA sequencing")
    assert "dna" in words
    assert "rna" in words


def test_reasoner_declines_plain_definitions():
    """Retrieval already handles these; reasoning must not intercept them."""
    assert _reasoner([PHOTO]).reason("what is photosynthesis") is None


def test_reasoner_declines_when_it_finds_nothing_useful():
    bare = FakeEntry("Photosynthesis", "Photosynthesis is a process.")
    assert _reasoner([bare]).reason("why does photosynthesis need light") is None


def test_comparison_will_not_build_on_the_wrong_article():
    """A comparison against an unrelated entry is worse than admitting a gap."""
    unrelated = FakeEntry("Brokeback Mountain", "A film about two shepherds.")
    result = _reasoner([AERO, unrelated]).reason(
        "difference between aeroponics and hydroponics"
    )
    assert result is None or "Brokeback" not in result.answer


def test_pick_uses_word_boundaries_not_substrings():
    """'art' should not match inside 'particle' or 'starting'."""
    from shaggoth.dialogue.reasoning import _pick, _CAUSAL_MARKER
    sentences = [
        "Because particle physics involves starting with quantum fields.",
        "Because art requires creativity and imagination to produce.",
    ]
    picked = _pick(sentences, _CAUSAL_MARKER, {"art"}, limit=5, min_len=10)
    assert len(picked) == 1
    assert "creativity" in picked[0]


def test_comparison_drops_redundant_topic_label():
    result = _reasoner([AERO, HYDRO]).reason(
        "what is the difference between aeroponics and hydroponics"
    )
    assert result is not None
    assert "Aeroponics:" not in result.answer
    assert "Hydroponics:" not in result.answer
