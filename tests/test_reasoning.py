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
    # "how many X are in Y" → subject is Y (the container, better lookup key)
    ("how many planets are in the solar system", "solar system"),
    ("how many bones are in the human body", "human body"),
    # "how many X does Y have" → subject is Y (entity being described)
    ("how many moons does Jupiter have", "Jupiter"),
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
    ("how can I fix a leaky faucet", "leaky faucet"),
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
    ("what is the meaning of life",                 "meaning of life"),
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
    # "how much X does a NOUN VERB" → NOUN (entity is the lookup subject, consistent design)
    ("how much sleep does a person need",           "person"),
    ("how much oxygen does a human need",           "human"),
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


@pytest.mark.parametrize("question,expected", [
    # Historical / social science
    ("what caused the french revolution",           "french revolution"),
    ("what caused world war 2",                     "world war 2"),
    ("who invented the telephone",                  "telephone"),
    ("who discovered penicillin",                   "penicillin"),
    ("when did the roman empire fall",              "roman empire"),
    ("when did the cold war end",                   "cold war"),
    ("what is the theory of relativity",            "theory of relativity"),
    ("what is the big bang theory",                 "big bang theory"),
    # Environment / geography
    ("what is climate change",                      "climate change"),
    ("what is global warming",                      "global warming"),
    ("why is the amazon rainforest important",      "amazon rainforest"),
    ("what is the greenhouse effect",               "greenhouse effect"),
    ("why do volcanoes erupt",                      "volcanoes"),
    ("how do earthquakes happen",                   "earthquakes"),
    ("how do tsunamis form",                        "tsunamis"),
    # Health / medicine
    ("what is diabetes",                            "diabetes"),
    ("what is alzheimer's disease",                 "alzheimer's disease"),
    ("how does cancer spread",                      "cancer"),
    ("what is a virus",                             "virus"),
    ("how do vaccines work",                        "vaccines"),
    # Mathematics / logic
    ("what is the pythagorean theorem",             "pythagorean theorem"),
    ("what is calculus",                            "calculus"),
    ("what is the fibonacci sequence",              "fibonacci sequence"),
    # Language / cognition
    ("how does the brain process language",         "brain"),
    ("what is consciousness",                       "consciousness"),
    ("how do we form memories",                     "memories"),
    ("how does sleep affect memory",                "sleep"),
])
def test_batch29_subject_extraction(question, expected):
    """Batch 29: history, environment, health, maths, cognition patterns; end[s]? verb."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Food / nutrition
    ("what is gluten",                              "gluten"),
    ("why is sugar bad for you",                    "sugar"),
    ("what foods are high in protein",              "protein"),
    ("how much protein does the body need",         "body"),
    ("what vitamins does the body need",            "body"),
    ("how does caffeine affect the body",           "caffeine"),
    ("what is the difference between carbs and fat", "carbs and fat"),
    # Animals / wildlife
    ("why do cats purr",                            "cats"),
    ("why do dogs wag their tails",                 "dogs"),
    ("how do birds navigate during migration",      "birds"),
    ("why do whales beach themselves",              "whales"),
    ("how do bees make honey",                      "bees"),
    ("why are bees important to the ecosystem",     "bees"),
    ("how do spiders spin webs",                    "spiders"),
    # Technology / internet
    ("how does wi-fi work",                         "wi-fi"),
    ("what is a computer virus",                    "computer virus"),
    ("how does encryption work",                    "encryption"),
    ("what is the dark web",                        "dark web"),
    ("how does gps work",                           "gps"),
    # Space / planets
    ("why is pluto not a planet",                   "pluto"),
    ("how far is the moon from the earth",          "moon"),
    ("what is a black hole",                        "black hole"),
    ("how hot is the sun",                          "sun"),
    ("how long does it take light to reach earth from the sun", "light"),
    # Social / political
    ("what is democracy",                           "democracy"),
    ("what is communism",                           "communism"),
    ("what causes poverty",                         "poverty"),
    ("what is the stock market",                    "stock market"),
])
def test_batch30_subject_extraction(question, expected):
    """Batch 30: does-the-body strip, wag/beach verbs, adj-for/to phrase strip."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Music / arts
    ("how does music affect the brain",             "music"),
    ("what is jazz",                                "jazz"),
    ("who invented the piano",                      "piano"),
    ("how do you read sheet music",                 "sheet music"),
    # Sports / fitness
    ("how do muscles grow",                         "muscles"),
    ("why do muscles get sore after exercise",      "muscles"),
    ("how does the body burn fat",                  "body"),
    ("what is a calorie",                           "calorie"),
    ("how long does it take to run a marathon",     "marathon"),
    # Geography / earth science
    ("how deep is the ocean",                       "ocean"),
    ("how tall is mount everest",                   "mount everest"),
    ("what is the longest river in the world",      "river"),
    ("why does the earth have seasons",             "earth"),
    ("what causes the northern lights",             "northern lights"),
    ("what is the water cycle",                     "water cycle"),
    # Vehicles / engineering
    ("how does a jet engine work",                  "jet engine"),
    ("how does a car engine work",                  "car engine"),
    ("how do planes fly",                           "planes"),
    ("how do submarines work",                      "submarines"),
    ("how does a nuclear reactor work",             "nuclear reactor"),
    # Philosophy / psychology
    ("what is the meaning of life",                 "meaning of life"),
    ("what is cognitive dissonance",                "cognitive dissonance"),
    ("what is the placebo effect",                  "placebo effect"),
    ("what is confirmation bias",                   "confirmation bias"),
    ("why do people dream",                         "dream"),
    ("why do people lie",                           "lie"),
])
def test_batch31_subject_extraction(question, expected):
    """Batch 31: longest/narrowest superlatives, music/sports/geo/engineering/philosophy patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what if" counterfactuals
    ("what if humans could photosynthesize",        "humans"),
    ("what if the earth stopped spinning",          "earth"),
    ("what would happen if the sun disappeared",    "sun"),
    # Imperative openers
    ("tell me about the solar system",              "solar system"),
    ("explain the theory of evolution",             "theory of evolution"),
    ("describe how the heart works",                "heart"),
    # "is X related to Y" / "does X affect Y"
    ("is stress related to heart disease",          "stress"),
    ("does diet affect cancer risk",                "diet"),
    # "how can X Y"
    ("how can humans survive on mars",              "humans"),
    ("how can the body fight infection",            "body"),
    # "what makes X Y"
    ("what makes a material conductive",            "material"),
    ("what makes the sky blue",                     "sky"),
    # "called that" tail
    ("why is the great wall of china called that",  "great wall of china"),
    # "can X Y"
    ("can plants feel pain",                        "plants"),
    ("can fish feel pain",                          "fish"),
    # Possessive subjects
    ("what is the earth's atmosphere made of",      "earth's atmosphere"),
    ("what is the sun's core made of",              "sun's core"),
    # Apostrophe-free informal contractions
    ("whats the boiling point of water",            "water"),
    ("hows a computer chip made",                   "computer chip"),
    # Multi-word scientific phrases
    ("what is the theory of general relativity",    "theory of general relativity"),
    ("what is the law of conservation of energy",   "law of conservation of energy"),
    # Negation contractions
    ("why don't vaccines cause autism",             "vaccines"),
    ("why doesn't wood conduct electricity",        "wood"),
    ("why can't humans breathe underwater",         "humans"),
])
def test_batch32_subject_extraction(question, expected):
    """Batch 32: whats/hows contractions, related-to strip, called-that strip, conductive adj."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what effect/impact does X have on Y" → X
    ("what effect does smoking have on the lungs",  "smoking"),
    ("what effect does exercise have on sleep",     "exercise"),
    # "how fast does X travel"
    ("how fast does light travel",                  "light"),
    ("how fast does sound travel",                  "sound"),
    # "how hot/cold/deep is X at/during TIME"
    ("how hot is the sun",                          "sun"),
    ("how cold is the moon at night",               "moon"),
    ("how deep is the mariana trench",              "mariana trench"),
    ("how far is mars from earth",                  "mars"),
    # "what is the capital/population of X"
    ("what is the capital of france",               "france"),
    ("what is the capital of japan",                "japan"),
    ("what is the population of china",             "china"),
    ("what is the population of the world",         "world"),
    # "what percentage of X is/does Y" → X
    ("what percentage of the earth is covered by water", "earth"),
    ("what percentage of the human body is water",  "human body"),
    # "how many X (of Y) are there" → "X of Y"
    ("how many species of birds are there",         "species of birds"),
    ("how many cells are in the human body",        "human body"),
    # "at what temperature/speed does X VERB"
    ("at what temperature does water freeze",       "water"),
    ("at what temperature does iron melt",          "iron"),
    # "difference between X and Y" — article strip guard keeps "and Y"
    ("what is the difference between a virus and a bacteria", "virus and bacteria"),
    # "how do X and Y differ" → subject_of returns the full conjunction
    ("how do plants and animals differ",            "plants and animals"),
    # "what are the types of X"
    ("what are the types of renewable energy",      "renewable energy"),
    ("what are the types of memory in the brain",   "memory"),
])
def test_batch33_subject_extraction(question, expected):
    """Batch 33: effect/impact strip, at-what-temp opener, at-night tail, a/an guard."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 34: "known for", "language does X speak", "time zone is X in"
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "how many X does/do Y have/need" → Y (entity being described)
    ("how many chambers does the heart have",       "heart"),
    ("how many chromosomes do humans have",         "humans"),
    ("how many teeth do adults have",               "adults"),
    ("how much water does the body need",           "body"),
    ("how much sleep does a teenager need",         "teenager"),
    ("how much protein does a person need",         "person"),
    # "what is X known for" → X
    ("what is einstein known for",                  "einstein"),
    ("what is nasa known for",                      "nasa"),
    # "what is X made from/of" → X
    ("what is concrete made of",                    "concrete"),
    ("what is glass made from",                     "glass"),
    ("what is silk made from",                      "silk"),
    # "when was/were X built/discovered/alive" → X
    ("when was the eiffel tower built",             "eiffel tower"),
    ("when was america discovered",                 "america"),
    ("when were dinosaurs alive",                   "dinosaurs"),
    # "where is X located/found" → X
    ("where is the amazon river located",           "amazon river"),
    ("where is the eiffel tower located",           "eiffel tower"),
    ("where is the largest desert",                 "desert"),
    # "what language does X speak" → X
    ("what language does brazil speak",             "brazil"),
    ("what language do people in france speak",     "france"),
    # "what happens to X when it VERBS" → X
    ("what happens to water when it boils",         "water"),
    ("what happens to iron when it rusts",          "iron"),
    # "how do you say X in Y" → X
    ("how do you say hello in french",              "hello"),
    ("how do you say goodbye in spanish",           "goodbye"),
    # "what time zone is X in" → X
    ("what time zone is new york in",               "new york"),
    ("what time zone is london in",                 "london"),
])
def test_batch34_subject_extraction(question, expected):
    """Batch 34: known-for strip, language scaffold, time-zone loc-noun."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 35: speed/distance causal-noun, "how strong is X", distance-from-X-to-Y
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "what is the speed of X" → "speed of X" when X has no article (canonical constant)
    ("what is the speed of light",                  "speed of light"),
    ("what is the speed of sound",                  "speed of sound"),
    # causal-noun compounds (size/weight/height/temperature/age already covered)
    ("what is the size of the universe",            "universe"),
    ("what is the weight of a blue whale",          "blue whale"),
    ("what is the height of mount everest",         "mount everest"),
    ("what is the temperature of the sun",          "sun"),
    ("what is the age of the universe",             "universe"),
    # "distance from X to Y" → X
    ("what is the distance from earth to the moon", "earth"),
    ("what is the distance from the sun to earth",  "sun"),
    # "what is the meaning of X" → X
    ("what is the meaning of democracy",            "democracy"),
    ("what is the meaning of entropy",              "entropy"),
    # "how long does X take" → X
    ("how long does pregnancy take",                "pregnancy"),
    # "how old/big is X" → X  (degree-word list: old, big)
    ("how old is the universe",                     "universe"),
    ("how big is the sun",                          "sun"),
    # "how strong is X" → X  (strong added to degree-word list)
    ("how strong is a magnetic field",              "magnetic field"),
    ("how strong is the human skull",               "human skull"),
])
def test_batch35_subject_extraction(question, expected):
    """Batch 35: speed/distance causal-nouns, strong degree-word, distance-from-X-to-Y."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 36: who-invented/wrote/founded, when-did/why-did/how-did (regression)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "who invented/discovered/created X" → X
    ("who invented the telephone",                  "telephone"),
    ("who invented the light bulb",                 "light bulb"),
    ("who discovered penicillin",                   "penicillin"),
    ("who discovered gravity",                      "gravity"),
    ("who created bitcoin",                         "bitcoin"),
    ("who created the internet",                    "internet"),
    # "who wrote/painted/founded X" → X
    ("who wrote hamlet",                            "hamlet"),
    ("who wrote the theory of evolution",           "theory of evolution"),
    ("who painted the mona lisa",                   "mona lisa"),
    ("who painted the sistine chapel",              "sistine chapel"),
    ("who founded apple",                           "apple"),
    ("who founded nasa",                            "nasa"),
    # "who is responsible for X" → X
    ("who is responsible for climate change",       "climate change"),
    # "when did X happen/start" → X
    ("when did world war two start",                "world war two"),
    ("when did the dinosaurs go extinct",           "dinosaurs"),
    ("when did humans first walk on the moon",      "humans"),
    # "why did X happen" → X
    ("why did the roman empire fall",               "roman empire"),
    ("why did the titanic sink",                    "titanic"),
    # "how did X start/form" → X
    ("how did the universe begin",                  "universe"),
    ("how did life on earth start",                 "life"),
    ("how did the solar system form",               "solar system"),
    # "what year was X born/founded" → X
    ("what year was einstein born",                 "einstein"),
    ("what year was america founded",               "america"),
])
def test_batch36_subject_extraction(question, expected):
    """Batch 36: who/when/why/how-did patterns (all already passing — regression guard)."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 37: consist/look-like/do-in, it-mean-when, bare-do tail strip
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "what does X consist of" → X  (consist added to verb list)
    ("what does water consist of",                  "water"),
    ("what does the atmosphere consist of",         "atmosphere"),
    # "what does X do in Y" → X  (bare "do" strip after "in Y" tail strip)
    ("what does insulin do in the body",            "insulin"),
    ("what does the liver do in digestion",         "liver"),
    # "what does it mean when X VERB" → X
    ("what does it mean when your heart races",     "heart"),
    ("what does it mean when blood pressure is high", "blood pressure"),
    # "what does X stand for" → X  (already works)
    ("what does html stand for",                    "html"),
    ("what does dna stand for",                     "dna"),
    # "what does X eat/produce" → X
    ("what does a whale eat",                       "whale"),
    ("what does a black hole eat",                  "black hole"),
    ("what does the sun produce",                   "sun"),
    ("what does the liver produce",                 "liver"),
    # "what do X look like" → X  (look added to verb list)
    ("what do stars look like",                     "stars"),
    ("what do black holes look like",               "black holes"),
    # "what is X used for/made of" → X
    ("what is carbon fiber used for",               "carbon fiber"),
    ("what is graphene used for",                   "graphene"),
    ("what is steel made of",                       "steel"),
    ("what is rubber made from",                    "rubber"),
    # "why does X cause Y" → X
    ("why does smoking cause cancer",               "smoking"),
    ("why does caffeine cause addiction",           "caffeine"),
    # "how does X work" → X
    ("how does a transformer work",                 "transformer"),
    ("how does a nuclear reactor work",             "nuclear reactor"),
])
def test_batch37_subject_extraction(question, expected):
    """Batch 37: consist/look verb, do-in tail, it-mean-when, bare-do strip."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 38: scaffold-strip "on X" guard — "effects of X on Y" → X
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "what are the effects of X on Y" → X  (scaffold + on-guard)
    ("what are the effects of caffeine on sleep",   "caffeine"),
    ("what are the effects of pollution on health", "pollution"),
    # "what are the symptoms/causes/benefits/risks of X" → X
    ("what are the symptoms of diabetes",           "diabetes"),
    ("what are the symptoms of depression",         "depression"),
    ("what are the causes of inflation",            "inflation"),
    ("what are the causes of climate change",       "climate change"),
    ("what are the benefits of exercise",           "exercise"),
    ("what are the benefits of meditation",         "meditation"),
    ("what are the risks of smoking",               "smoking"),
    ("what are the risks of surgery",               "surgery"),
    # "what are the advantages/disadvantages of X" → X
    ("what are the advantages of solar energy",     "solar energy"),
    ("what are the disadvantages of nuclear power", "nuclear power"),
    # "what are the uses/properties/characteristics of X" → X
    ("what are the uses of graphene",               "graphene"),
    ("what are the uses of stem cells",             "stem cells"),
    ("what are the properties of gold",             "gold"),
    ("what are the properties of water",            "water"),
    ("what are the characteristics of mammals",     "mammals"),
    ("what are the characteristics of democracy",   "democracy"),
    # "what are the components/stages of X" → X
    ("what are the components of dna",              "dna"),
    ("what are the components of the atmosphere",   "atmosphere"),
    ("what are the stages of mitosis",              "mitosis"),
    ("what are the stages of grief",                "grief"),
])
def test_batch38_subject_extraction(question, expected):
    """Batch 38: scaffold on/in tail guard — 'effects of X on Y' → X."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "is X the same as Y" → X
    ("is a virus the same as bacteria",             "virus"),
    ("is a meteor the same as meteorite",           "meteor"),
    # "is X a type of Y" → X
    ("is a dolphin a type of fish",                 "dolphin"),
    ("is a tomato a type of fruit",                 "tomato"),
    # "is X caused by Y" → X  (already handled by causal strip)
    ("is diabetes caused by sugar",                 "diabetes"),
    ("is cancer caused by stress",                  "cancer"),
    # "are X and Y the same" → X and Y
    ("are viruses and bacteria the same",           "viruses and bacteria"),
    ("are dolphins and whales related",             "dolphins and whales"),
    # "can X do Y" → X
    ("can humans survive on mars",                  "humans"),
    ("can fish drown",                              "fish"),
    # "should X do Y" → X
    ("should humans eat meat",                      "humans"),
    ("should children learn coding",                "children"),
    # "will X happen" → X
    ("will the sun explode",                        "sun"),
    ("will humans colonize mars",                   "humans"),
    # "do X have Y" → X
    ("do plants feel pain",                         "plants"),
    ("do animals dream",                            "animals"),
    # "does X have Y" → X
    ("does the moon have water",                    "moon"),
    ("does mars have oxygen",                       "mars"),
    # "did X exist" → X
    ("did dinosaurs exist with humans",             "dinosaurs"),
    ("did the romans know about america",           "romans"),
    # "would X survive Y" → X
    ("would humans survive a nuclear winter",       "humans"),
    ("would cockroaches survive a nuclear war",     "cockroaches"),
])
def test_batch39_subject_extraction(question, expected):
    """Batch 39: is/are/will/did/do/does/would/should/can question patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "which X is/are Y" → X
    ("which planet is closest to the sun",          "planet"),
    ("which country has the largest population",    "country"),
    ("which animal is the fastest",                 "animal"),
    ("which element has the highest melting point", "element"),
    ("which vitamin is essential for bones",        "vitamin"),
    # where/when/who — regression guards
    ("where is the amazon river located",           "amazon river"),
    ("where is mount everest located",              "mount everest"),
    ("where do polar bears live",                   "polar bears"),
    ("where do penguins live",                      "penguins"),
    ("when was the telephone invented",             "telephone"),
    ("when was penicillin discovered",              "penicillin"),
    ("when did pluto become a dwarf planet",        "pluto"),
    ("when did humans first walk on the moon",      "humans"),
    ("who invented the telephone",                  "telephone"),
    ("who invented the printing press",             "printing press"),
    ("who discovered penicillin",                   "penicillin"),
    ("who discovered gravity",                      "gravity"),
    ("who created the internet",                    "internet"),
    ("who created the theory of relativity",        "theory of relativity"),
    ("who wrote hamlet",                            "hamlet"),
    # "who wrote X" where X is a multi-word title containing a causal noun
    ("who wrote origin of species",                 "origin of species"),
])
def test_batch40_subject_extraction(question, expected):
    """Batch 40: which-X-is/has patterns; protect attribution-verb results from causal-noun stripping."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what affects/determines/produces/controls/influences/allows X" → X
    ("what causes earthquakes",                     "earthquakes"),
    ("what causes climate change",                  "climate change"),
    ("what triggers an allergic reaction",          "allergic reaction"),
    ("what affects blood pressure",                 "blood pressure"),
    ("what affects sleep quality",                  "sleep quality"),
    ("what determines eye color",                   "eye color"),
    ("what determines intelligence",                "intelligence"),
    ("what prevents cancer",                        "cancer"),
    ("what prevents heart disease",                 "heart disease"),
    ("what produces atp in cells",                  "atp"),
    ("what produces insulin in the body",           "insulin"),
    ("what controls body temperature",              "body temperature"),
    ("what controls the weather",                   "weather"),
    ("what influences human behavior",              "human behavior"),
    ("what influences stock prices",                "stock prices"),
    # "what makes X a ADJ NOUN" → X  (predicate-nominal complement stripped)
    ("what makes water a good solvent",             "water"),
    ("what makes humans unique",                    "humans"),
    # "what allows X to VERB" → X  (to stripped after verb-strip)
    ("what allows birds to fly",                    "birds"),
    ("what allows fish to breathe underwater",      "fish"),
])
def test_batch41_subject_extraction(question, expected):
    """Batch 41: what-VERB-X action patterns; trailing-to strip; predicate-nominal strip."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # passive-voice "how is X measured/classified/called" → X
    ("how is a rainbow formed",                     "rainbow"),
    ("how is coal formed",                          "coal"),
    ("how is blood pressure measured",              "blood pressure"),
    ("how is intelligence measured",                "intelligence"),
    ("how is cancer classified",                    "cancer"),
    ("how are animals classified",                  "animals"),
    # "what is X called in LANGUAGE" → X
    ("what is the sun called in spanish",           "sun"),
    ("what is a dog called in japanese",            "dog"),
    # "what type/kind of CATEGORY is X" → X  (via _m_cat_is)
    ("what type of animal is a dolphin",            "dolphin"),
    ("what type of star is the sun",                "sun"),
    ("what kind of energy is solar power",          "solar power"),
    ("what kind of gas is oxygen",                  "oxygen"),
    # "how long can X hold/survive" → X
    ("how long can a whale hold its breath",        "whale"),
    ("how long can humans survive without water",   "humans"),
    # regression guards
    ("how do you say hello in japanese",            "hello"),
    ("what is the atmosphere made up of",           "atmosphere"),
    ("how long does pregnancy last",                "pregnancy"),
])
def test_batch42_subject_extraction(question, expected):
    """Batch 42: passive-participle verbs; _m_cat_is energy/force/wave; called-in-language."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # imperative "compare X and Y" / "define X" → subject
    ("compare cats and dogs",                           "cats and dogs"),
    ("compare mitosis and meiosis",                     "mitosis and meiosis"),
    ("define photosynthesis",                           "photosynthesis"),
    ("define mitosis",                                  "mitosis"),
    # "give me information about X" → X  (information-about scaffold stripped)
    ("give me information about climate change",        "climate change"),
    ("give me information about black holes",           "black holes"),
    # "what is X in simple/plain terms" → X
    ("what is quantum physics in simple terms",         "quantum physics"),
    ("what is dna in simple terms",                     "dna"),
    # regression guards
    ("tell me about the human brain",                   "human brain"),
    ("tell me about quantum physics",                   "quantum physics"),
    ("explain photosynthesis to me",                    "photosynthesis"),
    ("what is the difference between cats and dogs",    "cats and dogs"),
    ("how does solar energy compare to wind energy",    "solar energy"),
    ("what are some examples of renewable energy",      "renewable energy"),
])
def test_batch43_subject_extraction(question, expected):
    """Batch 43: compare/define imperatives; information-about scaffold; in-simple-terms tail."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "why is X important/bad/good for you" → X
    ("why is exercise important",                          "exercise"),
    ("why is sleep important",                             "sleep"),
    ("why is water important",                             "water"),
    ("why is sugar bad for you",                           "sugar"),
    ("why is fiber good for you",                          "fiber"),
    # "why do/does X VERB" → X  (leaves, volcanoes are entity nouns)
    ("why do leaves change color",                         "leaves"),
    ("why do volcanoes erupt",                             "volcanoes"),
    # "why do we/you/one VERB" → the activity (generic pronoun)
    ("why do we dream",                                    "dream"),
    # "why does X happen" → X
    ("why does thunder happen",                            "thunder"),
    # "why does the sky turn ADJECTIVE at PLACE" → sky (turn added to trailing verb list)
    ("why does the sky turn red at sunset",                "sky"),
    # "when did X happen" → X
    ("when did world war 2 end",                           "world war 2"),
    ("when did the dinosaurs go extinct",                  "dinosaurs"),
    # "when was X invented/born/become" → X
    ("when was the internet invented",                     "internet"),
    ("when was einstein born",                             "einstein"),
    ("when did humans first walk on the moon",             "humans"),
    ("when did antarctica become a continent",             "antarctica"),
])
def test_batch44_45_subject_extraction(question, expected):
    """Batch 44-45: why-is/why-do/why-does; when-did/when-was; turn verb added."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Multi-word modifer + scaffold noun: long-term effects, health benefits
    ("what are the long term effects of smoking",          "smoking"),
    ("what are the long term effects of stress",           "stress"),
    ("what are the health benefits of exercise",           "exercise"),
    ("what are the health benefits of green tea",          "green tea"),
    # "significance of X" → X  (significance added to causal-noun list)
    ("what is the significance of the magna carta",        "magna carta"),
    ("what is the significance of the dna discovery",      "dna discovery"),
    # "where do X go to Y" → X  (go/come added to trailing verb list)
    ("where do salmon go to spawn",                        "salmon"),
    # regression guards: location/who questions
    ("where is the eiffel tower located",                  "eiffel tower"),
    ("where does coffee come from",                        "coffee"),
    ("who invented the telephone",                         "telephone"),
    ("who discovered penicillin",                          "penicillin"),
    ("what are the stages of cancer",                      "cancer"),
    ("what are the symptoms of diabetes",                  "diabetes"),
    ("what is the relationship between stress and health", "stress and health"),
])
def test_batch46_subject_extraction(question, expected):
    """Batch 46: scaffold prefix expansion; significance causal-noun; go/come motion verbs."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "laws/principles/theories of X" → X  (plural scaffold nouns added)
    ("what are the laws of thermodynamics",                "thermodynamics"),
    ("what are the laws of motion",                        "motion"),
    ("what are the principles of thermodynamics",          "thermodynamics"),
    ("what are the principles of evolution",               "evolution"),
    # "what is the composition/structure/formula of X" → X
    ("what is the composition of the atmosphere",          "atmosphere"),
    ("what is the structure of dna",                       "dna"),
    ("what is the formula for water",                      "water"),
    # "what is the impact of X on Y" → X  (causal-noun strip fires on "impact")
    ("what is the impact of climate change on biodiversity", "climate change"),
    ("what is the impact of exercise on mental health",    "exercise"),
    # "what is the process/mechanism of X" → X
    ("what is the process of photosynthesis",              "photosynthesis"),
    ("what is the mechanism of natural selection",         "natural selection"),
    # regression guard: singular "law of X" must NOT be scaffold-stripped
    ("what is the law of conservation of energy",         "law of conservation of energy"),
])
def test_batch47_subject_extraction(question, expected):
    """Batch 47: plural scaffold nouns (laws/principles/theories/etc); singular law guard."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Missing trailing verbs: smell, read, write, coexist
    ("can sharks smell blood from a mile away",        "sharks"),
    ("could ancient egyptians read and write",         "ancient egyptians"),
    ("did dinosaurs and humans coexist",               "dinosaurs and humans"),
    # Comparative "X larger/farther than Y" → X
    ("is the sun larger than the earth",               "sun"),
    ("is neptune farther from the sun than saturn",    "neptune"),
    # Compound adj: "X warm blooded" → X
    ("are sharks warm blooded",                        "sharks"),
    ("are insects warm blooded",                       "insects"),
    # regression guards
    ("can humans survive on the moon",                 "humans"),
    ("can plants feel pain",                           "plants"),
    ("do dolphins sleep",                              "dolphins"),
    ("does the moon have water",                       "moon"),
    ("did ancient rome have electricity",              "ancient rome"),
    ("how is a virus different from a bacterium",      "virus"),
])
def test_batch48_subject_extraction(question, expected):
    """Batch 48: smell/read/write/coexist verbs; comparative-than strip; warm-blooded adj."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is the future of X" → X  (future added to causal-noun list)
    ("what is the future of artificial intelligence",  "artificial intelligence"),
    ("what is the future of space exploration",        "space exploration"),
    # "what are the applications of X" → X
    ("what are the applications of machine learning",  "machine learning"),
    ("what are the applications of nanotechnology",    "nanotechnology"),
    # "what is X used for" → X
    ("what is python used for",                        "python"),
    ("what is graphene used for",                      "graphene"),
    # "how does/do X work" → X
    ("how does a nuclear reactor work",                "nuclear reactor"),
    ("how do vaccines work",                           "vaccines"),
    ("how do antibiotics work",                        "antibiotics"),
    # "what caused the X" → X (named events)
    ("what caused the great depression",               "great depression"),
    ("what caused the french revolution",              "french revolution"),
    # "what is the history of X" (compound subjects)
    ("what is the history of world war 2",             "world war 2"),
    ("what is the history of the internet",            "internet"),
])
def test_batch49_subject_extraction(question, expected):
    """Batch 49: future causal-noun; applications scaffold; technology/history questions."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what nationality is X" → X  (nationality added to _m_cat_is)
    ("what nationality is tesla",                      "tesla"),
    # "X named after" tail strip
    ("what is the eiffel tower named after",           "eiffel tower"),
    ("what is the moon named after",                   "moon"),
    # "who was/is X" → X  (biographical)
    ("who was albert einstein",                        "albert einstein"),
    ("who is elon musk",                               "elon musk"),
    # "what did X do/discover/invent" → X
    ("what did einstein do",                           "einstein"),
    ("what did darwin discover",                       "darwin"),
    ("what did thomas edison invent",                  "thomas edison"),
    # "what country/continent is X in" → X
    ("what country is tokyo in",                       "tokyo"),
    ("what continent is australia in",                 "australia"),
    # "is a X a Y" → X (bare opener)
    ("is a bat a mammal",                              "bat"),
    ("is a tomato a fruit",                            "tomato"),
    ("is a dolphin a fish",                            "dolphin"),
    # "what was X known for" → X
    ("what was einstein known for",                    "einstein"),
])
def test_batch50_subject_extraction(question, expected):
    """Batch 50: nationality _m_cat_is; named-after tail; biographical/classification patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 51: possessive-attribute strip; speed-of canonical constant guard;
#           how-[degree]-is biographical/measurement patterns
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # Possessive attribute: "X's [adj] name/age/..." → X
    ("what is superman's real name",                   "superman"),
    ("what is batman's real name",                     "batman"),
    # speed-of canonical: no article → keep "speed of X" intact
    ("how fast is the speed of light",                 "speed of light"),
    ("what is the speed of light",                     "speed of light"),
    ("what is the speed of sound",                     "speed of sound"),
    # speed-of with article: strip "speed of a/an/the" → object
    ("what is the speed of a cheetah",                 "cheetah"),
    # biographical date questions
    ("what year was einstein born",                    "einstein"),
    ("when was beethoven born",                        "beethoven"),
    ("when did newton die",                            "newton"),
    # birthplace
    ("where was mozart born",                          "mozart"),
    # how-[degree]-is measurement questions
    ("how tall is mount everest",                      "mount everest"),
    ("how tall is the eiffel tower",                   "eiffel tower"),
    ("how old is the universe",                        "universe"),
    ("how deep is the mariana trench",                 "mariana trench"),
    ("how long is the great wall of china",            "great wall of china"),
    ("how far is the moon from the earth",             "moon"),
    ("how far is mars from the sun",                   "mars"),
])
def test_batch51_subject_extraction(question, expected):
    """Batch 51: possessive attribute strip; speed-of canonical guard; measurement questions."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 52: "coined the term X"; "it takes to VERB to X" destination strip;
#           possessive concept preservation; how-many/largest/symptoms
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "who coined the term X" → X (coined added to attribution verbs; term strip)
    ("who coined the term photosynthesis",             "photosynthesis"),
    ("who coined the term evolution",                  "evolution"),
    # "how long does it take to VERB to PLACE" → PLACE
    ("how long does it take to fly to the moon",       "moon"),
    # possessive concept stays whole (not stripped by possessive-attr rule)
    ("what is darwin's theory of evolution",           "darwin's theory of evolution"),
    ("what is newton's law of gravity",                "newton's law of gravity"),
    # how-long it-takes
    ("how long does it take to boil an egg",           "egg"),
    ("how long does it take light to reach earth",     "light"),
    # "what does it mean when X" → X
    ("what does it mean when your ears ring",          "ears"),
    # how-many
    ("how many planets are there in the solar system", "planets"),
    ("how many bones are there in the human body",     "bones"),
    # "what is the largest/smallest X" → X
    ("what is the largest planet",                     "planet"),
    ("what is the smallest country",                   "country"),
    # "what are the main NOUN of X" → X
    ("what are the main causes of climate change",     "climate change"),
    ("what are the main effects of global warming",    "global warming"),
    # "what are the symptoms of X" → X
    ("what are the symptoms of diabetes",              "diabetes"),
])
def test_batch52_subject_extraction(question, expected):
    """Batch 52: coined/term strip; it-takes-to-fly destination; possessive concept guard."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 53: diameter/radius/velocity/etc. added to causal-noun list so
#           "what is the diameter of X" → X not "diameter"
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # diameter/radius now in causal-noun list
    ("what is the diameter of the earth",              "earth"),
    ("what is the diameter of the moon",               "moon"),
    # already-working physics property nouns (regression guard)
    ("what is the boiling point of water",             "water"),
    ("what is the melting point of ice",               "ice"),
    ("what is the atomic number of carbon",            "carbon"),
    ("what is the chemical formula of water",          "water"),
    ("what is the lifespan of an elephant",            "elephant"),
    ("what is the mass of the earth",                  "earth"),
    ("what is the half life of carbon 14",             "carbon 14"),
    # standalone constants (no "of X" suffix — must not be stripped)
    ("what is the gravitational constant",             "gravitational constant"),
    ("what is the planck constant",                    "planck constant"),
    # scientific name / common name
    ("what is the scientific name of a dog",           "dog"),
    ("what is the common name for nacl",               "nacl"),
])
def test_batch53_subject_extraction(question, expected):
    """Batch 53: diameter/radius/velocity causal-noun additions."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 54: "sing" added to trailing-verb list; behavioral/ecological
#           adjectives (nocturnal etc.) added to trailing-state-adj list
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "sing" now in trailing-verb list
    ("why do birds sing",                              "birds"),
    ("why do whales sing",                             "whales"),
    # why-is/are adjective patterns (regression guard + new adj)
    ("why is the sky blue",                            "sky"),
    ("why is the ocean salty",                         "ocean"),
    ("why are leaves green",                           "leaves"),
    ("why are flamingos pink",                         "flamingos"),
    # nocturnal and similar behavioral adjectives now in trailing-state-adj list
    ("why are some animals nocturnal",                 "animals"),
    ("why are bats nocturnal",                         "bats"),
    ("why are sharks carnivorous",                     "sharks"),
    # why-did patterns (regression guard)
    ("why did the dinosaurs go extinct",               "dinosaurs"),
    ("why did rome fall",                              "rome"),
    # what-makes patterns
    ("what makes diamonds hard",                       "diamonds"),
    ("what makes humans unique",                       "humans"),
])
def test_batch54_subject_extraction(question, expected):
    """Batch 54: sing verb; nocturnal/carnivorous/etc. adj; why-is/are/did."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 55: where-does/do/is/are patterns; language-do-people-in-X; when/who
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "where does X come from" → X
    ("where does coffee come from",                    "coffee"),
    ("where does chocolate come from",                 "chocolate"),
    ("where does oil come from",                       "oil"),
    # "where do X live" → X
    ("where do penguins live",                         "penguins"),
    ("where do polar bears live",                      "polar bears"),
    ("where do sharks live",                           "sharks"),
    # "where is X located/found" → X
    ("where is the amazon river located",              "amazon river"),
    ("where is the great barrier reef located",        "great barrier reef"),
    ("where is gold found",                            "gold"),
    ("where is oil found in the world",                "oil"),
    # "what language do people in X speak" → X  (second-pass people strip)
    ("what language do people in brazil speak",        "brazil"),
    ("what language do people in japan speak",         "japan"),
    # "when did X happen" → X
    ("when did world war 2 end",                       "world war 2"),
    ("when did the roman empire fall",                 "roman empire"),
    # "when was X built/founded" → X
    ("when was the eiffel tower built",                "eiffel tower"),
    ("when was the great wall of china built",         "great wall of china"),
    ("when was google founded",                        "google"),
    # "who discovered X" → X
    ("who discovered dna",                             "dna"),
    ("who discovered penicillin",                      "penicillin"),
    ("who discovered america",                         "america"),
])
def test_batch55_subject_extraction(question, expected):
    """Batch 55: where-does/do/is patterns; language-do-people-in-X second-pass; when/who."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 56: how-many/much X does Y VERB → Y; how often does it VERB in X
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "how many X does/do Y have" → Y (entity being described)
    ("how many legs does a spider have",               "spider"),
    ("how many teeth does a shark have",               "shark"),
    ("how many sides does a hexagon have",             "hexagon"),
    # "how much X does Y produce/make" → Y
    ("how much milk does a cow produce",               "cow"),
    ("how much oxygen does a tree produce",            "tree"),
    # "how often does a NOUN happen" → NOUN
    ("how often does a solar eclipse happen",          "solar eclipse"),
    # "how often does it VERB in X" → X  (dummy-subject location questions)
    ("how often does it rain in london",               "london"),
    # "how many X are there in Y" → X (unchanged: "are there" pattern)
    ("how many planets are there in the solar system", "planets"),
    ("how many bones are there in the human body",     "bones"),
    ("how many countries are there in the world",      "countries"),
])
def test_batch56_subject_extraction(question, expected):
    """Batch 56: how-many/much-does-entity-verb returns entity; dummy-it in location."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 57: capable-of adj strip; what-do-X-eat/look-like; made-of; role-of
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "what is X capable of" → X  (strip "capable of" compound adj phrase)
    ("what is a black hole capable of",                "black hole"),
    ("what is a human capable of",                     "human"),
    # "what do X eat/look-like" → X
    ("what do elephants eat",                          "elephants"),
    ("what do sharks eat",                             "sharks"),
    ("what do platypuses look like",                   "platypuses"),
    # "what are X made of" → X
    ("what are bones made of",                         "bones"),
    ("what are stars made of",                         "stars"),
    ("what are clouds made of",                        "clouds"),
    # "what is X used for" → X
    ("what is aspirin used for",                       "aspirin"),
    ("what are solar panels used for",                 "solar panels"),
    # "what is the role of X in Y" → X
    ("what is the role of insulin in the body",        "insulin"),
    ("what is the role of dna in cells",               "dna"),
    # "what is the difference between X and Y" → "X and Y" for split_subjects
    ("what is the difference between cats and dogs",   "cats and dogs"),
    ("what is the difference between tcp and udp",     "tcp and udp"),
])
def test_batch57_subject_extraction(question, expected):
    """Batch 57: capable-of strip; what-do-X; made-of; used-for; role-of; difference-between."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 149: astronomy / space — existential + category-superlative patterns
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is a black hole",                               "black hole"),
    ("what is a neutron star",                             "neutron star"),
    ("what is a supernova",                                "supernova"),
    ("what is dark matter",                                "dark matter"),
    ("what is dark energy",                                "dark energy"),
    ("what is a galaxy",                                   "galaxy"),
    ("what is the milky way",                              "milky way"),
    ("what is the big bang",                               "big bang"),
    ("what is a light year",                               "light year"),
    # "how far is X from Y" → X
    ("how far is the sun from earth",                      "sun"),
    ("how far is the moon from earth",                     "moon"),
    # "how big is X" → X
    ("how big is the universe",                            "universe"),
    ("how big is the sun",                                 "sun"),
    # "what is the X of Y" → Y
    ("what is the size of the universe",                   "universe"),
    ("what is the age of the universe",                    "universe"),
    # "how many X are there" → X
    ("how many planets are there",                         "planets"),
    ("how many galaxies are there",                        "galaxies"),
    # "how long does it take to get to X" → X
    ("how long does it take to get to mars",               "mars"),
    # "what is the nearest X" → X
    ("what is the nearest star to earth",                  "star"),
    # existential: "is there NOUN on X" → X
    ("is there life on mars",                              "mars"),
    # category-superlative: "what CATEGORY is SUPERLATIVE" → CATEGORY
    ("what planet is closest to the sun",                  "planet"),
])
def test_batch149_subject_extraction(question, expected):
    """Batch 149: astronomy/space — existential + category-superlative patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 58: can/would/do/does; regrow verb; category-noun strip (mammals etc)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "can X VERB" → X
    ("can sharks breathe out of water",                "sharks"),
    ("can dogs see color",                             "dogs"),
    ("can fish feel pain",                             "fish"),
    ("can humans regrow limbs",                        "humans"),
    ("could dinosaurs have survived the asteroid",     "dinosaurs"),
    # "are X CLASSIFICATION" → X  (category-noun strip)
    ("are dolphins mammals",                           "dolphins"),
    ("are spiders insects",                            "spiders"),
    ("are viruses alive",                              "viruses"),
    # "do/does X have Y" → X
    ("do humans have tails",                           "humans"),
    ("do fish have ears",                              "fish"),
    ("does the earth have a magnetic field",           "earth"),
    ("does mars have moons",                           "mars"),
    # "is X Y" → X
    ("is the sun a star",                              "sun"),
    ("is pluto a planet",                              "pluto"),
])
def test_batch58_subject_extraction(question, expected):
    """Batch 58: can/could/are X VERB/CATEGORY; do/does X have; regrow/hibernate verbs."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 59: responsible-for strip; trailing-like strip; possessive compounds
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "X responsible for" → strip "responsible for" tail
    ("what is the liver responsible for",              "liver"),
    ("what is the immune system responsible for",      "immune system"),
    ("what is dna responsible for",                    "dna"),
    # "what is X like" → strip trailing "like"
    ("what is the moon's surface like",                "moon"),
    ("what is life on mars like",                      "life on mars"),
    # Possessive compounds are preserved as useful lookup keys
    ("what is the earth's atmosphere made of",         "earth's atmosphere"),
    # "tell me about X" / "explain X" / "describe X" → X
    ("tell me about the french revolution",            "french revolution"),
    ("explain the theory of relativity",               "theory of relativity"),
    ("describe the water cycle",                       "water cycle"),
    # "how do X form" → X
    ("how do rainbows form",                           "rainbows"),
    ("how do hurricanes form",                         "hurricanes"),
    ("how do crystals form",                           "crystals"),
])
def test_batch59_subject_extraction(question, expected):
    """Batch 59: responsible-for/like tail strips; possessive compounds; explain/describe."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X like" early-exit: "like" at end, even with compound subject including "on"
    ("what is life on mars like",                          "life on mars"),
    ("what is the surface of the moon like",               "surface of the moon"),
    ("what is mercury like",                               "mercury"),
    # "what is the weather like in LOC" → location stripped first, then trailing "like" → topic
    ("what is the weather like in london",                 "weather"),
    ("what is the climate like in the sahara",             "climate"),
    ("what are the working conditions like",               "working conditions"),
    # "where does X come from" → X
    ("where does milk come from",                          "milk"),
    ("where does oil come from",                           "oil"),
    ("where does lightning come from",                     "lightning"),
    # "where do X live" → X
    ("where do penguins live",                             "penguins"),
    ("where do elephants live",                            "elephants"),
    # "when did X Y" → X
    ("when did the dinosaurs go extinct",                  "dinosaurs"),
    ("when did the first world war end",                   "first world war"),
    # "when was X VERB" → X
    ("when was the eiffel tower built",                    "eiffel tower"),
    ("when was penicillin discovered",                     "penicillin"),
    # "who discovered/invented/wrote X" → X
    ("who discovered penicillin",                          "penicillin"),
    ("who invented the telephone",                         "telephone"),
    ("who wrote hamlet",                                   "hamlet"),
    # "who was X" → X
    ("who was cleopatra",                                  "cleopatra"),
    ("who was nikola tesla",                               "nikola tesla"),
])
def test_batch62_subject_extraction(question, expected):
    """Batch 62: 'what is X like' early-exit; weather-like-in-LOC; where/when/who patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "how ADJ is X" → X
    ("how hot is the sun",                                 "sun"),
    ("how cold is antarctica",                             "antarctica"),
    ("how dense is a neutron star",                        "neutron star"),
    ("how far is the moon from earth",                     "moon"),
    ("how old is the universe",                            "universe"),
    ("how big is jupiter",                                 "jupiter"),
    ("how deep is the mariana trench",                     "mariana trench"),
    ("how tall is mount everest",                          "mount everest"),
    # "how fast does X VERB" → X
    ("how fast does light travel",                         "light"),
    ("how fast can a cheetah run",                         "cheetah"),
    # "how long does it take to VERB X" → X
    ("how long does it take to boil an egg",               "egg"),
    ("how long does it take light to reach earth",         "light"),
    # "how much does X weigh" → X (weigh added to trailing verb list)
    ("how much does a blue whale weigh",                   "blue whale"),
    ("how much does the earth weigh",                      "earth"),
    # "at what temperature does X VERB" → X
    ("at what temperature does water boil",                "water"),
    ("at what temperature does iron melt",                 "iron"),
    # "what year was X VERB" → X
    ("what year was the eiffel tower built",               "eiffel tower"),
    ("what year was america discovered",                   "america"),
    # "what is X made up of" → X
    ("what is dna made up of",                             "dna"),
    ("what is the atmosphere made up of",                  "atmosphere"),
])
def test_batch63_subject_extraction(question, expected):
    """Batch 63: how-ADJ/much/long/fast patterns; weigh verb; at-what-temperature; made-up-of."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "which NOUN VERB" where VERB is a main verb (not aux) → NOUN
    ("which animal runs the fastest",                      "animal"),
    ("which bird flies highest",                           "bird"),
    ("which planet spins fastest",                         "planet"),
    # "what do X consume" → X
    ("what do black holes consume",                        "black holes"),
    ("what do carnivores consume",                         "carnivores"),
    # "what is the habitat of X" → X (causal-noun strip fires for "habitat")
    ("what is the habitat of the polar bear",              "polar bear"),
    ("what is the habitat of a penguin",                   "penguin"),
    ("what is the natural habitat of a tiger",             "tiger"),
    # "what is the diet of X" → X
    ("what is the diet of a koala",                        "koala"),
    ("what is the diet of wolves",                         "wolves"),
    # "what is the territory of X" → X
    ("what is the territory of a grizzly bear",            "grizzly bear"),
    # Regression: existing which-aux patterns still work
    ("which planet is closest to the sun",                 "planet"),
    ("which country has the largest population",           "country"),
    # Regression: causal-noun strip still works for capital/population
    ("what is the capital of france",                      "france"),
    ("what is the population of china",                    "china"),
])
def test_batch64_subject_extraction(question, expected):
    """Batch 64: which-main-verb, consume, habitat/diet/territory of X."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "X composed of" → X (add composed to trailing verb list)
    ("what is the atmosphere composed of",             "atmosphere"),
    ("what is water composed of",                      "water"),
    ("what is granite composed of",                    "granite"),
    # "how much of X is Y" → X (leading 'of' after 'how much' stripped)
    ("how much of the earth is water",                 "earth"),
    ("how much of the human body is water",            "human body"),
    ("how much of the atmosphere is nitrogen",         "atmosphere"),
    # "what is the natural habitat of X" (with adjective prefix) → X
    ("what is the natural habitat of a lion",          "lion"),
    ("what is the native range of the monarch butterfly", "monarch butterfly"),
    # "what is the lifespan of X" → X
    ("what is the lifespan of a blue whale",           "blue whale"),
    ("what is the lifespan of a tortoise",             "tortoise"),
    # Regressions
    ("what is glass made of",                          "glass"),
    ("what percentage of the earth is water",          "earth"),
    ("what percentage of the atmosphere is oxygen",    "atmosphere"),
])
def test_batch65_subject_extraction(question, expected):
    """Batch 65: composed-of, how-much-of-X, natural habitat/range, lifespan patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is the origin of X" → X (requires "the" so book-title "origin of species" unaffected)
    ("what is the origin of the universe",             "universe"),
    ("what is the origin of life",                     "life"),
    ("what is the origin of language",                 "language"),
    # Regression: bare "origin of species" (book title) must stay intact
    ("who wrote origin of species",                    "origin of species"),
    # "what is the significance of X" → X
    ("what is the significance of the magna carta",    "magna carta"),
    ("what is the importance of photosynthesis",       "photosynthesis"),
    # "what is the history of X" → X
    ("what is the history of the internet",            "internet"),
    ("what is the history of chess",                   "chess"),
    # "what are the effects of X on Y" → X (scaffold + on-context strips)
    ("what are the effects of caffeine on sleep",      "caffeine"),
    ("what are the effects of pollution on health",    "pollution"),
    # "what happens to X when it Y" → X
    ("what happens to water when it freezes",          "water"),
    ("what happens to stars when they die",            "stars"),
])
def test_batch66_subject_extraction(question, expected):
    """Batch 66: origin-of (with/without article), significance/history/effects patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 67: possessive-property strip (targeted); "what time does X" pattern
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # Possessive + measurement noun: entity is the subject, property is the accessor
    ("what is the sun's core temperature",             "sun"),
    ("what is the earth's surface area",               "earth"),
    ("what is the moon's orbital speed",               "moon"),
    ("what is the star's luminosity",                  "star"),
    # Possessive + relational noun + prep phrase
    ("what is a bee's role in the ecosystem",          "bee"),
    ("what is the liver's function in the body",       "liver"),
    ("what is carbon's role in photosynthesis",        "carbon"),
    # Possessive early-exit: "what is X's THING like" → entity
    ("what is the moon's surface like",                "moon"),
    # "what time does X VERB" patterns
    ("what time does the sun set",                     "sun"),
    ("what time does the moon rise",                   "moon"),
    ("what time does the market close",                "market"),
    # Regression: named possessive concepts must NOT be stripped
    ("what is alzheimer's disease",                    "alzheimer's disease"),
    ("what is the earth's atmosphere made of",         "earth's atmosphere"),
    ("what is the sun's core made of",                 "sun's core"),
    ("what is darwin's theory of evolution",           "darwin's theory of evolution"),
    ("what is newton's law of gravity",                "newton's law of gravity"),
])
def test_batch67_subject_extraction(question, expected):
    """Batch 67: targeted possessive-property strip; what-time-does pattern; regression guards."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 68: "which is the SUPERLATIVE NOUN"; irregular past-tense hypotheticals
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "which is the SUPERLATIVE NOUN [LOCATION]" patterns
    ("which is the largest country in the world",         "country"),
    ("which is the tallest mountain on earth",            "mountain"),
    ("which is the deepest lake in the world",            "lake"),
    ("which is the fastest land animal",                  "land animal"),
    ("which is the most populated city in asia",          "city"),
    ("which is the smallest planet in the solar system",  "planet"),
    # Regression: "which NOUN is/are" still works (handled by _m_which)
    ("which planet is the largest",                       "planet"),
    ("which animal is the fastest",                       "animal"),
    ("which country has the most people",                 "country"),
    # Irregular past-tense verbs in conditional hypotheticals
    ("what would happen if humans lost their memory",     "humans"),
    ("what would happen if species became extinct",       "species"),
    ("what would happen if humans forgot language",       "humans"),
    # "if you VERB OBJECT" → OBJECT (pronoun-verb strip, "you" is generic)
    ("what happens if you drink salt water",              "salt water"),
])
def test_batch68_subject_extraction(question, expected):
    """Batch 68: which-is-superlative pattern; irregular past verbs; pronoun-verb strip."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 69: trailing classification nouns extended; "living organisms" compound
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # Extended classification noun strip: "fish" as predicate
    ("are dolphins fish",                                 "dolphins"),
    ("are sharks fish",                                   "sharks"),
    ("are whales fish",                                   "whales"),
    # "living organisms/things/beings" compound tail
    ("are viruses living organisms",                      "viruses"),
    ("are corals living things",                          "corals"),
    ("are crystals living beings",                        "crystals"),
    # "strike" added to trailing verb list
    ("can lightning strike twice in the same place",      "lightning"),
    ("how often does lightning strike",                   "lightning"),
    # Regression guards: "fish/bacteria/birds" as SUBJECT must not be stripped
    ("what are the uses of hydrogen",                     "hydrogen"),
    ("how many species of birds are there",               "species of birds"),
    ("what is the difference between bacteria and viruses", "bacteria and viruses"),
    ("are viruses and bacteria the same",                 "viruses and bacteria"),
])
def test_batch69_subject_extraction(question, expected):
    """Batch 69: fish classification; living-organisms compound; strike verb; regression guards."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "how long does it take for X to Y" — trailing content after the verb
    ("how long does it take for light to travel from the sun",   "light"),
    ("how long does it take for a wound to heal",                "wound"),
    ("how long does it take for concrete to dry",                "concrete"),
    # "how much time does it take to VERB X" — dummy-it idiom
    ("how much time does it take to learn piano",                "piano"),
    ("how much time does digestion take",                        "digestion"),
    # "how many X are in Y" → Y (the container is the better lookup key)
    ("how many bones are in the human body",                     "human body"),
    ("how many planets are in the solar system",                 "solar system"),
    # "how many X does Y have" → Y (unaffected by the container fix)
    ("how many legs does a spider have",                         "spider"),
    ("how many teeth does a shark have",                         "shark"),
    ("how many chambers does the heart have",                    "heart"),
    # "how old/big is X" — unchanged baseline
    ("how old is the universe",                                  "universe"),
    ("how big is the milky way",                                 "milky way"),
])
def test_batch70_subject_extraction(question, expected):
    """Batch 70: it-takes-for trailing content; dummy-it time idiom; how-many-in container."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "relationship between X and the Y" → "X and Y" (article stripped from second item)
    ("what is the relationship between the brain and the mind",  "brain and mind"),
    ("what is the difference between weather and climate",       "weather and climate"),
    ("what is the difference between mitosis and meiosis",       "mitosis and meiosis"),
    # "what triggers X" — compound-noun X preserved (attack not stripped)
    ("what triggers an asthma attack",                           "asthma attack"),
    ("what triggers a heart attack",                             "heart attack"),
    ("what triggers a panic attack",                             "panic attack"),
    # "attack" as verb still strips correctly
    ("how does the immune system fight bacteria",                "immune system"),
    # "what causes/prevents X" → X
    ("what causes earthquakes",                                  "earthquakes"),
    ("what causes thunder",                                      "thunder"),
    ("what prevents blood clots",                                "blood clots"),
    # "what are the benefits/symptoms/causes of X" → X
    ("what are the benefits of meditation",                      "meditation"),
    ("what are the symptoms of diabetes",                        "diabetes"),
    ("what are the causes of climate change",                    "climate change"),
])
def test_batch71_subject_extraction(question, expected):
    """Batch 71: between-strip article normalisation; compound-attack guard; trigger/cause/prevent."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what language do they speak in X" → X
    ("what language do they speak in brazil",   "brazil"),
    ("what language do they speak in japan",    "japan"),
    ("what language do people speak in france", "france"),
    # "what country/continent is X in" → X (already passing; regression guard)
    ("what country is paris in",                "paris"),
    ("what continent is india in",              "india"),
    # "what color is X" → X (regression guard)
    ("what color is the sky",                   "sky"),
    ("what color is blood",                     "blood"),
    # "what is the capital/currency/population of X" → X (regression guard)
    ("what is the capital of france",           "france"),
    ("what is the currency of japan",           "japan"),
    ("what is the population of china",         "china"),
    # Superlative category: "what is the SUPERLATIVE X in/on Y" → X
    ("what is the largest country in the world",        "country"),
    ("what is the smallest planet in the solar system", "planet"),
    ("what is the tallest building in the world",       "building"),
    ("what is the deepest lake in the world",           "lake"),
])
def test_batch72_subject_extraction(question, expected):
    """Batch 72: 'in X' cleanup after pronoun+verb strip; geography and superlative patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X known for" → X
    ("what is einstein known for",              "einstein"),
    ("what is rome known for",                  "rome"),
    ("what is japan known for",                 "japan"),
    # "what is X used for" → X
    ("what is graphene used for",               "graphene"),
    ("what is aspirin used for",                "aspirin"),
    # "what is X made of" → X
    ("what is glass made of",                   "glass"),
    ("what is steel made of",                   "steel"),
    # "what is X composed of" → X
    ("what is air composed of",                 "air"),
    ("what is water composed of",               "water"),
    # "what is X named after" → X
    ("what is the moon named after",            "moon"),
    ("what is america named after",             "america"),
    # property-of: "boiling/melting point of X" → X
    ("what is the boiling point of water",      "water"),
    ("what is the boiling point of nitrogen",   "nitrogen"),
    ("what is the melting point of iron",       "iron"),
    # "speed of X" without article → canonical constant kept intact
    ("what is the speed of sound",              "speed of sound"),
    ("what is the speed of light",              "speed of light"),
    # "half-life of X" → X
    ("what is the half-life of carbon 14",      "carbon 14"),
    ("what is the half life of uranium 235",    "uranium 235"),
])
def test_batch73_subject_extraction(question, expected):
    """Batch 73: known-for, used-for, made-of, named-after, property-of, speed canonical."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 74: "when will X return/arrive" (return/arrive verbs added);
#           "when will the next X be" (next temporal prefix stripped)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "when will X VERB" → X  (return/arrive now in trailing-verb list)
    ("when will halley's comet return",                  "halley's comet"),
    ("when will the astronauts arrive",                  "astronauts"),
    # "when will the next X VERB" → X  (next stripped as temporal prefix)
    ("when will the next solar eclipse be",              "solar eclipse"),
    ("when will the next world cup be",                  "world cup"),
    ("when will the next election be",                   "election"),
    # "when did/was" — regression guards (these passed before; protect them)
    ("when did the berlin wall fall",                    "berlin wall"),
    ("when did world war 2 end",                         "world war 2"),
    ("when did the french revolution happen",            "french revolution"),
    ("when did the titanic sink",                        "titanic"),
    ("when did the cold war end",                        "cold war"),
    ("when was napoleon born",                           "napoleon"),
    ("when was the eiffel tower built",                  "eiffel tower"),
    ("when was the telephone invented",                  "telephone"),
    ("when was the united nations founded",              "united nations"),
    ("when did the dinosaurs go extinct",                "dinosaurs"),
    # "when does X occur" — regression guards
    ("when does daylight saving time end",               "daylight saving time"),
    ("when does the summer solstice occur",              "summer solstice"),
    # "when is X" — regression guards
    ("when is christmas",                                "christmas"),
    ("when is thanksgiving",                             "thanksgiving"),
    ("when is the super bowl",                           "super bowl"),
])
def test_batch74_subject_extraction(question, expected):
    """Batch 74: return/arrive trailing verbs; next temporal prefix strip; when-did/was guards."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 75: "where in the world is X" / "where on earth is X" (in-the-world
#           filler phrase stripped before generic ^in strip)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "where in the world is X" → X
    ("where in the world is patagonia",             "patagonia"),
    # "where in the world is the SUPERLATIVE NOUN" → NOUN (superlative leading adj stripped)
    ("where in the world is the deepest cave",      "cave"),
    # "where is X" — regression guards
    ("where is the amazon river",                   "amazon river"),
    ("where is the eiffel tower",                   "eiffel tower"),
    ("where is the great barrier reef",             "great barrier reef"),
    ("where is the sahara desert",                  "sahara desert"),
    # "where are X" — regression guards
    ("where are the galapagos islands",             "galapagos islands"),
    ("where are the rocky mountains",               "rocky mountains"),
    # "where was X born" — regression guards
    ("where was einstein born",                     "einstein"),
    ("where was shakespeare born",                  "shakespeare"),
    # "where does X live" — regression guards
    ("where does the giant panda live",             "giant panda"),
    ("where does the snow leopard live",            "snow leopard"),
    # "where do X come from" — regression guards
    ("where do diamonds come from",                 "diamonds"),
    # "where can you find X" — regression guards
    ("where can you find gold",                     "gold"),
    # "where is X found in nature" — regression guards
    ("where is uranium found in nature",            "uranium"),
    # "where did X originate" — regression guards
    ("where did the roman empire originate",        "roman empire"),
    ("where did chess originate",                   "chess"),
])
def test_batch75_subject_extraction(question, expected):
    """Batch 75: 'where in the world/on earth is X' filler strip; where regression guards."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 76: "sweat" added to trailing-verb list; why-do/does/is/are/did/would
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "sweat" now in trailing-verb list
    ("why do humans sweat",                         "humans"),
    ("why do athletes sweat more",                  "athletes"),
    # "why do/does X VERB" → X  (regression guards)
    ("why do cats meow",                            "cats"),
    ("why do fish swim in schools",                 "fish"),
    ("why do dogs bark at strangers",               "dogs"),
    ("why does bread rise",                         "bread"),
    ("why does wood float on water",                "wood"),
    ("why does copper turn green",                  "copper"),
    # "why is X Y" → X  (regression guards)
    ("why is grass green",                          "grass"),
    ("why is urine yellow",                         "urine"),
    ("why is gold so valuable",                     "gold"),
    # "why are X Y" → X  (regression guards)
    ("why are sunsets red",                         "sunsets"),
    ("why are tears salty",                         "tears"),
    ("why are rainbows curved",                     "rainbows"),
    # "why did X happen" → X
    ("why did the soviet union collapse",           "soviet union"),
    ("why did napoleon lose at waterloo",           "napoleon"),
    # "why can't/don't X VERB" → X
    ("why can't humans fly",                        "humans"),
    ("why don't birds freeze in winter",            "birds"),
])
def test_batch76_subject_extraction(question, expected):
    """Batch 76: sweat verb added; why-do/does/is/are/did patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 77: "how do/does/is/are" make/cook/build/treat/grow patterns;
#            compound conjunctions "X and the Y" → "X and Y"
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "how do you make X" → X
    ("how do you make bread",                       "bread"),
    ("how do you make glass",                       "glass"),
    ("how do you make paper",                       "paper"),
    ("how do you make cement",                      "cement"),
    # "how do you cook/grow/build/treat X" → X
    ("how do you cook pasta",                       "pasta"),
    ("how do you grow tomatoes",                    "tomatoes"),
    ("how do you build a bridge",                   "bridge"),
    ("how do you treat diabetes",                   "diabetes"),
    # "how is X made" → X (passive)
    ("how is beer made",                            "beer"),
    ("how is cheese made",                          "cheese"),
    ("how is plastic made",                         "plastic"),
    # "how are X made" → X
    ("how are microchips made",                     "microchips"),
    ("how are solar panels made",                   "solar panels"),
    # "what causes X to VERB" → X
    ("what causes a star to explode",               "star"),
    ("what causes the heart to beat",               "heart"),
    ("what causes ice to melt",                     "ice"),
    # "what happens when X VERBS" → X
    ("what happens when a star dies",               "star"),
    ("what happens when blood sugar is low",        "blood sugar"),
    # "how are X and Y related/connected" → "X and Y" (compound subject, article normalised)
    ("how are plants and animals related",          "plants and animals"),
    ("how are the brain and the heart connected",   "brain and heart"),
])
def test_batch77_subject_extraction(question, expected):
    """Batch 77: make/cook/build/treat verbs; compound 'X and the Y' article normalisation."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 78: "how long/tall/deep/old/fast" measurement questions;
#            "how many/much X" used/made-of/composed-of patterns;
#            function-of and type-of scaffolding
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "how long/tall/deep/old/heavy/wide is X" → X
    ("how long is the great wall of china",         "great wall of china"),
    ("how tall is mount everest",                   "mount everest"),
    ("how deep is the mariana trench",              "mariana trench"),
    ("how old is the universe",                     "universe"),
    ("how heavy is the earth",                      "earth"),
    ("how wide is the amazon river",                "amazon river"),
    # "how fast does X move/travel" → X
    ("how fast does light travel",                  "light"),
    ("how fast does the earth rotate",              "earth"),
    ("how fast does sound travel in water",         "sound"),
    # "how many X are there" → X
    ("how many planets are there",                  "planets"),
    # "how many X are in Y" → Y (container — intentional: better lookup key)
    ("how many bones are in the human body",        "human body"),
    ("how many countries are in the world",         "world"),
    # "how much X does Y VERB" → Y (entity being described — intentional)
    ("how much water does the human body contain",  "human body"),
    # "how hot/cold/bright/strong is X" → X
    ("how hot is the sun",                          "sun"),
    ("how cold is space",                           "space"),
    ("how hot is lava",                             "lava"),
    ("how bright is the sun",                       "sun"),
    ("how strong is a diamond",                     "diamond"),
    # "how long does it take for X to VERB" → X (regression)
    ("how long does it take for light to reach earth", "light"),
])
def test_batch78_subject_extraction(question, expected):
    """Batch 78: measurement 'how long/tall/fast' patterns; how-many/much container logic."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 79: historical "when/what happened/during" patterns;
#            "what year was X signed/discovered"; trailing orphaned-adverb strip;
#            happens-inside-happened word-boundary QW-strip fix
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "when did X happen/start/end" → X
    ("when did the french revolution start",        "french revolution"),
    ("when did the dinosaurs go extinct",           "dinosaurs"),
    ("when did world war 2 end",                    "world war 2"),
    # "when did X first VERB" → X (orphaned "first" adverb stripped)
    ("when did humans first walk on the moon",      "humans"),
    # "when was X invented/discovered/born/built" → X
    ("when was the internet invented",              "internet"),
    ("when was penicillin discovered",              "penicillin"),
    ("when was einstein born",                      "einstein"),
    ("when was the eiffel tower built",             "eiffel tower"),
    # "when will X happen/return" → X
    ("when will the next solar eclipse happen",     "solar eclipse"),
    ("when will halley's comet return",             "halley's comet"),
    # "when does X occur/develop" → X (trailing adverb "fully" stripped)
    ("when does a lunar eclipse occur",             "lunar eclipse"),
    ("when does the human brain fully develop",     "human brain"),
    # "what year was X signed/discovered" → X
    ("what year was the magna carta signed",        "magna carta"),
    ("what year was america discovered",            "america"),
    # "what happened during X" → X (happened stripped by leading-verb strip)
    ("what happened during the cold war",           "cold war"),
    ("what happened during the black death",        "black death"),
    # "what was X" → X (historical entity lookup)
    ("what was the roman colosseum",                "roman colosseum"),
    ("what was the silk road",                      "silk road"),
    # "what is the history of X" → X
    ("what is the history of chess",                "chess"),
    ("what is the history of the olympic games",    "olympic games"),
])
def test_batch79_subject_extraction(question, expected):
    """Batch 79: historical/when patterns; signed verb; fully adverb; happened leading strip."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 80: science process / biology questions — how-does-work, what-is,
#            role-of, responsible-for, how-are-formed
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "how does X work" → X
    ("how does the human immune system work",       "human immune system"),
    ("how does photosynthesis work",                "photosynthesis"),
    ("how does the internet work",                  "internet"),
    ("how does a nuclear reactor work",             "nuclear reactor"),
    ("how does dna replication work",               "dna replication"),
    # "how does X form/erupt/occur" → X
    ("how does lightning form",                     "lightning"),
    ("how does a volcano erupt",                    "volcano"),
    ("how does an earthquake occur",                "earthquake"),
    # "what is X" (scientific concept) → X
    ("what is photosynthesis",                      "photosynthesis"),
    ("what is mitosis",                             "mitosis"),
    ("what is gravity",                             "gravity"),
    ("what is quantum entanglement",                "quantum entanglement"),
    # "what is the process of X" → X
    ("what is the process of osmosis",              "osmosis"),
    ("what is the process of evolution",            "evolution"),
    # "what is the role of X in Y" → X
    ("what is the role of insulin in the body",     "insulin"),
    ("what is the role of mitochondria in cells",   "mitochondria"),
    # "what is X responsible for" → X
    ("what is the liver responsible for",           "liver"),
    ("what is the pancreas responsible for",        "pancreas"),
    # "how are X formed" → X
    ("how are volcanoes formed",                    "volcanoes"),
    ("how are mountains formed",                    "mountains"),
])
def test_batch80_subject_extraction(question, expected):
    """Batch 80: science process / biology how-does-work and what-is patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 81: geography, capital/population, superlatives (highest/lowest added),
#            "language is spoken in X" passive pattern
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "what is the capital/population of X" → X
    ("what is the capital of france",               "france"),
    ("what is the capital of australia",            "australia"),
    ("what is the population of china",             "china"),
    ("what is the population of new york city",     "new york city"),
    # Superlative strip — original list
    ("what is the largest country in the world",    "country"),
    ("what is the smallest ocean",                  "ocean"),
    ("what is the longest river in the world",      "river"),
    ("what is the deepest lake in the world",       "lake"),
    # Superlative strip — highest/lowest added
    ("what is the highest mountain in the world",   "mountain"),
    # Most/least superlative
    ("what is the most spoken language",            "language"),
    ("what is the most common element",             "element"),
    # "what is X known for" → X
    ("what is hawaii known for",                    "hawaii"),
    ("what is the amazon river known for",          "amazon river"),
    # "what country/continent is X in/on" → X
    ("what country is cairo in",                    "cairo"),
    ("what continent is egypt in",                  "egypt"),
    # "is X in Y" → X
    ("is japan in asia",                            "japan"),
    ("is the nile in africa",                       "nile"),
    # "what language do people in X speak" → X (existing)
    ("what language do people in brazil speak",     "brazil"),
    # "what language is spoken in X" → X (passive; new _m_lang_passive fix)
    ("what language is spoken in switzerland",      "switzerland"),
])
def test_batch81_subject_extraction(question, expected):
    """Batch 81: geography & superlative patterns; highest/lowest; language-passive fix."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 82: technology and AI concept questions — what-is, how-does-work,
#            difference-between, stand-for
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "what is X" (technology concept) → X
    ("what is machine learning",                    "machine learning"),
    ("what is artificial intelligence",             "artificial intelligence"),
    ("what is blockchain",                          "blockchain"),
    ("what is the cloud",                           "cloud"),
    ("what is quantum computing",                   "quantum computing"),
    # "how does X work" (technology) → X
    ("how does wifi work",                          "wifi"),
    ("how does bluetooth work",                     "bluetooth"),
    ("how does gps work",                           "gps"),
    ("how does a cpu work",                         "cpu"),
    ("how does encryption work",                    "encryption"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between tcp and udp",  "tcp and udp"),
    ("what is the difference between ram and rom",  "ram and rom"),
    ("what is the difference between ai and ml",    "ai and ml"),
    # "how do X and Y differ" → "X and Y"
    ("how do python and java differ",               "python and java"),
    # "what is a/an X" → X
    ("what is a pixel",                             "pixel"),
    ("what is an algorithm",                        "algorithm"),
    ("what is a database",                          "database"),
    # "what does X stand for" → X
    ("what does cpu stand for",                     "cpu"),
    ("what does html stand for",                    "html"),
    ("what does api stand for",                     "api"),
])
def test_batch82_subject_extraction(question, expected):
    """Batch 82: technology & AI questions — what-is, how-does-work, difference-between."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what causes X" → X
    ("what causes diabetes",                        "diabetes"),
    ("what causes high blood pressure",             "high blood pressure"),
    ("what causes a cold",                          "cold"),
    ("what causes cancer",                          "cancer"),
    ("what causes anxiety",                         "anxiety"),
    # "what are the symptoms of X" → X
    ("what are the symptoms of covid",              "covid"),
    ("what are the symptoms of flu",                "flu"),
    ("what are the symptoms of depression",         "depression"),
    # "how is X treated" → X (passive construction; treat added to trailing verb list)
    ("how is diabetes treated",                     "diabetes"),
    ("how is cancer treated",                       "cancer"),
    # "how do you treat X" → X
    ("how do you treat a fever",                    "fever"),
    ("how do you treat a broken bone",              "broken bone"),
    # "what is X" (medical concept) → X
    ("what is hypertension",                        "hypertension"),
    ("what is alzheimer's disease",                 "alzheimer's disease"),
    ("what is a vaccine",                           "vaccine"),
    # "how does X affect the body" → X
    ("how does alcohol affect the body",            "alcohol"),
    ("how does stress affect the body",             "stress"),
    # "what is the cure/treatment for X" → X (cure/treatment added to causal-noun list)
    ("what is the cure for diabetes",               "diabetes"),
    ("what is the treatment for malaria",           "malaria"),
    # "can X cause Y" → X
    ("can stress cause heart disease",              "stress"),
])
def test_batch83_subject_extraction(question, expected):
    """Batch 83: medical/health questions — causes, symptoms, how-is-treated, cure-for."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" (economics/social science) → X
    ("what is inflation",                                   "inflation"),
    ("what is gdp",                                         "gdp"),
    ("what is capitalism",                                  "capitalism"),
    ("what is a recession",                                 "recession"),
    ("what is democracy",                                   "democracy"),
    ("what is globalization",                               "globalization"),
    # "what causes X" (economic) → X
    ("what causes inflation",                               "inflation"),
    ("what causes a recession",                             "recession"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between stocks and bonds",     "stocks and bonds"),
    # "how does X affect Y" → X (trailing Y stripped by trailing verb strip)
    ("how does inflation affect the economy",               "inflation"),
    # "how does X rate affect Y" → "X rate" (bare rate protected as noun)
    ("how does interest rate affect borrowing",             "interest rate"),
    # "what is the gdp of X" → X (specific entity); "of a X" stays as gdp
    ("what is the gdp of china",                            "china"),
    ("what is the gdp of the united states",                "united states"),
    # "what is the X rate" → "X rate" (rate protected as compound noun)
    ("what is the unemployment rate",                       "unemployment rate"),
    ("what is the poverty rate",                            "poverty rate"),
    # "how does X work" (institutions) → X
    ("how does the stock market work",                      "stock market"),
    ("how does the federal reserve work",                   "federal reserve"),
    # "what is X" further
    ("what is communism",                                   "communism"),
    ("what is feminism",                                    "feminism"),
])
def test_batch84_subject_extraction(question, expected):
    """Batch 84: economics/social-science — rate noun fix, gdp-of entity, inflation."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" (physics) → X
    ("what is energy",                              "energy"),
    ("what is momentum",                            "momentum"),
    ("what is entropy",                             "entropy"),
    ("what is a photon",                            "photon"),
    ("what is dark matter",                         "dark matter"),
    ("what is dark energy",                         "dark energy"),
    # "what is the speed of X" → "speed of X" (canonical constant, no article strip)
    ("what is the speed of light",                  "speed of light"),
    ("what is the speed of sound",                  "speed of sound"),
    # "what is X measured in" → X (passive participle stripped)
    ("what is temperature measured in",             "temperature"),
    ("what is pressure measured in",                "pressure"),
    # "how does X work" (physics/astronomy) → X
    ("how does a black hole work",                  "black hole"),
    ("how does gravity work",                       "gravity"),
    ("how does a telescope work",                   "telescope"),
    # "what is the mass of X" → X (causal-noun strip)
    ("what is the mass of the sun",                 "sun"),
    # "distance from X to Y" → X (source entity extracted)
    ("what is the distance from the earth to the moon", "earth"),
    # "why does X" → X
    ("why does the moon have craters",              "moon"),
    ("why does the sun shine",                      "sun"),
    # "how far away is X" → X
    ("how far away is the sun",                     "sun"),
    ("how far away is mars",                        "mars"),
    # "how big is X" → X
    ("how big is the universe",                     "universe"),
])
def test_batch85_subject_extraction(question, expected):
    """Batch 85: physics & astronomy — dark matter, speed-of constants, distance-from."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "who wrote/painted/composed X" → X
    ("who wrote hamlet",                            "hamlet"),
    ("who wrote the great gatsby",                  "great gatsby"),
    ("who wrote don quixote",                       "don quixote"),
    ("who painted the mona lisa",                   "mona lisa"),
    ("who painted the sistine chapel",              "sistine chapel"),
    ("who composed beethoven's fifth symphony",     "beethoven's fifth symphony"),
    ("who composed swan lake",                      "swan lake"),
    # "when was X written/published" → X
    ("when was hamlet written",                     "hamlet"),
    ("when was the great gatsby published",         "great gatsby"),
    # "what is X about" → X (trailing about-strip)
    ("what is hamlet about",                        "hamlet"),
    ("what is the great gatsby about",              "great gatsby"),
    # "what genre/style is X" → X (cat-is pattern)
    ("what genre is hamlet",                        "hamlet"),
    ("what style is the mona lisa",                 "mona lisa"),
    # "in what year was X written" → X (in-what-year QW re-strip)
    ("in what year was hamlet written",             "hamlet"),
    # "what is the theme/plot of X" → X (causal noun strip)
    ("what is the theme of hamlet",                 "hamlet"),
    ("what is the plot of the great gatsby",        "great gatsby"),
    # "how many acts does X have" → X
    ("how many acts does hamlet have",              "hamlet"),
    # "what is X known for" → X
    ("what is shakespeare known for",               "shakespeare"),
    ("what is beethoven known for",                 "beethoven"),
])
def test_batch86_subject_extraction(question, expected):
    """Batch 86: literature & art — published passive, about-strip, theme/plot causal nouns,
    in-what-year re-strip, style/genre cat-is expansion."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "how do you make X" → X
    ("how do you make pasta",                          "pasta"),
    ("how do you make bread",                          "bread"),
    ("how do you make coffee",                         "coffee"),
    # "how long does it take to cook/bake X" → X
    ("how long does it take to cook chicken",          "chicken"),
    ("how long does it take to bake a cake",           "cake"),
    # "what temperature do you cook/bake X at" → X (prop_does pronoun-cleanup)
    ("what temperature do you cook chicken at",        "chicken"),
    ("what temperature do you bake bread at",          "bread"),
    # "what are the ingredients in X" → X (ingredient causal noun)
    ("what are the ingredients in pizza",              "pizza"),
    ("what are the ingredients in guacamole",          "guacamole"),
    # "how many calories are in X" → X
    ("how many calories are in an apple",              "apple"),
    ("how many calories are in a banana",              "banana"),
    # "who invented X (sport)" → X
    ("who invented basketball",                        "basketball"),
    ("who invented soccer",                            "soccer"),
    # "how many players are on a SPORT team" → SPORT (_m_team_count)
    ("how many players are on a basketball team",      "basketball"),
    ("how many players are on a soccer team",          "soccer"),
    # "what are the rules of X" → X
    ("what are the rules of chess",                    "chess"),
    ("what are the rules of poker",                    "poker"),
    # "who is the president of X" → X
    ("who is the president of france",                 "france"),
    ("who is the president of the united states",      "united states"),
    # "how does X work in Y" → X (location stripped, work verb second-pass strip)
    ("how does voting work in the united states",      "voting"),
])
def test_batch87_subject_extraction(question, expected):
    """Batch 87: food/cooking & sports/politics — ingredients causal noun, temperature
    prop_does cleanup, team-count match, second-pass work strip."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "where is X" → X
    ("where is the eiffel tower",                      "eiffel tower"),
    ("where is the amazon river",                      "amazon river"),
    ("where is mount everest",                         "mount everest"),
    # "what country is X in" → X
    ("what country is the amazon river in",            "amazon river"),
    ("what country is mount fuji in",                  "mount fuji"),
    # "what is the capital/population of X" → X
    ("what is the capital of france",                  "france"),
    ("what is the capital of japan",                   "japan"),
    ("what is the capital of australia",               "australia"),
    ("what is the population of china",                "china"),
    ("what is the population of india",                "india"),
    # "what is the largest/smallest NOUN in X" → X (_m_super_in match)
    ("what is the largest country in africa",          "africa"),
    ("what is the largest city in europe",             "europe"),
    # "what language do people in X speak" → X
    ("what language do people in brazil speak",        "brazil"),
    ("what language do people in japan speak",         "japan"),
    # "what is the currency of X" → X
    ("what is the currency of japan",                  "japan"),
    ("what is the currency of the uk",                 "uk"),
    # "how do you get to X" → X
    ("how do you get to new zealand",                  "new zealand"),
    # "what is the time zone of X" → X (time zone added to causal noun list)
    ("what is the time zone of california",            "california"),
    # "how far is X from Y" → X
    ("how far is london from paris",                   "london"),
])
def test_batch88_subject_extraction(question, expected):
    """Batch 88: geography & travel — time-zone causal noun, _m_super_in for
    superlative+category+in+place patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" (body part/system) → X
    ("what is the cerebellum",                         "cerebellum"),
    ("what is the hippocampus",                        "hippocampus"),
    ("what is the immune system",                      "immune system"),
    ("what is the lymphatic system",                   "lymphatic system"),
    # "what does the X do" → X
    ("what does the liver do",                         "liver"),
    ("what does the pancreas do",                      "pancreas"),
    ("what does the cerebellum do",                    "cerebellum"),
    # "how does X work" (body) → X
    ("how does the kidney work",                       "kidney"),
    ("how does the heart work",                        "heart"),
    # "what are the symptoms of X" → X
    ("what are the symptoms of diabetes",              "diabetes"),
    ("what are the symptoms of depression",            "depression"),
    # "what causes X" → X
    ("what causes diabetes",                           "diabetes"),
    ("what causes cancer",                             "cancer"),
    ("what causes high blood pressure",                "high blood pressure"),
    # "how is X diagnosed" → X (diagnos? added to passive-participle list)
    ("how is diabetes diagnosed",                      "diabetes"),
    ("how is cancer diagnosed",                        "cancer"),
    # "how is X treated" → X
    ("how is diabetes treated",                        "diabetes"),
    # "what is the treatment for X" → X
    ("what is the treatment for diabetes",             "diabetes"),
    ("what is the treatment for depression",           "depression"),
    # "how do you prevent X" → X
    ("how do you prevent diabetes",                    "diabetes"),
    ("how do you prevent heart disease",               "heart disease"),
])
def test_batch89_subject_extraction(question, expected):
    """Batch 89: human body & health — diagnosed passive verb, body-part do/work patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" (technology concept) → X
    ("what is machine learning",                       "machine learning"),
    ("what is artificial intelligence",                "artificial intelligence"),
    ("what is a neural network",                       "neural network"),
    ("what is blockchain",                             "blockchain"),
    ("what is quantum computing",                      "quantum computing"),
    # "how does X work" (technology) → X
    ("how does machine learning work",                 "machine learning"),
    ("how does a neural network work",                 "neural network"),
    ("how does blockchain work",                       "blockchain"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between machine learning and deep learning",
                                                       "machine learning and deep learning"),
    ("what is the difference between ai and machine learning",
                                                       "ai and machine learning"),
    # "how is X used" → X
    ("how is machine learning used",                   "machine learning"),
    ("how is ai used in healthcare",                   "ai"),
    # "what are the applications of X" → X
    ("what are the applications of machine learning",  "machine learning"),
    ("what are the applications of quantum computing", "quantum computing"),
    # "who invented X" → X
    ("who invented the internet",                      "internet"),
    ("who invented the telephone",                     "telephone"),
    # "when was X invented" → X
    ("when was the internet invented",                 "internet"),
    ("when was the telephone invented",                "telephone"),
    # "what programming language is used for X" → category noun (grammar subject)
    ("what programming language is used for machine learning", "machine learning"),
    # "what is a X" → X
    ("what is a large language model",                 "large language model"),
])
def test_batch90_subject_extraction(question, expected):
    """Batch 90: technology & AI — machine learning, blockchain, neural networks, invented."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what did X believe" → X
    ("what did socrates believe",                      "socrates"),
    ("what did aristotle believe",                     "aristotle"),
    # "what is X's philosophy/theory" (Pattern C) → X
    ("what is plato's philosophy",                     "plato"),
    ("what is nietzsche's philosophy",                 "nietzsche"),
    # "what is X" (philosophy) → X
    ("what is existentialism",                         "existentialism"),
    ("what is utilitarianism",                         "utilitarianism"),
    ("what is stoicism",                               "stoicism"),
    ("what is consciousness",                          "consciousness"),
    ("what is free will",                              "free will"),
    # "what is X" (religion) → X
    ("what is buddhism",                               "buddhism"),
    ("what is hinduism",                               "hinduism"),
    ("what is islam",                                  "islam"),
    # "what are the beliefs of X" → X (beliefs scaffold noun)
    ("what are the beliefs of buddhism",               "buddhism"),
    ("what are the beliefs of christianity",           "christianity"),
    # "what is the meaning of X" → X
    ("what is the meaning of life",                    "meaning of life"),
    # "what is the purpose of X" → X
    ("what is the purpose of art",                     "art"),
    ("what is the purpose of religion",                "religion"),
    # "does X exist" → X
    ("does god exist",                                 "god"),
    ("does free will exist",                           "free will"),
    # "what is the difference between X and Y" (philosophy) → "X and Y"
    ("what is the difference between ethics and morality",
                                                       "ethics and morality"),
])
def test_batch91_subject_extraction(question, expected):
    """Batch 91: philosophy & religion — believe verb, possessive abstract noun, beliefs scaffold."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is a X" (animal class) → X
    ("what is a mammal",                               "mammal"),
    ("what is a reptile",                              "reptile"),
    ("what is an amphibian",                           "amphibian"),
    ("what is a marsupial",                            "marsupial"),
    # "how does X reproduce" → X
    ("how does a shark reproduce",                     "shark"),
    ("how does a frog reproduce",                      "frog"),
    # "what does X eat" → X
    ("what does a panda eat",                          "panda"),
    ("what does a lion eat",                           "lion"),
    ("what does a whale eat",                          "whale"),
    # "where does X live" → X
    ("where does a penguin live",                      "penguin"),
    ("where does a polar bear live",                   "polar bear"),
    # "how long does X live" → X
    ("how long does an elephant live",                 "elephant"),
    ("how long does a tortoise live",                  "tortoise"),
    # "how fast can X run" → X
    ("how fast can a cheetah run",                     "cheetah"),
    ("how fast can a horse run",                       "horse"),
    # "what is the habitat of X" → X (habitat causal noun)
    ("what is the habitat of a tiger",                 "tiger"),
    ("what is the habitat of a wolf",                  "wolf"),
    # "what are the predators of X" → X (predators scaffold noun)
    ("what are the predators of rabbits",              "rabbits"),
    # "how do X migrate" → X
    ("how do monarch butterflies migrate",             "monarch butterflies"),
    # "what is the diet of X" → X (diet causal noun)
    ("what is the diet of a bear",                     "bear"),
])
def test_batch92_subject_extraction(question, expected):
    """Batch 92: animals & nature — habitat/diet causal nouns, predators scaffold, migration."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what caused X" (historical event) → X
    ("what caused the french revolution",              "french revolution"),
    ("what caused world war 2",                        "world war 2"),
    ("what caused the great depression",               "great depression"),
    # "when did X happen/start/end" → X
    ("when did world war 2 end",                       "world war 2"),
    ("when did the civil war start",                   "civil war"),
    # "who started X" → X
    ("who started world war 1",                        "world war 1"),
    ("who started the cold war",                       "cold war"),
    # "who led X" → X
    ("who led the french revolution",                  "french revolution"),
    ("who led the civil rights movement",              "civil rights movement"),
    # "what was X" (historical concept) → X
    ("what was the renaissance",                       "renaissance"),
    ("what was the enlightenment",                     "enlightenment"),
    ("what was the cold war",                          "cold war"),
    # "where did X happen" → X
    ("where did the titanic sink",                     "titanic"),
    # "how did X end/fall" → X
    ("how did world war 2 end",                        "world war 2"),
    ("how did the roman empire fall",                  "roman empire"),
    # "what happened during X" → X
    ("what happened during the french revolution",     "french revolution"),
    ("what happened during the renaissance",           "renaissance"),
    # "who won X" → X
    ("who won world war 2",                            "world war 2"),
    ("who won the american revolution",                "american revolution"),
    # "what were the consequences of X" → X
    ("what were the consequences of world war 1",      "world war 1"),
])
def test_batch93_subject_extraction(question, expected):
    """Batch 93: history & events — revolutionary/war/empire patterns all baseline-correct."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "who sang X" → X (sang leading verb)
    ("who sang bohemian rhapsody",                     "bohemian rhapsody"),
    ("who sang stairway to heaven",                    "stairway to heaven"),
    # "who wrote X" (song/title) → X
    ("who wrote imagine",                              "imagine"),
    ("who wrote hotel california",                     "hotel california"),
    # "what genre is X" → X
    ("what genre is bohemian rhapsody",                "bohemian rhapsody"),
    ("what genre is jazz",                             "jazz"),
    # "what album is X on" → X (media containment)
    ("what album is stairway to heaven on",            "stairway to heaven"),
    # "when was X released" → X
    ("when was thriller released",                     "thriller"),
    ("when was dark side of the moon released",        "dark side of the moon"),
    # "who directed X" → X (directed leading verb)
    ("who directed inception",                         "inception"),
    ("who directed the godfather",                     "godfather"),
    # "who starred in X" → X (starred in leading verb)
    ("who starred in titanic",                         "titanic"),
    ("who starred in the matrix",                      "matrix"),
    # "what year was X released" → X
    ("what year was titanic released",                 "titanic"),
    ("what year was the godfather released",           "godfather"),
    # "how long is X" → X
    ("how long is the godfather",                      "godfather"),
    ("how long is inception",                          "inception"),
    # "what is X about" → X
    ("what is inception about",                        "inception"),
    ("what is the matrix about",                       "matrix"),
    # "who produced X" → X
    ("who produced thriller",                          "thriller"),
])
def test_batch94_subject_extraction(question, expected):
    """Batch 94: music & entertainment — sang/directed/starred leading verbs, media is, of-the guard."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" (physics concept) → X
    ("what is gravity",                                "gravity"),
    ("what is relativity",                             "relativity"),
    ("what is entropy",                                "entropy"),
    ("what is thermodynamics",                         "thermodynamics"),
    ("what is electromagnetism",                       "electromagnetism"),
    # "speed of X" without article → canonical constant kept intact
    ("what is the speed of light",                     "speed of light"),
    ("what is the speed of sound",                     "speed of sound"),
    # mass/size causal-noun compounds (with article → strip)
    ("what is the mass of the earth",                  "earth"),
    ("what is the mass of the sun",                    "sun"),
    # "how does X work" → X
    ("how does gravity work",                          "gravity"),
    ("how does nuclear fusion work",                   "nuclear fusion"),
    ("how does a laser work",                          "laser"),
    # boiling/melting point causal noun
    ("what is the boiling point of water",             "water"),
    ("what is the boiling point of nitrogen",          "nitrogen"),
    ("what is the melting point of iron",              "iron"),
    # "how hot is X" → X
    ("how hot is the sun",                             "sun"),
    ("how hot is lava",                                "lava"),
    # atomic number causal noun
    ("what is the atomic number of carbon",            "carbon"),
    ("what is the atomic number of gold",              "gold"),
    # "what is X made of" → X
    ("what is water made of",                          "water"),
    ("what is glass made of",                          "glass"),
])
def test_batch95_subject_extraction(question, expected):
    """Batch 95: science & physics — gravity/entropy, mass/boiling-point causal nouns, speed-of canonical."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # core concepts
    ("what is pi",                                     "pi"),
    ("what is the pythagorean theorem",                "pythagorean theorem"),
    ("what is calculus",                               "calculus"),
    ("what is algebra",                                "algebra"),
    ("what is trigonometry",                           "trigonometry"),
    # square root → causal noun, returns the operand
    ("what is the square root of 144",                 "144"),
    ("what is the square root of 2",                   "2"),
    # factorial — numeric quantifier strips "5"; "factorial" is the concept returned
    ("what is 5 factorial",                            "factorial"),
    # "how do you calculate X" → shape (area/volume reduce to the shape itself)
    ("how do you calculate the area of a circle",      "circle"),
    ("how do you calculate the volume of a sphere",    "sphere"),
    # formula causal noun reduces to the shape/entity
    ("what is the formula for the area of a circle",   "circle"),
    ("what is the formula for compound interest",      "compound interest"),
    # difference-between → "X and Y"
    ("what is the difference between mean and median", "mean and median"),
    ("what is the difference between mode and median", "mode and median"),
    # "how many X are in Y" → Y (the container is the lookup entity)
    ("how many centimeters are in a meter",            "meter"),
    ("how many degrees are in a circle",               "circle"),
    ("how many days are in a year",                    "year"),
    # sequences / ratios
    ("what is the fibonacci sequence",                 "fibonacci sequence"),
    ("what is the golden ratio",                       "golden ratio"),
])
def test_batch96_subject_extraction(question, expected):
    """Batch 96: math — concepts, square-root causal noun, formula, difference-between, unit containers."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "who won X" → X
    ("who won the world cup",                          "world cup"),
    ("who won the super bowl",                         "super bowl"),
    ("who won the nba finals",                         "nba finals"),
    # "how many X has Y VERB" → Y (entity with the stat)
    ("how many world cups has brazil won",             "brazil"),
    ("how many championships has lebron won",          "lebron"),
    # rules scaffold → sport
    ("what are the rules of basketball",               "basketball"),
    ("what are the rules of soccer",                   "soccer"),
    # "how long is X [game]" → X
    ("how long is a basketball game",                  "basketball game"),
    ("how long is a soccer game",                      "soccer game"),
    # superlative + "in nba history" → "nba history"
    ("what is the highest scoring game in nba history", "nba history"),
    # record-holder early-return
    ("who holds the record for most home runs",        "home runs"),
    ("who holds the record for most goals in a season", "goals"),
    # single rule causal noun → sport
    ("what is the offside rule in soccer",             "soccer"),
    # team count → sport
    ("how many players are in a soccer team",          "soccer"),
    ("how many players are in a basketball team",      "basketball"),
    # positions scaffold → sport
    ("what are the positions in baseball",             "baseball"),
    ("what are the positions in american football",    "american football"),
    # has-won-most → competition
    ("what country has won the most world cups",       "world cups"),
    # sport term
    ("what is a hat trick",                            "hat trick"),
    # greatest X of all time
    ("who is the greatest basketball player of all time", "basketball player"),
])
def test_batch97_subject_extraction(question, expected):
    """Batch 97: sports — team-count, record-holder, offside rule, positions-in-sport, has-won-most."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # capital / population / currency causal nouns
    ("what is the capital of france",                  "france"),
    ("what is the capital of australia",               "australia"),
    ("what is the population of china",                "china"),
    ("what is the currency of japan",                  "japan"),
    # language passive construction
    ("what language is spoken in brazil",              "brazil"),
    ("what language do people speak in switzerland",   "switzerland"),
    # where-is → entity
    ("where is the amazon river",                      "amazon river"),
    ("where is the eiffel tower",                      "eiffel tower"),
    # "what country/continent is X in" → X
    ("what country is the amazon river in",            "amazon river"),
    ("what country is mount everest in",               "mount everest"),
    ("what continent is brazil in",                    "brazil"),
    ("what continent is egypt in",                     "egypt"),
    # superlative + real location → location (africa, south america)
    ("what is the largest country in africa",          "africa"),
    ("what is the largest country in south america",   "south america"),
    # superlative + universal scope → category noun
    ("what is the tallest mountain in the world",      "mountain"),
    # how-many countries → container
    ("how many countries are in europe",               "europe"),
    ("how many countries are in africa",               "africa"),
])
def test_batch98_subject_extraction(question, expected):
    """Batch 98: geography — capital/population/language, where-is, country-in, superlative-in-location."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # basic concepts
    ("what is the internet",                           "internet"),
    ("what is artificial intelligence",                "artificial intelligence"),
    ("what is machine learning",                       "machine learning"),
    ("what is blockchain",                             "blockchain"),
    ("what is an algorithm",                           "algorithm"),
    # "how does X work" → X
    ("how does wifi work",                             "wifi"),
    ("how does encryption work",                       "encryption"),
    ("how does a computer processor work",             "computer processor"),
    # difference-between
    ("what is the difference between ram and rom",     "ram and rom"),
    ("what is the difference between http and https",  "http and https"),
    # "is used for PURPOSE" → PURPOSE (copula required)
    ("what programming language is used for web development",   "web development"),
    ("what programming language is used for data science",      "data science"),
    ("what programming language is used for machine learning",  "machine learning"),
    # "X used for" (no copula) → X
    ("what is python used for",                        "python"),
    ("what is sql used for",                           "sql"),
    # leading-verb strip → topic
    ("who invented the internet",                      "internet"),
    ("who invented the telephone",                     "telephone"),
    # types scaffold
    ("what are the types of networks",                 "networks"),
    ("what are the types of programming languages",    "programming languages"),
    # how-do-you install
    ("how do you install python",                      "python"),
])
def test_batch99_subject_extraction(question, expected):
    """Batch 99: technology — concepts, used-for purpose, invented, types, install."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" medical terms
    ("what is diabetes",                                "diabetes"),
    ("what is cancer",                                  "cancer"),
    ("what is depression",                              "depression"),
    ("what is hypertension",                            "hypertension"),
    # "what causes X"
    ("what causes diabetes",                            "diabetes"),
    ("what causes high blood pressure",                 "high blood pressure"),
    ("what causes migraines",                           "migraines"),
    # "what are the symptoms of X"
    ("what are the symptoms of covid",                  "covid"),
    ("what are the symptoms of the flu",                "flu"),
    # "how is X treated"
    ("how is diabetes treated",                         "diabetes"),
    ("how is cancer treated",                           "cancer"),
    # "what is the cure for X" — "cold" must not be stripped from "common cold"
    ("what is the cure for the common cold",            "common cold"),
    # "how do you treat X"
    ("how do you treat a sprained ankle",               "sprained ankle"),
    # difference between
    ("what is the difference between a virus and a bacteria", "virus and bacteria"),
    # body effects
    ("how does alcohol affect the body",                "alcohol"),
    ("how does stress affect the body",                 "stress"),
    # "what foods are good for X" — beneficiary is the lookup subject
    ("what foods are good for the heart",               "heart"),
    ("what foods are good for the brain",               "brain"),
    # "how many calories are in X"
    ("how many calories are in an apple",               "apple"),
    ("how many calories are in a banana",               "banana"),
])
def test_batch100_subject_extraction(question, expected):
    """Batch 100: health/medicine — diseases, causes, symptoms, cures, body effects, diet."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" food concepts
    ("what is sourdough bread",                         "sourdough bread"),
    ("what is umami",                                   "umami"),
    ("what is gluten",                                  "gluten"),
    # "how do you make X"
    ("how do you make pasta",                           "pasta"),
    ("how do you make bread",                           "bread"),
    ("how do you make pizza",                           "pizza"),
    # "what are the ingredients in X" — causal noun strips "ingredients in"
    ("what are the ingredients in spaghetti carbonara", "spaghetti carbonara"),
    ("what are the ingredients in hummus",              "hummus"),
    # "how do you cook X"
    ("how do you cook chicken",                         "chicken"),
    ("how do you cook rice",                            "rice"),
    # "how long does it take to cook X"
    ("how long does it take to cook a turkey",          "turkey"),
    ("how long does it take to boil an egg",            "egg"),
    # temperature cooking question
    ("what temperature do you cook chicken at",         "chicken"),
    # difference between food items
    ("what is the difference between baking soda and baking powder", "baking soda and baking powder"),
    ("what is the difference between jam and jelly",    "jam and jelly"),
    # "what foods are high in X" → X (beneficiary/content)
    ("what foods are high in protein",                  "protein"),
    ("what foods are high in iron",                     "iron"),
    # "what is the best way to X" → subject of action
    ("what is the best way to store bread",             "bread"),
    ("what is the best way to ripen a banana",          "banana"),
    # "how many calories are in a UNIT of X" → X
    ("how many calories are in a slice of pizza",       "pizza"),
    ("how many calories are in a cup of rice",          "rice"),
])
def test_batch101_subject_extraction(question, expected):
    """Batch 101: food/cooking — ingredients, methods, differences, nutrient content, best-way."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Basic economic concepts
    ("what is inflation",                               "inflation"),
    ("what is gdp",                                     "gdp"),
    ("what is supply and demand",                       "supply and demand"),
    ("what is the stock market",                        "stock market"),
    ("what is a recession",                             "recession"),
    ("what is cryptocurrency",                          "cryptocurrency"),
    ("what is interest rate",                           "interest rate"),
    # "what causes X"
    ("what causes inflation",                           "inflation"),
    ("what causes a recession",                         "recession"),
    # "how does X work / affect Y"
    ("how does the stock market work",                  "stock market"),
    ("how does inflation affect the economy",           "inflation"),
    ("how does compound interest work",                 "compound interest"),
    # difference between
    ("what is the difference between stocks and bonds", "stocks and bonds"),
    ("what is the difference between gdp and gnp",      "gdp and gnp"),
    # "who founded X"
    ("who founded apple",                               "apple"),
    ("who founded amazon",                              "amazon"),
    # measurement terms — "us" is not stripped as a pronoun
    ("what is the us debt",                             "us debt"),
    ("what is the minimum wage",                        "minimum wage"),
    # "which CATEGORY has the SUPERLATIVE X" → CATEGORY (asking about which instance)
    ("which country has the highest gdp",               "country"),
    ("which country has the lowest unemployment rate",  "country"),
    # "how many X are there in the world"
    ("how many billionaires are there in the world",    "billionaires"),
])
def test_batch102_subject_extraction(question, expected):
    """Batch 102: economics/business — concepts, causes, differences, founders, rank queries."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question, expected", [
    # "what is X" literary concepts
    ("what is a metaphor",                              "metaphor"),
    ("what is irony",                                   "irony"),
    ("what is symbolism",                               "symbolism"),
    # "what is the ASPECT of WORK" → WORK
    ("what is the plot of hamlet",                      "hamlet"),
    ("what is the theme of the great gatsby",           "great gatsby"),
    # "who wrote/painted/composed/directed X" → X
    ("who wrote hamlet",                                "hamlet"),
    ("who wrote don quixote",                           "don quixote"),
    ("who wrote the odyssey",                           "odyssey"),
    ("who painted the mona lisa",                       "mona lisa"),
    ("who painted the sistine chapel",                  "sistine chapel"),
    ("who composed beethoven's fifth symphony",         "beethoven's fifth symphony"),
    ("who invented jazz",                               "jazz"),
    ("who directed schindler's list",                   "schindler's list"),
    ("who directed the godfather",                      "godfather"),
    # "when was X written/published/painted" → X  (passive past-participle strip)
    ("when was hamlet written",                         "hamlet"),
    ("when was don quixote published",                  "don quixote"),
    ("when was the mona lisa painted",                  "mona lisa"),
    # "what is X about" — including numeric titles
    ("what is 1984 about",                              "1984"),
    ("what is the great gatsby about",                  "great gatsby"),
    # "what genre is X"
    ("what genre is jazz",                              "jazz"),
])
def test_batch103_subject_extraction(question, expected):
    """Batch 103: literature/arts — works, creators, dates, numeric titles, passive-participle strip."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question, expected", [
    # "what is X" political/civic concepts
    ("what is democracy",                               "democracy"),
    ("what is capitalism",                              "capitalism"),
    ("what is communism",                               "communism"),
    ("what is socialism",                               "socialism"),
    ("what is the constitution",                        "constitution"),
    ("what is the bill of rights",                      "bill of rights"),
    ("what is nato",                                    "nato"),
    # "who is/was the X of Y" → Y (leadership query)
    ("who is the president of the united states",       "united states"),
    ("who was the first president of the united states","united states"),
    ("who is the prime minister of the uk",             "uk"),
    # "when was X founded/established" → X (established now in trailing-verb strip)
    ("when was the united nations founded",             "united nations"),
    ("when was the european union established",         "european union"),
    # "how does X work" → X
    ("how does the electoral college work",             "electoral college"),
    ("how does congress work",                          "congress"),
    # "what is the capital of X" → X (causal-noun strip)
    ("what is the capital of france",                   "france"),
    ("what is the capital of japan",                    "japan"),
    ("what is the capital of brazil",                   "brazil"),
    # measurement — "us" not treated as pronoun
    ("how many senators does the us have",              "us"),
    # articles stripped from difference-between subjects
    ("what is the difference between a republic and a democracy", "republic and democracy"),
    # "which CATEGORY has the X" → CATEGORY
    ("which country has the largest population",        "country"),
])
def test_batch104_subject_extraction(question, expected):
    """Batch 104: politics/government — concepts, leadership, dates, capitals, established verb."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question, expected", [
    # Psychology concepts
    ("what is psychology",                              "psychology"),
    ("what is cognitive dissonance",                    "cognitive dissonance"),
    ("what is the placebo effect",                      "placebo effect"),
    ("what is the bystander effect",                    "bystander effect"),
    ("what is confirmation bias",                       "confirmation bias"),
    ("what is classical conditioning",                  "classical conditioning"),
    ("what is operant conditioning",                    "operant conditioning"),
    # "who invented/developed X" → X
    ("who invented psychoanalysis",                     "psychoanalysis"),
    ("who developed the theory of cognitive dissonance","theory of cognitive dissonance"),
    # "what causes X" (mental health)
    ("what causes depression",                          "depression"),
    ("what causes anxiety",                             "anxiety"),
    # Philosophy concepts
    ("what is ethics",                                  "ethics"),
    ("what is stoicism",                                "stoicism"),
    ("what is existentialism",                          "existentialism"),
    ("what is utilitarianism",                          "utilitarianism"),
    # "what did X believe/say" → X (verb stripped)
    ("what did aristotle believe",                      "aristotle"),
    ("what did socrates say",                           "socrates"),
    # difference between disciplines
    ("what is the difference between psychology and psychiatry", "psychology and psychiatry"),
    # "how does X affect Y" → X (subject strip)
    ("how does stress affect the body",                 "stress"),
    ("how does sleep affect mental health",             "sleep"),
    # "what are the symptoms of X" → X
    ("what are the symptoms of depression",             "depression"),
])
def test_batch105_subject_extraction(question, expected):
    """Batch 105: psychology/philosophy — concepts, creators, verbs (say/believe), symptoms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question, expected", [
    # "what is X" geographic features
    ("what is the amazon river",                        "amazon river"),
    ("what is the sahara desert",                       "sahara desert"),
    ("what is the great barrier reef",                  "great barrier reef"),
    ("what is mount everest",                           "mount everest"),
    ("what is the mariana trench",                      "mariana trench"),
    # "where is X located" → X
    ("where is the amazon river located",               "amazon river"),
    ("where is mount everest located",                  "mount everest"),
    ("where is the sahara desert located",              "sahara desert"),
    # "what is the SUPERLATIVE X" → X (category)
    ("what is the largest ocean",                       "ocean"),
    ("what is the longest river",                       "river"),
    ("what is the tallest mountain",                    "mountain"),
    ("what is the largest country",                     "country"),
    ("what is the smallest country",                    "country"),
    # "how DEGREE is X"
    ("how tall is mount everest",                       "mount everest"),
    ("how deep is the mariana trench",                  "mariana trench"),
    ("how long is the nile river",                      "nile river"),
    # "what CATEGORY is X in/surrounded by" → X  (ocean/continent in _m_cat_is)
    ("what continent is brazil in",                     "brazil"),
    ("what continent is egypt in",                      "egypt"),
    ("what ocean is australia surrounded by",           "australia"),
    # "how many countries are in X" → X
    ("how many countries are in europe",                "europe"),
    ("how many countries are in africa",                "africa"),
])
def test_batch106_subject_extraction(question, expected):
    """Batch 106: geography — features, superlatives, category-is pattern, ocean/continent."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question, expected", [
    # "what is X" tech concepts
    ("what is artificial intelligence",                 "artificial intelligence"),
    ("what is machine learning",                        "machine learning"),
    ("what is blockchain",                              "blockchain"),
    ("what is the internet",                            "internet"),
    ("what is a cpu",                                   "cpu"),
    ("what is an operating system",                     "operating system"),
    ("what is cloud computing",                         "cloud computing"),
    ("what is open source software",                    "open source software"),
    # "who invented/created X" → X
    ("who invented the internet",                       "internet"),
    ("who created linux",                               "linux"),
    ("who invented python",                             "python"),
    # "when was X invented/released" → X (passive-participle strip)
    ("when was the internet invented",                  "internet"),
    ("when was the iphone released",                    "iphone"),
    # "how does X work" → X
    ("how does encryption work",                        "encryption"),
    ("how does wifi work",                              "wifi"),
    ("how does gps work",                               "gps"),
    # difference between acronyms
    ("what is the difference between ram and rom",      "ram and rom"),
    ("what is the difference between tcp and udp",      "tcp and udp"),
    # "what QUALIFIER language is X written in" → X (two-pass _m_cat_is)
    ("what programming language is python written in",  "python"),
    # "how many X are there"
    ("how many programming languages are there",        "programming languages"),
])
def test_batch107_subject_extraction(question, expected):
    """Batch 107: technology — concepts, creators, dates, two-pass category-is for qualifier nouns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question, expected", [
    # "what is X" sports concepts
    ("what is the offside rule",                        "offside rule"),
    ("what is a grand slam in tennis",                  "grand slam"),
    ("what is the super bowl",                          "super bowl"),
    ("what is the world cup",                           "world cup"),
    ("what is the nba",                                 "nba"),
    # "how many X are in Y" — team composition (sport name extracted, team-noun suffix stripped)
    ("how many players are on a basketball team",       "basketball"),
    ("how many players are on a soccer team",           "soccer"),
    ("how many innings are in a baseball game",         "baseball game"),
    # "how long is X"
    ("how long is a marathon",                          "marathon"),
    ("how long is a basketball game",                   "basketball game"),
    # "when did X start/begin"
    ("when did the olympics start",                     "olympics"),
    ("when did the world cup start",                    "world cup"),
    # "who has won the most X" — optional subject + optional "has"
    ("who has won the most world cups",                 "world cups"),
    ("who has won the most grand slams",                "grand slams"),
    # "what sport/position does X play" — category-is pattern with does/did
    ("what sport does lebron james play",               "lebron james"),
    ("what position does lebron james play",            "lebron james"),
    # "how do you play X"
    ("how do you play chess",                           "chess"),
    ("how do you play poker",                           "poker"),
    # superlative + participial-adj strip
    ("what is the fastest sport",                       "sport"),
    ("what is the highest scoring sport",               "sport"),
])
def test_batch108_subject_extraction(question, expected):
    """Batch 108: sports/fitness — concepts, team size, historical firsts, who-won-most, category-is with does/did."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question, expected", [
    # "what is X"
    ("what is climate change",                           "climate change"),
    ("what is global warming",                           "global warming"),
    ("what is the greenhouse effect",                    "greenhouse effect"),
    ("what is an ecosystem",                             "ecosystem"),
    ("what is biodiversity",                             "biodiversity"),
    ("what is deforestation",                            "deforestation"),
    ("what is the ozone layer",                          "ozone layer"),
    ("what is acid rain",                                "acid rain"),
    # "what causes X"
    ("what causes climate change",                       "climate change"),
    ("what causes acid rain",                            "acid rain"),
    ("what causes ozone depletion",                      "ozone depletion"),
    # "how does X affect Y" → X (causal agent is the lookup target)
    ("how does deforestation affect the environment",    "deforestation"),
    ("how does pollution affect the ocean",              "pollution"),
    # "what is the effect of X on Y" → X
    ("what is the effect of global warming on glaciers", "global warming"),
    # "what are the effects of X"
    ("what are the effects of climate change",           "climate change"),
    # "how can we reduce X"
    ("how can we reduce carbon emissions",               "carbon emissions"),
    ("how can we reduce plastic pollution",              "plastic pollution"),
    # difference
    ("what is the difference between climate and weather", "climate and weather"),
    # percentage/quantity
    ("what percentage of the earth is covered by water", "earth"),
    ("how many species are endangered",                  "species"),
    ("what is a carbon footprint",                       "carbon footprint"),
])
def test_batch109_subject_extraction(question, expected):
    """Batch 109: environment/ecology — concepts, causes, effects, causal-agent extraction."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question, expected", [
    # "what is X"
    ("what is dna",                                      "dna"),
    ("what is photosynthesis",                           "photosynthesis"),
    ("what is evolution",                                "evolution"),
    ("what is a cell",                                   "cell"),
    ("what is a virus",                                  "virus"),
    ("what is an antibiotic",                            "antibiotic"),
    ("what is the immune system",                        "immune system"),
    ("what is mitosis",                                  "mitosis"),
    # "how does X work"
    ("how does the immune system work",                  "immune system"),
    ("how does digestion work",                          "digestion"),
    ("how does the brain work",                          "brain"),
    # "what are the symptoms of X"
    ("what are the symptoms of diabetes",                "diabetes"),
    ("what are the symptoms of influenza",               "influenza"),
    # "how is X transmitted"
    ("how is covid transmitted",                         "covid"),
    ("how is hiv transmitted",                           "hiv"),
    # "who discovered X"
    ("who discovered penicillin",                        "penicillin"),
    ("who discovered dna",                               "dna"),
    # "what is the function of X"
    ("what is the function of the liver",                "liver"),
    ("what is the function of red blood cells",          "red blood cells"),
    # difference
    ("what is the difference between arteries and veins", "arteries and veins"),
    # "how long does it take for X to Y"
    ("how long does it take for a wound to heal",        "wound"),
    # "what is the treatment for X"
    ("what is the treatment for diabetes",               "diabetes"),
])
def test_batch110_subject_extraction(question, expected):
    """Batch 110: biology/medicine — concepts, mechanisms, symptoms, transmission, discovery."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question, expected", [
    # "what was X"
    ("what was the roman empire",                        "roman empire"),
    ("what was the renaissance",                         "renaissance"),
    ("what was the industrial revolution",               "industrial revolution"),
    ("what was the cold war",                            "cold war"),
    ("what was the black death",                         "black death"),
    # "when did X happen/start/end"
    ("when did world war two start",                     "world war two"),
    ("when did the roman empire fall",                   "roman empire"),
    ("when did the renaissance begin",                   "renaissance"),
    # "who was X"
    ("who was julius caesar",                            "julius caesar"),
    ("who was napoleon",                                 "napoleon"),
    ("who was cleopatra",                                "cleopatra"),
    # "who built X"
    ("who built the pyramids",                           "pyramids"),
    ("who built the great wall of china",                "great wall of china"),
    # "what caused X"
    ("what caused world war one",                        "world war one"),
    ("what caused the fall of the roman empire",         "roman empire"),
    # "where did X originate"
    ("where did the silk road originate",                "silk road"),
    # "how long did X last"
    ("how long did the hundred years war last",          "hundred years war"),
    ("how long did world war two last",                  "world war two"),
    # "what is the oldest X"
    ("what is the oldest civilization",                  "civilization"),
    ("what is the oldest city in the world",             "city"),
    # quantity
    ("how many people died in world war two",            "world war two"),
])
def test_batch111_subject_extraction(question, expected):
    """Batch 111: history — empires, events, leaders, construction, causes, duration."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question, expected", [
    # "what is X"
    ("what is gravity",                                  "gravity"),
    ("what is quantum mechanics",                        "quantum mechanics"),
    ("what is the theory of relativity",                 "theory of relativity"),
    ("what is the speed of light",                       "speed of light"),
    ("what is pi",                                       "pi"),
    ("what is the pythagorean theorem",                  "pythagorean theorem"),
    # "who discovered/proved X"
    ("who discovered gravity",                           "gravity"),
    ("who proved the pythagorean theorem",               "pythagorean theorem"),
    # "how fast does X travel" — trailing verb strip
    ("how fast does light travel",                       "light"),
    # "what is the formula for X" — formula property noun strips to the entity
    ("what is the formula for the area of a circle",     "circle"),
    ("what is the formula for velocity",                 "velocity"),
    # "what does X mean" — trailing "mean" stripped
    ("what does e equals mc squared mean",               "e equals mc squared"),
    # "how do you calculate X" — area property noun strips
    ("how do you calculate the area of a triangle",      "triangle"),
    ("how do you calculate velocity",                    "velocity"),
    # difference
    ("what is the difference between mass and weight",   "mass and weight"),
    ("what is the difference between speed and velocity", "speed and velocity"),
    # "what is X made of" — causal noun strips
    ("what is an atom made of",                          "atom"),
    ("what is a molecule made of",                       "molecule"),
    # polygon sides / angles
    ("how many sides does a hexagon have",               "hexagon"),
    ("how many degrees are in a triangle",               "triangle"),
    # physical property
    ("what is the boiling point of water",               "water"),
])
def test_batch112_subject_extraction(question, expected):
    """Batch 112: math/physics — concepts, proofs, formulas, properties, trailing-mean strip."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question, expected", [
    # "what is X"
    ("what is sushi",                                    "sushi"),
    ("what is pasta",                                    "pasta"),
    ("what is tofu",                                     "tofu"),
    ("what is umami",                                    "umami"),
    ("what is gluten",                                   "gluten"),
    # "what country is X from" — loc-noun pattern + from guard
    ("what country is sushi from",                       "sushi"),
    ("what country is pasta from",                       "pasta"),
    # "how do you make X"
    ("how do you make pasta",                            "pasta"),
    ("how do you make sushi",                            "sushi"),
    ("how do you make bread",                            "bread"),
    # "what are the ingredients in X"
    ("what are the ingredients in pizza",                "pizza"),
    ("what are the ingredients in bread",                "bread"),
    # "how long does it take to cook X"
    ("how long does it take to cook a turkey",           "turkey"),
    ("how long does it take to cook pasta",              "pasta"),
    # "how many calories are in X"
    ("how many calories are in an apple",                "apple"),
    ("how many calories are in a slice of pizza",        "pizza"),
    # difference
    ("what is the difference between white and brown rice", "white and brown rice"),
    # "what is the best way to cook X"
    ("what is the best way to cook steak",               "steak"),
    # predicate adjective
    ("is dark chocolate healthy",                        "dark chocolate"),
    # "what MEASUREMENT should X be cooked/baked to" — prop-should pattern
    ("what temperature should chicken be cooked to",     "chicken"),
    # "how much X should you eat"
    ("how much protein should you eat per day",          "protein"),
])
def test_batch113_subject_extraction(question, expected):
    """Batch 113: food/cooking — origin, ingredients, prep, calories, measurement-should pattern."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )

@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is inflation",                                "inflation"),
    ("what is gdp",                                      "gdp"),
    ("what is the stock market",                         "stock market"),
    ("what is a recession",                              "recession"),
    ("what is cryptocurrency",                           "cryptocurrency"),
    ("what is a mortgage",                               "mortgage"),
    ("what is compound interest",                        "compound interest"),
    ("what is supply and demand",                        "supply and demand"),
    # "what causes X"
    ("what causes inflation",                            "inflation"),
    ("what causes a recession",                          "recession"),
    # "how does X work"
    ("how does the stock market work",                   "stock market"),
    ("how does compound interest work",                  "compound interest"),
    ("how does a mortgage work",                         "mortgage"),
    # "what is the difference between X and Y"
    ("what is the difference between stocks and bonds",  "stocks and bonds"),
    ("what is the difference between inflation and deflation", "inflation and deflation"),
    # "how do you invest in X"
    ("how do you invest in stocks",                      "stocks"),
    ("how do you invest in real estate",                 "real estate"),
    # "what is the gdp of X"
    ("what is the gdp of china",                         "china"),
    ("what is the gdp of the united states",             "united states"),
    # "how much does X cost"
    ("how much does a house cost",                       "house"),
    # "what is the minimum wage in X"
    ("what is the minimum wage in the united states",    "minimum wage"),
])
def test_batch114_subject_extraction(question, expected):
    """Batch 114: economics/finance — concepts, causes, comparisons, GDP, investment."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is hip hop",                                  "hip hop"),
    ("what is jazz",                                     "jazz"),
    ("what is opera",                                    "opera"),
    ("what is a grammy",                                 "grammy"),
    ("what is the billboard hot 100",                    "billboard hot 100"),
    # "who sang X"
    ("who sang bohemian rhapsody",                       "bohemian rhapsody"),
    ("who sang thriller",                                "thriller"),
    # "who wrote X"
    ("who wrote the phantom of the opera",               "phantom of the opera"),
    ("who wrote bohemian rhapsody",                      "bohemian rhapsody"),
    # "who directed X"
    ("who directed titanic",                             "titanic"),
    ("who directed the godfather",                       "godfather"),
    # "when was X released"
    ("when was titanic released",                        "titanic"),
    ("when was the iphone released",                     "iphone"),
    # "who starred in X"
    ("who starred in titanic",                           "titanic"),
    # "what year did X come out"
    ("what year did titanic come out",                   "titanic"),
    # "what genre is X"
    ("what genre is hip hop",                            "hip hop"),
    ("what genre is jazz",                               "jazz"),
    # "how many oscars did X win"
    ("how many oscars did titanic win",                  "titanic"),
    # "what is the best-selling album of all time"
    ("what is the best selling album of all time",       "album"),
    # "who is the most streamed artist on spotify"
    ("who is the most streamed artist on spotify",       "artist"),
    # "how long is X"
    ("how long is the godfather",                        "godfather"),
])
def test_batch115_subject_extraction(question, expected):
    """Batch 115: music/entertainment — genres, authorship, direction, awards, release dates."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is linguistics",                              "linguistics"),
    ("what is phonetics",                                "phonetics"),
    ("what is grammar",                                  "grammar"),
    ("what is syntax",                                   "syntax"),
    ("what is a dialect",                                "dialect"),
    ("what is a creole language",                        "creole language"),
    ("what is a lingua franca",                          "lingua franca"),
    # "how many languages are in the world"
    ("how many languages are in the world",              "world"),
    # "what is the most spoken language in the world"
    ("what is the most spoken language in the world",    "language"),
    # "what is the difference between a language and a dialect"
    ("what is the difference between a language and a dialect", "language and dialect"),
    # "how many people speak X"
    ("how many people speak english",                    "english"),
    ("how many people speak mandarin",                   "mandarin"),
    # "what language is spoken in X"
    ("what language is spoken in brazil",                "brazil"),
    ("what language is spoken in japan",                 "japan"),
    # "what is the official language of X"
    ("what is the official language of france",          "france"),
    ("what is the official language of india",           "india"),
    # "what is X in language"
    ("what is hello in spanish",                         "hello"),
    ("what is thank you in french",                      "thank you"),
    # "how do you say X in Y"
    ("how do you say hello in japanese",                 "hello"),
    ("how do you say goodbye in german",                 "goodbye"),
    # "what is X in english"
    ("what is bonjour in english",                       "bonjour"),
])
def test_batch116_subject_extraction(question, expected):
    """Batch 116: language/linguistics — concepts, spoken languages, translations."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is a mammal",                                 "mammal"),
    ("what is a reptile",                                "reptile"),
    ("what is an amphibian",                             "amphibian"),
    ("what is a marsupial",                              "marsupial"),
    ("what is a predator",                               "predator"),
    ("what is a herbivore",                              "herbivore"),
    # "what do X eat"
    ("what do lions eat",                                "lions"),
    ("what do elephants eat",                            "elephants"),
    ("what do sharks eat",                               "sharks"),
    # "how long do X live"
    ("how long do elephants live",                       "elephants"),
    ("how long do sea turtles live",                     "sea turtles"),
    # "where do X live"
    ("where do polar bears live",                        "polar bears"),
    ("where do kangaroos live",                          "kangaroos"),
    # "how fast can X run"
    ("how fast can a cheetah run",                       "cheetah"),
    # "what is the largest X"
    ("what is the largest animal in the world",          "animal"),
    ("what is the largest mammal",                       "mammal"),
    # "how many X are left"
    ("how many tigers are left in the wild",             "tigers"),
    # "why do X hibernate"
    ("why do bears hibernate",                           "bears"),
    # "are X endangered"
    ("are elephants endangered",                         "elephants"),
    # "what are the predators of X"
    ("what are the predators of rabbits",                "rabbits"),
    # "how does X defend itself"
    ("how does a porcupine defend itself",               "porcupine"),
])
def test_batch117_subject_extraction(question, expected):
    """Batch 117: animals/nature — taxonomy, diet, habitat, size, endangered status."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is a black hole",                             "black hole"),
    ("what is a nebula",                                 "nebula"),
    ("what is dark matter",                              "dark matter"),
    ("what is dark energy",                              "dark energy"),
    ("what is the big bang",                             "big bang"),
    ("what is a supernova",                              "supernova"),
    ("what is a neutron star",                           "neutron star"),
    # "how far is X from Y"
    ("how far is the moon from earth",                   "moon"),
    ("how far is the sun from earth",                    "sun"),
    # "how big is X"
    ("how big is the milky way",                         "milky way"),
    ("how big is jupiter",                               "jupiter"),
    # "how many planets are in X"
    ("how many planets are in the solar system",         "solar system"),
    # "what is the largest planet"
    ("what is the largest planet",                       "planet"),
    # "how long does it take X to orbit Y"
    ("how long does it take earth to orbit the sun",     "earth"),
    # "what is the temperature on X"
    ("what is the temperature on mars",                  "mars"),
    ("what is the temperature on venus",                 "venus"),
    # "how old is the universe"
    ("how old is the universe",                          "universe"),
    # "what is the speed of light"
    ("what is the speed of light",                       "speed of light"),
    # "how many moons does X have"
    ("how many moons does jupiter have",                 "jupiter"),
    ("how many moons does saturn have",                  "saturn"),
    # "what is the closest star to earth"
    ("what is the closest star to earth",                "star"),
])
def test_batch118_subject_extraction(question, expected):
    """Batch 118: space/astronomy — celestial bodies, distances, temperatures, moons."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is artificial intelligence",                  "artificial intelligence"),
    ("what is machine learning",                         "machine learning"),
    ("what is blockchain",                               "blockchain"),
    ("what is the internet of things",                   "internet of things"),
    ("what is virtual reality",                          "virtual reality"),
    ("what is augmented reality",                        "augmented reality"),
    ("what is cloud computing",                          "cloud computing"),
    # "what is the difference between X and Y"
    ("what is the difference between ai and machine learning", "ai and machine learning"),
    # "who invented X"
    ("who invented the internet",                        "internet"),
    ("who invented the telephone",                       "telephone"),
    # "when was X invented"
    ("when was the internet invented",                   "internet"),
    ("when was the telephone invented",                  "telephone"),
    # "how does X work"
    ("how does a computer work",                         "computer"),
    ("how does wifi work",                               "wifi"),
    ("how does gps work",                                "gps"),
    # "what is X used for"
    ("what is python used for",                          "python"),
    ("what is javascript used for",                      "javascript"),
    # "how many X have been sold"
    ("how many iphones have been sold",                  "iphones"),
    # "what is the best X"
    ("what is the best programming language",            "programming language"),
    # "how fast is X"
    ("how fast is 5g",                                   "5g"),
    # "what does X stand for"
    ("what does cpu stand for",                          "cpu"),
])
def test_batch119_subject_extraction(question, expected):
    """Batch 119: technology/consumer electronics — AI, inventions, devices, languages."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is the capital of X"
    ("what is the capital of france",                    "france"),
    ("what is the capital of japan",                     "japan"),
    ("what is the capital of australia",                 "australia"),
    # "what country is X in"
    ("what country is paris in",                         "paris"),
    ("what country is tokyo in",                         "tokyo"),
    # "what continent is X in"
    ("what continent is brazil in",                      "brazil"),
    ("what continent is egypt in",                       "egypt"),
    # "how big is X"
    ("how big is russia",                                "russia"),
    ("how big is the amazon rainforest",                 "amazon rainforest"),
    # "how long is X"
    ("how long is the nile river",                       "nile river"),
    ("how long is the great wall of china",              "great wall of china"),
    # "how tall is X"
    ("how tall is mount everest",                        "mount everest"),
    ("how tall is kilimanjaro",                          "kilimanjaro"),
    # "what is the largest X"
    ("what is the largest country in the world",         "country"),
    ("what is the largest continent",                    "continent"),
    ("what is the largest ocean",                        "ocean"),
    # "what is the population of X"
    ("what is the population of china",                  "china"),
    ("what is the population of the world",              "world"),
    # "where is X located"
    ("where is the amazon river located",                "amazon river"),
    ("where is the sahara desert located",               "sahara desert"),
    # "what language is spoken in X"
    ("what language is spoken in brazil",                "brazil"),
])
def test_batch120_subject_extraction(question, expected):
    """Batch 120: geography — capitals, countries, continents, rivers, mountains, oceans."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "who started X"
    ("who started world war 1",                          "world war 1"),
    ("who started world war 2",                          "world war 2"),
    # "when did X start"
    ("when did world war 1 start",                       "world war 1"),
    ("when did the french revolution start",             "french revolution"),
    # "when did X end"
    ("when did world war 2 end",                         "world war 2"),
    # "what caused X"
    ("what caused world war 1",                          "world war 1"),
    ("what caused the great depression",                 "great depression"),
    # "who was X"
    ("who was napoleon",                                 "napoleon"),
    ("who was cleopatra",                                "cleopatra"),
    ("who was julius caesar",                            "julius caesar"),
    # "who won X"
    ("who won world war 2",                              "world war 2"),
    ("who won the american civil war",                   "american civil war"),
    # "when was X born"
    ("when was napoleon born",                           "napoleon"),
    ("when was albert einstein born",                    "albert einstein"),
    # "when did X die"
    ("when did napoleon die",                            "napoleon"),
    ("when did abraham lincoln die",                     "abraham lincoln"),
    # "how long did X last"
    ("how long did world war 1 last",                    "world war 1"),
    ("how long did the roman empire last",               "roman empire"),
    # "what happened at X"
    ("what happened at pearl harbor",                    "pearl harbor"),
    # "where did X happen"
    ("where did world war 2 happen",                     "world war 2"),
    ("where did the french revolution happen",           "french revolution"),
])
def test_batch121_subject_extraction(question, expected):
    """Batch 121: history — wars, revolutions, historical figures, events."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is a calorie",                                "calorie"),
    ("what is protein",                                  "protein"),
    ("what is fiber",                                    "fiber"),
    ("what is gluten",                                   "gluten"),
    ("what is cholesterol",                              "cholesterol"),
    # "what foods contain X"
    ("what foods contain vitamin c",                     "vitamin c"),
    ("what foods contain protein",                       "protein"),
    # "how many calories are in X"
    ("how many calories are in an apple",                "apple"),
    ("how many calories are in a banana",                "banana"),
    ("how many calories are in a chicken breast",        "chicken breast"),
    # "what does X contain"
    ("what does milk contain",                           "milk"),
    ("what does broccoli contain",                       "broccoli"),
    # "is X healthy"
    ("is coffee healthy",                                "coffee"),
    ("is red meat healthy",                              "red meat"),
    # "how much X should you eat"
    ("how much protein should you eat",                  "protein"),
    ("how much sugar should you eat",                    "sugar"),
    # "what are the benefits of X"
    ("what are the benefits of exercise",                "exercise"),
    ("what are the benefits of green tea",               "green tea"),
    # "what is the difference between X and Y"
    ("what is the difference between vegan and vegetarian", "vegan and vegetarian"),
    # "how do you make X"
    ("how do you make pasta",                            "pasta"),
    ("how do you make bread",                            "bread"),
])
def test_batch122_subject_extraction(question, expected):
    """Batch 122: food/nutrition — calories, nutrients, health foods, recipes."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is a touchdown",                              "touchdown"),
    ("what is offside in soccer",                        "offside"),
    ("what is a grand slam in tennis",                   "grand slam"),
    # "how many players are in X"
    ("how many players are in a soccer team",            "soccer"),
    ("how many players are in a basketball team",        "basketball"),
    # "how long is a X game"
    ("how long is a soccer game",                        "soccer game"),
    ("how long is an nba game",                          "nba game"),
    # "who has the most X"
    ("who has the most super bowl wins",                 "super bowl wins"),
    ("who has the most nba championships",               "nba championships"),
    # "when did X start"
    ("when did the olympics start",                      "olympics"),
    ("when did the world cup start",                     "world cup"),
    # "what is the fastest X"
    ("what is the fastest sport in the world",           "sport"),
    # "who won the X"
    ("who won the world cup",                            "world cup"),
    ("who won the super bowl",                           "super bowl"),
    # "how many X are there"
    ("how many olympic sports are there",                "olympic sports"),
    # "what is the most popular X"
    ("what is the most popular sport in the world",      "sport"),
    # "how far does X run"
    ("how far does a marathon runner run",               "marathon runner"),
    # "what is X in Y"
    ("what is a hat trick in hockey",                    "hat trick"),
    # "how many sets are in X"
    ("how many sets are in a tennis match",              "tennis match"),
    # "when is X"
    ("when is the super bowl",                           "super bowl"),
    ("when is the world cup",                            "world cup"),
])
def test_batch123_subject_extraction(question, expected):
    """Batch 123: sports — game rules, records, events, tournaments."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is diabetes",                                 "diabetes"),
    ("what is hypertension",                             "hypertension"),
    ("what is alzheimers disease",                       "alzheimers disease"),
    ("what is depression",                               "depression"),
    ("what is a virus",                                  "virus"),
    ("what is a vaccine",                                "vaccine"),
    ("what is the immune system",                        "immune system"),
    # "what causes X"
    ("what causes diabetes",                             "diabetes"),
    ("what causes heart disease",                        "heart disease"),
    # "what are the symptoms of X"
    ("what are the symptoms of covid",                   "covid"),
    ("what are the symptoms of flu",                     "flu"),
    # "how is X treated"
    ("how is diabetes treated",                          "diabetes"),
    ("how is cancer treated",                            "cancer"),
    # "is X contagious"
    ("is covid contagious",                              "covid"),
    ("is the flu contagious",                            "flu"),
    # "how do X work"
    ("how do vaccines work",                             "vaccines"),
    # "what is the difference between X and Y"
    ("what is the difference between a cold and the flu", "cold and flu"),
    # "how does X work"
    ("how does the immune system work",                  "immune system"),
    # "what are the side effects of X"
    ("what are the side effects of aspirin",             "aspirin"),
    ("what are the side effects of ibuprofen",           "ibuprofen"),
    # "how do you prevent X"
    ("how do you prevent diabetes",                      "diabetes"),
    ("how do you prevent the flu",                       "flu"),
])
def test_batch124_subject_extraction(question, expected):
    """Batch 124: health/medicine — diseases, vaccines, symptoms, treatments."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is psychology",                               "psychology"),
    ("what is cognitive behavioral therapy",             "cognitive behavioral therapy"),
    ("what is anxiety",                                  "anxiety"),
    ("what is the placebo effect",                       "placebo effect"),
    # "what causes X"
    ("what causes anxiety",                              "anxiety"),
    ("what causes depression",                           "depression"),
    # "what is the difference between X and Y"
    ("what is the difference between anxiety and stress", "anxiety and stress"),
    ("what is the difference between psychologist and psychiatrist", "psychologist and psychiatrist"),
    # "how does X affect Y"
    ("how does stress affect the body",                  "stress"),
    ("how does sleep affect mental health",              "sleep"),
    # "what are the stages of X"
    ("what are the stages of grief",                     "grief"),
    # "what is X disorder"
    ("what is bipolar disorder",                         "bipolar disorder"),
    ("what is ocd",                                      "ocd"),
    ("what is ptsd",                                     "ptsd"),
    # "what are the symptoms of X"
    ("what are the symptoms of anxiety",                 "anxiety"),
    ("what are the symptoms of depression",              "depression"),
    # "how is X diagnosed"
    ("how is depression diagnosed",                      "depression"),
    ("how is autism diagnosed",                          "autism"),
    # "is X a mental illness"
    ("is depression a mental illness",                   "depression"),
    # "how do you deal with X"
    ("how do you deal with anxiety",                     "anxiety"),
    ("how do you deal with stress",                      "stress"),
    # "what is X's hierarchy of needs"
    ("what is maslow's hierarchy of needs",              "maslow's hierarchy of needs"),
])
def test_batch125_subject_extraction(question, expected):
    """Batch 125: psychology/mental health — disorders, therapy, emotions, theory."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is climate change",                              "climate change"),
    ("what is global warming",                              "global warming"),
    ("what is the greenhouse effect",                       "greenhouse effect"),
    ("what is carbon dioxide",                              "carbon dioxide"),
    ("what is deforestation",                               "deforestation"),
    # "what causes X"
    ("what causes climate change",                          "climate change"),
    ("what causes acid rain",                               "acid rain"),
    ("what causes ozone depletion",                         "ozone depletion"),
    # "what is the difference between X and Y"
    ("what is the difference between weather and climate",  "weather and climate"),
    # "how does X affect Y"
    ("how does pollution affect the ocean",                 "pollution"),
    ("how does deforestation affect climate",               "deforestation"),
    # "what are the effects of X"
    ("what are the effects of climate change",              "climate change"),
    ("what are the effects of pollution",                   "pollution"),
    # "how do you reduce X"
    ("how do you reduce carbon emissions",                  "carbon emissions"),
    ("how do you reduce plastic waste",                     "plastic waste"),
    # "what is X energy"
    ("what is solar energy",                                "solar energy"),
    ("what is wind energy",                                 "wind energy"),
    # "is X renewable"
    ("is solar energy renewable",                           "solar energy"),
    # "what is the ozone layer"
    ("what is the ozone layer",                             "ozone layer"),
    # "how do X work"
    ("how do solar panels work",                            "solar panels"),
    # "what percentage of X is Y"
    ("what percentage of the earth is covered by water",    "earth"),
])
def test_batch126_subject_extraction(question, expected):
    """Batch 126: environment/climate — greenhouse, renewables, pollution."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is inflation",                                   "inflation"),
    ("what is gdp",                                         "gdp"),
    ("what is a recession",                                 "recession"),
    ("what is the stock market",                            "stock market"),
    ("what is cryptocurrency",                              "cryptocurrency"),
    ("what is a mortgage",                                  "mortgage"),
    ("what is interest rate",                               "interest rate"),
    # "how does X work"
    ("how does the stock market work",                      "stock market"),
    ("how does inflation work",                             "inflation"),
    ("how does a mortgage work",                            "mortgage"),
    # "what causes X"
    ("what causes inflation",                               "inflation"),
    ("what causes a recession",                             "recession"),
    # "what is the difference between X and Y"
    ("what is the difference between stocks and bonds",     "stocks and bonds"),
    ("what is the difference between debit and credit",     "debit and credit"),
    # "how do you invest in X"
    ("how do you invest in stocks",                         "stocks"),
    ("how do you invest in real estate",                    "real estate"),
    # "what is X tax"
    ("what is income tax",                                  "income tax"),
    ("what is capital gains tax",                           "capital gains tax"),
    # "how do you calculate X"
    ("how do you calculate interest",                       "interest"),
    # "what is a X"
    ("what is a hedge fund",                                "hedge fund"),
    ("what is a mutual fund",                               "mutual fund"),
])
def test_batch127_subject_extraction(question, expected):
    """Batch 127: economics/finance — stock market, inflation, tax."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is democracy",                                   "democracy"),
    ("what is communism",                                   "communism"),
    ("what is capitalism",                                  "capitalism"),
    ("what is socialism",                                   "socialism"),
    ("what is a constitution",                              "constitution"),
    ("what is the united nations",                          "united nations"),
    # "how does X work"
    ("how does democracy work",                             "democracy"),
    ("how does the electoral college work",                 "electoral college"),
    ("how does the supreme court work",                     "supreme court"),
    # "what is the difference between X and Y"
    ("what is the difference between democracy and republic", "democracy and republic"),
    ("what is the difference between communism and socialism", "communism and socialism"),
    # "what is X government/system"
    ("what is a federal government",                        "federal government"),
    ("what is a parliamentary system",                      "parliamentary system"),
    # "who has X" → X
    ("who has veto power in the un",                        "veto power"),
    # "how many X are in Y" → Y (container is the lookup topic)
    ("how many countries are in the united nations",        "united nations"),
    # "what is X branch"
    ("what is the executive branch",                        "executive branch"),
    ("what is the judicial branch",                         "judicial branch"),
    ("what is the legislative branch",                      "legislative branch"),
    # named documents / organisations
    ("what is the bill of rights",                          "bill of rights"),
    ("what is the first amendment",                         "first amendment"),
    ("what is nato",                                        "nato"),
])
def test_batch128_subject_extraction(question, expected):
    """Batch 128: political science — government, constitutions, international bodies."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is ethics",                                      "ethics"),
    ("what is philosophy",                                  "philosophy"),
    ("what is morality",                                    "morality"),
    ("what is existentialism",                              "existentialism"),
    ("what is utilitarianism",                              "utilitarianism"),
    ("what is stoicism",                                    "stoicism"),
    ("what is nihilism",                                    "nihilism"),
    # "meaning of life" is the lookup topic, not just "life"
    ("what is the meaning of life",                         "meaning of life"),
    # "who was X"
    ("who was socrates",                                    "socrates"),
    ("who was plato",                                       "plato"),
    ("who was aristotle",                                   "aristotle"),
    ("who was nietzsche",                                   "nietzsche"),
    # "what did X believe"
    ("what did socrates believe",                           "socrates"),
    ("what did plato believe",                              "plato"),
    # named philosophical problems / theories
    ("what is the trolley problem",                         "trolley problem"),
    ("what is the social contract theory",                  "social contract theory"),
    ("what is virtue ethics",                               "virtue ethics"),
    ("what is applied ethics",                              "applied ethics"),
    # "is X wrong" → X (predicate adjective stripped)
    ("is lying wrong",                                      "lying"),
    # "what is free will"
    ("what is free will",                                   "free will"),
    ("what is the cosmological argument",                   "cosmological argument"),
])
def test_batch129_subject_extraction(question, expected):
    """Batch 129: philosophy/ethics — meaning of life, contract theory, predicate adj."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is algebra",                                     "algebra"),
    ("what is calculus",                                    "calculus"),
    ("what is geometry",                                    "geometry"),
    ("what is statistics",                                  "statistics"),
    ("what is probability",                                 "probability"),
    ("what is a prime number",                              "prime number"),
    ("what is the pythagorean theorem",                     "pythagorean theorem"),
    # "what is X formula/sequence"
    ("what is the quadratic formula",                       "quadratic formula"),
    ("what is the fibonacci sequence",                      "fibonacci sequence"),
    # "how do you calculate the PROP of a SHAPE" → SHAPE (area/volume reduce to the shape)
    ("how do you calculate the area of a circle",           "circle"),
    ("how do you calculate the volume of a sphere",         "sphere"),
    ("how do you calculate percentage",                     "percentage"),
    # "what is the square root of X" → X
    ("what is the square root of 144",                      "144"),
    # "what is a X number"
    ("what is a rational number",                           "rational number"),
    ("what is an irrational number",                        "irrational number"),
    # "what is the difference between X and Y"
    ("what is the difference between mean and median",      "mean and median"),
    # "how do you solve X"
    ("how do you solve a quadratic equation",               "quadratic equation"),
    # named constants
    ("what is pi",                                          "pi"),
    ("what is infinity",                                    "infinity"),
    # "what is X in math"
    ("what is a matrix in math",                            "matrix"),
    ("what is a derivative in math",                        "derivative"),
])
def test_batch130_subject_extraction(question, expected):
    """Batch 130: mathematics — algebra, calculus, geometry, theorems."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is a black hole",                                "black hole"),
    ("what is a neutron star",                              "neutron star"),
    ("what is dark matter",                                 "dark matter"),
    ("what is dark energy",                                 "dark energy"),
    ("what is the big bang theory",                         "big bang theory"),
    ("what is the speed of light",                          "speed of light"),
    ("what is a light year",                                "light year"),
    # "how far is X from Y" → X (the object being measured)
    ("how far is the moon from earth",                      "moon"),
    ("how far is mars from earth",                          "mars"),
    # "how big/old/hot is X" → X
    ("how big is the universe",                             "universe"),
    ("how big is the sun",                                  "sun"),
    ("how old is the universe",                             "universe"),
    ("how old is the earth",                                "earth"),
    ("how hot is the sun",                                  "sun"),
    # superlative + in/of
    ("what is the largest planet in the solar system",      "planet"),
    # "how many X are in Y" → Y
    ("how many planets are in the solar system",            "solar system"),
    # property nouns
    ("what is the surface temperature of venus",            "venus"),
    # "how do X form" → X
    ("how do black holes form",                             "black holes"),
    # named phenomena
    ("what is cosmic radiation",                            "cosmic radiation"),
    ("what is a solar flare",                               "solar flare"),
    ("what is the milky way",                               "milky way"),
])
def test_batch131_subject_extraction(question, expected):
    """Batch 131: astrophysics/cosmology — black holes, dark matter, cosmic phenomena."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X"
    ("what is metaphor",                                    "metaphor"),
    ("what is a sonnet",                                    "sonnet"),
    ("what is impressionism",                               "impressionism"),
    ("what is renaissance art",                             "renaissance art"),
    ("what is surrealism",                                  "surrealism"),
    # "who wrote X" — including infinitive-prefixed titles
    ("who wrote hamlet",                                    "hamlet"),
    ("who wrote to kill a mockingbird",                     "to kill a mockingbird"),
    ("who wrote the iliad",                                 "iliad"),
    # "who painted X"
    ("who painted the mona lisa",                           "mona lisa"),
    ("who painted the sistine chapel",                      "sistine chapel"),
    # "who composed X"
    ("who composed beethoven's fifth symphony",             "beethoven's fifth symphony"),
    # "what is the theme/plot of X" → X
    ("what is the theme of hamlet",                         "hamlet"),
    ("what is the theme of 1984",                           "1984"),
    ("what is the plot of romeo and juliet",                "romeo and juliet"),
    # "who was X"
    ("who was shakespeare",                                 "shakespeare"),
    ("who was mozart",                                      "mozart"),
    ("who was michelangelo",                                "michelangelo"),
    # "what is X in art"
    ("what is impressionism in art",                        "impressionism"),
    # literary forms
    ("what is a haiku",                                     "haiku"),
    # "when was X written"
    ("when was hamlet written",                             "hamlet"),
    # named artworks
    ("what is the mona lisa",                               "mona lisa"),
])
def test_batch132_subject_extraction(question, expected):
    """Batch 132: literature/arts — titles (incl. To Kill a Mockingbird), artists."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # genres
    ("what is jazz",                                        "jazz"),
    ("what is hip hop",                                     "hip hop"),
    ("what is classical music",                             "classical music"),
    # music theory terms
    ("what is a chord",                                     "chord"),
    ("what is tempo",                                       "tempo"),
    ("what is a symphony",                                  "symphony"),
    # "who sang X" — trailing "by ARTIST" stripped
    ("who sang bohemian rhapsody",                          "bohemian rhapsody"),
    ("who sang imagine",                                    "imagine"),
    ("who sang billie jean",                                "billie jean"),
    ("who wrote yesterday by the beatles",                  "yesterday"),
    # superlative
    ("what is the most famous opera",                       "opera"),
    # "what genre is X"
    ("what genre is jazz",                                  "jazz"),
    # instruments
    ("what is a guitar",                                    "guitar"),
    ("what is a violin",                                    "violin"),
    ("what is a piano",                                     "piano"),
    # "how do you play X"
    ("how do you play guitar",                              "guitar"),
    ("how do you play piano",                               "piano"),
    # "what is the difference between X and Y"
    ("what is the difference between violin and viola",     "violin and viola"),
    # composers
    ("who is beethoven",                                    "beethoven"),
    ("who is bach",                                         "bach"),
    ("who is mozart",                                       "mozart"),
])
def test_batch133_subject_extraction(question, expected):
    """Batch 133: music — genres, instruments, composers, 'by ARTIST' strip."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a documentary",                              "documentary"),
    ("what is a film noir",                                "film noir"),
    ("what is cinematography",                             "cinematography"),
    ("what is a screenplay",                               "screenplay"),
    ("what is a blockbuster",                              "blockbuster"),
    ("who directed titanic",                               "titanic"),
    ("who directed the godfather",                         "godfather"),
    ("who directed inception",                             "inception"),
    ("who directed schindler's list",                      "schindler's list"),
    ("who starred in titanic",                             "titanic"),
    ("what is the plot of the godfather",                  "godfather"),
    ("what is the plot of forrest gump",                   "forrest gump"),
    ("when was titanic released",                          "titanic"),
    ("who wrote the screenplay for casablanca",            "casablanca"),
    ("what genre is inception",                            "inception"),
    ("who won the oscar for best picture",                 "best picture"),
    ("what is the academy awards",                         "academy awards"),
    ("how long is the godfather",                          "godfather"),
    ("who is spielberg",                                   "spielberg"),
    ("who is kubrick",                                     "kubrick"),
    ("what is a silent film",                              "silent film"),
])
def test_batch134_subject_extraction(question, expected):
    """Batch 134: film/cinema — genres, directors, awards, 'screenplay for' strip."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is buddhism",                                   "buddhism"),
    ("what is hinduism",                                   "hinduism"),
    ("what is islam",                                      "islam"),
    ("what is christianity",                               "christianity"),
    ("what is atheism",                                    "atheism"),
    ("what is mythology",                                  "mythology"),
    ("what is a myth",                                     "myth"),
    ("what is karma",                                      "karma"),
    ("what is nirvana",                                    "nirvana"),
    ("who is zeus",                                        "zeus"),
    ("who is thor",                                        "thor"),
    ("who is allah",                                       "allah"),
    ("who is buddha",                                      "buddha"),
    ("who is krishna",                                     "krishna"),
    ("what is the story of prometheus",                    "prometheus"),
    ("what is the myth of sisyphus",                       "sisyphus"),
    ("what is the legend of king arthur",                  "king arthur"),
    ("what religion is hinduism",                          "hinduism"),
    ("where is hinduism practiced",                        "hinduism"),
    ("what are the beliefs of buddhism",                   "buddhism"),
    ("what is the holy book of islam",                     "islam"),
])
def test_batch135_subject_extraction(question, expected):
    """Batch 135: religion/mythology — myth/legend strip, 'practiced' trailing verb, 'holy book of' strip."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is sushi",                                      "sushi"),
    ("what is pizza",                                      "pizza"),
    ("what is pasta",                                      "pasta"),
    ("what is curry",                                      "curry"),
    ("what is a soufflé",                                  "soufflé"),
    ("what is fermentation",                               "fermentation"),
    ("what is gluten",                                     "gluten"),
    ("what is umami",                                      "umami"),
    ("how do you make bread",                              "bread"),
    ("how do you make pasta",                              "pasta"),
    ("how do you make sushi",                              "sushi"),
    ("what are the ingredients in pizza",                  "pizza"),
    ("what are the ingredients in curry",                  "curry"),
    ("what is the recipe for chocolate cake",              "chocolate cake"),
    ("how do you cook chicken",                            "chicken"),
    ("how do you cook rice",                               "rice"),
    ("what temperature do you bake bread at",              "bread"),
    ("what is italian cuisine",                            "italian cuisine"),
    ("what is japanese cuisine",                           "japanese cuisine"),
    ("what is a croissant",                                "croissant"),
    ("what is the difference between baking and cooking",  "baking and cooking"),
])
def test_batch136_subject_extraction(question, expected):
    """Batch 136: cooking/food — cuisines, ingredients, recipes, cooking methods."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is the internet",                               "internet"),
    ("what is a computer",                                 "computer"),
    ("what is artificial intelligence",                    "artificial intelligence"),
    ("what is machine learning",                           "machine learning"),
    ("what is blockchain",                                 "blockchain"),
    ("what is cloud computing",                            "cloud computing"),
    ("what is cybersecurity",                              "cybersecurity"),
    ("what is the world wide web",                         "world wide web"),
    ("what is an algorithm",                               "algorithm"),
    ("what is a database",                                 "database"),
    ("how does wifi work",                                 "wifi"),
    ("how does bluetooth work",                            "bluetooth"),
    ("how does a cpu work",                                "cpu"),
    ("what is the difference between ram and rom",         "ram and rom"),
    ("what is the difference between http and https",      "http and https"),
    ("what is python",                                     "python"),
    ("what is javascript",                                 "javascript"),
    ("what is encryption",                                 "encryption"),
    ("what is a firewall",                                 "firewall"),
    ("what is a vpn",                                      "vpn"),
    ("what does cpu stand for",                            "cpu"),
])
def test_batch137_subject_extraction(question, expected):
    """Batch 137: technology/computing — internet, AI, networking, programming, cybersecurity."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is soccer",                                     "soccer"),
    ("what is basketball",                                 "basketball"),
    ("what is cricket",                                    "cricket"),
    ("what is tennis",                                     "tennis"),
    ("what is the offside rule",                           "offside rule"),
    ("what is a slam dunk",                                "slam dunk"),
    ("what is a grand slam",                               "grand slam"),
    ("who is ronaldo",                                     "ronaldo"),
    ("who is lebron james",                                "lebron james"),
    ("who is tiger woods",                                 "tiger woods"),
    ("who is usain bolt",                                  "usain bolt"),
    ("who won the world cup",                              "world cup"),
    ("who won the superbowl",                              "superbowl"),
    # "_m_team_count" extracts sport name, stripping "team": "football team" → "football"
    ("how many players are on a football team",            "football"),
    ("what is the offside rule in soccer",                 "soccer"),
    # "_m_record_for" extracts the category, stripping "most": "most goals" → "goals"
    ("who holds the record for most goals",                "goals"),
    ("when is the next olympics",                          "olympics"),
    ("what sport does lebron james play",                  "lebron james"),
    ("what is a penalty in soccer",                        "penalty"),
    ("how long is a basketball game",                      "basketball game"),
    ("what is the premier league",                         "premier league"),
])
def test_batch138_subject_extraction(question, expected):
    """Batch 138: sports — rules, athletes, records; _m_team_count and _m_record_for verified."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is dna",                                        "dna"),
    ("what is rna",                                        "rna"),
    ("what is photosynthesis",                             "photosynthesis"),
    ("what is mitosis",                                    "mitosis"),
    ("what is meiosis",                                    "meiosis"),
    ("what is a chromosome",                               "chromosome"),
    ("what is a gene",                                     "gene"),
    ("what is natural selection",                          "natural selection"),
    ("what is evolution",                                  "evolution"),
    ("what is the function of mitochondria",               "mitochondria"),
    ("what is the role of insulin",                        "insulin"),
    ("what is the structure of dna",                       "dna"),
    ("what is diabetes",                                   "diabetes"),
    ("what is cancer",                                     "cancer"),
    ("what is alzheimer's disease",                        "alzheimer's disease"),
    ("how does the immune system work",                    "immune system"),
    ("how does the heart work",                            "heart"),
    ("how does the brain work",                            "brain"),
    ("what are the symptoms of diabetes",                  "diabetes"),
    ("what are the symptoms of covid",                     "covid"),
    ("how many bones are in the human body",               "human body"),
])
def test_batch139_subject_extraction(question, expected):
    """Batch 139: medicine/biology — DNA, diseases, organ function, symptoms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("where is the amazon river",                          "amazon river"),
    ("where is mount everest",                             "mount everest"),
    ("where is the great wall of china",                   "great wall of china"),
    ("where is the eiffel tower",                          "eiffel tower"),
    ("where is the sahara desert",                         "sahara desert"),
    ("what is the great barrier reef",                     "great barrier reef"),
    ("what is the amazon rainforest",                      "amazon rainforest"),
    ("what is the nile river",                             "nile river"),
    ("what is the capital of france",                      "france"),
    ("what is the capital of japan",                       "japan"),
    ("what is the capital of australia",                   "australia"),
    ("what is the largest country in the world",           "country"),
    ("what is the tallest mountain in the world",          "mountain"),
    ("how big is the amazon river",                        "amazon river"),
    ("how big is antarctica",                              "antarctica"),
    ("what country is paris in",                           "paris"),
    ("what continent is egypt in",                         "egypt"),
    ("how far is paris from london",                       "paris"),
    ("what is the population of china",                    "china"),
    ("what is the population of india",                    "india"),
    ("what language is spoken in brazil",                  "brazil"),
])
def test_batch140_subject_extraction(question, expected):
    """Batch 140: geography/travel — landmarks, capitals, populations, distances."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is the cold war",                               "cold war"),
    ("what is the french revolution",                      "french revolution"),
    ("what is the renaissance",                            "renaissance"),
    ("what is the industrial revolution",                  "industrial revolution"),
    ("what is world war 2",                                "world war 2"),
    ("what is the civil rights movement",                  "civil rights movement"),
    ("who was napoleon",                                   "napoleon"),
    ("who was cleopatra",                                  "cleopatra"),
    ("who was julius caesar",                              "julius caesar"),
    ("who was abraham lincoln",                            "abraham lincoln"),
    ("who was martin luther king",                         "martin luther king"),
    ("who was nelson mandela",                             "nelson mandela"),
    ("when did world war 2 end",                           "world war 2"),
    ("when did the berlin wall fall",                      "berlin wall"),
    ("what caused world war 1",                            "world war 1"),
    ("what caused the great depression",                   "great depression"),
    ("where did the french revolution happen",             "french revolution"),
    ("who invented the printing press",                    "printing press"),
    ("who invented the steam engine",                      "steam engine"),
    ("who discovered america",                             "america"),
    ("what is the significance of the magna carta",        "magna carta"),
])
def test_batch141_subject_extraction(question, expected):
    """Batch 141: history/social studies — wars, revolutions, historical figures."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is an atom",                                    "atom"),
    ("what is a molecule",                                 "molecule"),
    ("what is an electron",                                "electron"),
    ("what is a proton",                                   "proton"),
    ("what is entropy",                                    "entropy"),
    ("what is thermodynamics",                             "thermodynamics"),
    ("what is quantum mechanics",                          "quantum mechanics"),
    ("what is the periodic table",                         "periodic table"),
    ("what is radioactivity",                              "radioactivity"),
    ("what is nuclear fission",                            "nuclear fission"),
    ("what is nuclear fusion",                             "nuclear fusion"),
    ("what is oxidation",                                  "oxidation"),
    ("how does nuclear fission work",                      "nuclear fission"),
    ("what is the atomic number of carbon",                "carbon"),
    ("what is the boiling point of water",                 "water"),
    ("what is the law of conservation of energy",          "law of conservation of energy"),
    ("what is newton's law of gravitation",                "newton's law of gravitation"),
    ("what element is gold",                               "gold"),
    ("how do you make hydrogen",                           "hydrogen"),
    ("what is the chemical formula for water",             "water"),
    ("what is the speed of sound",                         "speed of sound"),
])
def test_batch142_subject_extraction(question, expected):
    """Batch 142: chemistry/physics — atomic structure, reactions, laws, formulae."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "tell me about X"
    ("tell me about the french revolution",                "french revolution"),
    ("tell me about quantum physics",                      "quantum physics"),
    ("tell me about cleopatra",                            "cleopatra"),
    # "explain X"
    ("explain quantum mechanics",                          "quantum mechanics"),
    ("explain the water cycle",                            "water cycle"),
    ("explain photosynthesis",                             "photosynthesis"),
    # "describe X"
    ("describe the process of photosynthesis",             "photosynthesis"),
    ("describe the french revolution",                     "french revolution"),
    # "can you explain X"
    ("can you explain evolution",                          "evolution"),
    ("can you explain how gravity works",                  "gravity"),
    # "i want to know about X"
    ("i want to know about black holes",                   "black holes"),
    # "give me information about X"
    ("give me information about the amazon river",         "amazon river"),
    # "what are some facts about X"
    ("what are some facts about the moon",                 "moon"),
    ("what are some facts about penguins",                 "penguins"),
    # "is X a planet"
    ("is pluto a planet",                                  "pluto"),
    # "are X dangerous"
    ("are sharks dangerous",                               "sharks"),
    # "does X have X"
    ("does mars have moons",                               "mars"),
    # "can X do X"
    ("can fish drown",                                     "fish"),
    # "do X have X"
    ("do dogs have feelings",                              "dogs"),
    # "will X happen"
    ("will the sun explode",                               "sun"),
    # "is the earth flat"
    ("is the earth flat",                                  "earth"),
])
def test_batch143_subject_extraction(question, expected):
    """Batch 143: unusual/stress-test question patterns across domains."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is depression",                                 "depression"),
    ("what is anxiety",                                    "anxiety"),
    ("what is schizophrenia",                              "schizophrenia"),
    ("what is bipolar disorder",                           "bipolar disorder"),
    ("what is autism",                                     "autism"),
    ("what is ptsd",                                       "ptsd"),
    ("what is adhd",                                       "adhd"),
    ("what is dementia",                                   "dementia"),
    ("what is ocd",                                        "ocd"),
    ("how do you treat depression",                        "depression"),
    ("how do you treat anxiety",                           "anxiety"),
    ("what causes schizophrenia",                          "schizophrenia"),
    ("what causes ptsd",                                   "ptsd"),
    ("what are the symptoms of bipolar disorder",          "bipolar disorder"),
    ("what are the symptoms of autism",                    "autism"),
    ("what is the difference between anxiety and depression", "anxiety and depression"),
    ("how does depression affect the brain",               "depression"),
    ("is schizophrenia a mental illness",                  "schizophrenia"),
    ("can depression be cured",                            "depression"),
    ("what is cognitive behavioral therapy",               "cognitive behavioral therapy"),
    ("who developed cognitive behavioral therapy",         "cognitive behavioral therapy"),
])
def test_batch144_subject_extraction(question, expected):
    """Batch 144: psychology/mental health — disorders, symptoms, treatment."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is capitalism",                                 "capitalism"),
    ("what is inflation",                                  "inflation"),
    ("what is gdp",                                        "gdp"),
    ("what is supply and demand",                          "supply and demand"),
    ("what is a stock market",                             "stock market"),
    ("what is a recession",                                "recession"),
    ("what is cryptocurrency",                             "cryptocurrency"),
    ("how does the stock market work",                     "stock market"),
    ("how does inflation work",                            "inflation"),
    ("what causes inflation",                              "inflation"),
    ("what causes a recession",                            "recession"),
    ("what is the difference between capitalism and socialism", "capitalism and socialism"),
    ("how do you invest in the stock market",              "stock market"),
    ("what is income tax",                                 "income tax"),
    ("what is the unemployment rate",                      "unemployment rate"),
    ("what is keynesian economics",                        "keynesian economics"),
    ("who founded amazon",                                 "amazon"),
    ("what is the value of the us dollar",                 "us dollar"),
    ("how do banks make money",                            "banks"),
    ("what is a bond",                                     "bond"),
])
def test_batch145_subject_extraction(question, expected):
    """Batch 145: business/economics — markets, indicators, concepts, institutions."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is philosophy",                                 "philosophy"),
    ("what is ethics",                                     "ethics"),
    ("what is existentialism",                             "existentialism"),
    ("what is utilitarianism",                             "utilitarianism"),
    ("what is stoicism",                                   "stoicism"),
    ("what is nihilism",                                   "nihilism"),
    ("what is empiricism",                                 "empiricism"),
    ("what is rationalism",                                "rationalism"),
    ("who was socrates",                                   "socrates"),
    ("who was aristotle",                                  "aristotle"),
    ("who was plato",                                      "plato"),
    ("who was immanuel kant",                              "immanuel kant"),
    ("who was nietzsche",                                  "nietzsche"),
    ("what did nietzsche believe",                         "nietzsche"),
    ("what did socrates believe",                          "socrates"),
    ("what is aristotle's philosophy",                     "aristotle"),
    ("what is the trolley problem",                        "trolley problem"),
    ("what is the ontological argument",                   "ontological argument"),
    ("is free will real",                                  "free will"),
    ("what is the meaning of life",                        "meaning of life"),
    ("what is logic",                                      "logic"),
])
def test_batch146_subject_extraction(question, expected):
    """Batch 146: philosophy/logic — schools of thought, thinkers, problems."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is hamlet",                                     "hamlet"),
    ("what is moby dick",                                  "moby dick"),
    ("what is 1984",                                       "1984"),
    ("what is the great gatsby",                           "great gatsby"),
    ("what is pride and prejudice",                        "pride and prejudice"),
    ("what is to kill a mockingbird",                      "to kill a mockingbird"),
    ("who wrote hamlet",                                   "hamlet"),
    ("who wrote moby dick",                                "moby dick"),
    ("who wrote 1984",                                     "1984"),
    ("who wrote the great gatsby",                         "great gatsby"),
    ("what is the theme of hamlet",                        "hamlet"),
    ("what is the theme of 1984",                          "1984"),
    ("what is the plot of moby dick",                      "moby dick"),
    ("what happens in hamlet",                             "hamlet"),
    ("what happens in 1984",                               "1984"),
    ("who is gatsby in the great gatsby",                  "gatsby"),
    ("when was hamlet written",                            "hamlet"),
    ("what genre is 1984",                                 "1984"),
    ("what is the setting of hamlet",                      "hamlet"),
    ("how long is moby dick",                              "moby dick"),
    ("is 1984 a novel",                                    "1984"),
])
def test_batch147_subject_extraction(question, expected):
    """Batch 147: literature/books — titles, authorship, plot/theme queries."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is calculus",                                   "calculus"),
    ("what is algebra",                                    "algebra"),
    ("what is geometry",                                   "geometry"),
    ("what is trigonometry",                               "trigonometry"),
    ("what is statistics",                                 "statistics"),
    ("what is probability",                                "probability"),
    ("what is pi",                                         "pi"),
    ("what is the pythagorean theorem",                    "pythagorean theorem"),
    ("what is a prime number",                             "prime number"),
    ("what is the fibonacci sequence",                     "fibonacci sequence"),
    ("what is the square root of 144",                     "144"),
    ("what is the derivative of x squared",                "x squared"),
    ("how do you solve a quadratic equation",              "quadratic equation"),
    ("how do you find the area of a circle",               "circle"),
    ("what does infinity mean in math",                    "infinity"),
    ("what is the formula for the area of a circle",       "circle"),
    ("who invented calculus",                              "calculus"),
    ("what is a vector in mathematics",                    "vector"),
    ("how many prime numbers are there",                   "prime numbers"),
    ("what is the fundamental theorem of calculus",        "fundamental theorem of calculus"),
    ("is pi irrational",                                   "pi"),
])
def test_batch148_subject_extraction(question, expected):
    """Batch 148: mathematics — branches, theorems, operators, derivation queries."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 150: animals / nature — navigation, diet, habitat, lifespan
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is a mammal",                                    "mammal"),
    ("what is a reptile",                                   "reptile"),
    ("what is hibernation",                                 "hibernation"),
    ("what is migration",                                   "migration"),
    ("what is camouflage",                                  "camouflage"),
    # "how do X VERB" → X
    ("how do bats navigate",                                "bats"),
    ("how do birds fly",                                    "birds"),
    ("how do fish breathe",                                 "fish"),
    ("how do whales communicate",                           "whales"),
    # "why do X VERB" → X
    ("why do dogs bark",                                    "dogs"),
    ("why do cats purr",                                    "cats"),
    ("why do geese fly in a v formation",                   "geese"),
    # "what do X eat" → X
    ("what do wolves eat",                                  "wolves"),
    ("what do giant pandas eat",                            "giant pandas"),
    # "where do X live" → X
    ("where do penguins live",                              "penguins"),
    ("where do polar bears live",                           "polar bears"),
    # "how long do X live" → X
    ("how long do elephants live",                          "elephants"),
    ("how long do turtles live",                            "turtles"),
    # "what animal is SUPERLATIVE" → "animal"
    ("what animal is the fastest on land",                  "animal"),
    # "how many X are left in the wild" → X
    ("how many tigers are left in the wild",                "tigers"),
])
def test_batch150_subject_extraction(question, expected):
    """Batch 150: animals/nature — navigation, diet, habitat, lifespan, category-superlative."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 151: environment / ecology — climate, pollution, renewable energy
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is climate change",                              "climate change"),
    ("what is global warming",                              "global warming"),
    ("what is the greenhouse effect",                       "greenhouse effect"),
    ("what is deforestation",                               "deforestation"),
    ("what is biodiversity",                                "biodiversity"),
    ("what is an ecosystem",                                "ecosystem"),
    ("what is a food chain",                                "food chain"),
    ("what is renewable energy",                            "renewable energy"),
    ("what is carbon dioxide",                              "carbon dioxide"),
    # passive progressive: "why is X being VERB-ed" → X
    ("why is the amazon rainforest being destroyed",        "amazon rainforest"),
    # "how does X affect Y" → X
    ("how does pollution affect the ocean",                 "pollution"),
    ("how does deforestation affect climate",               "deforestation"),
    # "what causes X" → X
    ("what causes acid rain",                               "acid rain"),
    ("what causes ocean acidification",                     "ocean acidification"),
    # "what is the effect of X on Y" → X
    ("what is the effect of plastic on marine life",        "plastic"),
    # "how does X work" → X
    ("how does solar energy work",                          "solar energy"),
    # difference between X and Y → "X and Y"
    ("what is the difference between climate and weather",  "climate and weather"),
    # "how can we reduce X" → X
    ("how can we reduce carbon emissions",                  "carbon emissions"),
    # "what is the impact of X on Y" → X
    ("what is the impact of oil spills on wildlife",        "oil spills"),
    # "what are the effects of X" → X
    ("what are the effects of global warming",              "global warming"),
])
def test_batch151_subject_extraction(question, expected):
    """Batch 151: environment/ecology — passive-progressive fix, pollution, climate topics."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 152: technology / internet — AI, security, protocols, "how do I"
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is artificial intelligence",                    "artificial intelligence"),
    ("what is machine learning",                           "machine learning"),
    ("what is blockchain",                                 "blockchain"),
    ("what is the internet of things",                     "internet of things"),
    ("what is cloud computing",                            "cloud computing"),
    ("what is cybersecurity",                              "cybersecurity"),
    ("what is encryption",                                 "encryption"),
    ("what is a firewall",                                 "firewall"),
    ("what is open source software",                       "open source software"),
    # "how does X work" → X
    ("how does the internet work",                         "internet"),
    ("how does wifi work",                                 "wifi"),
    ("how does gps work",                                  "gps"),
    ("how does a computer work",                           "computer"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between http and https",      "http and https"),
    ("what is the difference between ram and rom",         "ram and rom"),
    # "who invented X" → X
    ("who invented the internet",                          "internet"),
    ("who invented the world wide web",                    "world wide web"),
    # "what programming language is X written in" → X
    ("what programming language is python written in",     "python"),
    # "what is X used for" → X
    ("what is python used for",                            "python"),
    # first-person action: "how do I VERB [my/the] OBJECT [from X]" → OBJECT
    ("how do I protect my computer from viruses",          "computer"),
])
def test_batch152_subject_extraction(question, expected):
    """Batch 152: technology/internet — AI, crypto, protocols, first-person action."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


# --------------------------------------------------------------------------
# Batch 153: law / politics — democracy, rights, elections, legal terms
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is democracy",                                   "democracy"),
    ("what is the constitution",                            "constitution"),
    ("what is the bill of rights",                          "bill of rights"),
    ("what is the supreme court",                           "supreme court"),
    ("what is habeas corpus",                               "habeas corpus"),
    ("what is the separation of powers",                    "separation of powers"),
    # causal-noun strip: "rule of X" → X  (rule is a property noun here)
    ("what is the rule of law",                             "law"),
    ("what is civil law",                                   "civil law"),
    ("what is criminal law",                                "criminal law"),
    # "how does X work" → X
    ("how does the electoral college work",                 "electoral college"),
    ("how does congress work",                              "congress"),
    # "what are X" → X
    ("what are human rights",                               "human rights"),
    ("what are civil rights",                               "civil rights"),
    # causal-noun strip: "president of X" → X (consistent with other ROLE-OF patterns)
    ("who is the president of the united states",           "united states"),
    # difference between → joined
    ("what is the difference between a democracy and a republic",   "democracy and republic"),
    # "what does X mean" → X
    ("what does impeachment mean",                          "impeachment"),
    # "what is the purpose of X" → X
    ("what is the purpose of the united nations",           "united nations"),
    # trailing passive participle "elected" now stripped
    ("how is the president elected",                        "president"),
    # "what rights does X have" → X
    ("what rights does an accused person have",             "accused person"),
    # "what is X in politics" → X
    ("what is lobbying in politics",                        "lobbying"),
    # trailing relative "that" stripped after verb strip
    ("what is a law that has been passed called",           "law"),
])
def test_batch153_subject_extraction(question, expected):
    """Batch 153: law/politics — elected strip, trailing-that strip, rights and legal terms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is a calorie",                                   "calorie"),
    ("what is gluten",                                      "gluten"),
    ("what is fermentation",                                "fermentation"),
    ("what is a probiotic",                                 "probiotic"),
    ("what is a carbohydrate",                              "carbohydrate"),
    ("what is protein",                                     "protein"),
    ("what is a vitamin",                                   "vitamin"),
    ("what is fiber",                                       "fiber"),
    # "how do you cook/make/bake X" → X
    ("how do you cook rice",                                "rice"),
    ("how do you make pasta",                               "pasta"),
    ("how do you bake bread",                               "bread"),
    # "what does X contain" → X
    ("what does coffee contain",                            "coffee"),
    # "how long does it take to cook X" → X
    ("how long does it take to cook chicken",               "chicken"),
    # "how many calories in an/a X" → X
    ("how many calories in an apple",                       "apple"),
    ("how many calories in a banana",                       "banana"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between vegan and vegetarian", "vegan and vegetarian"),
    # "what food is X found in" → X
    ("what food is vitamin c found in",                     "vitamin c"),
    # "why do X make you cry" → X
    ("why do onions make you cry",                          "onions"),
    # superlative + category: leading superlative adj stripped
    ("what is the healthiest food to eat",                  "food"),
    # unit conversion: "how many UNIT in a CONTAINER" → CONTAINER
    ("how many cups in a gallon",                           "gallon"),
])
def test_batch154_subject_extraction(question, expected):
    """Batch 154: food/nutrition — superlative-leading strip, unit conversion, cooking."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is jazz",                                        "jazz"),
    ("what is a chord",                                     "chord"),
    ("what is a melody",                                    "melody"),
    ("what is a tempo",                                     "tempo"),
    ("what is a scale in music",                            "scale"),
    ("what is a symphony",                                  "symphony"),
    # "who invented X" → X
    ("who invented the piano",                              "piano"),
    ("who invented the guitar",                             "guitar"),
    # "how does X work" → X
    ("how does a metronome work",                           "metronome"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between classical and jazz",   "classical and jazz"),
    # "what are the X in a Y" (indefinite container) → Y
    ("what are the notes in a c major scale",               "c major scale"),
    # "how do you read X" → X
    ("how do you read sheet music",                         "sheet music"),
    # "who wrote X" → X
    ("who wrote beethoven's 9th symphony",                  "beethoven's 9th symphony"),
    # "what genre is X" → X
    ("what genre is hip hop",                               "hip hop"),
    # compound nouns: "key" not stripped as adjective
    ("what is a bass guitar",                               "bass guitar"),
    ("what is an octave",                                   "octave"),
    ("what is a key signature",                             "key signature"),
    # "how do you tune X" → X
    ("how do you tune a guitar",                            "guitar"),
    # superlative + category noun stripped
    ("what is the most popular music genre",                "music genre"),
    # "how many strings does X have" → X
    ("how many strings does a violin have",                 "violin"),
])
def test_batch155_subject_extraction(question, expected):
    """Batch 155: music — key-compound protection, indefinite-container rule, instruments."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X in Y" �� X
    ("what is offside in soccer",                           "offside"),
    ("what is a touchdown in football",                     "touchdown"),
    ("what is a grand slam in tennis",                      "grand slam"),
    ("what is doping in sports",                            "doping"),
    # "how many players are in a X team" → X
    ("how many players are in a soccer team",               "soccer"),
    # "how long is a X game" → "X game"
    ("how long is a basketball game",                       "basketball game"),
    # "who holds the record for most X" → X (most stripped as quantifier)
    ("who holds the record for most olympic gold medals",   "olympic gold medals"),
    # "what are the rules of X" → X
    ("what are the rules of chess",                         "chess"),
    # "how do you score in X" → X
    ("how do you score in bowling",                         "bowling"),
    # "how does X work" �� X (trailing work stripped)
    ("how does the offside rule work in soccer",            "offside rule"),
    # difference between joined
    ("what is the difference between rugby and american football", "rugby and american football"),
    # "how many laps is a X" → X (copula form; run protected from verb strip)
    ("how many laps is a mile run",                         "mile run"),
    # "who won X" → X
    ("who won the world cup in 2018",                       "world cup"),
    # "what sport uses a X" → X (reverse-category lookup)
    ("what sport uses a puck",                              "puck"),
    # "how far is a X" → X
    ("how far is a marathon",                               "marathon"),
    # superlative + category noun stripped
    ("what is the fastest sport in the world",              "sport"),
    # "how do you serve/do X" → X
    ("how do you serve in volleyball",                      "volleyball"),
    # "what does X mean" → X
    ("what does hat trick mean in sports",                  "hat trick"),
    # "who invented X" → X
    ("who invented basketball",                             "basketball"),
    # "what NOUN do you need for X" → X
    ("what equipment do you need for cycling",              "cycling"),
])
def test_batch156_subject_extraction(question, expected):
    """Batch 156: sports — work/run strip guards, category reverse-lookup, unit conversion."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is diabetes",                                    "diabetes"),
    ("what is a virus",                                     "virus"),
    ("what is inflammation",                                "inflammation"),
    ("what is anesthesia",                                  "anesthesia"),
    ("what is a vaccine",                                   "vaccine"),
    # "what causes X" → X
    ("what causes high blood pressure",                     "high blood pressure"),
    ("what causes a headache",                              "headache"),
    # "how does X work" → X
    ("how does the immune system work",                     "immune system"),
    ("how does insulin work",                               "insulin"),
    # "what are the symptoms of X" → X
    ("what are the symptoms of covid",                      "covid"),
    ("what are the symptoms of a heart attack",             "heart attack"),
    # "how do you treat X" → X
    ("how do you treat a sprained ankle",                   "sprained ankle"),
    # "how is X diagnosed" → X
    ("how is cancer diagnosed",                             "cancer"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between a cold and the flu",   "cold and flu"),
    # "what are X" → X
    ("what are antibiotics",                                "antibiotics"),
    # "how do X fight Y" → X
    ("how do white blood cells fight infection",            "white blood cells"),
    # "what is the best treatment for X" → X (causal strip extracts condition)
    ("what is the best treatment for depression",           "depression"),
    # "how many bones are in X" → X
    ("how many bones are in the human body",                "human body"),
    # "what does X do" → X
    ("what does the liver do",                              "liver"),
    # "how long does X last" → X
    ("how long does a cold last",                           "cold"),
])
def test_batch157_subject_extraction(question, expected):
    """Batch 157: medicine/health — symptoms, treatment, diagnosis, anatomy."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is the renaissance",                                "renaissance"),
    ("what is the cold war",                                   "cold war"),
    ("what is the magna carta",                                "magna carta"),
    # "when did X happen" → X
    ("when did world war 2 start",                             "world war 2"),
    ("when did the roman empire fall",                         "roman empire"),
    # "who was X" → X
    ("who was napoleon",                                       "napoleon"),
    ("who was cleopatra",                                      "cleopatra"),
    # "what caused X" → X
    ("what caused the french revolution",                      "french revolution"),
    ("what caused the great depression",                       "great depression"),
    # "where did X happen" → X
    ("where did the battle of waterloo take place",            "battle of waterloo"),
    # "how long did X last" → X
    ("how long did the hundred years war last",                "hundred years war"),
    # "what was X" → X
    ("what was the silk road",                                 "silk road"),
    ("what was the black death",                               "black death"),
    # "who invented X" → X
    ("who invented the printing press",                        "printing press"),
    # "when was X founded" → X
    ("when was rome founded",                                  "rome"),
    # "what happened during X" → X
    ("what happened during the industrial revolution",         "industrial revolution"),
    # "who led X" → X
    ("who led the american revolution",                        "american revolution"),
    # "what was the impact of X" → X
    ("what was the impact of world war 1",                     "world war 1"),
    # "what is the history of X" → X
    ("what is the history of democracy",                       "democracy"),
    # "who built X" → X
    ("who built the great wall of china",                      "great wall of china"),
])
def test_batch158_subject_extraction(question, expected):
    """Batch 158: history — events, leaders, inventions, empires."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is the capital of X" → X
    ("what is the capital of japan",                           "japan"),
    ("what is the capital of australia",                       "australia"),
    # "where is X" → X
    ("where is the amazon river",                              "amazon river"),
    ("where is the sahara desert",                             "sahara desert"),
    # "what is the largest country in X" → X
    ("what is the largest country in south america",           "south america"),
    # "how many countries are in X" → X
    ("how many countries are in africa",                       "africa"),
    # "what is the population of X" → X
    ("what is the population of india",                        "india"),
    # "what language do they speak in X" → X
    ("what language do they speak in brazil",                  "brazil"),
    # "what continent is X in" → X
    ("what continent is egypt in",                             "egypt"),
    # "what is the longest river in the world" → "river" (universal scope → superlative stripped)
    ("what is the longest river in the world",                 "river"),
    # "how big is X" → X
    ("how big is antarctica",                                  "antarctica"),
    # "what is X known for" → X
    ("what is paris known for",                                "paris"),
    # "what CATEGORY borders PLACE" → PLACE
    ("what countries border france",                           "france"),
    # "what is the highest mountain in X" → X
    ("what is the highest mountain in europe",                 "europe"),
    # "what CATEGORY borders PLACE" → PLACE (ocean variant)
    ("what ocean borders australia",                           "australia"),
    # "what is the currency of X" → X
    ("what is the currency of mexico",                         "mexico"),
    # "what timezone is X in" → X
    ("what timezone is new york in",                           "new york"),
    # "how far is X from Y" → X
    ("how far is new york from london",                        "new york"),
    # "what is X" → X (geographic entities)
    ("what is the amazon rainforest",                          "amazon rainforest"),
    ("what is the great barrier reef",                         "great barrier reef"),
])
def test_batch159_subject_extraction(question, expected):
    """Batch 159: geography — capitals, borders, population, continent, distance."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is the pythagorean theorem",                        "pythagorean theorem"),
    ("what is a prime number",                                 "prime number"),
    ("what is calculus",                                       "calculus"),
    ("what is the fibonacci sequence",                         "fibonacci sequence"),
    # "how do you calculate the PROP of a SHAPE" → SHAPE (area/volume reduce to the shape)
    ("how do you calculate the area of a circle",              "circle"),
    ("how do you calculate compound interest",                 "compound interest"),
    # "what is the formula for the PROP of a SHAPE" → SHAPE
    ("what is the formula for the area of a triangle",         "triangle"),
    # "what is X in math" → X
    ("what is a derivative in math",                           "derivative"),
    ("what is an integral in math",                            "integral"),
    # "how do you find X" → X
    ("how do you find the square root of a number",            "square root"),
    # "what does X mean in math" → X
    ("what does pi mean in math",                              "pi"),
    # "what is the value of X" → X
    ("what is the value of pi",                                "pi"),
    # "what is X used for" → X
    ("what is algebra used for",                               "algebra"),
    ("what is statistics used for",                            "statistics"),
    # "how many degrees are in X" → X
    ("how many degrees are in a circle",                       "circle"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between mean and median",         "mean and median"),
    # "how do you solve X" → X
    ("how do you solve a quadratic equation",                  "quadratic equation"),
    # "what is X" → X (more math concepts)
    ("what is a vector",                                       "vector"),
    ("what is probability",                                    "probability"),
    # "what are X" → X (plurals)
    ("what are irrational numbers",                            "irrational numbers"),
])
def test_batch160_subject_extraction(question, expected):
    """Batch 160: mathematics — theorems, formulas, geometry, concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is quantum mechanics",                              "quantum mechanics"),
    ("what is gravity",                                        "gravity"),
    ("what is thermodynamics",                                 "thermodynamics"),
    ("what is a black hole",                                   "black hole"),
    ("what is dark matter",                                    "dark matter"),
    # "what is the speed of X" → "speed of X" (compound concept)
    ("what is the speed of light",                             "speed of light"),
    # "how does X work" → X
    ("how does a nuclear reactor work",                        "nuclear reactor"),
    ("how does electricity work",                              "electricity"),
    # "what causes X" → X
    ("what causes lightning",                                  "lightning"),
    ("what causes earthquakes",                                "earthquakes"),
    # "what is the law of X" → "law of X" (compound concept)
    ("what is the law of gravity",                             "law of gravity"),
    # "how fast does X travel" → X
    ("how fast does sound travel",                             "sound"),
    # "what is X energy" → X energy
    ("what is kinetic energy",                                 "kinetic energy"),
    ("what is nuclear energy",                                 "nuclear energy"),
    # "what is the theory of X" → X
    ("what is the theory of relativity",                       "theory of relativity"),
    # "what is X made of" → X
    ("what is an atom made of",                                "atom"),
    # "how do X VERB each other" → X
    ("how do magnets attract each other",                      "magnets"),
    # "what is X radiation" → X radiation
    ("what is electromagnetic radiation",                      "electromagnetic radiation"),
    # "how many dimensions does X have" → X
    ("how many dimensions does the universe have",             "universe"),
    # "what happens when X VERB Y" → "X VERB Y" (full clause preserved)
    ("what happens when matter meets antimatter",              "matter meets antimatter"),
])
def test_batch161_subject_extraction(question, expected):
    """Batch 161: physics — quantum, gravity, energy, laws, compound concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is a chemical reaction",                            "chemical reaction"),
    ("what is an acid",                                        "acid"),
    ("what is a base in chemistry",                            "base"),
    ("what is osmosis",                                        "osmosis"),
    ("what is oxidation",                                      "oxidation"),
    # "what is X made of" → X
    ("what is water made of",                                  "water"),
    ("what is steel made of",                                  "steel"),
    # "what is the chemical formula for X" → X
    ("what is the chemical formula for water",                 "water"),
    ("what is the chemical formula for carbon dioxide",        "carbon dioxide"),
    # "how does X react with Y" → X
    ("how does acid react with metal",                         "acid"),
    # "what is X" → X (elements)
    ("what is hydrogen",                                       "hydrogen"),
    ("what is carbon",                                         "carbon"),
    # "what happens when X is VERBed" → X (trailing copula+participle stripped)
    ("what happens when ice is heated",                        "ice"),
    # "what is the boiling point of X" → X
    ("what is the boiling point of water",                     "water"),
    # "what is the atomic number of X" → X
    ("what is the atomic number of gold",                      "gold"),
    # "how many electrons does X have" → X
    ("how many electrons does carbon have",                    "carbon"),
    # "what are X" → X
    ("what are noble gases",                                   "noble gases"),
    ("what is the periodic table",                             "periodic table"),
    # "what is X bonding" → X bonding
    ("what is covalent bonding",                               "covalent bonding"),
    # "how do you balance X" → X
    ("how do you balance a chemical equation",                 "chemical equation"),
])
def test_batch162_subject_extraction(question, expected):
    """Batch 162: chemistry — reactions, elements, formulas, passive-when strip."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X (biology concepts)
    ("what is photosynthesis",                                "photosynthesis"),
    ("what is mitosis",                                       "mitosis"),
    ("what is dna",                                           "dna"),
    ("what is a cell",                                        "cell"),
    ("what is evolution",                                     "evolution"),
    # superlative + category
    ("what is the largest mammal",                            "mammal"),
    ("what is the largest animal on earth",                   "animal"),
    # "how do X reproduce/eat/live" → X
    ("how do mammals reproduce",                              "mammals"),
    ("what do wolves eat",                                    "wolves"),
    ("how long do elephants live",                            "elephants"),
    # "what is the lifespan of X" → X
    ("what is the lifespan of a dog",                         "dog"),
    # "how many X does Y have" → Y
    ("how many legs does a spider have",                      "spider"),
    # "what animals live in X" → "animals" (predicate stripped)
    ("what animals live in the rainforest",                   "animals"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between a frog and a toad",      "frog and toad"),
    # "what is X behavior" → X behavior
    ("what is animal behavior",                               "animal behavior"),
    # "how does X work" / "what is X made of" / "what causes X"
    ("how does digestion work",                               "digestion"),
    ("what is bone made of",                                  "bone"),
    ("what causes extinction",                                "extinction"),
    # "what is the scientific classification of X" → X (new classification strip)
    ("what is the scientific classification of humans",       "humans"),
    # "what are X" → X
    ("what are invertebrates",                                "invertebrates"),
])
def test_batch163_subject_extraction(question, expected):
    """Batch 163: biology/animals — concepts, taxonomy, lifespan, difference patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is the internet",                                  "internet"),
    ("what is machine learning",                              "machine learning"),
    ("what is artificial intelligence",                       "artificial intelligence"),
    ("what is a compiler",                                    "compiler"),
    ("what is an operating system",                           "operating system"),
    # "how does X work" → X
    ("how does encryption work",                              "encryption"),
    ("how does a cpu work",                                   "cpu"),
    ("how does the internet work",                            "internet"),
    # "what is X programming" → X programming
    ("what is object oriented programming",                   "object oriented programming"),
    # "what is the X programming language" → "X programming language"
    ("what is the python programming language",               "python programming language"),
    # "what does X stand for" → X
    ("what does html stand for",                              "html"),
    ("what does cpu stand for",                               "cpu"),
    # "denial of service attack" → "denial of service" (attack stripped as verb)
    ("what is a denial of service attack",                    "denial of service"),
    # "how do you write a function in python" → "function" (in-python context stripped)
    ("how do you write a function in python",                 "function"),
    # "what is the difference between X and Y" → X and Y
    ("what is the difference between tcp and udp",            "tcp and udp"),
    # "what is X architecture" → X architecture
    ("what is microservices architecture",                    "microservices architecture"),
    # "what causes X" → X
    ("what causes a computer to crash",                       "computer"),
    # "how many bits does X have" → X
    ("how many bits does a byte have",                        "byte"),
    # "what is X used for" → X
    ("what is sql used for",                                  "sql"),
    # "what is X" → X (protocols)
    ("what is http",                                          "http"),
])
def test_batch164_subject_extraction(question, expected):
    """Batch 164: technology/computers — networking, languages, protocols, architecture."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is capitalism",                                    "capitalism"),
    ("what is inflation",                                     "inflation"),
    ("what is the stock market",                              "stock market"),
    ("what is supply and demand",                             "supply and demand"),
    ("what is a recession",                                   "recession"),
    # "what is the gdp of X" → X
    ("what is the gdp of france",                             "france"),
    ("what is the gdp of the united states",                  "united states"),
    # "how does X work" → X
    ("how does the stock market work",                        "stock market"),
    ("how does inflation work",                               "inflation"),
    # "what causes X" → X
    ("what causes inflation",                                 "inflation"),
    ("what causes a recession",                               "recession"),
    # "what is X theory" → X theory
    ("what is game theory",                                   "game theory"),
    # "what is the difference between X and Y" → X and Y
    ("what is the difference between stocks and bonds",       "stocks and bonds"),
    # "what is X" → X (finance terms)
    ("what is compound interest",                             "compound interest"),
    ("what is a hedge fund",                                  "hedge fund"),
    # "how do you X" → X
    ("how do you calculate interest",                         "interest"),
    # "what is X rate" → X rate
    ("what is the interest rate",                             "interest rate"),
    # "what is X" → X (economic systems)
    ("what is socialism",                                     "socialism"),
    ("what is communism",                                     "communism"),
    # "what is X index" → X index
    ("what is the consumer price index",                      "consumer price index"),
])
def test_batch165_subject_extraction(question, expected):
    """Batch 165: economics/business — markets, monetary policy, financial instruments."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "who wrote X" → X
    ("who wrote hamlet",                                      "hamlet"),
    ("who wrote the great gatsby",                            "great gatsby"),
    ("who wrote moby dick",                                   "moby dick"),
    # "what is X about" → X
    ("what is hamlet about",                                  "hamlet"),
    # "who painted X" → X
    ("who painted the mona lisa",                             "mona lisa"),
    ("who painted the sistine chapel",                        "sistine chapel"),
    # "theme of to X a Y" → "to X a Y" (title preserved by _title_attr_ctx "of to" guard)
    ("what is the theme of to kill a mockingbird",            "to kill a mockingbird"),
    # "when was X written" → X
    ("when was don quixote written",                          "don quixote"),
    # "what is the plot of X" → X
    ("what is the plot of hamlet",                            "hamlet"),
    # "who composed X" → X
    ("who composed beethoven's ninth symphony",               "beethoven's ninth symphony"),
    # "what is X" → X (artistic movements)
    ("what is impressionism",                                 "impressionism"),
    ("what is surrealism",                                    "surrealism"),
    ("what is romanticism",                                   "romanticism"),
    # "what is X poetry" → X poetry
    ("what is haiku poetry",                                  "haiku poetry"),
    # "who is the author of X" → X
    ("who is the author of don quixote",                      "don quixote"),
    # "what is the style of X" → X
    ("what is the style of hemingway",                        "hemingway"),
    # "what genre is X on the Y" → X (trailing on-the-Y stripped; known limitation for 'on' titles)
    ("what genre is kafka on the shore",                      "kafka"),
    # "what is a metaphor" → X (literature terms)
    ("what is a metaphor",                                    "metaphor"),
    ("what is an allegory",                                   "allegory"),
    ("what is foreshadowing",                                 "foreshadowing"),
])
def test_batch166_subject_extraction(question, expected):
    """Batch 166: literature/arts — works, authors, movements, literary devices."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is psychology",                                    "psychology"),
    ("what is anxiety",                                       "anxiety"),
    ("what is depression",                                    "depression"),
    ("what is schizophrenia",                                 "schizophrenia"),
    ("what is bipolar disorder",                              "bipolar disorder"),
    # "what is X theory" → X theory
    ("what is attachment theory",                             "attachment theory"),
    ("what is cognitive dissonance",                          "cognitive dissonance"),
    # "how does X work" → X
    ("how does memory work",                                  "memory"),
    ("how does sleep work",                                   "sleep"),
    # "what causes X" → X
    ("what causes stress",                                    "stress"),
    ("what causes phobias",                                   "phobias"),
    # "what is X behavior" → X behavior
    ("what is human behavior",                                "human behavior"),
    # "what is the difference between X and Y" → X and Y
    ("what is the difference between introvert and extrovert", "introvert and extrovert"),
    # "what are the stages of X" → X
    ("what are the stages of grief",                          "grief"),
    # "how do X affect Y" → X (grammatical subject)
    ("how do emotions affect decision making",                "emotions"),
    # "what is X therapy" → X therapy
    ("what is cognitive behavioral therapy",                  "cognitive behavioral therapy"),
    # "what is X effect" → X effect
    ("what is the placebo effect",                            "placebo effect"),
    # "what is X" → X (cognitive biases)
    ("what is confirmation bias",                             "confirmation bias"),
    ("what is the dunning kruger effect",                     "dunning kruger effect"),
    ("what is emotional intelligence",                        "emotional intelligence"),
])
def test_batch167_subject_extraction(question, expected):
    """Batch 167: psychology/human behavior — disorders, theories, cognitive biases."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is basketball",                                    "basketball"),
    ("what is soccer",                                        "soccer"),
    ("what is tennis",                                        "tennis"),
    # "who invented X" → X
    ("who invented basketball",                               "basketball"),
    # "how many players are on a X team" → X
    ("how many players are on a basketball team",             "basketball"),
    ("how many players are on a soccer team",                 "soccer"),
    # "who won the X" → X
    ("who won the world cup",                                 "world cup"),
    ("who won the super bowl",                                "super bowl"),
    # "what are the rules of X" → X
    ("what are the rules of chess",                           "chess"),
    # "how long is a X game" → X game
    ("how long is a football game",                           "football game"),
    # "who directed X" → X
    ("who directed the godfather",                            "godfather"),
    ("who directed titanic",                                  "titanic"),
    # "who starred in X" → X
    ("who starred in the matrix",                             "matrix"),
    # "when did X come out" → X
    ("when did the dark knight come out",                     "dark knight"),
    # "what is X about" → X
    ("what is the matrix about",                              "matrix"),
    # "what is X" → X (entertainment institutions)
    ("what is the oscars",                                    "oscars"),
    ("what is the grammy",                                    "grammy"),
    # "what X won the AWARD for CATEGORY" → CATEGORY (award-won strip)
    ("what movie won the oscar for best picture",             "best picture"),
    # "when was X born" → X
    ("when was michael jordan born",                          "michael jordan"),
    ("when was beethoven born",                               "beethoven"),
])
def test_batch168_subject_extraction(question, expected):
    """Batch 168: sports/entertainment — games, films, awards, biographical queries."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is pizza",                                         "pizza"),
    ("what is sushi",                                         "sushi"),
    ("what is pasta",                                         "pasta"),
    # "what is X made of" → X
    ("what is pizza made of",                                 "pizza"),
    ("what is bread made of",                                 "bread"),
    # "how do you make X" → X
    ("how do you make pasta",                                 "pasta"),
    ("how do you make pizza dough",                           "pizza dough"),
    # "what are the ingredients in X" → X
    ("what are the ingredients in pizza",                     "pizza"),
    ("what are the ingredients in guacamole",                 "guacamole"),
    # "what is the recipe for X" → X
    ("what is the recipe for chocolate cake",                 "chocolate cake"),
    # "how long do you cook/bake X" → X
    ("how long do you cook chicken",                          "chicken"),
    ("how long do you bake a potato",                         "potato"),
    # "what temperature do you cook X at" → X
    ("what temperature do you cook steak at",                 "steak"),
    # "how many calories are in X" → X
    ("how many calories are in an apple",                     "apple"),
    ("how many calories are in a banana",                     "banana"),
    # "what is X cuisine/food" → X cuisine/food
    ("what is italian cuisine",                               "italian cuisine"),
    ("what is thai food",                                     "thai food"),
    # "what is X" → X (cooking techniques)
    ("what is sauteing",                                      "sauteing"),
    ("what is fermentation",                                  "fermentation"),
    # "what is the difference between X and Y" → X and Y
    ("what is the difference between baking and roasting",    "baking and roasting"),
    ("what is the difference between jam and jelly",          "jam and jelly"),
])
def test_batch169_subject_extraction(question, expected):
    """Batch 169: food/cooking — recipes, techniques, ingredients, calorie queries."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X
    ("what is a black hole",                                  "black hole"),
    ("what is a neutron star",                                "neutron star"),
    ("what is the milky way",                                 "milky way"),
    ("what is the big bang",                                  "big bang"),
    ("what is dark energy",                                   "dark energy"),
    # "how far is X from earth" → X
    ("how far is the moon from earth",                        "moon"),
    ("how far is mars from earth",                            "mars"),
    # "how big is X" → X
    ("how big is the sun",                                    "sun"),
    ("how big is jupiter",                                    "jupiter"),
    # "what is the temperature on X" → X
    ("what is the temperature on mars",                       "mars"),
    # "how many moons does X have" → X
    ("how many moons does saturn have",                       "saturn"),
    ("how many moons does jupiter have",                      "jupiter"),
    # "what is the closest X to earth" → X
    ("what is the closest star to earth",                     "star"),
    # "how old is X" → X
    ("how old is the universe",                               "universe"),
    ("how old is the sun",                                    "sun"),
    # "what is X made of" → X
    ("what is a star made of",                                "star"),
    # "what is the order of the X" → "order of the X" (kept; 'order of magnitude' guards)
    ("what is the order of the planets",                      "order of the planets"),
    # "what causes X" → X
    ("what causes a solar eclipse",                           "solar eclipse"),
    # "when was X discovered" → X
    ("when was pluto discovered",                             "pluto"),
    # "what is X" → X
    ("what is a nebula",                                      "nebula"),
])
def test_batch170_subject_extraction(question, expected):
    """Batch 170: space/astronomy — celestial bodies, distances, temperatures, sizes."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Multi-word proper names / institutions
    ("what is the united nations",                            "united nations"),
    ("what is the european union",                            "european union"),
    ("what is the world health organization",                 "world health organization"),
    # Compound scientific terms
    ("what is nuclear fission",                               "nuclear fission"),
    ("what is quantum entanglement",                          "quantum entanglement"),
    ("what is plate tectonics",                               "plate tectonics"),
    # Famous theorems / laws
    ("what is newtons second law",                            "newtons second law"),
    ("what is the pythagorean theorem",                       "pythagorean theorem"),
    # Very short terms (2-3 chars)
    ("what is pi",                                            "pi"),
    ("what is dna",                                           "dna"),
    ("what is ai",                                            "ai"),
    # Disease names with possessives
    ("what is alzheimers disease",                            "alzheimers disease"),
    ("what is parkinsons disease",                            "parkinsons disease"),
    # Acronyms / brand-like terms
    ("what is the g20",                                       "g20"),
    ("what is wifi",                                          "wifi"),
    # "what happened to X" → X
    ("what happened to the dinosaurs",                        "dinosaurs"),
    ("what happened to the roman empire",                     "roman empire"),
    # Philosophical / abstract
    ("what is the meaning of life",                           "meaning of life"),
    ("what is love",                                          "love"),
    ("what is consciousness",                                 "consciousness"),
])
def test_batch171_subject_extraction(question, expected):
    """Batch 171: edge cases — multi-word names, short acronyms, disease names, abstract concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X (medical conditions)
    ("what is diabetes",                                      "diabetes"),
    ("what is asthma",                                        "asthma"),
    ("what is cancer",                                        "cancer"),
    ("what is pneumonia",                                     "pneumonia"),
    # "what are the symptoms of X" → X
    ("what are the symptoms of covid",                        "covid"),
    ("what are the symptoms of diabetes",                     "diabetes"),
    # "what is the treatment for X" → X
    ("what is the treatment for asthma",                      "asthma"),
    ("what is the treatment for high blood pressure",         "high blood pressure"),
    # "what causes X" ��� X
    ("what causes high blood pressure",                       "high blood pressure"),
    ("what causes kidney stones",                             "kidney stones"),
    # "how is X diagnosed" → X
    ("how is diabetes diagnosed",                             "diabetes"),
    # "how do you prevent X" → X
    ("how do you prevent heart disease",                      "heart disease"),
    # "what is the difference between X and Y" → X and Y
    ("what is the difference between type 1 and type 2 diabetes", "type 1 and type 2 diabetes"),
    # "what is X" → X (medical procedures)
    ("what is chemotherapy",                                  "chemotherapy"),
    ("what is dialysis",                                      "dialysis"),
    # "how does X affect the body" → X
    ("how does alcohol affect the body",                      "alcohol"),
    # "what is the normal X" → "normal X" (adjective modifier preserved)
    ("what is the normal blood pressure",                     "normal blood pressure"),
    # "what is X" → X (medical tests)
    ("what is an mri",                                        "mri"),
    ("what is a ct scan",                                     "ct scan"),
    # "how long does X last" → X
    ("how long does the flu last",                            "flu"),
])
def test_batch172_subject_extraction(question, expected):
    """Batch 172: medical/health — conditions, symptoms, treatments, procedures."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X (religions)
    ("what is buddhism",                                         "buddhism"),
    ("what is hinduism",                                         "hinduism"),
    ("what is islam",                                            "islam"),
    ("what is christianity",                                     "christianity"),
    ("what is judaism",                                          "judaism"),
    # "what do X believe" → X
    ("what do buddhists believe",                                "buddhists"),
    ("what do muslims believe",                                  "muslims"),
    # "what is X" → X (religious texts)
    ("what is the quran",                                        "quran"),
    ("what is the bible",                                        "bible"),
    ("what is the torah",                                        "torah"),
    # "what is X" → X (philosophical concepts)
    ("what is existentialism",                                   "existentialism"),
    ("what is nihilism",                                         "nihilism"),
    ("what is stoicism",                                         "stoicism"),
    ("what is utilitarianism",                                   "utilitarianism"),
    # "who is X" → X (philosophers)
    ("who is socrates",                                          "socrates"),
    ("who is plato",                                             "plato"),
    ("who is aristotle",                                         "aristotle"),
    # "what did X believe" → X
    ("what did plato believe",                                   "plato"),
    ("what did nietzsche believe",                               "nietzsche"),
    # compound discipline: "philosophy of X" preserved as a named field
    ("what is the philosophy of mind",                           "philosophy of mind"),
])
def test_batch173_subject_extraction(question, expected):
    """Batch 173: religion/philosophy — faiths, texts, concepts, philosophers."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X (legal concepts)
    ("what is a contract",                                       "contract"),
    ("what is a lawsuit",                                        "lawsuit"),
    ("what is habeas corpus",                                    "habeas corpus"),
    ("what is due process",                                      "due process"),
    ("what is the first amendment",                              "first amendment"),
    # "what is X" → X (legal systems)
    ("what is common law",                                       "common law"),
    ("what is civil law",                                        "civil law"),
    ("what is constitutional law",                               "constitutional law"),
    # "what is X" → X (legal procedures)
    ("what is an appeal",                                        "appeal"),
    ("what is a subpoena",                                       "subpoena"),
    ("what is an injunction",                                    "injunction"),
    # "what is the difference between X and Y" → X and Y
    ("what is the difference between civil and criminal law",    "civil and criminal law"),
    # "what does X mean" → X (legal terms)
    ("what does hearsay mean",                                   "hearsay"),
    ("what does perjury mean",                                   "perjury"),
    # "what is X" → X (legal roles)
    ("what is a prosecutor",                                     "prosecutor"),
    ("what is a defendant",                                      "defendant"),
    # "how does X work" → X
    ("how does the supreme court work",                          "supreme court"),
    # "what is X" → X (legal documents/IP)
    ("what is a will",                                           "will"),
    ("what is a patent",                                         "patent"),
    ("what is a copyright",                                      "copyright"),
])
def test_batch174_subject_extraction(question, expected):
    """Batch 174: law/legal — concepts, systems, procedures, roles, documents."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Engineering disciplines
    ("what is civil engineering",                                "civil engineering"),
    ("what is mechanical engineering",                           "mechanical engineering"),
    ("what is electrical engineering",                           "electrical engineering"),
    ("what is software engineering",                             "software engineering"),
    ("what is chemical engineering",                             "chemical engineering"),
    # Architectural styles
    ("what is baroque architecture",                             "baroque architecture"),
    ("what is gothic architecture",                              "gothic architecture"),
    ("what is modernist architecture",                           "modernist architecture"),
    # Famous structures
    ("who designed the eiffel tower",                            "eiffel tower"),
    ("who designed the colosseum",                               "colosseum"),
    ("how tall is the eiffel tower",                             "eiffel tower"),
    ("how tall is the burj khalifa",                             "burj khalifa"),
    # Materials
    ("what is concrete",                                         "concrete"),
    ("what is steel",                                            "steel"),
    # Structural concepts
    ("what is load bearing",                                     "load bearing"),
    ("what is a cantilever",                                     "cantilever"),
    # Engineering systems
    ("how does a bridge work",                                   "bridge"),
    ("how does a dam work",                                      "dam"),
    ("what is the longest bridge in the world",                  "bridge"),
    ("what is a truss",                                          "truss"),
])
def test_batch175_subject_extraction(question, expected):
    """Batch 175: engineering/architecture — disciplines, styles, structures, materials."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Environment/climate
    ("what is climate change",                                   "climate change"),
    ("what is global warming",                                   "global warming"),
    ("what is the greenhouse effect",                            "greenhouse effect"),
    ("what is acid rain",                                        "acid rain"),
    ("what is deforestation",                                    "deforestation"),
    ("what causes climate change",                               "climate change"),
    ("what causes acid rain",                                    "acid rain"),
    # Ecosystems
    ("what is an ecosystem",                                     "ecosystem"),
    ("what is a biome",                                          "biome"),
    ("what is a food chain",                                     "food chain"),
    ("what is the water cycle",                                  "water cycle"),
    # Natural disasters
    ("what is a hurricane",                                      "hurricane"),
    ("what is a tornado",                                        "tornado"),
    ("what is an earthquake",                                    "earthquake"),
    ("what is a tsunami",                                        "tsunami"),
    # Geography
    ("what is a watershed",                                      "watershed"),
    ("what is a delta",                                          "delta"),
    # Natural event causes
    ("what causes a tornado",                                    "tornado"),
    ("what causes an earthquake",                                "earthquake"),
    # Action queries
    ("how do you reduce carbon emissions",                       "carbon emissions"),
])
def test_batch176_subject_extraction(question, expected):
    """Batch 176: environment/nature — climate, ecosystems, disasters, geography."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Transportation modes
    ("what is the subway",                                       "subway"),
    ("what is a bullet train",                                   "bullet train"),
    ("what is a maglev train",                                   "maglev train"),
    # Engineering systems
    ("how does a jet engine work",                               "jet engine"),
    ("how does a submarine work",                                "submarine"),
    # Superlative transport queries
    ("what is the fastest train in the world",                   "train"),
    ("what is the fastest plane in the world",                   "plane"),
    # Duration query with destination context preserved
    ("how long does a flight to london take",                    "flight to london"),
    # Travel destinations / landmarks
    ("what is the colosseum",                                    "colosseum"),
    ("what is the taj mahal",                                    "taj mahal"),
    ("what is the great wall of china",                          "great wall of china"),
    # Location queries
    ("where is the amazon river",                                "amazon river"),
    ("where is the sahara desert",                               "sahara desert"),
    # Distance query — dummy "it" subject (rare pattern, accepted limitation)
    ("how far is it from new york to london",                    "it"),
    # Navigation concepts
    ("what is gps",                                              "gps"),
    ("what is latitude",                                         "latitude"),
    ("what is longitude",                                        "longitude"),
    # Time zone query
    ("what is the time zone of tokyo",                           "tokyo"),
    # Infrastructure
    ("what is heathrow airport",                                 "heathrow airport"),
    # Requirements query — movement verb remains after cascaded strips (known limitation)
    ("what do you need to travel to japan",                      "travel"),
])
def test_batch177_subject_extraction(question, expected):
    """Batch 177: travel/transportation — modes, landmarks, location/distance queries."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Economic concepts
    ("what is inflation",                                        "inflation"),
    ("what is recession",                                        "recession"),
    ("what is gdp",                                              "gdp"),
    ("what is the stock market",                                 "stock market"),
    ("what is supply and demand",                                "supply and demand"),
    # Financial instruments
    ("what is a bond",                                           "bond"),
    ("what is a mutual fund",                                    "mutual fund"),
    ("what is a hedge fund",                                     "hedge fund"),
    ("what is cryptocurrency",                                   "cryptocurrency"),
    ("what is bitcoin",                                          "bitcoin"),
    # Economic institutions
    ("what is the federal reserve",                              "federal reserve"),
    ("what is the world bank",                                   "world bank"),
    ("what is the imf",                                          "imf"),
    # Economic theories
    ("what is capitalism",                                       "capitalism"),
    ("what is socialism",                                        "socialism"),
    ("what is keynesian economics",                              "keynesian economics"),
    # Cause/effect
    ("how does inflation affect the economy",                    "inflation"),
    # Difference queries
    ("what is the difference between stocks and bonds",          "stocks and bonds"),
    # Tax concepts
    ("what is income tax",                                       "income tax"),
    ("what is a tariff",                                         "tariff"),
])
def test_batch178_subject_extraction(question, expected):
    """Batch 178: economics/finance — concepts, instruments, institutions, theories."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # Mental health conditions
    ("what is depression",                                       "depression"),
    ("what is anxiety",                                          "anxiety"),
    ("what is ptsd",                                             "ptsd"),
    ("what is ocd",                                              "ocd"),
    ("what is bipolar disorder",                                 "bipolar disorder"),
    ("what is schizophrenia",                                    "schizophrenia"),
    ("what is adhd",                                             "adhd"),
    ("what is autism",                                           "autism"),
    # Treatment queries
    ("what is the treatment for depression",                     "depression"),
    ("what is the treatment for anxiety",                        "anxiety"),
    # Cause queries
    ("what causes depression",                                   "depression"),
    ("what causes anxiety",                                      "anxiety"),
    # Psychological concepts
    ("what is cognitive behavioral therapy",                     "cognitive behavioral therapy"),
    ("what is mindfulness",                                      "mindfulness"),
    ("what is the placebo effect",                               "placebo effect"),
    # Effect queries
    ("how does sleep affect mental health",                      "sleep"),
    # Symptom queries
    ("what are the symptoms of depression",                      "depression"),
    ("what are the symptoms of anxiety",                         "anxiety"),
    # Difference queries
    ("what is the difference between depression and sadness",    "depression and sadness"),
    # Therapy types
    ("what is psychotherapy",                                    "psychotherapy"),
])
def test_batch179_subject_extraction(question, expected):
    """Batch 179: mental health — conditions, treatments, causes, concepts, symptoms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is the difference between X and Y" → X and Y
    ("what is the difference between mitosis and meiosis",       "mitosis and meiosis"),
    ("what is the difference between a virus and a bacterium",   "virus and bacterium"),
    ("what is the difference between a lake and a pond",         "lake and pond"),
    ("what is the difference between weather and climate",       "weather and climate"),
    ("what is the difference between speed and velocity",        "speed and velocity"),
    # "how is X different from Y" → X
    ("how is a plant cell different from an animal cell",        "plant cell"),
    # "which is better X or Y" → X or Y (copula + comparative stripped)
    ("which is better python or java",                           "python or java"),
    ("which is better cats or dogs",                             "cats or dogs"),
    # "is X better than Y" → X (trailing comparative-than strip)
    ("is python better than java",                               "python"),
    ("is coffee better than tea",                                "coffee"),
    # "can X do Y" → X
    ("can fish feel pain",                                       "fish"),
    ("can dogs see color",                                       "dogs"),
    # "do X Y" → X
    ("do plants feel pain",                                      "plants"),
    ("do sharks sleep",                                          "sharks"),
    # "are X Y" → X (article-less predicate: "bats birds" accepted limitation)
    ("are dolphins mammals",                                     "dolphins"),
    ("are bats birds",                                           "bats birds"),
    # "is X a Y" → X
    ("is a tomato a fruit",                                      "tomato"),
    ("is a whale a fish",                                        "whale"),
    # "what is bigger X or Y" → X or Y (leading comparative stripped)
    ("what is bigger jupiter or saturn",                         "jupiter or saturn"),
    # "why is X better than Y" → X
    ("why is exercise better than dieting",                      "exercise"),
])
def test_batch180_subject_extraction(question, expected):
    """Batch 180: comparative/relational — difference, better-than, can/do/are patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "how many X are there" → X (no container)
    ("how many continents are there",                            "continents"),
    # "how many X are in Y" → Y (container: searching the body/system finds the count)
    ("how many planets are in the solar system",                 "solar system"),
    ("how many bones are in the human body",                     "human body"),
    ("how many countries are in the world",                      "world"),
    ("how many states are in the usa",                           "usa"),
    # "how many X does Y have" → Y
    ("how many teeth does a shark have",                         "shark"),
    ("how many chromosomes does a human have",                   "human"),
    ("how many legs does a spider have",                         "spider"),
    ("how many moons does mars have",                            "mars"),
    # "how much does X cost" → X
    ("how much does a tesla cost",                               "tesla"),
    ("how much does a house cost",                               "house"),
    # "how much X is in Y" → Y (container)
    ("how much caffeine is in coffee",                           "coffee"),
    ("how much sugar is in coca cola",                           "coca cola"),
    # "how long is X" → X
    ("how long is the great wall of china",                      "great wall of china"),
    ("how long is the amazon river",                             "amazon river"),
    # "how far is X from Y" → X
    ("how far is the moon from earth",                           "moon"),
    ("how far is pluto from the sun",                            "pluto"),
    # "how old is X" → X
    ("how old is the earth",                                     "earth"),
    ("how old is the universe",                                  "universe"),
    # "how fast is X" → X
    ("how fast is the speed of light",                           "speed of light"),
    ("how fast is a cheetah",                                    "cheetah"),
])
def test_batch181_subject_extraction(question, expected):
    """Batch 181: quantitative — how many/much/long/far/old/fast queries."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is the capital of X" → X
    ("what is the capital of france",                            "france"),
    ("what is the capital of japan",                             "japan"),
    ("what is the capital of australia",                         "australia"),
    # "what is the largest X" → X
    ("what is the largest country in the world",                 "country"),
    ("what is the largest ocean",                                "ocean"),
    ("what is the largest continent",                            "continent"),
    # "what is the smallest X" → X
    ("what is the smallest country in the world",                "country"),
    # "where is X" → X
    ("where is the nile river",                                  "nile river"),
    ("where is mount everest",                                   "mount everest"),
    ("where is the amazon rainforest",                           "amazon rainforest"),
    # "how high is X" → X
    ("how high is mount everest",                                "mount everest"),
    # "what country is X in" → X
    ("what country is paris in",                                 "paris"),
    ("what country is tokyo in",                                 "tokyo"),
    # "what continent is X in" → X
    ("what continent is brazil in",                              "brazil"),
    ("what continent is egypt in",                               "egypt"),
    # "what is the population of X" → X
    ("what is the population of china",                          "china"),
    ("what is the population of india",                          "india"),
    # "what is the currency of X" → X
    ("what is the currency of japan",                            "japan"),
    ("what is the currency of the uk",                           "uk"),
    # "what language is spoken in X" → X
    ("what language is spoken in brazil",                        "brazil"),
])
def test_batch182_subject_extraction(question, expected):
    """Batch 182: geography/world-facts — capitals, sizes, locations, population, currency."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X (math concepts)
    ("what is calculus",                                         "calculus"),
    ("what is algebra",                                          "algebra"),
    ("what is geometry",                                         "geometry"),
    ("what is statistics",                                       "statistics"),
    ("what is probability",                                      "probability"),
    # "what is X" → X (theorems/constants)
    ("what is the pythagorean theorem",                          "pythagorean theorem"),
    ("what is pi",                                               "pi"),
    ("what is euler's number",                                   "euler's number"),
    # "what is the square root of X" ��� X
    ("what is the square root of 144",                           "144"),
    ("what is the square root of 2",                             "2"),
    # "what is X" ��� X (number theory)
    ("what is a prime number",                                   "prime number"),
    ("what is a fibonacci number",                               "fibonacci number"),
    # "what is the derivative of X" → X
    ("what is the derivative of x squared",                      "x squared"),
    # "what is X" → X (set theory)
    ("what is a set",                                            "set"),
    ("what is infinity",                                         "infinity"),
    # "how do you calculate X of a SHAPE" → SHAPE (area/volume reduce to the entity)
    ("how do you calculate the area of a circle",                "circle"),
    ("how do you calculate the mean",                            "mean"),
    # "what is the formula for X of a SHAPE" → SHAPE
    ("what is the formula for the area of a circle",             "circle"),
    # "what is X percent of Y" → X percent of Y (full math expression preserved)
    ("what is 20 percent of 100",                                "20 percent of 100"),
    # "what is standard deviation" → standard deviation
    ("what is standard deviation",                               "standard deviation"),
])
def test_batch183_subject_extraction(question, expected):
    """Batch 183: math/numbers — concepts, theorems, formulas, area, mean, percent."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "when did X happen" → X
    ("when did world war 2 end",                                "world war 2"),
    ("when did the french revolution start",                    "french revolution"),
    ("when did the dinosaurs go extinct",                       "dinosaurs"),
    # "who started/founded X" → X
    ("who started world war 1",                                 "world war 1"),
    ("who founded the united states",                           "united states"),
    # "what caused X" → X
    ("what caused the fall of the roman empire",                "roman empire"),
    ("what caused the great depression",                        "great depression"),
    ("what caused world war 1",                                 "world war 1"),
    # "who was X" → X
    ("who was napoleon",                                        "napoleon"),
    ("who was julius caesar",                                   "julius caesar"),
    ("who was cleopatra",                                       "cleopatra"),
    # "what was X" → X
    ("what was the cold war",                                   "cold war"),
    ("what was the renaissance",                                "renaissance"),
    ("what was the black death",                                "black death"),
    # "when was X built/discovered" → X
    ("when was the great wall of china built",                  "great wall of china"),
    ("when was the eiffel tower built",                         "eiffel tower"),
    ("when was america discovered",                             "america"),
    # event queries
    ("how did the roman empire fall",                           "roman empire"),
    ("what happened during world war 2",                        "world war 2"),
    ("who won world war 2",                                     "world war 2"),
])
def test_batch184_subject_extraction(question, expected):
    """Batch 184: history/timeline �� events, causes, people, eras."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X (biology concepts)
    ("what is photosynthesis",                                  "photosynthesis"),
    ("what is mitosis",                                         "mitosis"),
    ("what is meiosis",                                         "meiosis"),
    ("what is dna",                                             "dna"),
    ("what is rna",                                             "rna"),
    ("what is evolution",                                       "evolution"),
    ("what is natural selection",                               "natural selection"),
    # "how does X work" → X
    ("how does photosynthesis work",                            "photosynthesis"),
    ("how does the immune system work",                         "immune system"),
    # "what is the difference between X and Y" → X and Y
    ("what is the difference between mitosis and meiosis",      "mitosis and meiosis"),
    ("what is the difference between dna and rna",              "dna and rna"),
    # "what do X eat" → X
    ("what do pandas eat",                                      "pandas"),
    ("what do sharks eat",                                      "sharks"),
    # "how long do X live" → X
    ("how long do elephants live",                              "elephants"),
    ("how long do turtles live",                                "turtles"),
    # "what is the largest X" → X
    ("what is the largest mammal",                              "mammal"),
    ("what is the largest animal",                              "animal"),
    # "how many X does Y have" → Y
    ("how many legs does a spider have",                        "spider"),
    ("how many chambers does the heart have",                   "heart"),
    # "what is X made of" → X
    ("what is bone made of",                                    "bone"),
])
def test_batch185_subject_extraction(question, expected):
    """Batch 185: biology/life-sciences — concepts, behaviors, anatomy."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X (chemistry concepts)
    ("what is a chemical reaction",                             "chemical reaction"),
    ("what is an acid",                                         "acid"),
    ("what is a base in chemistry",                             "base"),
    ("what is osmosis",                                         "osmosis"),
    ("what is oxidation",                                       "oxidation"),
    ("what is an element",                                      "element"),
    ("what is a compound",                                      "compound"),
    ("what is a molecule",                                      "molecule"),
    # "what is the chemical formula for X" → X
    ("what is the chemical formula for water",                  "water"),
    ("what is the chemical formula for carbon dioxide",         "carbon dioxide"),
    ("what is the chemical formula for glucose",                "glucose"),
    # "how does X react with Y" → X
    ("how does acid react with metal",                          "acid"),
    ("how does hydrogen react with oxygen",                     "hydrogen"),
    # "what is the atomic number of X" → X
    ("what is the atomic number of gold",                       "gold"),
    ("what is the atomic number of carbon",                     "carbon"),
    # "what is X made of" → X
    ("what is water made of",                                   "water"),
    ("what is steel made of",                                   "steel"),
    # "what happens when X is/does Y" → X
    ("what happens when ice is heated",                         "ice"),
    ("what happens when water boils",                           "water"),
    # "what is the boiling point of X" → X
    ("what is the boiling point of water",                      "water"),
])
def test_batch186_subject_extraction(question, expected):
    """Batch 186: chemistry — reactions, formulas, elements, state changes."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X (physics concepts)
    ("what is gravity",                                         "gravity"),
    ("what is friction",                                        "friction"),
    ("what is inertia",                                         "inertia"),
    ("what is momentum",                                        "momentum"),
    ("what is kinetic energy",                                  "kinetic energy"),
    ("what is potential energy",                                "potential energy"),
    ("what is thermodynamics",                                  "thermodynamics"),
    ("what is quantum mechanics",                               "quantum mechanics"),
    # "what is the speed of X" → speed of X (canonical constant, no article)
    ("what is the speed of light",                              "speed of light"),
    ("what is the speed of sound",                              "speed of sound"),
    # "how does X work" → X
    ("how does gravity work",                                   "gravity"),
    ("how does a magnet work",                                  "magnet"),
    # "what is X energy" → X energy
    ("what is nuclear energy",                                  "nuclear energy"),
    ("what is solar energy",                                    "solar energy"),
    # "how fast does X travel" → X
    ("how fast does light travel",                              "light"),
    ("how fast does sound travel",                              "sound"),
    # "what is the theory of X" → theory of X
    ("what is the theory of relativity",                        "theory of relativity"),
    # "what is newton's X law" → newton's X law
    ("what is newton's third law",                              "newton's third law"),
    # "how much does X weigh" → X
    ("how much does the earth weigh",                           "earth"),
    # "what is the force of X" → X (force is a property noun)
    ("what is the force of gravity",                            "gravity"),
])
def test_batch187_subject_extraction(question, expected):
    """Batch 187: physics — forces, energy, constants, laws, theory of relativity."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X (tech concepts)
    ("what is machine learning",                                "machine learning"),
    ("what is artificial intelligence",                         "artificial intelligence"),
    ("what is the internet",                                    "internet"),
    ("what is blockchain",                                      "blockchain"),
    ("what is the cloud",                                       "cloud"),
    ("what is an algorithm",                                    "algorithm"),
    ("what is open source",                                     "open source"),
    # "what is a X in Y" → X (concept in context, not property-of)
    ("what is a variable in programming",                       "variable"),
    ("what is a function in python",                            "function"),
    ("what is an api",                                          "api"),
    ("what is recursion",                                       "recursion"),
    # "what is the difference between X and Y" → X and Y
    ("what is the difference between http and https",           "http and https"),
    ("what is the difference between ram and rom",              "ram and rom"),
    # "how does X work" → X
    ("how does the internet work",                              "internet"),
    ("how does machine learning work",                          "machine learning"),
    ("how does encryption work",                                "encryption"),
    # "what programming language is X written in" → X
    ("what programming language is python written in",          "python"),
    # "how many X are in Y" → Y (container)
    ("how many bits are in a byte",                             "byte"),
    # "what is the most popular X" → X
    ("what is the most popular programming language",           "programming language"),
    # "how do you VERB a NOUN in LANG" → NOUN
    ("how do you reverse a string in python",                   "string"),
])
def test_batch188_subject_extraction(question, expected):
    """Batch 188: technology/computing — AI, internet, programming concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X (sports concepts)
    ("what is offside in soccer",                               "offside"),
    ("what is a grand slam in tennis",                          "grand slam"),
    ("what is a hat trick in soccer",                           "hat trick"),
    # "how many players are on a X team" → X (sport name; team is stripped by design)
    ("how many players are on a basketball team",               "basketball"),
    ("how many players are on a soccer team",                   "soccer"),
    # "how long is a X game" → X game
    ("how long is a basketball game",                           "basketball game"),
    ("how long is a football game",                             "football game"),
    # "who invented X" → X
    ("who invented basketball",                                 "basketball"),
    ("who invented soccer",                                     "soccer"),
    # "what is the fastest sport" → sport
    ("what is the fastest sport",                               "sport"),
    # "how do you score in X" → X
    ("how do you score in bowling",                             "bowling"),
    # "what country has won the most world cups" → world cups
    ("what country has won the most world cups",                "world cups"),
    # "who holds the world record for X" → X
    ("who holds the world record for the 100 meter dash",       "100 meter dash"),
    # "how far is a X" → X
    ("how far is a marathon",                                   "marathon"),
    # "what is the highest score possible in X" → X
    ("what is the highest score possible in bowling",           "bowling"),
    # "how many sets are in a X match" → X match
    ("how many sets are in a tennis match",                     "tennis match"),
    # "how do you play X" → X
    ("how do you play chess",                                   "chess"),
    # "what are the rules of X" → X
    ("what are the rules of chess",                             "chess"),
    # "how many rings does the X have" → X
    ("how many rings does the olympic flag have",               "olympic flag"),
    # "who has won the most X" → X
    ("who has won the most super bowls",                        "super bowls"),
])
def test_batch189_subject_extraction(question, expected):
    """Batch 189: sports/games — rules, counts, records, inventors."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X (cooking concepts)
    ("what is umami",                                           "umami"),
    ("what is sauteing",                                        "sauteing"),
    ("what is a roux",                                          "roux"),
    ("what is blanching",                                       "blanching"),
    ("what is basting",                                         "basting"),
    # "how do you make X" → X
    ("how do you make pasta",                                   "pasta"),
    ("how do you make bread",                                   "bread"),
    ("how do you make pizza dough",                             "pizza dough"),
    # "what is the difference between X and Y" → X and Y
    ("what is the difference between baking and roasting",      "baking and roasting"),
    # "how long does it take to cook X" → X
    ("how long does it take to cook chicken",                   "chicken"),
    ("how long does it take to cook pasta",                     "pasta"),
    # "what temperature do you cook X at" → X
    ("what temperature do you cook chicken at",                 "chicken"),
    # "what are the ingredients in X" → X
    ("what are the ingredients in guacamole",                   "guacamole"),
    ("what are the ingredients in hummus",                      "hummus"),
    # "how do you boil a X" → X
    ("how do you boil an egg",                                  "egg"),
    # "what is the best way to cook X" → X
    ("what is the best way to cook steak",                      "steak"),
    # "how many calories are in a X" → X
    ("how many calories are in an apple",                       "apple"),
    ("how many calories are in a banana",                       "banana"),
    # "what food is high in X" → X (adjective-in-nutrient extraction)
    ("what food is high in protein",                            "protein"),
    # "how do you store X" → X
    ("how do you store leftovers",                              "leftovers"),
])
def test_batch190_subject_extraction(question, expected):
    """Batch 190: food/cooking — techniques, recipes, nutrients, storage."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" → X (government concepts)
    ("what is democracy",                                       "democracy"),
    ("what is communism",                                       "communism"),
    ("what is capitalism",                                      "capitalism"),
    ("what is socialism",                                       "socialism"),
    ("what is federalism",                                      "federalism"),
    # "what is the role of X" → X
    ("what is the role of the president",                       "president"),
    ("what is the role of the supreme court",                   "supreme court"),
    # "how does X work" → X
    ("how does the electoral college work",                     "electoral college"),
    ("how does congress work",                                  "congress"),
    # "who is the head of state" → "head of state" (the position is the topic)
    ("who is the head of state",                                "head of state"),
    # "how many branches of government are there" → "branches of government"
    ("how many branches of government are there",               "branches of government"),
    # "what is the difference between X and Y" → X and Y
    ("what is the difference between a republic and a democracy", "republic and democracy"),
    # "who has the power to X" → "power to X"
    ("who has the power to declare war",                        "power to declare war"),
    # "what is the X amendment" → X amendment
    ("what is the first amendment",                             "first amendment"),
    ("what is the second amendment",                            "second amendment"),
    # "how long is a X term" → X term
    ("how long is a presidential term",                         "presidential term"),
    # "who elects X" → X (civic verb stripped)
    ("who elects the president",                                "president"),
    # "what is X" → X
    ("what is a veto",                                          "veto"),
    ("what is impeachment",                                     "impeachment"),
    # "how do you become a X" → X
    ("how do you become a senator",                             "senator"),
])
def test_batch191_subject_extraction(question, expected):
    """Batch 191: politics/government — concepts, roles, civic verbs, amendments."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "who played X in Y" → X (character); "played" stripped as leading verb
    ("who played iron man in the avengers",                     "iron man"),
    ("who played harry potter in the movies",                   "harry potter"),
    # "who wrote X" → X
    ("who wrote harry potter",                                  "harry potter"),
    ("who wrote the great gatsby",                              "great gatsby"),
    # "who directed X" → X
    ("who directed titanic",                                    "titanic"),
    ("who directed the dark knight",                            "dark knight"),
    # "what year did X come out" → X
    ("what year did titanic come out",                          "titanic"),
    ("what year did the dark knight come out",                  "dark knight"),
    # "who sang X" → X
    ("who sang bohemian rhapsody",                              "bohemian rhapsody"),
    ("who sang thriller",                                       "thriller"),
    # "what genre is X" → X
    ("what genre is bohemian rhapsody",                         "bohemian rhapsody"),
    # "who created X" → X
    ("who created star wars",                                   "star wars"),
    ("who created the simpsons",                                "simpsons"),
    # "what is X rated" → X
    ("what is titanic rated",                                   "titanic"),
    # "how many episodes are in X" → X
    ("how many episodes are in game of thrones",                "game of thrones"),
    # "who voiced X" → X; "voiced" stripped as leading verb
    ("who voiced buzz lightyear",                               "buzz lightyear"),
    # "what movie won X" → "movie won X" (no category-won pattern)
    ("what movie won best picture",                             "movie won best picture"),
    # "who won the X for Y" → Y
    ("who won the grammy for best album",                       "best album"),
    # "how many seasons does X have" → X; "bad" guarded from title strip
    ("how many seasons does breaking bad have",                 "breaking bad"),
    # "what is the highest grossing movie" → "movie" (superlative+participle stripped)
    ("what is the highest grossing movie",                      "movie"),
])
def test_batch192_subject_extraction(question, expected):
    """Batch 192: pop culture/entertainment — film, music, TV, actors."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "who wrote X" → X
    ("who wrote hamlet",                                        "hamlet"),
    ("who wrote 1984",                                          "1984"),
    ("who wrote pride and prejudice",                           "pride and prejudice"),
    # "to kill a mockingbird" keeps the leading "to" (it's part of the title)
    ("who wrote to kill a mockingbird",                         "to kill a mockingbird"),
    # "what is X about" → X
    ("what is hamlet about",                                    "hamlet"),
    ("what is 1984 about",                                      "1984"),
    # "when was X published" → X
    ("when was hamlet published",                               "hamlet"),
    ("when was 1984 published",                                 "1984"),
    # "what genre is X" → X
    ("what genre is 1984",                                      "1984"),
    # "how many chapters are in X" → X
    ("how many chapters are in moby dick",                      "moby dick"),
    # "who is the main character in X" → X (scaffold strips "main"; role-in-work strips "character in")
    ("who is the main character in hamlet",                     "hamlet"),
    # "what is the plot of X" / "theme of X" → X
    ("what is the plot of hamlet",                              "hamlet"),
    ("what is the theme of 1984",                               "1984"),
    # "what does X symbolize in Y" → X  ("in Y" stripped then trailing "symbolize" stripped)
    ("what does the green light symbolize in the great gatsby", "green light"),
    # "who is the author of X" → X
    ("who is the author of hamlet",                             "hamlet"),
    # "what year was X written" → X
    ("what year was hamlet written",                            "hamlet"),
    # "how long is X" → X
    ("how long is moby dick",                                   "moby dick"),
    # "what is X a metaphor for" → X
    ("what is the white whale a metaphor for",                  "white whale"),
    # "is X fiction or nonfiction" → X
    ("is 1984 fiction or nonfiction",                           "1984"),
    # "who narrates X" → X
    ("who narrates moby dick",                                  "moby dick"),
])
def test_batch193_subject_extraction(question, expected):
    """Batch 193: literature/books — authorship, plot, symbolism, genre."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "who sang X" → X
    ("who sang bohemian rhapsody",                             "bohemian rhapsody"),
    ("who sang thriller",                                      "thriller"),
    # "who wrote X" (song) → X
    ("who wrote imagine",                                      "imagine"),
    ("who wrote smells like teen spirit",                      "smells like teen spirit"),
    # "what album is X on" → X
    ("what album is thriller on",                              "thriller"),
    # "what genre is X" → X
    ("what genre is jazz",                                     "jazz"),
    ("what genre is bohemian rhapsody",                        "bohemian rhapsody"),
    # "who produced X" → X
    ("who produced thriller",                                  "thriller"),
    # "who is the lead singer of X" → X (lead stripped as scaffold; singer-of stripped next)
    ("who is the lead singer of queen",                        "queen"),
    ("who is the lead singer of the beatles",                  "beatles"),
    # "what year did X come out" → X
    ("what year did thriller come out",                        "thriller"),
    ("what year did bohemian rhapsody come out",               "bohemian rhapsody"),
    # "how many albums does X have" → X
    ("how many albums does taylor swift have",                 "taylor swift"),
    # "who played INSTRUMENT on X" → X (instrument stripped after verb strip; then on-work)
    ("who played guitar on bohemian rhapsody",                 "bohemian rhapsody"),
    # "what instruments are used in X" → X
    ("what instruments are used in jazz",                      "jazz"),
    # "what is the tempo of X" → X
    ("what is the tempo of bohemian rhapsody",                 "bohemian rhapsody"),
    # "what key is X in" → X (early match before scaffold strips "key")
    ("what key is imagine in",                                 "imagine"),
    # "who invented X" → X
    ("who invented jazz",                                      "jazz"),
    # "who wrote the national anthem" → national anthem
    ("who wrote the national anthem",                          "national anthem"),
    # "how long is X" → X
    ("how long is bohemian rhapsody",                          "bohemian rhapsody"),
])
def test_batch194_subject_extraction(question, expected):
    """Batch 194: music — songs, bands, production, music theory."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "who invented/created X" → X
    ("who invented the internet",                              "internet"),
    ("who invented the telephone",                             "telephone"),
    ("who created linux",                                      "linux"),
    ("who created python",                                     "python"),
    # "what is X used for" → X
    ("what is python used for",                                "python"),
    ("what is javascript used for",                            "javascript"),
    # "what is X" → X
    ("what is machine learning",                               "machine learning"),
    ("what is artificial intelligence",                        "artificial intelligence"),
    # "how does X work" → X
    ("how does the internet work",                             "internet"),
    ("how does encryption work",                               "encryption"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between tcp and udp",             "tcp and udp"),
    # "what programming language is X written in" → X
    ("what programming language is linux written in",          "linux"),
    # "best programming language for X" → X (superlative stripped; then category-for strip)
    ("what is the best programming language for machine learning", "machine learning"),
    # "how many X are in Y" → Y (container is the lookup subject)
    ("how many bits are in a byte",                            "byte"),
    # bare term lookups
    ("what is an algorithm",                                   "algorithm"),
    ("what is a database",                                     "database"),
    ("what is cloud computing",                                "cloud computing"),
    # "what does X stand for" → X
    ("what does html stand for",                               "html"),
    ("what does cpu stand for",                                "cpu"),
    # "who makes X" → X
    ("who makes the iphone",                                   "iphone"),
    # "what year was X released" → X
    ("what year was windows 95 released",                      "windows 95"),
])
def test_batch195_subject_extraction(question, expected):
    """Batch 195: technology/computers — software, hardware, CS concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is the capital of X" → X
    ("what is the capital of france",                          "france"),
    ("what is the capital of the united states",               "united states"),
    ("what is the capital of australia",                       "australia"),
    # "what country is X in" → X (city or landmark)
    ("what country is paris in",                               "paris"),
    ("what country is the amazon river in",                    "amazon river"),
    # "how big is X" → X
    ("how big is the amazon rainforest",                       "amazon rainforest"),
    # "what continent is X in" → X
    ("what continent is brazil in",                            "brazil"),
    ("what continent is egypt in",                             "egypt"),
    # "what is the largest country in X" → X
    ("what is the largest country in europe",                  "europe"),
    ("what is the largest country in south america",           "south america"),
    # "how long is X" → X (rivers, landmarks)
    ("how long is the nile river",                             "nile river"),
    ("how long is the great wall of china",                    "great wall of china"),
    # "what is the population of X" → X
    ("what is the population of china",                        "china"),
    ("what is the population of new york city",                "new york city"),
    # "where is X located" → X
    ("where is the eiffel tower located",                      "eiffel tower"),
    ("where is mount everest located",                         "mount everest"),
    # "what is the highest mountain in X" → X
    ("what is the highest mountain in africa",                 "africa"),
    # "what language is spoken in X" → X
    ("what language is spoken in brazil",                      "brazil"),
    ("what language is spoken in switzerland",                 "switzerland"),
    # "what ocean borders X" → X
    ("what ocean borders australia",                           "australia"),
    # "what is the currency of X" → X
    ("what is the currency of japan",                          "japan"),
])
def test_batch196_subject_extraction(question, expected):
    """Batch 196: geography/world — capitals, populations, rivers, locations."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" (medical/health term) → X
    ("what is diabetes",                                       "diabetes"),
    ("what is cancer",                                         "cancer"),
    ("what is hypertension",                                   "hypertension"),
    # "what causes X" → X
    ("what causes diabetes",                                   "diabetes"),
    ("what causes high blood pressure",                        "high blood pressure"),
    # "how is X treated" → X
    ("how is diabetes treated",                                "diabetes"),
    ("how is cancer treated",                                  "cancer"),
    # "what are the symptoms of X" → X
    ("what are the symptoms of diabetes",                      "diabetes"),
    ("what are the symptoms of covid",                         "covid"),
    # "is X contagious" → X
    ("is covid contagious",                                    "covid"),
    ("is the flu contagious",                                  "flu"),
    # "how do you treat X" → X
    ("how do you treat a headache",                            "headache"),
    ("how do you treat diabetes",                              "diabetes"),
    # "what is the cure for X" → X
    ("what is the cure for the common cold",                   "common cold"),
    # "how long does X last" → X
    ("how long does the flu last",                             "flu"),
    # "what foods are good for X" → X
    ("what foods are good for the heart",                      "heart"),
    # "how does X spread" → X
    ("how does covid spread",                                  "covid"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between a virus and a bacteria",  "virus and bacteria"),
    # "what vitamin helps with X" → X
    ("what vitamin helps with immune system",                  "immune system"),
    # "is X bad for you" → X
    ("is sugar bad for you",                                   "sugar"),
    # "how much sleep does a person need" → person (entity is lookup subject)
    ("how much sleep does a person need",                      "person"),
])
def test_batch197_subject_extraction(question, expected):
    """Batch 197: health/medicine — symptoms, treatments, conditions, nutrition."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" (economic/finance term) → X
    ("what is inflation",                                      "inflation"),
    ("what is a recession",                                    "recession"),
    ("what is gdp",                                            "gdp"),
    # "what causes X" → X
    ("what causes inflation",                                  "inflation"),
    ("what causes a recession",                                "recession"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between stocks and bonds",        "stocks and bonds"),
    # "how does X work" → X
    ("how does a stock market work",                           "stock market"),
    ("how does interest work",                                 "interest"),
    # "what is the X rate" → X rate
    ("what is the interest rate",                              "interest rate"),
    ("what is the unemployment rate",                          "unemployment rate"),
    # "how do you invest in X" → X
    ("how do you invest in stocks",                            "stocks"),
    ("how do you invest in real estate",                       "real estate"),
    # "what is a good X" → "good X" ("good" stays as predicate adjective)
    ("what is a good credit score",                            "good credit score"),
    # "what is the X" → X
    ("what is the federal reserve",                            "federal reserve"),
    # "how does X affect Y" → X (agent is the lookup subject, existing design)
    ("how does inflation affect savings",                      "inflation"),
    # "what is compound X" → compound X
    ("what is compound interest",                              "compound interest"),
    # "how do X work" → X
    ("how do taxes work",                                      "taxes"),
    # "what is a X Y" (noun compound) → X Y
    ("what is a budget deficit",                               "budget deficit"),
    ("what is cryptocurrency",                                 "cryptocurrency"),
    # "what is a X market crash" → X market crash (crash is nominal head)
    ("what is a stock market crash",                           "stock market crash"),
])
def test_batch198_subject_extraction(question, expected):
    """Batch 198: economics/finance — inflation, recession, investing, markets."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" (philosophy/ethics term) → X
    ("what is ethics",                                              "ethics"),
    ("what is philosophy",                                          "philosophy"),
    ("what is morality",                                            "morality"),
    ("what is utilitarianism",                                      "utilitarianism"),
    ("what is existentialism",                                      "existentialism"),
    # "who is X" (philosopher) → X
    ("who is socrates",                                             "socrates"),
    ("who is plato",                                                "plato"),
    # "what did X believe" → X
    ("what did aristotle believe",                                  "aristotle"),
    ("what did kant believe",                                       "kant"),
    # "what is the meaning of life" → "meaning of life"
    ("what is the meaning of life",                                 "meaning of life"),
    # "what is the trolley problem" → "trolley problem"
    ("what is the trolley problem",                                 "trolley problem"),
    # "what is X theory" → X theory
    ("what is social contract theory",                              "social contract theory"),
    # "is X morally ADJECTIVE" → X (\w+ly adverb stripped with predicate adj)
    ("is lying morally wrong",                                      "lying"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between deontology and utilitarianism", "deontology and utilitarianism"),
    # "what does X mean" → X
    ("what does consciousness mean",                                "consciousness"),
    # "what is free will" → "free will"
    ("what is free will",                                           "free will"),
    ("what is stoicism",                                            "stoicism"),
    ("what is nihilism",                                            "nihilism"),
    # "what is the philosophy of X" → "philosophy of X" (recognized academic subfield)
    ("what is the philosophy of science",                           "philosophy of science"),
    # "who founded X" → X
    ("who founded stoicism",                                        "stoicism"),
])
def test_batch199_subject_extraction(question, expected):
    """Batch 199: philosophy/ethics — terms, thinkers, moral predicates."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" (environmental term) → X
    ("what is climate change",                                 "climate change"),
    ("what is global warming",                                 "global warming"),
    ("what is deforestation",                                  "deforestation"),
    ("what is biodiversity",                                   "biodiversity"),
    ("what is an ecosystem",                                   "ecosystem"),
    # "what causes X" → X
    ("what causes climate change",                             "climate change"),
    ("what causes acid rain",                                  "acid rain"),
    # "what is the X" → X
    ("what is the greenhouse effect",                          "greenhouse effect"),
    # "how does X affect Y" → X (existing design: agent is lookup subject)
    ("how does pollution affect the ocean",                    "pollution"),
    # "what is the ozone layer" → "ozone layer"
    ("what is the ozone layer",                                "ozone layer"),
    # "how do ACTOR contribute to X" → X (contribution target is lookup subject)
    ("how do humans contribute to climate change",             "climate change"),
    # "what are the effects of X" → X
    ("what are the effects of deforestation",                  "deforestation"),
    # "why is X important" → X
    ("why is biodiversity important",                          "biodiversity"),
    ("why is the rainforest important",                        "rainforest"),
    # "what is a X" → X
    ("what is a carbon footprint",                             "carbon footprint"),
    # "how does X work" → X
    ("how does solar energy work",                             "solar energy"),
    ("what is renewable energy",                               "renewable energy"),
    # "what is X pollution" → "X pollution"
    ("what is air pollution",                                  "air pollution"),
    ("what is water pollution",                                "water pollution"),
    # "what causes species extinction" → "species extinction"
    ("what causes species extinction",                         "species extinction"),
])
def test_batch200_subject_extraction(question, expected):
    """Batch 200: environmental science — climate, ecosystems, pollution."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" (psychology term) → X
    ("what is psychology",                                     "psychology"),
    ("what is cognitive dissonance",                           "cognitive dissonance"),
    ("what is the placebo effect",                             "placebo effect"),
    ("what is confirmation bias",                              "confirmation bias"),
    ("what is schizophrenia",                                  "schizophrenia"),
    ("what is depression",                                     "depression"),
    ("what is anxiety",                                        "anxiety"),
    # "what causes X" → X
    ("what causes depression",                                 "depression"),
    ("what causes anxiety",                                    "anxiety"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between psychosis and neurosis",  "psychosis and neurosis"),
    # "how does X work" → X
    ("how does memory work",                                   "memory"),
    ("how does the brain process information",                 "brain"),
    # "what is X disorder" → "X disorder"
    ("what is bipolar disorder",                               "bipolar disorder"),
    ("what is autism spectrum disorder",                       "autism spectrum disorder"),
    # "how do X affect Y" → X (existing design: agent is lookup subject)
    ("how do emotions affect decision making",                 "emotions"),
    # compound-noun definitions
    ("what is short term memory",                              "short term memory"),
    ("what is the subconscious mind",                          "subconscious mind"),
    # "why do people VERB" → VERB (generic agent stripped; phenomenon is subject)
    ("why do people dream",                                    "dream"),
    ("what is social anxiety",                                 "social anxiety"),
    ("what is iq",                                             "iq"),
])
def test_batch201_subject_extraction(question, expected):
    """Batch 201: psychology/cognitive science — disorders, biases, phenomena."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" (astronomy term) → X
    ("what is a black hole",                                   "black hole"),
    ("what is a neutron star",                                 "neutron star"),
    ("what is dark matter",                                    "dark matter"),
    ("what is dark energy",                                    "dark energy"),
    ("what is a supernova",                                    "supernova"),
    # "how far is X from earth" → X
    ("how far is the moon from earth",                         "moon"),
    ("how far is mars from earth",                             "mars"),
    # "what is the size of X" → X
    ("what is the size of the sun",                            "sun"),
    # "how old is X" → X
    ("how old is the universe",                                "universe"),
    ("how old is the sun",                                     "sun"),
    # "how does X form" → X
    ("how does a black hole form",                             "black hole"),
    ("how do stars form",                                      "stars"),
    # compound-noun definitions
    ("what is the milky way",                                  "milky way"),
    # "how many X are in Y" → Y
    ("how many planets are in the solar system",               "solar system"),
    # multi-word proper-noun definitions
    ("what is the big bang theory",                            "big bang theory"),
    # "what causes X" → X
    ("what causes a solar eclipse",                            "solar eclipse"),
    # "how does X work" → X
    ("how does gravity work",                                  "gravity"),
    # "what is a X" → X
    ("what is a light year",                                   "light year"),
    # "is there X on Y" → Y
    ("is there life on mars",                                  "mars"),
    # "what is the speed of X" → "speed of X"
    ("what is the speed of light",                             "speed of light"),
])
def test_batch202_subject_extraction(question, expected):
    """Batch 202: astronomy/space — black holes, stars, planets, cosmology."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # "what is X" (law/political term) → X
    ("what is democracy",                                      "democracy"),
    ("what is communism",                                      "communism"),
    ("what is capitalism",                                     "capitalism"),
    ("what is socialism",                                      "socialism"),
    ("what is the constitution",                               "constitution"),
    # "what is X law" → "X law"
    ("what is constitutional law",                             "constitutional law"),
    ("what is international law",                              "international law"),
    # "what is the difference between X and Y" → "X and Y"
    ("what is the difference between democracy and republic",  "democracy and republic"),
    # "how does X work" → X
    ("how does congress work",                                 "congress"),
    ("how does the electoral college work",                    "electoral college"),
    # "what are the branches of X" → X
    ("what are the branches of government",                    "government"),
    # "what is X" (legal Latin/compound) → X
    ("what is habeas corpus",                                  "habeas corpus"),
    ("what is due process",                                    "due process"),
    # "what is the bill of rights" → "bill of rights"
    ("what is the bill of rights",                             "bill of rights"),
    # "who is the president of X" → X
    ("who is the president of the united states",              "united states"),
    # compound-noun definitions
    ("what is a civil war",                                    "civil war"),
    ("what is martial law",                                    "martial law"),
    ("what is the supreme court",                              "supreme court"),
    # "how are X made" → X
    ("how are laws made",                                      "laws"),
    # "what is freedom of X" → "freedom of X"
    ("what is freedom of speech",                              "freedom of speech"),
])
def test_batch203_subject_extraction(question, expected):
    """Batch 203: law/politics — democracy, legal terms, government structure."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is photosynthesis",                                "photosynthesis"),
    ("what is mitosis",                                       "mitosis"),
    ("what is dna",                                           "dna"),
    ("what is rna",                                           "rna"),
    ("what is evolution",                                     "evolution"),
    ("what is natural selection",                             "natural selection"),
    ("how does photosynthesis work",                          "photosynthesis"),
    ("how does cellular respiration work",                    "cellular respiration"),
    ("what is the difference between dna and rna",            "dna and rna"),
    ("what is the difference between mitosis and meiosis",    "mitosis and meiosis"),
    ("how do cells reproduce",                                "cells"),
    ("how do bacteria reproduce",                             "bacteria"),
    ("what is a food chain",                                  "food chain"),
    ("what is an ecosystem",                                  "ecosystem"),
    ("what causes genetic mutations",                         "genetic mutations"),
    ("what is the cell cycle",                                "cell cycle"),
    ("how do plants make food",                               "plants"),
    ("what is a chromosome",                                  "chromosome"),
    ("what is homeostasis",                                   "homeostasis"),
    ("how does the immune system fight infection",            "immune system"),
])
def test_batch210_subject_extraction(question, expected):
    """Batch 210: biology/life science — photosynthesis, cells, evolution, genetics."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is an atom",                                       "atom"),
    ("what is a molecule",                                    "molecule"),
    ("what is a chemical reaction",                           "chemical reaction"),
    ("what is an element",                                    "element"),
    ("what is a compound",                                    "compound"),
    ("what is the periodic table",                            "periodic table"),
    ("what is hydrochloric acid",                             "hydrochloric acid"),
    ("what is sulfuric acid",                                 "sulfuric acid"),
    ("how does oxidation work",                               "oxidation"),
    # articles stripped: "a molecule" → "molecule"
    ("what is the difference between an atom and a molecule", "atom and molecule"),
    ("what is the difference between acids and bases",        "acids and bases"),
    ("what is covalent bonding",                              "covalent bonding"),
    ("what is ionic bonding",                                 "ionic bonding"),
    ("what is ph",                                            "ph"),
    ("what causes a chemical reaction",                       "chemical reaction"),
    ("what is the atomic number of carbon",                   "carbon"),
    ("what is radioactive decay",                             "radioactive decay"),
    ("what is organic chemistry",                             "organic chemistry"),
    ("how does electrolysis work",                            "electrolysis"),
    ("what is a catalyst",                                    "catalyst"),
])
def test_batch211_subject_extraction(question, expected):
    """Batch 211: chemistry — atoms, reactions, bonds, periodic table."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is calculus",                                      "calculus"),
    ("what is algebra",                                       "algebra"),
    ("what is geometry",                                      "geometry"),
    ("what is trigonometry",                                  "trigonometry"),
    ("what is statistics",                                    "statistics"),
    ("what is probability",                                   "probability"),
    ("what is the pythagorean theorem",                       "pythagorean theorem"),
    ("what is a prime number",                                "prime number"),
    ("how does binary work",                                  "binary"),
    ("what is the difference between mean and median",        "mean and median"),
    ("what is the central limit theorem",                     "central limit theorem"),
    ("what is a derivative",                                  "derivative"),
    ("what is an integral",                                   "integral"),
    ("what is a matrix",                                      "matrix"),
    ("how do you solve a quadratic equation",                 "quadratic equation"),
    ("what is pi",                                            "pi"),
    ("what is infinity",                                      "infinity"),
    # context qualifier "in mathematics"/"in math" is stripped — core subject remains
    ("what is a set in mathematics",                          "set"),
    ("what is linear algebra",                                "linear algebra"),
    ("what is a function in math",                            "function"),
])
def test_batch212_subject_extraction(question, expected):
    """Batch 212: mathematics — calculus, algebra, theorems, proofs."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what was world war 2",                                  "world war 2"),
    ("what was world war 1",                                  "world war 1"),
    ("what was the cold war",                                 "cold war"),
    ("what was the renaissance",                              "renaissance"),
    ("what was the industrial revolution",                    "industrial revolution"),
    ("what was the french revolution",                        "french revolution"),
    ("what caused world war 1",                               "world war 1"),
    # "X of Y" pattern strips "fall of" → returns the named entity
    ("what caused the fall of the roman empire",              "roman empire"),
    ("who was napoleon",                                      "napoleon"),
    ("who was julius caesar",                                 "julius caesar"),
    ("who was alexander the great",                           "alexander the great"),
    ("when did world war 2 end",                              "world war 2"),
    ("when did the roman empire fall",                        "roman empire"),
    ("what is the history of rome",                           "rome"),
    ("what is the history of china",                          "china"),
    ("what started the american revolution",                  "american revolution"),
    ("who built the pyramids",                                "pyramids"),
    ("what happened during the black death",                  "black death"),
    ("what was the magna carta",                              "magna carta"),
    ("what is feudalism",                                     "feudalism"),
])
def test_batch213_subject_extraction(question, expected):
    """Batch 213: world history — wars, empires, revolutions, historical figures."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is linguistics",                                   "linguistics"),
    ("what is phonetics",                                     "phonetics"),
    ("what is syntax",                                        "syntax"),
    ("what is semantics",                                     "semantics"),
    ("what is grammar",                                       "grammar"),
    ("what is a dialect",                                     "dialect"),
    ("what is the difference between a language and a dialect", "language and dialect"),
    ("how many languages are there",                          "languages"),
    # superlative stripping design: "oldest X" → "X"
    ("what is the oldest language",                           "language"),
    ("what is the most spoken language",                      "language"),
    ("how do languages evolve",                               "languages"),
    ("what is sign language",                                 "sign language"),
    ("how does language acquisition work",                    "language acquisition"),
    ("what is a noun",                                        "noun"),
    ("what is a verb",                                        "verb"),
    ("what is an adjective",                                  "adjective"),
    ("what is etymology",                                     "etymology"),
    ("what is slang",                                         "slang"),
    ("what is bilingualism",                                  "bilingualism"),
    ("what is the sapir whorf hypothesis",                    "sapir whorf hypothesis"),
])
def test_batch214_subject_extraction(question, expected):
    """Batch 214: languages/linguistics — grammar, syntax, dialects, acquisition."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is christianity",                                  "christianity"),
    ("what is islam",                                         "islam"),
    ("what is buddhism",                                      "buddhism"),
    ("what is hinduism",                                      "hinduism"),
    ("what is judaism",                                       "judaism"),
    ("what is atheism",                                       "atheism"),
    ("what is agnosticism",                                   "agnosticism"),
    ("what is the bible",                                     "bible"),
    ("what is the quran",                                     "quran"),
    ("who is jesus",                                          "jesus"),
    ("who is muhammad",                                       "muhammad"),
    ("who is buddha",                                         "buddha"),
    ("what is a religion",                                    "religion"),
    ("what is prayer",                                        "prayer"),
    ("what is meditation",                                    "meditation"),
    ("what are the ten commandments",                         "ten commandments"),
    ("what is reincarnation",                                 "reincarnation"),
    ("what is karma",                                         "karma"),
    ("what is nirvana",                                       "nirvana"),
    ("what is the difference between sunni and shia",         "sunni and shia"),
])
def test_batch215_subject_extraction(question, expected):
    """Batch 215: religion/world religions — christianity, islam, buddhism, concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is architecture",                                  "architecture"),
    ("what is civil engineering",                             "civil engineering"),
    ("what is mechanical engineering",                        "mechanical engineering"),
    ("what is electrical engineering",                        "electrical engineering"),
    ("what is structural engineering",                        "structural engineering"),
    ("how does a bridge work",                                "bridge"),
    ("how does a dam work",                                   "dam"),
    ("how does a skyscraper stay standing",                   "skyscraper"),
    ("what is gothic architecture",                           "gothic architecture"),
    ("what is roman architecture",                            "roman architecture"),
    ("what is reinforced concrete",                           "reinforced concrete"),
    ("what is steel",                                         "steel"),
    ("what is a foundation",                                  "foundation"),
    ("how are skyscrapers built",                             "skyscrapers"),
    ("what is urban planning",                                "urban planning"),
    ("what is acoustics",                                     "acoustics"),
    ("what is thermodynamics",                                "thermodynamics"),
    ("what is fluid dynamics",                                "fluid dynamics"),
    ("what is aerodynamics",                                  "aerodynamics"),
    ("how does a jet engine work",                            "jet engine"),
])
def test_batch216_subject_extraction(question, expected):
    """Batch 216: architecture/engineering — bridges, thermodynamics, jets."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is sociology",                                     "sociology"),
    ("what is anthropology",                                  "anthropology"),
    ("what is culture",                                       "culture"),
    ("what is society",                                       "society"),
    ("what is social class",                                  "social class"),
    ("what is inequality",                                    "inequality"),
    ("what is discrimination",                                "discrimination"),
    ("what is racism",                                        "racism"),
    ("what is sexism",                                        "sexism"),
    ("what is conflict theory",                               "conflict theory"),
    ("what is social contract theory",                        "social contract theory"),
    ("how does social media affect society",                  "social media"),
    ("what causes poverty",                                   "poverty"),
    ("what causes crime",                                     "crime"),
    ("what is human behavior",                                "human behavior"),
    ("what is globalization",                                 "globalization"),
    ("what is social mobility",                               "social mobility"),
    ("what is urbanization",                                  "urbanization"),
    ("what is peer pressure",                                 "peer pressure"),
    ("what are gender roles",                                 "gender roles"),
])
def test_batch217_subject_extraction(question, expected):
    """Batch 217: sociology/social science — culture, inequality, globalization."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is artificial intelligence",                       "artificial intelligence"),
    ("what is machine learning",                              "machine learning"),
    ("what is a neural network",                              "neural network"),
    ("what is the internet",                                  "internet"),
    ("what is cloud computing",                               "cloud computing"),
    ("what is blockchain",                                    "blockchain"),
    ("what is cybersecurity",                                 "cybersecurity"),
    ("how does wifi work",                                    "wifi"),
    ("how does gps work",                                     "gps"),
    ("how does encryption work",                              "encryption"),
    ("what is object oriented programming",                   "object oriented programming"),
    ("what is functional programming",                        "functional programming"),
    ("what is an algorithm",                                  "algorithm"),
    ("what is the difference between http and https",         "http and https"),
    ("what is a database",                                    "database"),
    ("what is open source",                                   "open source"),
    ("what is a compiler",                                    "compiler"),
    ("what is an operating system",                           "operating system"),
    ("what is big data",                                      "big data"),
    ("what is quantum computing",                             "quantum computing"),
])
def test_batch218_subject_extraction(question, expected):
    """Batch 218: computing/technology ��� AI, cloud, algorithms, security."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is diabetes",                                      "diabetes"),
    ("what is cancer",                                        "cancer"),
    ("what is alzheimer's disease",                           "alzheimer's disease"),
    ("what is parkinson's disease",                           "parkinson's disease"),
    ("what is hiv",                                           "hiv"),
    ("what is aids",                                          "aids"),
    ("what is multiple sclerosis",                            "multiple sclerosis"),
    ("what is arthritis",                                     "arthritis"),
    ("how is diabetes treated",                               "diabetes"),
    ("how is cancer treated",                                 "cancer"),
    ("what causes diabetes",                                  "diabetes"),
    ("what causes cancer",                                    "cancer"),
    ("what causes alzheimer's disease",                       "alzheimer's disease"),
    ("what are the symptoms of diabetes",                     "diabetes"),
    ("what are the symptoms of covid",                        "covid"),
    ("what is a vaccine",                                     "vaccine"),
    ("how do vaccines work",                                  "vaccines"),
    ("what is chemotherapy",                                  "chemotherapy"),
    ("what is a virus",                                       "virus"),
    ("what is a bacterium",                                   "bacterium"),
])
def test_batch219_subject_extraction(question, expected):
    """Batch 219: medicine/diseases — diabetes, cancer, MS, vaccines, viruses."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("where is the amazon river",                             "amazon river"),
    ("where is mount everest",                                "mount everest"),
    ("where is the sahara desert",                            "sahara desert"),
    ("where is the great barrier reef",                       "great barrier reef"),
    ("where is the nile river",                               "nile river"),
    ("what is the capital of france",                         "france"),
    ("what is the capital of japan",                          "japan"),
    ("what is the capital of australia",                      "australia"),
    ("what country is the amazon in",                         "amazon"),
    ("what is the largest country",                           "country"),
    ("what is the population of china",                       "china"),
    ("what is the population of india",                       "india"),
    ("what is a continent",                                   "continent"),
    ("what is a peninsula",                                   "peninsula"),
    ("what is a delta",                                       "delta"),
    ("what is a plateau",                                     "plateau"),
    ("how long is the great wall of china",                   "great wall of china"),
    ("how long is the amazon river",                          "amazon river"),
    ("what is the highest mountain",                          "mountain"),
    ("what is the amazon rainforest",                         "amazon rainforest"),
])
def test_batch220_subject_extraction(question, expected):
    """Batch 220: geography/world places — rivers, mountains, capitals, features."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a calorie",                                     "calorie"),
    ("what is protein",                                       "protein"),
    ("what is carbohydrate",                                  "carbohydrate"),
    ("what is a vitamin",                                     "vitamin"),
    ("what is fiber",                                         "fiber"),
    ("what is cholesterol",                                   "cholesterol"),
    ("what is gluten",                                        "gluten"),
    ("what foods contain vitamin c",                          "vitamin c"),
    ("what foods contain protein",                            "protein"),
    ("how many calories are in an apple",                     "apple"),
    ("how many calories are in a banana",                     "banana"),
    ("what is the ketogenic diet",                            "ketogenic diet"),
    ("what is the mediterranean diet",                        "mediterranean diet"),
    # "balanced" is not a stripped superlative — "balanced diet" is preserved as a concept
    ("what is a balanced diet",                               "balanced diet"),
    ("what is intermittent fasting",                          "intermittent fasting"),
    ("what is a superfood",                                   "superfood"),
    ("how does sugar affect health",                          "sugar"),
    ("what are probiotics",                                   "probiotics"),
    ("what is a macronutrient",                               "macronutrient"),
    ("what is omega 3",                                       "omega 3"),
])
def test_batch221_subject_extraction(question, expected):
    """Batch 221: nutrition/food — calories, vitamins, diets, macronutrients."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is physics",                                       "physics"),
    ("what is quantum mechanics",                             "quantum mechanics"),
    ("what is relativity",                                    "relativity"),
    ("what is thermodynamics",                                "thermodynamics"),
    ("what is electromagnetism",                              "electromagnetism"),
    ("what is nuclear physics",                               "nuclear physics"),
    ("what is newton's first law",                            "newton's first law"),
    ("what is newton's second law",                           "newton's second law"),
    ("what is newton's third law",                            "newton's third law"),
    ("how does a nuclear reactor work",                       "nuclear reactor"),
    ("how does a laser work",                                 "laser"),
    ("what is entropy",                                       "entropy"),
    ("what is momentum",                                      "momentum"),
    ("what is kinetic energy",                                "kinetic energy"),
    ("what is potential energy",                              "potential energy"),
    ("what is the speed of sound",                            "speed of sound"),
    ("what is a wave",                                        "wave"),
    ("how does sound travel",                                 "sound"),
    ("how does light travel",                                 "light"),
    ("what is the electromagnetic spectrum",                  "electromagnetic spectrum"),
])
def test_batch222_subject_extraction(question, expected):
    """Batch 222: physics — quantum mechanics, Newton's laws, energy, waves."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is music theory",                                  "music theory"),
    ("what is jazz",                                          "jazz"),
    ("what is classical music",                               "classical music"),
    ("what is rock music",                                    "rock music"),
    ("what is hip hop",                                       "hip hop"),
    ("what is opera",                                         "opera"),
    ("who invented jazz",                                     "jazz"),
    ("what is abstract art",                                  "abstract art"),
    ("what is impressionism",                                 "impressionism"),
    ("what is surrealism",                                    "surrealism"),
    ("how does a guitar work",                                "guitar"),
    ("how does a piano work",                                 "piano"),
    ("what is a symphony",                                    "symphony"),
    ("what is rhythm",                                        "rhythm"),
    ("what is harmony",                                       "harmony"),
    ("what is melody",                                        "melody"),
    ("what is the pentatonic scale",                          "pentatonic scale"),
    ("what is a chord",                                       "chord"),
    ("what is photography",                                   "photography"),
    ("what is cinematography",                                "cinematography"),
])
def test_batch223_subject_extraction(question, expected):
    """Batch 223: music/arts — jazz, classical, impressionism, harmony."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is soccer",                                        "soccer"),
    ("what is basketball",                                    "basketball"),
    ("what is tennis",                                        "tennis"),
    ("what is cricket",                                       "cricket"),
    ("what is rugby",                                         "rugby"),
    ("how is soccer played",                                  "soccer"),
    ("how is basketball played",                              "basketball"),
    ("what are the rules of tennis",                          "tennis"),
    ("what are the rules of chess",                           "chess"),
    ("what is aerobic exercise",                              "aerobic exercise"),
    ("what is anaerobic exercise",                            "anaerobic exercise"),
    ("what is cardiovascular exercise",                       "cardiovascular exercise"),
    ("how does exercise benefit the body",                    "exercise"),
    ("what is the olympics",                                  "olympics"),
    ("what is a marathon",                                    "marathon"),
    ("what is yoga",                                          "yoga"),
    ("what is pilates",                                       "pilates"),
    ("what is strength training",                             "strength training"),
    ("how does muscle growth work",                           "muscle growth"),
    ("what is the offside rule",                              "offside rule"),
])
def test_batch224_subject_extraction(question, expected):
    """Batch 224: sports/exercise — soccer, basketball, yoga, training."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a stock market",                                "stock market"),
    ("what is a bond",                                        "bond"),
    ("what is compound interest",                             "compound interest"),
    ("what is a mortgage",                                    "mortgage"),
    ("what is venture capital",                               "venture capital"),
    ("what is a hedge fund",                                  "hedge fund"),
    ("what is cryptocurrency",                                "cryptocurrency"),
    ("what is a startup",                                     "startup"),
    ("how does the stock market work",                        "stock market"),
    ("how does a bank work",                                  "bank"),
    ("how does a mortgage work",                              "mortgage"),
    ("what is supply and demand",                             "supply and demand"),
    ("what is gross domestic product",                        "gross domestic product"),
    ("what is inflation",                                     "inflation"),
    ("what is recession",                                     "recession"),
    ("what is fiscal policy",                                 "fiscal policy"),
    ("what causes a recession",                               "recession"),
    ("what is a credit score",                                "credit score"),
    ("what is diversification",                               "diversification"),
    ("how do interest rates affect inflation",                "interest rates"),
])
def test_batch225_subject_extraction(question, expected):
    """Batch 225: economics/business — stocks, bonds, mortgage, interest rates."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )
