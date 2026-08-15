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
    # "how many X" asks for a count/list
    "how many planets are in the solar system",
    "how many moons does Jupiter have",
    "how many bones are in the human body",
])
def test_enumerating_questions(question):
    assert classify(question) == Intent.ENUMERATE


@pytest.mark.parametrize("question,expected", [
    # "how many X are in Y" → subject is X
    ("how many planets are in the solar system", "planets"),
    ("how many bones are in the human body", "bones"),
    # "how many X does Y have" → subject is X
    ("how many moons does Jupiter have", "moons"),
    # "how long does X take" → strip degree word + trailing "take"
    ("how long does photosynthesis take", "photosynthesis"),
])
def test_subject_of_how_many_and_how_long(question, expected):
    """how many/long degree words and possessive 'does Y have' strip cleanly."""
    assert subject_of(question) == expected


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


@pytest.mark.parametrize("question,expected", [
    # "how does X differ from Y" — "differ" is a comparison verb between subject and joiner
    ("how does DNA differ from RNA", ["DNA", "RNA"]),
    ("how does Python differ from JavaScript", ["Python", "JavaScript"]),
    # "how does X relate to Y" — "relate" similarly sits between subject and joiner
    ("how does photosynthesis relate to respiration", ["photosynthesis", "respiration"]),
])
def test_split_subjects_differ_and_relate(question, expected):
    """Comparison verbs 'differ from' and 'relate to' must be stripped before splitting."""
    assert classify(question) in (Intent.COMPARE, Intent.CONTRAST)
    assert split_subjects(question) == expected


def test_subject_of_drops_the_trailing_verb_phrase():
    """The subject is what to look up; the rest is what to look for."""
    assert subject_of("why does photosynthesis need light") == "photosynthesis"
    assert subject_of("what causes gravity") == "gravity"
    assert subject_of("what are the types of cryptography") == "cryptography"
    assert subject_of("how does a river work") == "river"


@pytest.mark.parametrize("question,expected", [
    ("how is steel made", "steel"),
    ("how are vaccines produced", "vaccines"),
    ("how do earthquakes happen", "earthquakes"),
    ("how can I fix a leaky faucet", "I fix a leaky faucet"),
    ("what is the process of photosynthesis", "photosynthesis"),
    ("what is the cause of inflation", "inflation"),
    ("what happens when water boils", "water"),
    ("what leads to inflation", "inflation"),
    ("what triggers an earthquake", "earthquake"),
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
    ("what caused the Great Depression", "Great Depression"),
    ("what caused the financial crisis", "financial crisis"),
    # Extinction/state trailing verbs
    ("why did the dinosaurs go extinct", "dinosaurs"),
    ("how did the Roman Empire fall", "Roman Empire"),
    ("how did the Soviet Union collapse", "Soviet Union"),
    # Enumeration with "some types" article prefix
    ("what are some types of cancer", "cancer"),
    # Imperative enumeration commands
    ("name the different types of machine learning", "machine learning"),
    ("list the planets in the solar system", "planets"),
])
def test_subject_of_new_patterns(question, expected):
    assert subject_of(question) == expected


@pytest.mark.parametrize("question,expected", [
    # "who" opening + attribution verb strip at the start
    ("who invented the telephone", "telephone"),
    ("who discovered penicillin", "penicillin"),
    ("who developed the theory of relativity", "theory of relativity"),
    ("who designed the Eiffel Tower", "Eiffel Tower"),
    # "when" opening + passive attribution verb at the end
    ("when was the internet invented", "internet"),
    ("when was electricity discovered", "electricity"),
    # "what happens during X" → "during" preposition strip
    ("what happens during photosynthesis", "photosynthesis"),
    ("what happens during an earthquake", "earthquake"),
    # Action verb (fight/affect) at end — previously leaked into subject
    ("how does the immune system fight viruses", "immune system"),
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
    # "fall/collapse/rise of X" — strip the event noun to get the core topic.
    ("what caused the fall of the Roman Empire", "Roman Empire"),
    ("what caused the collapse of the Soviet Union", "Soviet Union"),
    ("what caused the rise of nationalism", "nationalism"),
    # "X fall" with no following "of" — "fall" IS a verb here; strip it too.
    ("how did Rome fall", "Rome"),
    ("why did the Soviet Union collapse", "Soviet Union"),
    # "originate" is now in the trailing-verb list.
    ("where did humans originate", "humans"),
    ("where did life originate", "life"),
    # "role/function of X in Y" — "in Y" is context, not part of subject.
    ("what is the role of mitochondria in cell energy", "mitochondria"),
    ("what is the function of chlorophyll in photosynthesis", "chlorophyll"),
    ("what is the role of ATP in muscle contraction", "ATP"),
    # "in the solar system" context stripped; "planets" is the KB lookup term.
    ("list the planets in the solar system", "planets"),
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
    ("what started the industrial revolution", "industrial revolution"),
    ("what ended the Cold War", "Cold War"),
    ("what sparked the French Revolution", "French Revolution"),
    ("what stopped the plague", "plague"),
    ("what brought about the Great Depression", "Great Depression"),
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


@pytest.mark.parametrize("question", [
    "what led to the fall of the Roman Empire",
    "what led to World War 1",
    "what led to the Great Depression",
])
def test_causal_past_tense_led(question):
    """'what led to X' uses past tense; must classify as CAUSAL, not DEFINE."""
    assert classify(question) == Intent.CAUSAL


@pytest.mark.parametrize("question,expected", [
    # Medical/descriptive "of" nouns should strip cleanly to the real subject
    ("what are the symptoms of diabetes", "diabetes"),
    ("what are the effects of climate change", "climate change"),
    ("what are the benefits of exercise", "exercise"),
    ("what are the causes of heart disease", "heart disease"),
    ("what are the signs of dehydration", "dehydration"),
    # 'what led to X' — past-tense lead; "fall of" stripped to core topic
    ("what led to the fall of the Roman Empire", "Roman Empire"),
    ("what led to World War 1", "World War 1"),
    # 'have phases/feathers' — possession verb trailing strip
    ("why does the moon have phases", "moon"),
    ("why do birds have feathers", "birds"),
])
def test_subject_of_batch3_patterns(question, expected):
    """Batch 3: descriptive-noun strip, 'led to', possession 'have'."""
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


# --------------------------------------------------------------------------
# Batch 5: expanded _CAUSAL_MARKER, _ENUM_MARKER, give-me subject strip
# --------------------------------------------------------------------------


def test_causal_marker_new_connectives():
    """leads to / stems from / triggers / consequently / as a consequence /
    contributes to are all causal connectives that should match _CAUSAL_MARKER
    so that those sentences are selected when answering causal questions."""
    from shaggoth.dialogue.reasoning import _CAUSAL_MARKER

    sentences = [
        "Heat leads to molecular expansion, causing pressure to rise.",
        "The condition stems from a genetic mutation.",
        "Cold air triggers vasoconstriction to preserve core temperature.",
        "Consequently, the reaction releases carbon dioxide as a byproduct.",
        "As a consequence of deforestation, regional rainfall patterns shifted.",
        "Regular exercise contributes to improved cardiovascular health.",
    ]
    for sentence in sentences:
        assert _CAUSAL_MARKER.search(sentence), (
            f"_CAUSAL_MARKER should match: {sentence!r}"
        )


def test_enum_marker_the_following_and_there_are():
    """'the following' and 'there are' are high-precision enumeration signals."""
    from shaggoth.dialogue.reasoning import _ENUM_MARKER

    sentences = [
        "The following are the main types of cloud computing: IaaS, PaaS, and SaaS.",
        "There are three primary types of rock: igneous, sedimentary, and metamorphic.",
        "There are eight planets in the solar system.",
    ]
    for sentence in sentences:
        assert _ENUM_MARKER.search(sentence), (
            f"_ENUM_MARKER should match: {sentence!r}"
        )


@pytest.mark.parametrize("question,expected", [
    # "give me examples of X" — previously the "give me" prefix blocked the
    # types-of strip because the article word (the/some) was missing.
    ("give me examples of renewable energy", "renewable energy"),
    ("give examples of machine learning", "machine learning"),
    # "show me" variant
    ("show me some types of cancer", "cancer"),
    ("give me the types of cryptography", "cryptography"),
    # "give me some X" — with article word present
    ("give me some examples of cloud computing", "cloud computing"),
])
def test_subject_of_give_me_examples(question, expected):
    """'give me examples of X' must strip the imperative prefix and extract X."""
    assert subject_of(question) == expected


@pytest.mark.parametrize("question", [
    "give me examples of renewable energy",
    "give me the types of machine learning",
    "show me some examples of cloud computing",
])
def test_enumerate_classify_give_me_questions(question):
    """'give me examples of X' questions should classify as ENUMERATE."""
    assert classify(question) == Intent.ENUMERATE


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


# --------------------------------------------------------------------------
# Batch 6: comparison depth, snippet punctuation, extended bonus
# --------------------------------------------------------------------------


def test_comparison_includes_second_sentence_when_first_is_short():
    """When the first sentence of an entry is < 100 chars, the comparison
    answer should include the second sentence to give more substance."""
    aero2 = FakeEntry(
        "Aeroponics",
        "Aeroponics grows plants in mist. It uses 95 percent less water than soil farming.",
    )
    hydro2 = FakeEntry(
        "Hydroponics",
        "Hydroponics grows plants in nutrient-rich water. No soil is required at all.",
    )
    result = _reasoner([aero2, hydro2]).reason("compare aeroponics and hydroponics")
    assert result is not None
    # Second sentence from each entry should appear in the combined answer.
    assert "95 percent" in result.answer, (
        f"Second sentence of aeroponics missing: {result.answer!r}"
    )
    assert "No soil" in result.answer, (
        f"Second sentence of hydroponics missing: {result.answer!r}"
    )


def test_comparison_does_not_duplicate_second_sentence_for_long_first():
    """When the first sentence is >= 100 chars it already carries enough
    information, so the second sentence must NOT be appended."""
    long_aero = FakeEntry(
        "Aeroponics",
        "Aeroponics is a highly efficient soil-free plant-growing method in which roots "
        "are continuously misted with nutrient-rich water inside a sealed chamber. "
        "This is the second sentence which must not appear.",
    )
    hydro2 = FakeEntry(
        "Hydroponics",
        "Hydroponics grows plants in water. No soil is needed.",
    )
    result = _reasoner([long_aero, hydro2]).reason("compare aeroponics and hydroponics")
    assert result is not None
    assert "must not appear" not in result.answer, (
        f"Second sentence of long entry must be suppressed: {result.answer!r}"
    )


def test_search_snippets_get_terminal_punctuation():
    """Snippets returned by the search callable that lack a sentence terminator
    must get a '.' appended so they don't run together when joined."""
    class FakeResult:
        def __init__(self, snippet):
            self.snippet = snippet
            self.title = "Test"
            self.url = "http://example.com"

    def fake_search(query, limit):
        return [
            FakeResult("Tectonic plates move slowly over millions of years"),
            FakeResult("This movement releases enormous amounts of energy!"),
        ]

    r = Reasoner(
        FakeKnowledge([]),
        summarize=lambda c, t: (c, True),
        sentences=lambda c: [s.strip() + "." for s in c.split(".") if s.strip()],
        search=fake_search,
    )
    snippets, _ = r._search_web("test query", limit=2)
    assert snippets[0].endswith("."), f"Unpunctuated snippet should get '.': {snippets[0]!r}"
    assert snippets[1].endswith("!"), f"Exclamation-terminated snippet unchanged: {snippets[1]!r}"


def test_causal_what_triggers_prefers_object_position_sentence():
    """'what triggers X' should prefer sentences where something triggers X
    (X in object position) over sentences where X triggers something else.
    Uses plural 'earthquakes' so the FakeKnowledge entry-title match succeeds."""
    earthquake_article = (
        "Earthquakes trigger tsunamis when they occur undersea. "
        "Tectonic plate movement triggers earthquakes when accumulated stress releases. "
        "Earthquakes also trigger landslides on unstable slopes."
    )
    entry = FakeEntry("Earthquakes", earthquake_article)
    result = _reasoner([entry]).reason("what triggers earthquakes")
    assert result is not None
    assert "plate movement" in result.answer.lower() or "Tectonic" in result.answer, (
        f"Expected 'plate movement triggers earthquakes'; got: {result.answer!r}"
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


# --------------------------------------------------------------------------
# Batch 7: _QUESTION_WORDS imperative scaffolding expansion
# --------------------------------------------------------------------------


@pytest.mark.parametrize("word", [
    "give", "show", "name", "different", "some", "me", "of", "a", "an",
    "all", "any", "few",
])
def test_question_words_contains_imperative_scaffolding(word):
    """Imperative scaffolding words from enumerate questions must be in
    _QUESTION_WORDS so they are excluded from the focus-word set."""
    from shaggoth.dialogue.reasoning import _QUESTION_WORDS
    assert word in _QUESTION_WORDS, (
        f"{word!r} not in _QUESTION_WORDS; it will leak into focus sets for "
        "questions like 'give me examples of X' and bias sentence ranking."
    )


@pytest.mark.parametrize("question,subject,expected_focus", [
    (
        "give me examples of renewable energy",
        "renewable energy",
        set(),
    ),
    (
        "name the different types of machine learning",
        "machine learning",
        set(),
    ),
    (
        "show me some types of cancer",
        "cancer",
        set(),
    ),
    (
        "list some examples of programming languages",
        "programming languages",
        set(),
    ),
])
def test_imperative_enumerate_focus_is_empty(question, subject, expected_focus):
    """After stripping subject words and _QUESTION_WORDS, no spurious
    scaffolding word should remain in the focus set for enumerate questions."""
    from shaggoth.dialogue.reasoning import _topic_words, _QUESTION_WORDS
    focus = _topic_words(question) - _topic_words(subject) - _QUESTION_WORDS
    assert focus == expected_focus, (
        f"For {question!r}: expected empty focus set, got {focus!r}"
    )


# --------------------------------------------------------------------------
# Batch 8: contraction normalization and negation stripping
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    ("why doesn't ice float", "ice"),
    ("how doesn't water conduct electricity", "water"),
    ("why don't vaccines cause autism", "vaccines"),
    ("what's causing earthquakes", "earthquakes"),
    ("how's steel made", "steel"),
    ("why doesn't water boil at room temperature", "water"),
])
def test_subject_of_contractions(question, expected):
    """Contractions like "doesn't", "don't", and "what's" must expand before
    subject stripping so auxiliary forms are recognised and removed."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


def test_subject_of_negation_not_stripped():
    """'why does photosynthesis not use water' → subject is 'photosynthesis',
    not 'photosynthesis not' (the residual 'not' must be removed)."""
    assert subject_of("why does photosynthesis not use water") == "photosynthesis"


@pytest.mark.parametrize("question,intent", [
    ("why doesn't ice float", "causal"),
    ("what's causing climate change", "causal"),
    ("why isn't Python faster than Ruby", "compare"),
    ("how's aeroponics different from hydroponics", "compare"),
])
def test_classify_contractions(question, intent):
    """Contractions must not break intent classification."""
    assert classify(question) == intent


@pytest.mark.parametrize("question,expected_subjects", [
    ("why isn't Python faster than Ruby", ["Python", "Ruby"]),
    ("how's aeroponics different from hydroponics", ["aeroponics", "hydroponics"]),
])
def test_split_subjects_contractions(question, expected_subjects):
    """split_subjects must work through contractions."""
    result = split_subjects(question)
    assert result == expected_subjects, (
        f"split_subjects({question!r}): expected {expected_subjects!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 9: imperative prefix strip, quantifier strip, new classify patterns
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    ("tell me about different types of databases", "databases"),
    ("explain how vaccines work", "vaccines"),
    ("describe the role of mitochondria in cells", "mitochondria"),
    ("discuss the effects of climate change", "climate change"),
    ("give me an overview of quantum mechanics", "quantum mechanics"),
])
def test_subject_of_imperative_prefix_strip(question, expected):
    """Imperative prefixes like 'tell me about', 'explain', 'describe' must
    be stripped from the subject so the reasoner looks up the right topic."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what are some programming languages", "programming languages"),
    ("what are various forms of energy", "energy"),
    ("what are several types of volcanoes", "volcanoes"),
])
def test_subject_of_leading_quantifier_stripped(question, expected):
    """Bare leading quantifiers ('some', 'various', 'several') left after
    stripping 'what are' must not pollute the extracted subject."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question", [
    "what do plants need to grow",
    "what does a cell need to survive",
    "what do vaccines require for effectiveness",
    "what do plants use for photosynthesis",
])
def test_classify_what_do_x_need_is_causal(question):
    """'what do X need/require/use' asks for requirements — a causal question."""
    assert classify(question) == Intent.CAUSAL


@pytest.mark.parametrize("question", [
    "what renewable energy sources are there",
    "what programming languages are available",
    "what types of stars are common",
])
def test_classify_what_x_are_there_is_enumerate(question):
    """'what X are there/available/common' asks for a list — an enumerate question."""
    assert classify(question) == Intent.ENUMERATE


# ---------------------------------------------------------------------------
# Batch 10: degree-adverb handling, "how fast/far/quickly", leading-article
# strip, "X are in Y" container redirect, enumerate for "name all/give/show",
# trailing intransitive verbs, trailing state adjectives
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("question,expected_intent,expected_subject", [
    # "how fast/far/quickly does X" → CAUSAL + subject is X
    ("how fast does light travel", Intent.CAUSAL, "light"),
    ("how quickly does water evaporate", Intent.CAUSAL, "water"),
    ("how far does sound travel", Intent.CAUSAL, "sound"),
    ("how far is the moon from earth", Intent.CAUSAL, "moon"),
    ("how slowly does a glacier move", Intent.CAUSAL, "glacier"),
    # Leading "the" strip
    ("what is the speed of light", Intent.DEFINE, "speed of light"),
    ("how does the immune system work", Intent.CAUSAL, "immune system"),
    ("what caused the great depression", Intent.CAUSAL, "great depression"),
    # Leading "a/an" strip
    ("why do stars twinkle", Intent.CAUSAL, "stars"),
    # Trailing intransitive verbs
    ("why do stars twinkle", Intent.CAUSAL, "stars"),
    ("how does sound travel", Intent.CAUSAL, "sound"),
    ("why do we dream", Intent.CAUSAL, "dream"),
    ("how does light shine", Intent.CAUSAL, "light"),
    # Trailing state adjectives  
    ("why is the sky blue", Intent.CAUSAL, "sky"),
    ("why is gold so valuable", Intent.CAUSAL, "gold"),
    # "what are the different states of matter" → ENUMERATE + "matter"
    ("what are the different states of matter", Intent.ENUMERATE, "matter"),
])
def test_batch10_degree_adverb_and_subject_cleanup(question, expected_intent, expected_subject):
    """Batch 10: degree adverbs, article strip, intransitive verbs, adjectives."""
    assert classify(question) == expected_intent
    assert subject_of(question) == expected_subject


@pytest.mark.parametrize("question,expected_intent", [
    # "name/give/show all/some/the X" should be enumerate
    ("name all the continents", Intent.ENUMERATE),
    ("give me the main organs of the body", Intent.ENUMERATE),
    ("show me the planets", Intent.ENUMERATE),
    # "what are all the X" should be enumerate
    ("what are all the planets", Intent.ENUMERATE),
    ("what are all the major oceans", Intent.ENUMERATE),
    # "what X are in Y" should be enumerate
    ("what elements are in water", Intent.ENUMERATE),
    ("what gases are in the atmosphere", Intent.ENUMERATE),
])
def test_batch10_enumerate_patterns(question, expected_intent):
    """Batch 10: 'name all', 'give me the', 'what X are in Y' → ENUMERATE."""
    assert classify(question) == expected_intent


@pytest.mark.parametrize("question,expected_subject", [
    # "what X are in Y" → look up Y
    ("what elements are in water", "water"),
    ("what gases are in the atmosphere", "atmosphere"),
    # "all" quantifier stripped
    ("what are all the planets in the solar system", "planets"),
    # "name all the X" → X
    ("name all the continents", "continents"),
    # "in the solar system" context stripped
    ("list the planets in the solar system", "planets"),
    # "from earth" trailing strip
    ("how far is the moon from earth", "moon"),
])
def test_batch10_subject_extraction(question, expected_subject):
    """Batch 10: container redirect, quantifier, article, and location strips."""
    assert subject_of(question) == expected_subject


# ---------------------------------------------------------------------------
# Batch 11: "when did/was X" → CAUSAL, temporal scaffolding, transitive verbs,
# qualifier adjective strip, "layers of X" scaffold noun
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("question", [
    "when did the roman empire fall",
    "when was the eiffel tower built",
    "when did the dinosaurs go extinct",
])
def test_batch11_when_historical_is_causal(question):
    """'when did/was X' historical questions should classify as CAUSAL."""
    assert classify(question) == Intent.CAUSAL


@pytest.mark.parametrize("question,expected", [
    # "when did/was X" → correct subject (article stripped, trailing verb stripped)
    ("when did the roman empire fall", "roman empire"),
    ("when was the eiffel tower built", "eiffel tower"),
    ("when did the dinosaurs go extinct", "dinosaurs"),
    # "what year was X" → strip temporal scaffolding "year was"
    ("what year was penicillin discovered", "penicillin"),
    # Trailing transitive verbs not previously in the list
    ("how does the brain process information", "brain"),
    ("how does the heart pump blood", "heart"),
    ("how does wifi connect to the internet", "wifi"),
    # Leading qualifier adjective strip: "different/main/major/key"
    ("what are the different blood types", "blood types"),
    ("what are the main programming languages", "programming languages"),
    # "layers of X" scaffold noun → X
    ("what are the layers of the atmosphere", "atmosphere"),
    ("what are the layers of the earth", "earth"),
])
def test_batch11_subject_extraction(question, expected):
    """Batch 11: temporal strip, transitive verbs, qualifier adjectives, layers scaffold."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected_intent", [
    # "what are the layers of X" → ENUMERATE (matches "what are the" pattern)
    ("what are the layers of the atmosphere", Intent.ENUMERATE),
    ("what are the layers of the earth", Intent.ENUMERATE),
    # Leading qualifier but still enumerate
    ("what are the main programming languages", Intent.ENUMERATE),
    ("what are the different blood types", Intent.ENUMERATE),
])
def test_batch11_enumerate_classify(question, expected_intent):
    """'what are the layers/main/different X' should classify as ENUMERATE."""
    assert classify(question) == expected_intent


# ---------------------------------------------------------------------------
# Batch 12: components/parts scaffold nouns, biological/physical process verbs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "components of X" and "parts of X" scaffold nouns → X
    ("what are the components of a cell", "cell"),
    ("what are the parts of the brain", "brain"),
    ("what are the sections of DNA", "DNA"),
    ("what are the members of the solar system", "solar system"),
    # Biological/physical process verbs stripped trailing
    ("how does the kidney filter blood", "kidney"),
    ("how does electricity flow through a wire", "electricity"),
    ("how do red blood cells carry oxygen", "red blood cells"),
    ("how does the stomach digest food", "stomach"),
    ("how does the body regulate temperature", "body"),
])
def test_batch12_subject_extraction(question, expected):
    """Batch 12: components/parts scaffold, filter/flow/carry/digest/regulate verbs."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected_intent", [
    ("what are the components of a cell", Intent.ENUMERATE),
    ("what are the parts of the brain", Intent.ENUMERATE),
    ("how does the kidney filter blood", Intent.CAUSAL),
    ("how does electricity flow through a wire", Intent.CAUSAL),
])
def test_batch12_classify(question, expected_intent):
    """Batch 12: components/parts → ENUMERATE; process verbs → CAUSAL."""
    assert classify(question) == expected_intent


# ---------------------------------------------------------------------------
# Batch 13: stages/phases/steps/organs/branches scaffold nouns; more verbs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # Scaffold nouns for sequence/group questions
    ("what are the stages of mitosis",               "mitosis"),
    ("what are the phases of the moon",              "moon"),
    ("what are the steps of the water cycle",        "water cycle"),
    ("what are the organs of the digestive system",  "digestive system"),
    ("what are the branches of government",          "government"),
    # Additional transitive/intransitive process verbs
    ("how does the liver detoxify blood",            "liver"),
    ("how does the lung exchange gases",             "lung"),
    ("how does yeast ferment sugar",                 "yeast"),
    ("how does a magnet attract metal",              "magnet"),
    ("how does gravity pull objects",                "gravity"),
    # "form on" pattern: subject is the thing being explained, not the substrate
    ("how does rust form on iron",                   "rust"),
])
def test_batch13_subject_extraction(question, expected):
    """Batch 13: stages/phases/steps/organs/branches scaffold; detoxify/exchange/ferment/attract/pull."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected_intent", [
    ("what are the stages of mitosis",               Intent.ENUMERATE),
    ("what are the phases of the moon",              Intent.ENUMERATE),
    ("what are the steps of the water cycle",        Intent.ENUMERATE),
    ("what are the organs of the digestive system",  Intent.ENUMERATE),
    ("what are the branches of government",          Intent.ENUMERATE),
    ("how does the liver detoxify blood",            Intent.CAUSAL),
    ("how does a magnet attract metal",              Intent.CAUSAL),
])
def test_batch13_classify(question, expected_intent):
    """Batch 13: stages/phases/steps/organs/branches → ENUMERATE; new verbs → CAUSAL."""
    assert classify(question) == expected_intent


# --------------------------------------------------------------------------
# Batch 14: numeric/article leading strip, bare "in X" context strip,
#            "change OBJECT" trailing strip, erupt verb
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # Numeric quantifier + early article strip
    ("what are the 3 states of matter",             "matter"),
    ("what are the 4 blood types",                  "blood types"),
    ("what are 5 types of clouds",                  "clouds"),
    # "change OBJECT" trailing strip (verb use): subject precedes "change X"
    ("why do leaves change color",                  "leaves"),
    ("how does the sun change seasons",             "sun"),
    ("how does a river change course",              "river"),
    ("why do leaves change color in autumn",        "leaves"),
    # "climate change" preserved as compound noun (no object after "change")
    ("what is the impact of climate change on ecosystems", "climate change"),
    ("how does climate change affect sea levels",   "climate change"),
    ("why does the climate change",                 "climate change"),
    # erupt trailing verb
    ("why do volcanoes erupt",                      "volcanoes"),
    # bare "in WORD" context strip
    ("what causes turbulence in planes",            "turbulence"),
    ("what causes pain in joints",                  "pain"),
    ("what causes traffic in cities",               "traffic"),
])
def test_batch14_subject_extraction(question, expected):
    """Batch 14: numeric strip, bare-in-word strip, change-object strip, erupt verb."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected_intent", [
    ("what are the 3 states of matter",             Intent.ENUMERATE),
    ("what are the 4 blood types",                  Intent.ENUMERATE),
    ("why do leaves change color",                  Intent.CAUSAL),
    ("why do volcanoes erupt",                      Intent.CAUSAL),
    ("what causes turbulence in planes",            Intent.CAUSAL),
    ("what is the impact of climate change on ecosystems", Intent.CAUSAL),
])
def test_batch14_classify(question, expected_intent):
    """Batch 14: numeric → ENUMERATE; change/erupt/turbulence → CAUSAL."""
    assert classify(question) == expected_intent


# --------------------------------------------------------------------------
# Batch 15: factual-property nouns, historical-event nouns, migrate/dissolve
#            verbs, generic-pronoun activity extraction
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # Factual property nouns: "capital/population/height of X" → X
    ("what is the capital of france",               "france"),
    ("what is the population of china",             "china"),
    ("what is the height of mount everest",         "mount everest"),
    ("what is the area of texas",                   "texas"),
    ("what is the meaning of life",                 "life"),
    ("what is the definition of democracy",         "democracy"),
    # Historical event nouns: "fall/collapse/rise/decline of X" → X
    ("what caused the fall of the roman empire",    "roman empire"),
    ("what caused the collapse of the soviet union", "soviet union"),
    ("what caused the rise of nationalism",         "nationalism"),
    ("what caused the decline of rome",             "rome"),
    # New trailing verbs: migrate, dissolve
    ("how do birds migrate",                        "birds"),
    ("why does salt dissolve in water",             "salt"),
    ("why does sugar dissolve in tea",              "sugar"),
    # Generic-pronoun activity extraction: "we/people VERB" → the activity
    ("why do we dream",                             "dream"),
    ("why do we age",                               "age"),
    ("why do people yawn",                          "yawn"),
    # Entity noun with originate — trailing-verb strip should give entity
    ("where did humans originate",                  "humans"),
    ("where did life originate",                    "life"),
])
def test_batch15_subject_extraction(question, expected):
    """Batch 15: property/event nouns stripped; migrate/dissolve verbs; pronoun-activity extraction."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected_intent", [
    ("what is the capital of france",               Intent.DEFINE),
    ("what caused the fall of the roman empire",    Intent.CAUSAL),
    ("how do birds migrate",                        Intent.CAUSAL),
    ("why does salt dissolve in water",             Intent.CAUSAL),
    ("why do we dream",                             Intent.CAUSAL),
    ("why do people yawn",                          Intent.CAUSAL),
])
def test_batch15_classify(question, expected_intent):
    """Batch 15: property questions → DEFINE; historical/biological → CAUSAL."""
    assert classify(question) == expected_intent


# --------------------------------------------------------------------------
# Batch 16: location-noun pattern, "it takes to VERB X", "X of the world",
#            measurement compound nouns, last/persist verbs, post-led-to event strip
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "what LOCATION-NOUN is X in/on" → X
    ("what country is tokyo in",                    "tokyo"),
    ("what continent is australia on",              "australia"),
    ("what country is paris in",                    "paris"),
    # "how long does it take to VERB X" → X
    ("how long does it take to boil water",         "water"),
    ("how long does it take to learn python",       "python"),
    # "how long does it take for X to VERB" → X
    ("how long does it take for a bone to heal",    "bone"),
    ("how long does it take for a wound to heal",   "wound"),
    # Duration verb
    ("how long does pregnancy last",                "pregnancy"),
    ("how long does a cold last",                   "cold"),
    # "X of the world/universe/etc." → X
    ("what are the oceans of the world",            "oceans"),
    ("what are the continents of the world",        "continents"),
    ("what are the countries of the world",         "countries"),
    # Measurement compound nouns: "boiling point of X" → X
    ("what is the boiling point of water",          "water"),
    ("what is the melting point of iron",           "iron"),
    ("what is the freezing point of alcohol",       "alcohol"),
    # Post-led-to event noun strip
    ("what led to the fall of the roman empire",    "roman empire"),
    ("what led to the collapse of the soviet union", "soviet union"),
    ("what caused the spread of covid",             "covid"),
    ("what caused the rise of democracy",           "democracy"),
])
def test_batch16_subject_extraction(question, expected):
    """Batch 16: location noun, it-takes, of-the-world, measurement nouns, event nouns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected_intent", [
    ("what country is tokyo in",                    Intent.DEFINE),
    ("how long does it take to boil water",         Intent.CAUSAL),
    ("how long does pregnancy last",                Intent.CAUSAL),
    ("what are the oceans of the world",            Intent.ENUMERATE),
    ("what is the boiling point of water",          Intent.DEFINE),
    ("what led to the fall of the roman empire",    Intent.CAUSAL),
])
def test_batch16_classify(question, expected_intent):
    """Batch 16: geography/duration → CAUSAL; ocean enumeration; measurement → DEFINE."""
    assert classify(question) == expected_intent


@pytest.mark.parametrize("question,expected", [
    # "where is X located" → X (strip trailing "located")
    ("where is the amazon river located",       "amazon river"),
    ("where is mount everest located",          "mount everest"),
    ("where is the sahara desert located",      "sahara desert"),
    # "when was X founded/built" → X (past-participle trailing strip)
    ("when was america founded",                "america"),
    ("when was rome founded",                   "rome"),
    ("when was the great wall built",           "great wall"),
    # "what temperature/speed does X VERB" → X
    ("what temperature does water boil",        "water"),
    ("what temperature does iron melt",         "iron"),
    ("what speed does light travel",            "light"),
    # Superlative strip: "largest/tallest/fastest X" → X
    ("what is the largest ocean",               "ocean"),
    ("what is the tallest mountain",            "mountain"),
    ("what is the fastest animal",              "animal"),
    ("what is the smallest country",            "country"),
    ("what is the oldest civilization",         "civilization"),
    ("what is the most common element",         "element"),
    # Predicate adjective strip: "why is X [adj]" → X
    ("why is the ocean salty",                  "ocean"),
    ("why is blood red",                        "blood"),
    ("why is the sea blue",                     "sea"),
])
def test_batch17_subject_extraction(question, expected):
    """Batch 17: located strip, founded/built, temperature-does, superlative, predicate adj."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what do X eat" → X (eat added to trailing verb list)
    ("what do lions eat",                   "lions"),
    ("what do elephants eat",               "elephants"),
    ("what do whales eat",                  "whales"),
    ("what do sharks eat",                  "sharks"),
    # Bare yes/no opener stripped
    ("do humans have tails",                "humans"),
    ("do sharks have bones",                "sharks"),
    ("does a spider have a brain",          "spider"),
    ("does the moon have water",            "moon"),
    # "who won/ruled X" attribution verb strip
    ("who won world war 2",                 "world war 2"),
    ("who won world war 1",                 "world war 1"),
    ("who ruled ancient egypt",             "ancient egypt"),
    # "X stand for" trailing strip
    ("what does nasa stand for",            "nasa"),
    ("what does dna stand for",             "dna"),
    ("what does atm stand for",             "atm"),
    ("what does gps stand for",             "gps"),
    # "how BIG is X" — big/hot/cold/heavy now in measurement word list
    ("how big is the sun",                  "sun"),
    ("how hot is the sun",                  "sun"),
    ("how cold is space",                   "space"),
    ("how heavy is the earth",              "earth"),
    ("how huge is the universe",            "universe"),
])
def test_batch18_subject_extraction(question, expected):
    """Batch 18: eat/hunt, do-opener, won/ruled, stand-for, big/hot/cold."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Modal opener: "can/could X VERB" → X
    ("can humans survive in space",         "humans"),
    ("can fish drown",                      "fish"),
    ("can plants feel pain",                "plants"),
    ("can robots think",                    "robots"),
    ("could dinosaurs swim",                "dinosaurs"),
    # "how long ago did X" → X
    ("how long ago did dinosaurs go extinct", "dinosaurs"),
    ("how long ago did life evolve",        "life"),
    # "how long has X existed" → X  (has/have/had in auxiliary list)
    ("how long has the universe existed",   "universe"),
    ("how long has life existed on earth",  "life"),
    # Orphaned-adverb strip: "when did humans first appear" → "humans"
    ("when did humans first appear",        "humans"),
    ("when did life first appear",          "life"),
    # "dark matter": removing "matter" from verb list
    ("what is dark matter",                 "dark matter"),
    ("what is gray matter",                 "gray matter"),
    # "what type of CATEGORY is X" → X
    ("what type of animal is a whale",      "whale"),
    ("what type of star is the sun",        "sun"),
    ("what type of rock is granite",        "granite"),
    ("what type of metal is gold",          "gold"),
    # Role/title in causal-noun strip: "president of X" → X
    ("who is the president of france",      "france"),
    ("who is the king of spain",            "spain"),
    ("who was the founder of apple",        "apple"),
])
def test_batch19_subject_extraction(question, expected):
    """Batch 19: modal openers, ago, has-existed, orphaned-adverb, dark matter, cat-is, role-of."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Bare "is/are" opener: "is the earth flat" → "earth"
    ("is the earth flat",                           "earth"),
    ("is lightning hot",                            "lightning"),
    ("is the sky blue",                             "sky"),
    # Trailing "a/an NOUN" copular predicate: "is pluto a planet" → "pluto"
    ("is pluto a planet",                           "pluto"),
    ("is a virus alive",                            "virus"),
    # "what has caused X" → classify CAUSAL, subject = X
    ("what has caused the most wars",               "wars"),
    ("what has caused the extinction of dinosaurs", "dinosaurs"),
    # "why doesn't X mix with Y" → X  (mix added to trailing verb list)
    ("why doesn't oil mix with water",              "oil"),
    ("why doesn't water mix with oil",              "water"),
    # "what happens when X dies/boils/rusts" → X
    ("what happens when a star dies",               "star"),
    ("what happens when iron rusts",                "iron"),
    # Predicate copula: "what happens when blood sugar is low" → "blood sugar"
    ("what happens when blood sugar is low",        "blood sugar"),
    ("what happens when body temperature is high",  "body temperature"),
    # Modal + subject + verb tail: "how much X should you VERB" → X
    ("how much water should you drink",             "water"),
    ("how much protein should you eat",             "protein"),
    # Modal + article + noun + verb tail: "how much X does a NOUN VERB" → X
    ("how much sleep does a person need",           "sleep"),
    ("how much oxygen does a human need",           "oxygen"),
    # Unit-noun does pattern: "how many calories does X burn" → X
    ("how many calories does running burn",         "running"),
    ("how many calories does swimming burn",        "swimming"),
    # "when you mix X and Y" → "X and Y"
    ("what happens when you mix baking soda and vinegar", "baking soda and vinegar"),
    ("what happens when you combine hydrogen and oxygen",  "hydrogen and oxygen"),
])
def test_batch20_subject_extraction(question, expected):
    """Batch 20: bare is/are opener, trailing a/an-noun, mix/dies verbs, modal tails, unit-does."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected_intent", [
    ("what has caused the most wars",           Intent.CAUSAL),
    ("what has caused global warming",          Intent.CAUSAL),
    ("what has caused the extinction of birds", Intent.CAUSAL),
])
def test_batch20_classify(question, expected_intent):
    """Batch 20: 'what has caused' should classify as CAUSAL not DEFINE."""
    assert classify(question) == expected_intent


@pytest.mark.parametrize("question,expected", [
    # "what would happen if X VERB" — second-pass if strip + stopped/disappeared/exploded
    ("what would happen if the sun disappeared",         "sun"),
    ("what would happen if the earth stopped rotating",  "earth"),
    ("what would happen if humans stopped eating",       "humans"),
    ("what would happen if the moon exploded",           "moon"),
    ("what would happen if gravity disappeared",         "gravity"),
    # "how long does it take SUBJECT to VERB" — _m_it_takes_subj
    ("how long does it take light to reach earth",       "light"),
    # "difference/similarity between X and Y" → "X and Y"
    ("what is the difference between dna and rna",       "dna and rna"),
    ("what is the difference between bacteria and viruses", "bacteria and viruses"),
    ("what is the similarity between plants and animals",   "plants and animals"),
    # navigate[sd]? trailing verb
    ("how do birds navigate",                            "birds"),
    # come from / get — trailing verb
    ("where does energy come from",                      "energy"),
    ("where does the sun get its energy",                "sun"),
    # half life causal noun
    ("what is the half life of carbon 14",               "carbon 14"),
    # heavy/loud adj strip
    ("why is ice not heavy",                             "ice"),
])
def test_batch21_subject_extraction(question, expected):
    """Batch 21: disappeared/stopped/exploded verbs, it-take-subject, difference-between scaffold."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # born passive
    ("where was einstein born",                     "einstein"),
    ("where was shakespeare born",                  "shakespeare"),
    # differ / different from
    ("how does mitosis differ from meiosis",        "mitosis"),
    ("how is a virus different from a bacterium",   "virus"),
    # percentage/fraction of X is Y → X
    ("what percentage of the earth is water",       "earth"),
    ("what fraction of air is oxygen",              "air"),
    # difference between scaffold (batch 21 overlap, sanity)
    ("what is the difference between dna and rna",  "dna and rna"),
])
def test_batch22_subject_extraction(question, expected):
    """Batch 22: born passive, differ/different-from, percentage/fraction causal scaffold."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Apostrophe-free contraction expansion
    ("why cant cats be vegan",                    "cats"),
    ("why doesnt wood conduct electricity",       "wood"),
    ("why dont fish drown in water",              "fish"),
    # Trailing similar/different adj
    ("how are plants and animals different",      "plants and animals"),
    ("how are mitosis and meiosis similar",       "mitosis and meiosis"),
    # Modal-verb tail: "what if X could VERB"
    ("what if humans could photosynthesize",      "humans"),
    # transmitted (past passive)
    ("how is hiv transmitted",                    "hiv"),
    # find - trailing verb
    ("how do salmon find their way home",         "salmon"),
    # purr - trailing verb
    ("why do cats purr",                          "cats"),
    # away after "how far"
    ("how far away is the moon",                  "moon"),
])
def test_batch23_subject_extraction(question, expected):
    """Batch 23: apostrophe-free contractions, similar/different adj, find/purr/transmitted verbs, away strip."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # compare to
    ("how does nuclear energy compare to solar energy",  "nuclear energy"),
    ("how does python compare to java",                  "python"),
    # trailing dangerous/hard adj
    ("what makes plutonium dangerous",                   "plutonium"),
    ("what makes diamonds hard",                         "diamonds"),
    # what role does X play in Y
    ("what role does insulin play in the body",          "insulin"),
    ("what role does the liver play in digestion",       "liver"),
    # will-future opener
    ("will the sun eventually explode",                  "sun"),
    ("will humans ever live on mars",                    "humans"),
    # what happens to X when it VERBS
    ("what happens to metal when it rusts",              "metal"),
    ("what happens to food when it rots",                "food"),
])
def test_batch24_subject_extraction(question, expected):
    """Batch 24: compare-to verb, dangerous/hard adj, role-does-play, will-opener, happens-to."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X made of/from" → "X"
    ("what is glass made of",                       "glass"),
    ("what is plastic made from",                   "plastic"),
    # "what is X used for" → "X"
    ("what is uranium used for",                    "uranium"),
    ("what is graphene used for",                   "graphene"),
    # "how do you know if X" → "X"
    ("how do you know if a mushroom is poisonous",  "mushroom"),
    # Tell-me / explain patterns
    ("tell me about the black death",               "black death"),
    ("explain how hurricanes form",                 "hurricanes"),
    # "who was the first X to Y" → destination/achievement
    ("who was the first person to walk on the moon",   "moon"),
    ("who was the first woman to win the nobel prize", "nobel prize"),
    # "when did X first Y" → "X"
    ("when did humans first use fire",              "humans"),
    ("when did life first appear on earth",         "life"),
    # Weather/nature questions
    ("what causes thunder",                         "thunder"),
    ("what is a tornado",                           "tornado"),
    # "what are the types of X" → "X"
    ("what are the types of clouds",                "clouds"),
    ("what are the types of volcanoes",             "volcanoes"),
    # "what type of X is Y" → "Y"
    ("what type of animal is a platypus",           "platypus"),
    ("what type of rock is marble",                 "marble"),
])
def test_batch25_subject_extraction(question, expected):
    """Batch 25: used-for, first-X-to-Y, when-did-X-first-Y, type-of patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is the chemical formula of X" → "X"
    ("what is the chemical formula of water",           "water"),
    ("what is the molecular structure of dna",          "dna"),
    # "what is X and how does it work" → "X" (strips second clause)
    ("what is bitcoin and how does it work",            "bitcoin"),
    ("what is dna and how does it replicate",           "dna"),
    # "what does X do to Y" → "X"
    ("what does caffeine do to the brain",              "caffeine"),
    ("what does exercise do to the body",               "exercise"),
    # "is X bad/good for you" → "X"
    ("is coffee bad for you",                           "coffee"),
    ("is asbestos dangerous",                           "asbestos"),
    # "why does X cause Y" → "X"
    ("why does stress cause headaches",                 "stress"),
    ("why does alcohol cause liver damage",             "alcohol"),
    # "how does X affect Y" → "X"
    ("how does exercise affect the brain",              "exercise"),
    ("how does diet affect the heart",                  "diet"),
    # "how many X are there in Y" → "X"
    ("how many bones are there in the human body",      "bones"),
    ("how many planets are there in the solar system",  "planets"),
    # "what are the effects of X" → "X"
    ("what are the effects of climate change",          "climate change"),
    ("what are the effects of alcohol",                 "alcohol"),
])
def test_batch26_subject_extraction(question, expected):
    """Batch 26: chemical-formula, and-how, do-to, bad-for-you, effects-of patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "how does X help Y" → "X"
    ("how does sleep help the brain",               "sleep"),
    ("how does vitamin c help the immune system",   "vitamin c"),
    # "why is X important" / "why is X important for Y" → "X"
    ("why is sleep important",                      "sleep"),
    ("why is water important for life",             "water"),
    ("why is the ozone layer important",            "ozone layer"),
    # "where is X found [in Y]" → "X"
    ("where is gold found in nature",               "gold"),
    ("where is platinum found",                     "platinum"),
    # superlative question: "what X is most Y" → "X"
    ("what element is most abundant on earth",      "element"),
    # "can X Y" (ability) → "X"
    ("can bacteria live in extreme heat",           "bacteria"),
    ("can viruses survive outside a host",          "viruses"),
    # "how old is X" → "X"
    ("how old is the earth",                        "earth"),
    ("how old is the sun",                          "sun"),
    # "how big is X" → "X"
    ("how big is the milky way",                    "milky way"),
    ("how big is jupiter",                          "jupiter"),
    # "what is the largest/smallest X" → "X"
    ("what is the largest planet",                  "planet"),
    ("what is the smallest country in the world",   "country"),
])
def test_batch27_subject_extraction(question, expected):
    """Batch 27: help-verb, important-adj, found-passive, superlative, ability, size patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Technology / computing
    ("how does a computer process data",            "computer"),
    ("how does the internet work",                  "internet"),
    ("what is machine learning",                    "machine learning"),
    ("how does artificial intelligence learn",      "artificial intelligence"),
    ("what is blockchain technology",               "blockchain technology"),
    # Human body
    ("how does the human immune system work",       "human immune system"),
    ("why do humans need sleep",                    "humans"),
    ("how does the nervous system work",            "nervous system"),
    ("why do we get hungry",                        "hungry"),
    ("why do we yawn",                              "yawn"),
    # Biology
    ("how do plants make food",                     "plants"),
    ("how do bacteria become resistant to antibiotics", "bacteria"),
    ("how do viruses mutate",                       "viruses"),
    ("what do mitochondria do",                     "mitochondria"),
    # Economics / social
    ("what causes inflation",                       "inflation"),
    ("why does inflation happen",                   "inflation"),
    ("what is the gdp of a country",                "gdp"),
    # Physics
    ("what is quantum entanglement",                "quantum entanglement"),
    ("how does nuclear fission work",               "nuclear fission"),
    ("what is electromagnetic radiation",           "electromagnetic radiation"),
    # Chemistry
    ("what happens when you mix bleach and ammonia",  "bleach and ammonia"),
    ("why does iron rust in water",                 "iron"),
    ("how do acids and bases neutralize each other",  "acids and bases"),
    # Astronomy
    ("what is a neutron star",                      "neutron star"),
    ("how do stars form",                           "stars"),
    ("what causes a solar eclipse",                 "solar eclipse"),
])
def test_batch28_subject_extraction(question, expected):
    """Batch 28: learn/mutate/neutralize verbs, orphaned 'of' strip, compound subject retention."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )
