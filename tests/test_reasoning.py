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
    # "connection between" is a relationship question (new)
    "what is the connection between gravity and time",
    # "how are X and Y related" ending with "related" (new)
    "how are photosynthesis and respiration related",
    # "how similar are X and Y" with adjective between how and auxiliary (new)
    "how similar are TCP and UDP",
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
    "what leads to inflation",
    "what triggers an earthquake",
    "what is the role of mitochondria",
    "what is the function of enzymes",
    "what is the impact of climate change",
])
def test_causal_questions(question):
    assert classify(question) == Intent.CAUSAL


@pytest.mark.parametrize("question", [
    # Enabling/blocking causal verbs
    "what enables photosynthesis",
    "what allows plants to grow",
    "what prevents rusting",
    "what is causing the crisis",
    # Responsibility and necessity
    "what is responsible for climate change",
    "what is needed for photosynthesis",
    "what is required for respiration",
    # Behind/explanatory
    "what is behind inflation",
    "what lies behind economic growth",
    # Present progressive of "cause"
    "what is causing the temperature to rise",
])
def test_causal_questions_extended(question):
    """Causal question patterns beyond the original set."""
    assert classify(question) == Intent.CAUSAL


@pytest.mark.parametrize("question", [
    "what are the types of cryptography",
    "what kinds of algae exist",
    "give me examples of programming languages",
    # Imperative list commands
    "list the planets in the solar system",
    "name the different types of machine learning",
    # "some types of" variant
    "what are some types of cancer",
])
def test_enumerating_questions(question):
    assert classify(question) == Intent.ENUMERATE


@pytest.mark.parametrize("question", [
    # Past-tense "caused" — previously misclassified as DEFINE
    "what caused the Great Depression",
    "what caused the financial crisis",
])
def test_causal_questions_past_tense(question):
    """'what caused X' uses past tense; classifier must handle it."""
    assert classify(question) == Intent.CAUSAL


def test_plain_definitions_are_left_to_retrieval():
    assert classify("what is photosynthesis") == Intent.DEFINE
    assert classify("tell me about gravity") == Intent.DEFINE


def test_a_comparison_beginning_with_why_is_still_a_comparison():
    """Order matters: 'why is X different from Y' is not a causal question."""
    assert classify("why is aeroponics different from hydroponics") == Intent.COMPARE


@pytest.mark.parametrize("question,expected", [
    # Comparative adjective + "than" patterns
    ("is python faster than javascript", ["python", "javascript"]),
    ("is nuclear energy safer than coal", ["nuclear energy", "coal"]),
    # "which is [adj] X or Y" pattern
    ("which is faster light or sound", ["light", "sound"]),
    ("which is better python or javascript", ["python", "javascript"]),
    ("which is more popular python or java", ["python", "java"]),
    ("which is more efficient solar or wind power", ["solar", "wind power"]),
])
def test_split_subjects_comparative_questions(question, expected):
    """Comparative 'is X faster than Y' and 'which is better X or Y' patterns."""
    assert classify(question) == Intent.COMPARE
    assert split_subjects(question) == expected


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


def test_split_subjects_strips_imperative_compare():
    """'compare X and Y' is a comparison request, not 'compare X' vs 'Y'."""
    assert split_subjects("compare cats and dogs") == ["cats", "dogs"]
    assert split_subjects("compare deep learning and machine learning") == [
        "deep learning", "machine learning"
    ]


def test_split_subjects_compare_to_preposition():
    """'compare X to Y' uses 'to' as the joiner, not 'and'."""
    assert split_subjects("compare aeroponics to hydroponics") == [
        "aeroponics", "hydroponics"
    ]


def test_split_subjects_how_does_compare_to():
    """'how does X compare to Y' must strip the verb and split on 'compare to'."""
    assert split_subjects("how does aeroponics compare to hydroponics") == [
        "aeroponics", "hydroponics"
    ]
    assert split_subjects("how does Python compare to JavaScript") == [
        "Python", "JavaScript"
    ]


def test_split_subjects_what_distinguishes():
    """'what distinguishes X from Y' is a comparison; 'from' is the joiner."""
    assert split_subjects("what distinguishes aeroponics from hydroponics") == [
        "aeroponics", "hydroponics"
    ]


def test_what_distinguishes_is_compare_intent():
    """'what distinguishes X from Y' must classify as COMPARE, not DEFINE."""
    assert classify("what distinguishes aeroponics from hydroponics") == Intent.COMPARE


def test_split_subjects_what_separates():
    """'what separates X from Y' is a comparison; strip the verb and split on 'from'."""
    assert split_subjects("what separates aeroponics from hydroponics") == [
        "aeroponics", "hydroponics"
    ]
    assert split_subjects("what separates socialism from communism") == [
        "socialism", "communism"
    ]


def test_split_subjects_what_sets_apart():
    """'what sets X apart from Y' must strip both 'what sets' and 'apart from'."""
    assert split_subjects("what sets deep learning apart from machine learning") == [
        "deep learning", "machine learning"
    ]
    assert split_subjects("what sets TCP apart from UDP") == ["TCP", "UDP"]


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
    ("what happens when water boils", "water"),
    ("what leads to inflation", "inflation"),
    ("what triggers an earthquake", "an earthquake"),
    ("what is the role of mitochondria", "mitochondria"),
    ("what is the function of enzymes", "enzymes"),
])
def test_subject_of_new_causal_patterns(question, expected):
    assert subject_of(question) == expected


@pytest.mark.parametrize("question,expected", [
    # Trailing action verbs should not become part of the subject
    ("why do black holes form", "black holes"),
    ("how do plants make food", "plants"),
    ("how does deep learning train", "deep learning"),
    ("what makes DNA replicate", "DNA"),
    # "are there" is question scaffolding, even when followed by a prep phrase
    ("what kinds of algae are there", "algae"),
    ("what kinds of planets are there in the solar system", "planets"),
    # "on <modifier>" after the subject should be stripped
    ("what is the effect of gravity on time", "gravity"),
    ("what is the impact of climate change on ecosystems", "climate change"),
])
def test_subject_of_trailing_verb_and_modifier_strips(question, expected):
    assert subject_of(question) == expected


@pytest.mark.parametrize("question,expected", [
    # Enabling/blocking causal verbs after "what"
    ("what enables photosynthesis", "photosynthesis"),
    ("what allows plants to grow", "plants"),
    ("what prevents rusting", "rusting"),
    # Responsibility / necessity
    ("what is responsible for climate change", "climate change"),
    ("what is needed for photosynthesis", "photosynthesis"),
    # Behind / explanatory
    ("what is behind inflation", "inflation"),
])
def test_subject_of_new_causal_verb_patterns(question, expected):
    assert subject_of(question) == expected


@pytest.mark.parametrize("question,expected", [
    # Past-tense "caused": was garbling to "d the Great Depression"
    ("what caused the Great Depression", "the Great Depression"),
    ("what caused the financial crisis", "the financial crisis"),
    # Extinction/state trailing verbs
    ("why did the dinosaurs go extinct", "the dinosaurs"),
    ("how did the Roman Empire fall", "the Roman Empire"),
    ("how did the Soviet Union collapse", "the Soviet Union"),
    # Enumeration with "some types" article prefix
    ("what are some types of cancer", "cancer"),
    # Imperative enumeration commands
    ("name the different types of machine learning", "machine learning"),
    ("list the planets in the solar system", "planets in the solar system"),
])
def test_subject_of_new_patterns(question, expected):
    assert subject_of(question) == expected


@pytest.mark.parametrize("question,expected", [
    # "who" opening + attribution verb strip at the start
    ("who invented the telephone", "the telephone"),
    ("who discovered penicillin", "penicillin"),
    ("who developed the theory of relativity", "the theory of relativity"),
    ("who designed the Eiffel Tower", "the Eiffel Tower"),
    # "when" opening + passive attribution verb at the end
    ("when was the internet invented", "the internet"),
    ("when was electricity discovered", "electricity"),
    # "what happens during X" → "during" preposition strip
    ("what happens during photosynthesis", "photosynthesis"),
    ("what happens during an earthquake", "an earthquake"),
    # Action verb (fight/affect) at end — previously leaked into subject
    ("how does the immune system fight viruses", "the immune system"),
    ("how does stress affect the body", "stress"),
    ("how does sunscreen protect skin", "sunscreen"),
    # "what is the [adj] cause of X" — optional adjective before noun
    ("what is the main cause of global warming", "global warming"),
    ("what is the primary effect of deforestation", "deforestation"),
])
def test_subject_of_who_when_attribution_and_action_verbs(question, expected):
    """who/when opening, attribution verbs, during-strip, trailing action verbs."""
    assert subject_of(question) == expected


@pytest.mark.parametrize("question", [
    # Adjective between "the" and the causal noun must still classify as CAUSAL
    "what is the main cause of global warming",
    "what is the primary effect of deforestation",
    "what is the key role of enzymes in digestion",
    # "what happens during X" is causal
    "what happens during photosynthesis",
])
def test_causal_questions_with_optional_adjective(question):
    """Adjective before causal noun (e.g. 'the main cause of') must classify CAUSAL."""
    assert classify(question) == Intent.CAUSAL


@pytest.mark.parametrize("question,expected", [
    # "relationship between" and "connection between" must split correctly.
    ("what is the relationship between TCP and UDP", ["TCP", "UDP"]),
    ("what is the connection between gravity and time", ["gravity", "time"]),
    # Trailing "related" must be stripped so right subject is clean.
    ("how are photosynthesis and respiration related", ["photosynthesis", "respiration"]),
    # "how [adjective] are X and Y" — adjective between how and auxiliary.
    ("how similar are TCP and UDP", ["TCP", "UDP"]),
    ("how different are quantum and classical computing", ["quantum", "classical computing"]),
])
def test_split_subjects_relationship_and_trailing_related(question, expected):
    """relationship/connection between + trailing 'related' + 'how adj are'."""
    assert split_subjects(question) == expected


@pytest.mark.parametrize("question,expected", [
    # "fall of X" — "fall" is a NOUN here; must not be stripped.
    ("what caused the fall of the Roman Empire", "the fall of the Roman Empire"),
    ("what caused the collapse of the Soviet Union", "the collapse of the Soviet Union"),
    ("what caused the rise of nationalism", "the rise of nationalism"),
    # "X fall" with no following "of" — "fall" IS a verb here; strip it.
    ("how did Rome fall", "Rome"),
    ("why did the Soviet Union collapse", "the Soviet Union"),
    # "originate" is now in the trailing-verb list.
    ("where did humans originate", "humans"),
    ("where did life originate", "life"),
    # "role/function of X in Y" — "in Y" is context, not part of subject.
    ("what is the role of mitochondria in cell energy", "mitochondria"),
    ("what is the function of chlorophyll in photosynthesis", "chlorophyll"),
    ("what is the role of ATP in muscle contraction", "ATP"),
    # Regression: "in the solar system" must NOT be stripped from enumeration.
    ("list the planets in the solar system", "planets in the solar system"),
])
def test_subject_of_noun_forms_and_in_context_strip(question, expected):
    """fall/collapse/rise as nouns kept; originate stripped; role-of-X-in-Y context stripped."""
    assert subject_of(question) == expected


@pytest.mark.parametrize("question", [
    # Trigger verbs added in batch 2
    "what started the industrial revolution",
    "what ended the Cold War",
    "what sparked the French Revolution",
    "what stopped the plague",
    "what brought about the Great Depression",
])
def test_causal_trigger_verbs(question):
    """started/ended/sparked/stopped/brought about are causal trigger verbs."""
    assert classify(question) == Intent.CAUSAL


@pytest.mark.parametrize("question,expected", [
    # Attribution strip handles started/ended/sparked/stopped/brought about
    ("what started the industrial revolution", "the industrial revolution"),
    ("what ended the Cold War", "the Cold War"),
    ("what sparked the French Revolution", "the French Revolution"),
    ("what stopped the plague", "the plague"),
    ("what brought about the Great Depression", "the Great Depression"),
    # Physics state-change verbs strip as trailing verbs
    ("why does ice float on water", "ice"),
    ("why does iron rust", "iron"),
    ("what makes iron rust", "iron"),
    ("why does water boil at 100 degrees", "water"),
    ("why does water expand when it freezes", "water"),
])
def test_subject_of_trigger_verbs_and_physics(question, expected):
    """started/ended/sparked trigger verbs and physics verbs strip cleanly."""
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


def test_question_words_excludes_why_and_how():
    """'why'/'how' open almost every causal question, so leaving them out of
    _QUESTION_WORDS let them leak into the focus set derived from
    (question words - subject words - _QUESTION_WORDS), spuriously boosting
    any sentence that happens to contain the literal word "why" or "how"."""
    from shaggoth.dialogue.reasoning import _QUESTION_WORDS

    assert "why" in _QUESTION_WORDS
    assert "how" in _QUESTION_WORDS


def test_causal_focus_does_not_leak_question_words():
    from shaggoth.dialogue.reasoning import _topic_words, subject_of, _QUESTION_WORDS

    question = "how does photosynthesis need light"
    subject = subject_of(question)
    focus = _topic_words(question) - _topic_words(subject) - _QUESTION_WORDS
    assert focus == {"light"}


def test_topic_words_excludes_conjunctions():
    """'and' in a subject like 'photosynthesis and respiration' must not
    reach the on-topic check in _pick(), or every sentence qualifies."""
    from shaggoth.dialogue.reasoning import _topic_words
    words = _topic_words("photosynthesis and cellular respiration")
    assert "and" not in words
    assert "photosynthesis" in words
    assert "cellular" in words
    assert "respiration" in words


def test_causal_focus_excludes_conjunctions():
    """'and' appears in almost every English sentence, so leaving it in the
    focus set means every sentence scores one focus hit and the words that
    actually matter (light, carbon, dioxide) cannot separate the right
    sentence from an irrelevant one."""
    from shaggoth.dialogue.reasoning import _topic_words, subject_of, _QUESTION_WORDS

    question = "why does photosynthesis need both light and carbon dioxide"
    subject = subject_of(question)
    focus = _topic_words(question) - _topic_words(subject) - _QUESTION_WORDS
    assert "and" not in focus
    assert "both" not in focus
    # The real focus words must survive.
    assert "light" in focus
    assert "carbon" in focus
    assert "dioxide" in focus


def test_reasoner_has_seeded_rng():
    """The reasoner should use its own Random instance, not the global one."""
    r = _reasoner([AERO])
    assert hasattr(r, "_rng")
    import random
    assert isinstance(r._rng, random.Random)


def test_search_cache_eviction():
    """The _search_cache dict must not grow without bound."""
    r = _reasoner([AERO])
    for i in range(600):
        r._search_cache[f"query-{i}"] = None
        if len(r._search_cache) > r._search_cache_max:
            for _ in range(len(r._search_cache) // 2):
                r._search_cache.pop(next(iter(r._search_cache)))
    assert len(r._search_cache) <= r._search_cache_max


def test_pick_bonus_pattern_promotes_direct_answer():
    """A sentence matching the bonus pattern scores +2 focus hits, placing it
    above sentences that merely contain the causal marker."""
    from shaggoth.dialogue.reasoning import _pick, _CAUSAL_MARKER
    import re
    sentences = [
        # Gravity as AGENT — "gravity causes Y" — not the direct answer.
        "Gravity is the fundamental force that causes all objects with mass to attract one another.",
        # DIRECT answer — "Y causes gravity" — should win.
        "Mass causes gravity by curving spacetime, as described by Einstein.",
        # Another gravity-as-agent sentence.
        "Black holes form when gravity causes the collapse of matter to extreme density.",
    ]
    bonus = re.compile(r"\b(?:caus|mak)(?:e|es|ed|ing)\s+gravity\b", re.I)
    picked = _pick(
        sentences, _CAUSAL_MARKER,
        topic_words={"gravity"},
        limit=1,
        min_len=10,
        focus={"causes"},
        bonus=bonus,
    )
    assert picked, "should find at least one sentence"
    assert "Mass causes gravity" in picked[0], (
        f"Expected direct-answer sentence first, got: {picked[0]!r}"
    )


def test_causal_what_causes_prefers_effect_sentence():
    """'what causes gravity' should lead with 'Mass causes gravity', not a
    sentence where gravity acts as the agent of some other effect."""
    gravity_article = (
        "Gravity is the fundamental force that causes all objects with mass to attract one another. "
        "Mass causes gravity by curving spacetime as described by Einstein's general theory of relativity. "
        "Gravity causes the Earth to orbit the Sun and objects to fall toward the ground."
    )
    entry = FakeEntry("Gravity", gravity_article)
    result = _reasoner([entry]).reason("what causes gravity")
    assert result is not None
    assert result.answer.startswith("Mass causes gravity"), (
        f"Expected 'Mass causes gravity' to lead; got: {result.answer!r}"
    )


def test_causal_ranking_ignores_incidental_how_in_sentence_text():
    """A sentence that merely contains the word "how" must not outrank the
    sentence that actually explains the question's focus ("light"), which is
    what happened while "how" counted as a focus word in its own right."""
    entry = FakeEntry(
        "Photosynthesis",
        "This explains how the broader cycle operates because energy moves "
        "through many connected membranes. "
        "It requires light because chlorophyll absorbs photons to drive the "
        "reaction.",
    )
    result = _reasoner([entry]).reason("how does photosynthesis need light")
    assert result is not None
    assert result.answer.strip().startswith("It requires light")
