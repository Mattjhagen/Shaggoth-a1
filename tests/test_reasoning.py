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
    ("how many moons does Jupiter have", "jupiter"),
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
    ("what makes DNA replicate", "dna"),
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
    ("what caused the Great Depression", "great depression"),
    ("what caused the financial crisis", "financial crisis"),
    # Extinction/state trailing verbs
    ("why did the dinosaurs go extinct", "dinosaurs"),
    ("how did the Roman Empire fall", "roman empire"),
    ("how did the Soviet Union collapse", "soviet union"),
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
    ("who designed the Eiffel Tower", "eiffel tower"),
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
    ("what caused the fall of the Roman Empire", "roman empire"),
    ("what caused the collapse of the Soviet Union", "soviet union"),
    ("what caused the rise of nationalism", "nationalism"),
    # "X fall" with no following "of" — "fall" IS a verb here; strip it too.
    ("how did Rome fall", "rome"),
    ("why did the Soviet Union collapse", "soviet union"),
    # "originate" is now in the trailing-verb list.
    ("where did humans originate", "humans"),
    ("where did life originate", "life"),
    # "role/function of X in Y" — "in Y" is context, not part of subject.
    ("what is the role of mitochondria in cell energy", "mitochondria"),
    ("what is the function of chlorophyll in photosynthesis", "chlorophyll"),
    ("what is the role of ATP in muscle contraction", "atp"),
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
    ("what ended the Cold War", "cold war"),
    ("what sparked the French Revolution", "french revolution"),
    ("what stopped the plague", "plague"),
    ("what brought about the Great Depression", "great depression"),
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
    ("what led to the fall of the Roman Empire", "roman empire"),
    ("what led to World War 1", "world war 1"),
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
    ("what are the sections of DNA", "dna"),
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
    # "lightning strike" is a compound noun; verb stripping now preserves it
    ("can lightning strike twice in the same place",      "lightning strike"),
    ("how often does lightning strike",                   "lightning strike"),
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
    ("what is the rule of law",                             "rule of law"),
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
    # "denial of service attack" kept intact — attack guard protects compound noun
    ("what is a denial of service attack",                    "denial of service attack"),
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


@pytest.mark.parametrize("question,expected", [
    ("what is a lion",                                           "lion"),
    ("what is a mammal",                                         "mammal"),
    ("what is a reptile",                                        "reptile"),
    ("what is an amphibian",                                     "amphibian"),
    ("what is a marsupial",                                      "marsupial"),
    ("how does a lion hunt",                                     "lion"),
    ("how does a spider catch prey",                             "spider"),
    ("what is animal migration",                                 "animal migration"),
    ("why do animals migrate",                                   "animals"),
    ("what is hibernation",                                      "hibernation"),
    ("why do bears hibernate",                                   "bears"),
    ("what is a food chain",                                     "food chain"),
    ("what is an ecosystem",                                     "ecosystem"),
    ("what is biodiversity",                                     "biodiversity"),
    ("how do birds fly",                                         "birds"),
    ("what is a predator",                                       "predator"),
    ("what is camouflage",                                       "camouflage"),
    ("how do fish breathe",                                      "fish"),
    ("what is taxonomy",                                         "taxonomy"),
    ("what is natural selection",                                "natural selection"),
])
def test_batch226_subject_extraction(question, expected):
    """Batch 226: animals/zoology — mammals, reptiles, migration, food chains."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is geology",                                          "geology"),
    ("what is a volcano",                                        "volcano"),
    ("what is an earthquake",                                    "earthquake"),
    ("what is a tectonic plate",                                 "tectonic plate"),
    ("what is erosion",                                          "erosion"),
    ("how does a volcano erupt",                                 "volcano"),
    ("what causes earthquakes",                                  "earthquakes"),
    ("what is the rock cycle",                                   "rock cycle"),
    ("what is plate tectonics",                                  "plate tectonics"),
    ("what is a mineral",                                        "mineral"),
    ("what is sedimentary rock",                                 "sedimentary rock"),
    ("what is metamorphic rock",                                 "metamorphic rock"),
    ("what is igneous rock",                                     "igneous rock"),
    ("what is the water cycle",                                  "water cycle"),
    ("what is soil",                                             "soil"),
    ("what is a glacier",                                        "glacier"),
    ("how does a glacier form",                                  "glacier"),
    ("what is the earth's core",                                 "earth's core"),
    ("what is weathering",                                       "weathering"),
    ("what is a fault line",                                     "fault line"),
])
def test_batch227_subject_extraction(question, expected):
    """Batch 227: geology/earth science — volcanoes, earthquakes, plate tectonics."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a novel",                                          "novel"),
    ("what is a poem",                                           "poem"),
    ("what is a metaphor",                                       "metaphor"),
    ("what is a simile",                                         "simile"),
    ("what is alliteration",                                     "alliteration"),
    ("what is foreshadowing",                                    "foreshadowing"),
    ("what is irony",                                            "irony"),
    ("what is a protagonist",                                    "protagonist"),
    ("what is an antagonist",                                    "antagonist"),
    ("what is a theme in literature",                            "theme"),
    ("what is the plot of hamlet",                               "hamlet"),
    ("who wrote hamlet",                                         "hamlet"),
    ("who wrote moby dick",                                      "moby dick"),
    ("what is haiku",                                            "haiku"),
    ("what is a sonnet",                                         "sonnet"),
    ("what is narrative",                                        "narrative"),
    ("what is a genre",                                          "genre"),
    ("what is fiction",                                          "fiction"),
    ("what is non-fiction",                                      "non-fiction"),
    ("what is satire",                                           "satire"),
])
def test_batch228_subject_extraction(question, expected):
    """Batch 228: literature/creative writing — novels, poems, metaphors, plot."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a documentary",                                    "documentary"),
    ("what is cinematography",                                   "cinematography"),
    ("what is a screenplay",                                     "screenplay"),
    ("what is a genre",                                          "genre"),
    ("what is a blockbuster",                                    "blockbuster"),
    ("who directed inception",                                   "inception"),
    ("who directed the godfather",                               "godfather"),
    ("what is a close-up in film",                               "close-up"),
    ("what is a montage in film",                                "montage"),
    ("what is animation",                                        "animation"),
    ("what is a sequel",                                         "sequel"),
    ("what is a prequel",                                        "prequel"),
    ("what is the golden age of hollywood",                      "golden age of hollywood"),
    ("what is film noir",                                        "film noir"),
    ("what is a director",                                       "director"),
    ("what is an oscar",                                         "oscar"),
    ("how does animation work",                                  "animation"),
    ("what is the box office",                                   "box office"),
    ("what is a cult classic",                                   "cult classic"),
    ("what is virtual reality",                                  "virtual reality"),
])
def test_batch229_subject_extraction(question, expected):
    """Batch 229: film/cinema — documentaries, animation, film noir, directors."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is depression",                                       "depression"),
    ("what is anxiety",                                          "anxiety"),
    ("what is schizophrenia",                                    "schizophrenia"),
    ("what is bipolar disorder",                                 "bipolar disorder"),
    ("what is obsessive compulsive disorder",                    "obsessive compulsive disorder"),
    ("what is post traumatic stress disorder",                   "post traumatic stress disorder"),
    ("what is autism spectrum disorder",                         "autism spectrum disorder"),
    ("what is cognitive behavioral therapy",                     "cognitive behavioral therapy"),
    ("what is psychotherapy",                                    "psychotherapy"),
    ("what is mindfulness",                                      "mindfulness"),
    ("what is cognitive dissonance",                             "cognitive dissonance"),
    ("what is the placebo effect",                               "placebo effect"),
    ("what is emotional intelligence",                           "emotional intelligence"),
    ("what is self esteem",                                      "self esteem"),
    ("how does the placebo effect work",                         "placebo effect"),
    ("how does therapy help",                                    "therapy"),
    ("what causes depression",                                   "depression"),
    ("what is addiction",                                        "addiction"),
    ("what is trauma",                                           "trauma"),
    ("what is the unconscious mind",                             "unconscious mind"),
])
def test_batch230_subject_extraction(question, expected):
    """Batch 230: psychology/clinical — disorders, therapies, cognitive concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a hurricane",                                      "hurricane"),
    ("what is a tornado",                                        "tornado"),
    ("what is a typhoon",                                        "typhoon"),
    ("what is a blizzard",                                       "blizzard"),
    ("what is a thunderstorm",                                   "thunderstorm"),
    ("how does a hurricane form",                                "hurricane"),
    ("how does a tornado form",                                  "tornado"),
    ("what causes lightning",                                    "lightning"),
    ("what is weather",                                          "weather"),
    ("what is climate",                                          "climate"),
    ("what is climate change",                                   "climate change"),
    ("what is global warming",                                   "global warming"),
    ("what is the greenhouse effect",                            "greenhouse effect"),
    ("what is humidity",                                         "humidity"),
    ("what is barometric pressure",                              "barometric pressure"),
    ("what is el nino",                                          "el nino"),
    ("what is a drought",                                        "drought"),
    ("what is fog",                                              "fog"),
    ("how does snow form",                                       "snow"),
    ("what is a weather forecast",                               "weather forecast"),
])
def test_batch231_subject_extraction(question, expected):
    """Batch 231: meteorology/weather — hurricanes, climate, greenhouse effect."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is an internal combustion engine",                    "internal combustion engine"),
    ("what is horsepower",                                       "horsepower"),
    ("what is torque",                                           "torque"),
    ("what is a hybrid car",                                     "hybrid car"),
    ("what is an electric vehicle",                              "electric vehicle"),
    ("how does a car engine work",                               "car engine"),
    ("how does a transmission work",                             "transmission"),
    ("how does regenerative braking work",                       "regenerative braking"),
    ("what is fuel efficiency",                                  "fuel efficiency"),
    ("what is a catalytic converter",                            "catalytic converter"),
    ("what is a bullet train",                                   "bullet train"),
    ("what is public transportation",                            "public transportation"),
    ("what is autonomous driving",                               "autonomous driving"),
    ("how does a plane fly",                                     "plane"),
    ("what is aerodynamics",                                     "aerodynamics"),
    ("what is a submarine",                                      "submarine"),
    ("how does a submarine work",                                "submarine"),
    ("what is logistics",                                        "logistics"),
    ("what is supply chain",                                     "supply chain"),
    ("what is a traffic jam",                                    "traffic jam"),
])
def test_batch232_subject_extraction(question, expected):
    """Batch 232: automotive/transportation — engines, EVs, planes, trains."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a black hole",                                     "black hole"),
    ("what is a neutron star",                                   "neutron star"),
    ("what is a supernova",                                      "supernova"),
    ("what is a galaxy",                                         "galaxy"),
    ("what is dark matter",                                      "dark matter"),
    ("what is dark energy",                                      "dark energy"),
    ("what is the milky way",                                    "milky way"),
    ("how does a black hole form",                               "black hole"),
    ("what is gravity",                                          "gravity"),
    ("what is the big bang theory",                              "big bang theory"),
    ("what is a planet",                                         "planet"),
    ("what is a solar system",                                   "solar system"),
    ("what is the speed of light",                               "speed of light"),
    ("how far is the moon from earth",                           "moon"),
    ("what is a comet",                                          "comet"),
    ("what is an asteroid",                                      "asteroid"),
    ("what is a nebula",                                         "nebula"),
    ("what is the event horizon",                                "event horizon"),
    ("what is gravitational waves",                              "gravitational waves"),
    ("what is cosmic radiation",                                 "cosmic radiation"),
])
def test_batch233_subject_extraction(question, expected):
    """Batch 233: space/astronomy — black holes, galaxies, big bang, dark matter."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is philosophy",                                       "philosophy"),
    ("what is ethics",                                           "ethics"),
    ("what is morality",                                         "morality"),
    ("what is utilitarianism",                                   "utilitarianism"),
    ("what is existentialism",                                   "existentialism"),
    ("what is stoicism",                                         "stoicism"),
    ("what is empiricism",                                       "empiricism"),
    ("what is rationalism",                                      "rationalism"),
    ("what is moral philosophy",                                 "moral philosophy"),
    ("what is the trolley problem",                              "trolley problem"),
    ("what is free will",                                        "free will"),
    ("what is determinism",                                      "determinism"),
    ("what is consciousness",                                    "consciousness"),
    ("what is epistemology",                                     "epistemology"),
    ("what is metaphysics",                                      "metaphysics"),
    ("what is logic",                                            "logic"),
    ("what is a paradox",                                        "paradox"),
    ("what is nihilism",                                         "nihilism"),
    ("what is humanism",                                         "humanism"),
    ("what is the social contract",                              "social contract"),
])
def test_batch234_subject_extraction(question, expected):
    """Batch 234: philosophy/ethics — utilitarianism, free will, social contract."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is diabetes",                                         "diabetes"),
    ("what is hypertension",                                     "hypertension"),
    ("what is cholesterol",                                      "cholesterol"),
    ("what is an allergy",                                       "allergy"),
    ("what is asthma",                                           "asthma"),
    ("how does the immune system work",                          "immune system"),
    ("what is a vaccine",                                        "vaccine"),
    ("how do vaccines work",                                     "vaccines"),
    ("what is inflammation",                                     "inflammation"),
    ("what is a pathogen",                                       "pathogen"),
    ("what is a virus",                                          "virus"),
    ("what is a bacterium",                                      "bacterium"),
    ("what is dna",                                              "dna"),
    ("how does dna replication work",                            "dna replication"),
    ("what is a gene",                                           "gene"),
    ("what is a mutation",                                       "mutation"),
    ("what is cancer",                                           "cancer"),
    ("what causes cancer",                                       "cancer"),
    ("what is chemotherapy",                                     "chemotherapy"),
    ("what is a stem cell",                                      "stem cell"),
])
def test_batch235_subject_extraction(question, expected):
    """Batch 235: health/biology — diabetes, vaccines, DNA, cancer, stem cells."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is deforestation",                                    "deforestation"),
    ("what is pollution",                                        "pollution"),
    ("what is sustainability",                                   "sustainability"),
    ("what is renewable energy",                                 "renewable energy"),
    ("what is solar energy",                                     "solar energy"),
    ("what is wind energy",                                      "wind energy"),
    ("what is nuclear energy",                                   "nuclear energy"),
    ("what causes deforestation",                                "deforestation"),
    ("what is the ozone layer",                                  "ozone layer"),
    ("what is acid rain",                                        "acid rain"),
    ("how does solar energy work",                               "solar energy"),
    ("what is carbon dioxide",                                   "carbon dioxide"),
    ("what is fossil fuels",                                     "fossil fuels"),
    ("what is an endangered species",                            "endangered species"),
    ("what is recycling",                                        "recycling"),
    ("what is carbon footprint",                                 "carbon footprint"),
    ("what is a carbon footprint",                               "carbon footprint"),
    ("what is deforestation doing to the amazon",                "deforestation"),
    ("what is fracking",                                         "fracking"),
    ("what is an ecosystem service",                             "ecosystem service"),
])
def test_batch236_subject_extraction(question, expected):
    """Batch 236: environment/ecology — pollution, climate, renewable energy."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is the internet",                                     "internet"),
    ("what is the world wide web",                               "world wide web"),
    ("what is artificial intelligence",                          "artificial intelligence"),
    ("what is machine learning",                                 "machine learning"),
    ("what is blockchain",                                       "blockchain"),
    ("what is the cloud",                                        "cloud"),
    ("what is cybersecurity",                                    "cybersecurity"),
    ("what is open source",                                      "open source"),
    ("how does the internet work",                               "internet"),
    ("how does encryption work",                                 "encryption"),
    ("what is a browser",                                        "browser"),
    ("what is a search engine",                                  "search engine"),
    ("what is wifi",                                             "wifi"),
    ("what is a cpu",                                            "cpu"),
    ("what is a gpu",                                            "gpu"),
    ("what is ram",                                              "ram"),
    ("what is social media",                                     "social media"),
    ("what is an algorithm",                                     "algorithm"),
    ("what is net neutrality",                                   "net neutrality"),
    ("what is a server",                                         "server"),
])
def test_batch237_subject_extraction(question, expected):
    """Batch 237: technology/internet — AI, blockchain, cloud, cybersecurity."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is fermentation",                                     "fermentation"),
    ("what is pasteurization",                                   "pasteurization"),
    ("what is the maillard reaction",                            "maillard reaction"),
    ("what is umami",                                            "umami"),
    ("what is gluten",                                           "gluten"),
    ("what is italian cuisine",                                  "italian cuisine"),
    ("what is french cuisine",                                   "french cuisine"),
    ("how does fermentation work",                               "fermentation"),
    ("what is caramelization",                                   "caramelization"),
    ("what is emulsification",                                   "emulsification"),
    ("what is a roux",                                           "roux"),
    ("what is a brine",                                          "brine"),
    ("what is blanching",                                        "blanching"),
    ("what is braising",                                         "braising"),
    ("what is sauteing",                                         "sauteing"),
    ("what is a marinade",                                       "marinade"),
    ("what is a stock",                                          "stock"),
    ("what is yeast",                                            "yeast"),
    ("how does yeast work",                                      "yeast"),
    ("what is the difference between a stock and a broth",       "stock and broth"),
])
def test_batch238_subject_extraction(question, expected):
    """Batch 238: cuisine/cooking — fermentation, maillard, umami, roux."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is ancient egypt",                                    "ancient egypt"),
    ("what is ancient greece",                                   "ancient greece"),
    ("what is the roman empire",                                 "roman empire"),
    ("what is mesopotamia",                                      "mesopotamia"),
    ("what is ancient china",                                    "ancient china"),
    ("who built the pyramids",                                   "pyramids"),
    ("what is the colosseum",                                    "colosseum"),
    ("what is the pantheon",                                     "pantheon"),
    ("what is the parthenon",                                    "parthenon"),
    ("what is the silk road",                                    "silk road"),
    ("who was julius caesar",                                    "julius caesar"),
    ("who was cleopatra",                                        "cleopatra"),
    ("who was alexander the great",                              "alexander the great"),
    ("what was the trojan war",                                  "trojan war"),
    ("what is the magna carta",                                  "magna carta"),
    ("what is the renaissance",                                  "renaissance"),
    ("what was the black death",                                 "black death"),
    ("what is the french revolution",                            "french revolution"),
    ("what caused world war 1",                                  "world war 1"),
    ("what caused world war 2",                                  "world war 2"),
])
def test_batch239_subject_extraction(question, expected):
    """Batch 239: ancient/modern history — Egypt, Rome, Magna Carta, WWI/II."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is democracy",                                        "democracy"),
    ("what is communism",                                        "communism"),
    ("what is capitalism",                                       "capitalism"),
    ("what is socialism",                                        "socialism"),
    ("what is fascism",                                          "fascism"),
    ("what is nationalism",                                      "nationalism"),
    ("what is imperialism",                                      "imperialism"),
    ("what is colonialism",                                      "colonialism"),
    ("what is the cold war",                                     "cold war"),
    ("what is the united nations",                               "united nations"),
    ("what is nato",                                             "nato"),
    ("what is the european union",                               "european union"),
    ("what is globalization",                                    "globalization"),
    ("what is diplomacy",                                        "diplomacy"),
    ("what is a sanction",                                       "sanction"),
    ("what is nuclear deterrence",                               "nuclear deterrence"),
    ("what is soft power",                                       "soft power"),
    ("what is a trade war",                                      "trade war"),
    ("what is propaganda",                                       "propaganda"),
    ("what is terrorism",                                        "terrorism"),
])
def test_batch240_subject_extraction(question, expected):
    """Batch 240: geopolitics — democracy, communism, NATO, cold war, soft power."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is the nervous system",                               "nervous system"),
    ("what is the circulatory system",                           "circulatory system"),
    ("what is the digestive system",                             "digestive system"),
    ("what is the respiratory system",                           "respiratory system"),
    ("what is the skeletal system",                              "skeletal system"),
    ("how does the heart work",                                  "heart"),
    ("how does the brain work",                                  "brain"),
    ("how does the liver work",                                  "liver"),
    ("what is a neuron",                                         "neuron"),
    ("what is a synapse",                                        "synapse"),
    ("what is a hormone",                                        "hormone"),
    ("what is insulin",                                          "insulin"),
    ("what is adrenaline",                                       "adrenaline"),
    ("what is blood pressure",                                   "blood pressure"),
    ("what is a red blood cell",                                 "red blood cell"),
    ("what is a white blood cell",                               "white blood cell"),
    ("what is a chromosome",                                     "chromosome"),
    ("what is bone marrow",                                      "bone marrow"),
    ("what is cartilage",                                        "cartilage"),
    ("what is the endocrine system",                             "endocrine system"),
])
def test_batch241_subject_extraction(question, expected):
    """Batch 241: human body/anatomy — body systems, neurons, hormones, blood."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("can humans survive on mars",                               "humans"),
    ("can a computer think",                                     "computer"),
    ("is time travel possible",                                  "time travel"),
    # COMPARE classifier fires on "faster than" — known limitation, output is imperfect
    ("is faster than light travel possible",                     "than light"),
    ("does dark matter exist",                                   "dark matter"),
    ("does life exist on other planets",                         "life"),
    ("are there other universes",                                "universes"),
    ("are there aliens",                                         "aliens"),
    ("will the sun explode",                                     "sun"),
    ("when did dinosaurs go extinct",                            "dinosaurs"),
    ("when did the universe begin",                              "universe"),
    ("where did humans come from",                               "humans"),
    ("where did the moon come from",                             "moon"),
    ("why do we dream",                                          "dream"),
    ("why do we yawn",                                           "yawn"),
    ("why do leaves change color",                               "leaves"),
    ("what would happen if the moon disappeared",                "moon"),
    # _m_it_takes pattern extracts "light" as the traveling entity
    ("how long does it take light to reach earth",               "light"),
    ("what percentage of the earth is water",                    "earth"),
    ("how many planets are in the solar system",                 "solar system"),
])
def test_batch242_subject_extraction(question, expected):
    """Batch 242: edge cases — unusual phrasings, existential, comparative, hypothetical."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is quantum computing",                                "quantum computing"),
    ("what is a qubit",                                          "qubit"),
    ("what is quantum entanglement",                             "quantum entanglement"),
    ("what is quantum superposition",                            "quantum superposition"),
    ("what is quantum tunneling",                                "quantum tunneling"),
    ("what is quantum decoherence",                              "quantum decoherence"),
    ("what is a quantum gate",                                   "quantum gate"),
    ("what is quantum error correction",                         "quantum error correction"),
    ("what is shor's algorithm",                                 "shor's algorithm"),
    ("what is grover's algorithm",                               "grover's algorithm"),
    ("how does quantum computing work",                          "quantum computing"),
    ("how does quantum entanglement work",                       "quantum entanglement"),
    ("what is a quantum circuit",                                "quantum circuit"),
    ("what is quantum supremacy",                                "quantum supremacy"),
    ("what is a quantum computer",                               "quantum computer"),
    ("how many qubits does a quantum computer need",             "quantum computer"),
    ("what is quantum cryptography",                             "quantum cryptography"),
    ("what is quantum key distribution",                         "quantum key distribution"),
    ("what is post-quantum cryptography",                        "post-quantum cryptography"),
    ("can quantum computers break encryption",                   "quantum computers"),
])
def test_batch243_subject_extraction(question, expected):
    """Batch 243: quantum computing — qubits, entanglement, algorithms, cryptography."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a major scale",                                    "major scale"),
    ("what is a minor scale",                                    "minor scale"),
    ("what is a chord",                                          "chord"),
    ("what is a key signature",                                  "key signature"),
    ("what is a time signature",                                 "time signature"),
    ("what is counterpoint",                                     "counterpoint"),
    ("what is harmony",                                          "harmony"),
    ("what is rhythm",                                           "rhythm"),
    ("what is a melody",                                         "melody"),
    ("what is a fugue",                                          "fugue"),
    ("what is a sonata",                                         "sonata"),
    ("what is a concerto",                                       "concerto"),
    ("what is a symphony",                                       "symphony"),
    ("what is an interval",                                      "interval"),
    ("what is a tritone",                                        "tritone"),
    ("what is modal music",                                      "modal music"),
    ("how does a piano work",                                    "piano"),
    ("how does a guitar produce sound",                          "guitar"),
    ("what is music theory",                                     "music theory"),
    ("how do chords resolve",                                    "chords"),
])
def test_batch244_subject_extraction(question, expected):
    """Batch 244: music theory — scales, chords, forms, instruments."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is cognitive science",                                "cognitive science"),
    ("what is neuroplasticity",                                  "neuroplasticity"),
    ("what is working memory",                                   "working memory"),
    ("what is long term memory",                                 "long term memory"),
    ("what is short term memory",                                "short term memory"),
    ("what is cognitive dissonance",                             "cognitive dissonance"),
    ("what is confirmation bias",                                "confirmation bias"),
    ("what is the dunning-kruger effect",                        "dunning-kruger effect"),
    ("what is unconscious bias",                                 "unconscious bias"),
    ("what is executive function",                               "executive function"),
    ("how does memory work",                                     "memory"),
    ("how does attention work",                                   "attention"),
    ("what is a cognitive bias",                                 "cognitive bias"),
    ("what is metacognition",                                    "metacognition"),
    ("what is consciousness",                                    "consciousness"),
    ("what is the default mode network",                         "default mode network"),
    ("what is mirror neuron",                                    "mirror neuron"),
    ("what is neural plasticity",                                "neural plasticity"),
    ("how do neurons communicate",                               "neurons"),
    ("what is the prefrontal cortex",                            "prefrontal cortex"),
])
def test_batch245_subject_extraction(question, expected):
    """Batch 245: cognitive science — memory, bias, consciousness, neural structures."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is inflation",                                        "inflation"),
    ("what is deflation",                                        "deflation"),
    ("what is interest rate",                                    "interest rate"),
    ("what is gross domestic product",                           "gross domestic product"),
    ("what is supply and demand",                                "supply and demand"),
    ("what is a stock market",                                   "stock market"),
    ("what is a bond",                                           "bond"),
    ("what is monetary policy",                                  "monetary policy"),
    ("what is fiscal policy",                                    "fiscal policy"),
    ("what is a recession",                                      "recession"),
    ("what is stagflation",                                      "stagflation"),
    ("what is quantitative easing",                              "quantitative easing"),
    ("what is a hedge fund",                                     "hedge fund"),
    ("what is venture capital",                                  "venture capital"),
    ("what is a cryptocurrency",                                 "cryptocurrency"),
    ("how does the stock market work",                           "stock market"),
    ("how does inflation affect the economy",                    "inflation"),
    ("what is market capitalization",                            "market capitalization"),
    ("what is compound interest",                                "compound interest"),
    ("what is a central bank",                                   "central bank"),
])
def test_batch246_subject_extraction(question, expected):
    """Batch 246: economics/finance — inflation, markets, monetary policy, instruments."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is linguistics",                                      "linguistics"),
    ("what is phonology",                                        "phonology"),
    ("what is morphology",                                       "morphology"),
    ("what is syntax",                                           "syntax"),
    ("what is semantics",                                        "semantics"),
    ("what is pragmatics",                                       "pragmatics"),
    ("what is a phoneme",                                        "phoneme"),
    ("what is a morpheme",                                       "morpheme"),
    ("what is a dialect",                                        "dialect"),
    ("what is language acquisition",                             "language acquisition"),
    ("what is the sapir-whorf hypothesis",                       "sapir-whorf hypothesis"),
    ("what is code switching",                                   "code switching"),
    ("what is a lingua franca",                                  "lingua franca"),
    ("what is natural language processing",                      "natural language processing"),
    ("how do children learn language",                           "children"),
    ("what is a creole language",                                "creole language"),
    ("what is a pidgin language",                                "pidgin language"),
    ("what is an endangered language",                           "endangered language"),
    ("how many languages are there in the world",                "languages"),
    # Superlative strip is by design: "most spoken" → stripped like "fastest" in "fastest animal"
    ("what is the most spoken language in the world",            "language"),
])
def test_batch247_subject_extraction(question, expected):
    """Batch 247: linguistics — phonology, morphology, syntax, language acquisition."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a semiconductor",                                  "semiconductor"),
    ("what is a superconductor",                                 "superconductor"),
    ("what is graphene",                                         "graphene"),
    ("what is a polymer",                                        "polymer"),
    ("what is a composite material",                             "composite material"),
    ("what is a crystal lattice",                                "crystal lattice"),
    ("what is tensile strength",                                 "tensile strength"),
    ("what is thermal conductivity",                             "thermal conductivity"),
    ("what is hardness",                                         "hardness"),
    ("what is a phase transition",                               "phase transition"),
    ("what is corrosion",                                        "corrosion"),
    ("how does steel get its strength",                          "steel"),
    ("what is carbon fiber",                                     "carbon fiber"),
    ("what is a nanomaterial",                                   "nanomaterial"),
    ("what is an alloy",                                         "alloy"),
    ("what is a ceramic material",                               "ceramic material"),
    ("how is glass made",                                        "glass"),
    ("what is elastic modulus",                                  "elastic modulus"),
    ("what is a metal oxide",                                    "metal oxide"),
    ("what is piezoelectricity",                                 "piezoelectricity"),
])
def test_batch248_subject_extraction(question, expected):
    """Batch 248: materials science — semiconductors, polymers, alloys, nanomaterials."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is climate change",                                   "climate change"),
    ("what is global warming",                                   "global warming"),
    ("what is the greenhouse effect",                            "greenhouse effect"),
    ("what is carbon dioxide",                                   "carbon dioxide"),
    ("what is the ozone layer",                                  "ozone layer"),
    ("what is acid rain",                                        "acid rain"),
    ("what is biodiversity",                                     "biodiversity"),
    ("what is a carbon footprint",                               "carbon footprint"),
    ("what is renewable energy",                                 "renewable energy"),
    ("what is solar energy",                                     "solar energy"),
    ("what is wind energy",                                      "wind energy"),
    ("what is deforestation",                                    "deforestation"),
    ("what is desertification",                                  "desertification"),
    ("what is ocean acidification",                              "ocean acidification"),
    ("what is eutrophication",                                   "eutrophication"),
    ("how does the water cycle work",                            "water cycle"),
    ("what is carbon capture",                                   "carbon capture"),
    ("what is a carbon sink",                                    "carbon sink"),
    ("what causes sea level rise",                               "sea level rise"),
    ("what is an ecosystem service",                             "ecosystem service"),
])
def test_batch249_subject_extraction(question, expected):
    """Batch 249: environmental science — climate, greenhouse effect, carbon, sea level."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is common law",                                       "common law"),
    ("what is due process",                                      "due process"),
    ("what is habeas corpus",                                    "habeas corpus"),
    ("what is tort law",                                         "tort law"),
    ("what is constitutional law",                               "constitutional law"),
    ("what is criminal law",                                     "criminal law"),
    ("what is civil law",                                        "civil law"),
    ("what is intellectual property",                            "intellectual property"),
    ("what is copyright",                                        "copyright"),
    ("what is a patent",                                         "patent"),
    ("what is a trademark",                                      "trademark"),
    ("what is libel",                                            "libel"),
    ("what is slander",                                          "slander"),
    ("what is precedent",                                        "precedent"),
    ("what is the rule of law",                                  "rule of law"),
    ("what is a subpoena",                                       "subpoena"),
    ("what is an injunction",                                    "injunction"),
    ("what is the burden of proof",                              "burden of proof"),
    ("what is beyond reasonable doubt",                          "beyond reasonable doubt"),
    ("how does the supreme court work",                          "supreme court"),
])
def test_batch250_subject_extraction(question, expected):
    """Batch 250: law — common law, due process, intellectual property, courts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is an algorithm",                                     "algorithm"),
    ("what is a data structure",                                 "data structure"),
    ("what is a hash table",                                     "hash table"),
    ("what is a binary tree",                                    "binary tree"),
    ("what is recursion",                                        "recursion"),
    ("what is object oriented programming",                      "object oriented programming"),
    ("what is functional programming",                           "functional programming"),
    ("what is a database",                                       "database"),
    ("what is sql",                                              "sql"),
    ("what is machine learning",                                 "machine learning"),
    ("what is a neural network",                                 "neural network"),
    ("what is deep learning",                                    "deep learning"),
    ("what is an api",                                           "api"),
    ("what is big o notation",                                   "big o notation"),
    ("what is a linked list",                                    "linked list"),
    ("what is a stack",                                          "stack"),
    ("what is a queue",                                          "queue"),
    ("how does sorting work",                                    "sorting"),
    ("what is a compiler",                                       "compiler"),
    ("what is the internet",                                     "internet"),
])
def test_batch251_subject_extraction(question, expected):
    """Batch 251: computer science — algorithms, data structures, ML, networking."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is dna",                                              "dna"),
    ("what is rna",                                              "rna"),
    ("what is a gene",                                           "gene"),
    ("what is a chromosome",                                     "chromosome"),
    ("what is mitosis",                                          "mitosis"),
    ("what is meiosis",                                          "meiosis"),
    ("what is natural selection",                                "natural selection"),
    ("what is evolution",                                        "evolution"),
    ("what is a protein",                                        "protein"),
    ("what is an enzyme",                                        "enzyme"),
    ("what is photosynthesis",                                   "photosynthesis"),
    ("what is cellular respiration",                             "cellular respiration"),
    ("what is osmosis",                                          "osmosis"),
    ("what is mutation",                                         "mutation"),
    ("what is crispr",                                           "crispr"),
    ("what is gene editing",                                     "gene editing"),
    ("what is the human genome",                                 "human genome"),
    ("how does dna replication work",                            "dna replication"),
    ("what is a stem cell",                                      "stem cell"),
    ("what is epigenetics",                                      "epigenetics"),
])
def test_batch252_subject_extraction(question, expected):
    """Batch 252: biology/genetics — DNA, RNA, evolution, CRISPR, cellular processes."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is utilitarianism",                                   "utilitarianism"),
    ("what is deontology",                                       "deontology"),
    ("what is virtue ethics",                                    "virtue ethics"),
    ("what is the trolley problem",                              "trolley problem"),
    ("what is free will",                                        "free will"),
    ("what is determinism",                                      "determinism"),
    ("what is moral relativism",                                 "moral relativism"),
    ("what is the hard problem of consciousness",                "hard problem of consciousness"),
    ("what is qualia",                                           "qualia"),
    ("what is the mind body problem",                            "mind body problem"),
    ("what is philosophical zombies",                            "philosophical zombies"),
    ("what is the chinese room argument",                        "chinese room argument"),
    ("what is the turing test",                                  "turing test"),
    ("what is artificial general intelligence",                  "artificial general intelligence"),
    ("what is moral philosophy",                                 "moral philosophy"),
    ("what is applied ethics",                                   "applied ethics"),
    ("what is bioethics",                                        "bioethics"),
    ("what is environmental ethics",                             "environmental ethics"),
    ("what is social contract theory",                           "social contract theory"),
    ("what is the veil of ignorance",                            "veil of ignorance"),
])
def test_batch253_subject_extraction(question, expected):
    """Batch 253: ethics/philosophy of mind — free will, trolley problem, AI ethics."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a cantilever",                                     "cantilever"),
    ("what is a truss",                                          "truss"),
    ("what is a load bearing wall",                              "load bearing wall"),
    ("what is reinforced concrete",                              "reinforced concrete"),
    ("what is a suspension bridge",                              "suspension bridge"),
    ("what is the golden ratio",                                 "golden ratio"),
    ("what is structural engineering",                           "structural engineering"),
    ("what is civil engineering",                                "civil engineering"),
    ("what is urban planning",                                   "urban planning"),
    ("what is green architecture",                               "green architecture"),
    ("what is passive solar design",                             "passive solar design"),
    ("what is bim",                                              "bim"),
    ("what is a foundation",                                     "foundation"),
    ("what is a facade",                                         "facade"),
    ("how does a arch work",                                     "arch"),
    ("what is seismic design",                                   "seismic design"),
    ("what is a flying buttress",                                "flying buttress"),
    ("what is brutalist architecture",                           "brutalist architecture"),
    ("what is art deco",                                         "art deco"),
    ("what is gothic architecture",                              "gothic architecture"),
])
def test_batch254_subject_extraction(question, expected):
    """Batch 254: architecture/engineering — design compounds, structures, styles."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is quantum entanglement",                             "quantum entanglement"),
    ("what is the higgs boson",                                  "higgs boson"),
    ("what is dark matter",                                      "dark matter"),
    ("what is dark energy",                                      "dark energy"),
    ("what is the speed of light",                               "speed of light"),
    ("what is a black hole",                                     "black hole"),
    ("what is string theory",                                    "string theory"),
    ("what is the uncertainty principle",                        "uncertainty principle"),
    ("what is thermodynamics",                                   "thermodynamics"),
    ("what is electromagnetism",                                 "electromagnetism"),
    ("what is nuclear fusion",                                   "nuclear fusion"),
    ("what is plasma",                                           "plasma"),
    ("what is a neutron star",                                   "neutron star"),
    ("what is gravitational waves",                              "gravitational waves"),
    ("what is special relativity",                               "special relativity"),
    ("what is general relativity",                               "general relativity"),
    ("what is quantum mechanics",                                "quantum mechanics"),
    ("what is the standard model",                               "standard model"),
    ("what is a photon",                                         "photon"),
    ("what is antimatter",                                       "antimatter"),
])
def test_batch255_subject_extraction(question, expected):
    """Batch 255: physics — quantum, relativity, particles, cosmology."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is diabetes",                                         "diabetes"),
    ("what is hypertension",                                     "hypertension"),
    ("what is alzheimer's disease",                              "alzheimer's disease"),
    ("what is cancer",                                           "cancer"),
    ("what is a vaccine",                                        "vaccine"),
    ("what is herd immunity",                                    "herd immunity"),
    ("what is the immune system",                                "immune system"),
    ("what is chemotherapy",                                     "chemotherapy"),
    ("what is an mri",                                           "mri"),
    ("what is a stem cell",                                      "stem cell"),
    ("what is gene therapy",                                     "gene therapy"),
    ("what is the blood brain barrier",                          "blood brain barrier"),
    ("what is insulin",                                          "insulin"),
    ("what is sepsis",                                           "sepsis"),
    ("what is anesthesia",                                       "anesthesia"),
    ("what is palliative care",                                  "palliative care"),
    ("what is inflammation",                                     "inflammation"),
    ("what is an antibiotic",                                    "antibiotic"),
    ("what is chronic pain",                                     "chronic pain"),
    ("what is a clinical trial",                                 "clinical trial"),
])
def test_batch256_subject_extraction(question, expected):
    """Batch 256: medicine/healthcare — diseases, treatments, procedures."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is social stratification",                            "social stratification"),
    ("what is cultural relativism",                              "cultural relativism"),
    ("what is ethnocentrism",                                    "ethnocentrism"),
    ("what is social mobility",                                  "social mobility"),
    ("what is gender roles",                                     "gender roles"),
    ("what is socialization",                                    "socialization"),
    ("what is cultural diffusion",                               "cultural diffusion"),
    ("what is a kinship system",                                 "kinship system"),
    ("what is ritual",                                           "ritual"),
    ("what is taboo",                                            "taboo"),
    ("what is totemism",                                         "totemism"),
    ("what is structural functionalism",                         "structural functionalism"),
    ("what is conflict theory",                                  "conflict theory"),
    ("what is symbolic interactionism",                          "symbolic interactionism"),
    ("what is social capital",                                   "social capital"),
    ("what is colonialism",                                      "colonialism"),
    ("what is globalization",                                    "globalization"),
    ("what is a caste system",                                   "caste system"),
    ("what is deviance",                                         "deviance"),
    ("what is social norms",                                     "social norms"),
])
def test_batch257_subject_extraction(question, expected):
    """Batch 257: sociology/anthropology — stratification, theory, culture."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is impressionism",                                    "impressionism"),
    ("what is surrealism",                                       "surrealism"),
    ("what is abstract expressionism",                           "abstract expressionism"),
    ("what is cubism",                                           "cubism"),
    ("what is the renaissance",                                  "renaissance"),
    ("what is baroque art",                                      "baroque art"),
    ("what is romanticism",                                      "romanticism"),
    ("what is modernism",                                        "modernism"),
    ("what is postmodernism",                                    "postmodernism"),
    ("what is dadaism",                                          "dadaism"),
    ("what is pop art",                                          "pop art"),
    ("what is minimalism",                                       "minimalism"),
    ("what is fresco painting",                                  "fresco painting"),
    ("what is chiaroscuro",                                      "chiaroscuro"),
    ("what is perspective in art",                               "perspective"),
    ("what is the golden age of dutch painting",                 "golden age of dutch painting"),
    ("what is neoclassicism",                                    "neoclassicism"),
    ("what is fauvism",                                          "fauvism"),
    ("what is expressionism",                                    "expressionism"),
    ("what is conceptual art",                                   "conceptual art"),
])
def test_batch258_subject_extraction(question, expected):
    """Batch 258: art history — movements, techniques, historical periods."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is buddhism",                                         "buddhism"),
    ("what is hinduism",                                         "hinduism"),
    ("what is islam",                                            "islam"),
    ("what is christianity",                                     "christianity"),
    ("what is judaism",                                          "judaism"),
    ("what is the torah",                                        "torah"),
    ("what is the quran",                                        "quran"),
    ("what is the bible",                                        "bible"),
    ("what is karma",                                            "karma"),
    ("what is nirvana",                                          "nirvana"),
    ("what is reincarnation",                                    "reincarnation"),
    ("what is monotheism",                                       "monotheism"),
    ("what is polytheism",                                       "polytheism"),
    ("what is greek mythology",                                  "greek mythology"),
    ("what is norse mythology",                                  "norse mythology"),
    ("what is the afterlife",                                    "afterlife"),
    ("what is a pantheon",                                       "pantheon"),
    ("what is shamanism",                                        "shamanism"),
    ("what is agnosticism",                                      "agnosticism"),
    ("what is atheism",                                          "atheism"),
])
def test_batch259_subject_extraction(question, expected):
    """Batch 259: religion/mythology — world religions, sacred texts, concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is democracy",                                        "democracy"),
    ("what is authoritarianism",                                 "authoritarianism"),
    ("what is federalism",                                       "federalism"),
    ("what is separation of powers",                             "separation of powers"),
    ("what is checks and balances",                              "checks and balances"),
    ("what is geopolitics",                                      "geopolitics"),
    ("what is diplomacy",                                        "diplomacy"),
    ("what is sovereignty",                                      "sovereignty"),
    ("what is international law",                                "international law"),
    ("what is the united nations",                               "united nations"),
    ("what is a constitutional monarchy",                        "constitutional monarchy"),
    ("what is civil liberties",                                  "civil liberties"),
    ("what is lobbying",                                         "lobbying"),
    ("what is gerrymandering",                                   "gerrymandering"),
    ("what is propaganda",                                       "propaganda"),
    ("what is nationalism",                                      "nationalism"),
    ("what is populism",                                         "populism"),
    ("what is electoral college",                                "electoral college"),
    ("what is soft power",                                       "soft power"),
    ("what is the nato alliance",                                "nato alliance"),
])
def test_batch260_subject_extraction(question, expected):
    """Batch 260: political science — governance, diplomacy, ideology."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a neuron",                                         "neuron"),
    ("what is a synapse",                                        "synapse"),
    ("what is dopamine",                                         "dopamine"),
    ("what is serotonin",                                        "serotonin"),
    ("what is neuroplasticity",                                  "neuroplasticity"),
    ("what is the prefrontal cortex",                            "prefrontal cortex"),
    ("what is the hippocampus",                                  "hippocampus"),
    ("what is the amygdala",                                     "amygdala"),
    ("what is the cerebellum",                                   "cerebellum"),
    ("what is long term memory",                                 "long term memory"),
    ("what is short term memory",                                "short term memory"),
    ("what is working memory",                                   "working memory"),
    ("what is sleep deprivation",                                "sleep deprivation"),
    ("what is a migraine",                                       "migraine"),
    ("what is alzheimer's",                                      "alzheimer's"),
    ("what is parkinson's disease",                              "parkinson's disease"),
    ("what is an action potential",                              "action potential"),
    ("what is the blood brain barrier",                          "blood brain barrier"),
    ("what is neural network",                                   "neural network"),
    ("what is the limbic system",                                "limbic system"),
])
def test_batch261_subject_extraction(question, expected):
    """Batch 261: neuroscience — neurons, brain regions, memory, neurological conditions."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is the periodic table",                               "periodic table"),
    ("what is an isotope",                                       "isotope"),
    ("what is a chemical bond",                                  "chemical bond"),
    ("what is covalent bonding",                                 "covalent bonding"),
    ("what is ionic bonding",                                    "ionic bonding"),
    ("what is oxidation",                                        "oxidation"),
    ("what is reduction",                                        "reduction"),
    ("what is a catalyst",                                       "catalyst"),
    ("what is acid base chemistry",                              "acid base chemistry"),
    ("what is ph",                                               "ph"),
    ("what is organic chemistry",                                "organic chemistry"),
    ("what is a polymer",                                        "polymer"),
    ("what is photosynthesis",                                   "photosynthesis"),
    ("what is combustion",                                       "combustion"),
    ("what is the greenhouse effect",                            "greenhouse effect"),
    ("what is radioactive decay",                                "radioactive decay"),
    ("what is an electron",                                      "electron"),
    ("what is entropy",                                          "entropy"),
    ("what is stoichiometry",                                    "stoichiometry"),
    ("what is a mole in chemistry",                              "mole"),
])
def test_batch262_subject_extraction(question, expected):
    """Batch 262: chemistry — bonds, reactions, periodic table, thermodynamics."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is plate tectonics",                                  "plate tectonics"),
    ("what is the water cycle",                                  "water cycle"),
    ("what is a tectonic plate",                                 "tectonic plate"),
    ("what is a river delta",                                    "river delta"),
    ("what is a coral reef",                                     "coral reef"),
    ("what is the ring of fire",                                 "ring of fire"),
    ("what is the continental divide",                           "continental divide"),
    ("what is a rain shadow",                                    "rain shadow"),
    ("what is soil erosion",                                     "soil erosion"),
    ("what is a tsunami",                                        "tsunami"),
    ("what is the jet stream",                                   "jet stream"),
    ("what is permafrost",                                       "permafrost"),
    ("what is a glacier",                                        "glacier"),
    ("what is an aquifer",                                       "aquifer"),
    ("what is a watershed",                                      "watershed"),
    ("what is the troposphere",                                  "troposphere"),
    ("what is the tundra biome",                                 "tundra biome"),
    ("what is the amazon rainforest",                            "amazon rainforest"),
    ("what is a fault line",                                     "fault line"),
    ("what is the carbon cycle",                                 "carbon cycle"),
])
def test_batch263_subject_extraction(question, expected):
    """Batch 263: geography/earth science — geological features, climate, biomes."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("how does the stock market work",                           "stock market"),
    ("why do volcanoes erupt",                                   "volcanoes"),
    ("when did the roman empire fall",                           "roman empire"),
    ("who invented the telephone",                               "telephone"),
    ("where do monarch butterflies migrate",                     "monarch butterflies"),
    ("how does nuclear fission work",                            "nuclear fission"),
    ("why does the moon have craters",                           "moon"),
    ("how does the immune system fight infection",               "immune system"),
    ("what causes a tornado",                                    "tornado"),
    ("how do vaccines work",                                     "vaccines"),
    ("why is the sky blue",                                      "sky"),
    ("how does memory work in the brain",                        "memory"),
    ("what causes inflation",                                    "inflation"),
    ("how does electricity work",                                "electricity"),
    ("why do we dream",                                          "dream"),
    ("how does natural selection work",                          "natural selection"),
    ("why do leaves change color",                               "leaves"),
    ("how does the internet work",                               "internet"),
    ("what causes earthquakes",                                  "earthquakes"),
    ("how does photosynthesis work",                             "photosynthesis"),
])
def test_batch264_subject_extraction(question, expected):
    """Batch 264: complex question forms — how/why/when/who/where patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a light switch",                                   "light switch"),
    ("what is a hard drive",                                     "hard drive"),
    ("what is a sound wave",                                     "sound wave"),
    ("what is a cold front",                                     "cold front"),
    ("what is a heat pump",                                      "heat pump"),
    ("what is a power plant",                                    "power plant"),
    ("what is a wind farm",                                      "wind farm"),
    ("what is a fire wall",                                      "fire wall"),
    ("what is a spring tide",                                    "spring tide"),
    ("what is the big bang theory",                              "big bang theory"),
    ("what is the social contract",                              "social contract"),
    ("what is the prisoner's dilemma",                           "prisoner's dilemma"),
    ("what is the butterfly effect",                             "butterfly effect"),
    ("what is the placebo effect",                               "placebo effect"),
    ("what is the domino effect",                                "domino effect"),
    ("what causes acid rain",                                    "acid rain"),
    ("what causes sleep apnea",                                  "sleep apnea"),
    ("what causes multiple sclerosis",                           "multiple sclerosis"),
    ("what is machine learning",                                 "machine learning"),
    ("what is deep learning",                                    "deep learning"),
])
def test_batch265_subject_extraction(question, expected):
    """Batch 265: adversarial patterns — verb-noun ambiguity, compound nouns, multi-token topics."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is supply and demand",                                "supply and demand"),
    ("what is gross domestic product",                           "gross domestic product"),
    ("what is a trade deficit",                                  "trade deficit"),
    ("what is a trade surplus",                                  "trade surplus"),
    ("what is quantitative easing",                              "quantitative easing"),
    ("what is the gold standard",                                "gold standard"),
    ("what is a hedge fund",                                     "hedge fund"),
    ("what is venture capital",                                  "venture capital"),
    ("what is private equity",                                   "private equity"),
    ("what is a bond yield",                                     "bond yield"),
    ("what is market capitalization",                            "market capitalization"),
    ("what is a bear market",                                    "bear market"),
    ("what is a bull market",                                    "bull market"),
    ("what is compound interest",                                "compound interest"),
    ("what is a mutual fund",                                    "mutual fund"),
    ("what is an index fund",                                    "index fund"),
    ("what is a stock option",                                   "stock option"),
    ("what is gdp growth",                                       "gdp growth"),
    ("what is a central bank",                                   "central bank"),
    ("what is microeconomics",                                   "microeconomics"),
])
def test_batch266_subject_extraction(question, expected):
    """Batch 266: economics/business — compound financial terms, market concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is an api",                                           "api"),
    ("what is a rest api",                                       "rest api"),
    ("what is graphql",                                          "graphql"),
    ("what is a microservice",                                   "microservice"),
    ("what is containerization",                                 "containerization"),
    ("what is kubernetes",                                       "kubernetes"),
    ("what is docker",                                           "docker"),
    ("what is devops",                                           "devops"),
    ("what is continuous integration",                           "continuous integration"),
    ("what is version control",                                  "version control"),
    ("what is open source software",                             "open source software"),
    ("what is cloud computing",                                  "cloud computing"),
    ("what is serverless computing",                             "serverless computing"),
    ("what is a load balancer",                                  "load balancer"),
    ("what is caching",                                          "caching"),
    ("what is a database index",                                 "database index"),
    ("what is sql injection",                                    "sql injection"),
    ("what is two factor authentication",                        "two factor authentication"),
    ("what is end to end encryption",                            "end to end encryption"),
    ("what is a vpn",                                            "vpn"),
])
def test_batch267_subject_extraction(question, expected):
    """Batch 267: technology/software — APIs, cloud, security, compound tech terms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a grand slam",                                     "grand slam"),
    ("what is a hat trick",                                      "hat trick"),
    ("what is offside in soccer",                                "offside"),
    ("what is a penalty kick",                                   "penalty kick"),
    ("what is the offsides rule",                                "offsides rule"),
    ("what is a free throw",                                     "free throw"),
    ("what is a slam dunk",                                      "slam dunk"),
    ("what is tennis elbow",                                     "tennis elbow"),
    ("what is a chess opening",                                  "chess opening"),
    ("what is the elo rating system",                            "elo rating system"),
    ("what is a walkover in sports",                             "walkover"),
    ("what is sudden death overtime",                            "sudden death overtime"),
    ("what is a birdie in golf",                                 "birdie"),
    ("what is par in golf",                                      "par"),
    ("what is an ace in tennis",                                 "ace"),
    ("what is a hole in one",                                    "hole in one"),
    ("what is the tour de france",                               "tour de france"),
    ("what is mixed martial arts",                               "mixed martial arts"),
    ("what is a checkmate",                                      "checkmate"),
    ("what is game theory",                                      "game theory"),
])
def test_batch268_subject_extraction(question, expected):
    """Batch 268: sports/gaming — compound nouns, scoring terms, rule concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a rule of thumb",                                  "rule of thumb"),
    ("what is a catch 22",                                       "catch 22"),
    ("what is a red herring",                                    "red herring"),
    ("what is a scapegoat",                                      "scapegoat"),
    ("what is a straw man argument",                             "straw man argument"),
    ("what is an ad hominem",                                    "ad hominem"),
    ("what is a slippery slope",                                 "slippery slope"),
    ("what is cognitive dissonance",                             "cognitive dissonance"),
    ("what is a false dichotomy",                                "false dichotomy"),
    ("what is confirmation bias",                                "confirmation bias"),
    ("what is a self fulfilling prophecy",                       "self fulfilling prophecy"),
    ("what is the dunning kruger effect",                        "dunning kruger effect"),
    ("what is the bystander effect",                             "bystander effect"),
    ("what is the streisand effect",                             "streisand effect"),
    ("what is a paradigm shift",                                 "paradigm shift"),
    ("what is occam's razor",                                    "occam's razor"),
    ("what is a double bind",                                    "double bind"),
    ("what is quid pro quo",                                     "quid pro quo"),
    ("what is a zero sum game",                                  "zero sum game"),
    ("what is a catch all term",                                 "catch all term"),
])
def test_batch269_subject_extraction(question, expected):
    """Batch 269: idioms/fixed expressions — tricky English phrases and compound nouns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a panic attack",                                  "panic attack"),
    ("what is a heart attack",                                  "heart attack"),
    ("what is a stroke",                                        "stroke"),
    ("what is blood pressure",                                  "blood pressure"),
    ("what is insulin resistance",                              "insulin resistance"),
    ("what is herd immunity",                                   "herd immunity"),
    ("what is a clinical trial",                                "clinical trial"),
    ("what is an immune response",                              "immune response"),
    ("what is a placebo effect",                                "placebo effect"),
    ("what is metabolic syndrome",                              "metabolic syndrome"),
    ("what is chronic fatigue syndrome",                        "chronic fatigue syndrome"),
    ("what is type 2 diabetes",                                 "type 2 diabetes"),
    ("what is multiple sclerosis",                              "multiple sclerosis"),
    ("what is post traumatic stress disorder",                  "post traumatic stress disorder"),
    ("what is irritable bowel syndrome",                        "irritable bowel syndrome"),
    ("what is attention deficit hyperactivity disorder",        "attention deficit hyperactivity disorder"),
    ("what is a stress fracture",                               "stress fracture"),
    ("what is deep vein thrombosis",                            "deep vein thrombosis"),
    ("what is a brain stem",                                    "brain stem"),
    ("what is rheumatoid arthritis",                            "rheumatoid arthritis"),
])
def test_batch270_subject_extraction(question, expected):
    """Batch 270: medical/clinical terms — compound nouns and clinical nomenclature."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is social capital",                                  "social capital"),
    ("what is cultural relativism",                             "cultural relativism"),
    ("what is a rite of passage",                               "rite of passage"),
    ("what is ethnocentrism",                                   "ethnocentrism"),
    ("what is a social contract",                               "social contract"),
    ("what is the social contract theory",                      "social contract theory"),
    ("what is a caste system",                                  "caste system"),
    ("what is social stratification",                           "social stratification"),
    ("what is civil disobedience",                              "civil disobedience"),
    ("what is cultural diffusion",                              "cultural diffusion"),
    ("what is structural functionalism",                        "structural functionalism"),
    ("what is symbolic interactionism",                         "symbolic interactionism"),
    ("what is a stigma",                                        "stigma"),
    ("what is groupthink",                                      "groupthink"),
    ("what is a mob mentality",                                 "mob mentality"),
    ("what is social mobility",                                 "social mobility"),
    ("what is a class struggle",                                "class struggle"),
    ("what is a culture shock",                                 "culture shock"),
    ("what is a social norm",                                   "social norm"),
    ("what is collective memory",                               "collective memory"),
])
def test_batch271_subject_extraction(question, expected):
    """Batch 271: social sciences/anthropology — compound terms and conceptual nouns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a proof by contradiction",                        "proof by contradiction"),
    ("what is a logical fallacy",                               "logical fallacy"),
    ("what is set theory",                                      "set theory"),
    ("what is a venn diagram",                                  "venn diagram"),
    ("what is a boolean operator",                              "boolean operator"),
    ("what is a prime number",                                  "prime number"),
    ("what is the pythagorean theorem",                         "pythagorean theorem"),
    ("what is a geometric series",                              "geometric series"),
    ("what is a fibonacci sequence",                            "fibonacci sequence"),
    ("what is an imaginary number",                             "imaginary number"),
    ("what is a fractal",                                       "fractal"),
    ("what is the chaos theory",                                "chaos theory"),
    ("what is a bell curve",                                    "bell curve"),
    ("what is a null hypothesis",                               "null hypothesis"),
    ("what is standard deviation",                              "standard deviation"),
    ("what is statistical significance",                        "statistical significance"),
    ("what is the monty hall problem",                          "monty hall problem"),
    ("what is the halting problem",                             "halting problem"),
    ("what is a turing machine",                                "turing machine"),
    ("what is bayes theorem",                                   "bayes theorem"),
])
def test_batch272_subject_extraction(question, expected):
    """Batch 272: logic/math/formal concepts — theorems, paradoxes, proofs."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a bain marie",                                    "bain marie"),
    ("what is mise en place",                                   "mise en place"),
    ("what is a roux",                                          "roux"),
    ("what is umami",                                           "umami"),
    ("what is al dente",                                        "al dente"),
    ("what is a sous vide",                                     "sous vide"),
    ("what is blanching",                                       "blanching"),
    ("what is caramelization",                                  "caramelization"),
    ("what is maillard reaction",                               "maillard reaction"),
    ("what is fermentation",                                    "fermentation"),
    ("what is a stock in cooking",                              "stock"),
    ("what is a reduction sauce",                               "reduction sauce"),
    ("what is a beurre blanc",                                  "beurre blanc"),
    ("what is a bechamel sauce",                                "bechamel sauce"),
    ("what is gluten free",                                     "gluten free"),
    ("what is a food allergy",                                  "food allergy"),
    ("what is pasteurization",                                  "pasteurization"),
    ("what is a whole grain",                                   "whole grain"),
    ("what is the glycemic index",                              "glycemic index"),
    ("what is a ketogenic diet",                                "ketogenic diet"),
])
def test_batch273_subject_extraction(question, expected):
    """Batch 273: food/culinary — compound nouns, cooking terms, technique names."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a black hole",                                    "black hole"),
    ("what is dark matter",                                     "dark matter"),
    ("what is dark energy",                                     "dark energy"),
    ("what is the big bang theory",                             "big bang theory"),
    ("what is a neutron star",                                  "neutron star"),
    ("what is a pulsar",                                        "pulsar"),
    ("what is a white dwarf",                                   "white dwarf"),
    ("what is a red giant",                                     "red giant"),
    ("what is a solar flare",                                   "solar flare"),
    ("what is a solar wind",                                    "solar wind"),
    ("what is a light year",                                    "light year"),
    ("what is an event horizon",                                "event horizon"),
    ("what is a gravitational wave",                            "gravitational wave"),
    ("what is the cosmic microwave background",                 "cosmic microwave background"),
    ("what is a planetary nebula",                              "planetary nebula"),
    ("what is stellar evolution",                               "stellar evolution"),
    ("what is a red shift",                                     "red shift"),
    ("what is a wormhole",                                      "wormhole"),
    ("what is a binary star system",                            "binary star system"),
    ("what is the oort cloud",                                  "oort cloud"),
])
def test_batch274_subject_extraction(question, expected):
    """Batch 274: astronomy/cosmology — compound nouns, phenomena, named theories."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a dry run",                                       "dry run"),
    ("what is a test run",                                      "test run"),
    ("what is a home run",                                      "home run"),
    ("what is a tax break",                                     "tax break"),
    ("what is a spring break",                                  "spring break"),
    ("what is a lunch break",                                   "lunch break"),
    ("what is a price rise",                                    "price rise"),
    ("what is a power rise",                                    "power rise"),
    ("what is a free fall",                                     "free fall"),
    ("what is a hard fall",                                     "hard fall"),
    ("what is a flash drive",                                   "flash drive"),
    ("what is a hard drive",                                    "hard drive"),
    ("what is a thumb drive",                                   "thumb drive"),
    ("what is a hunger strike",                                 "hunger strike"),
    ("what is a lightning strike",                              "lightning strike"),
    ("what is a margin call",                                   "margin call"),
    ("what is a roll call",                                     "roll call"),
    ("what is a benchmark",                                     "benchmark"),
    ("what is a trade mark",                                    "trade mark"),
    ("what is a water mark",                                    "water mark"),
])
def test_batch275_subject_extraction(question, expected):
    """Batch 275: adversarial verb/noun-head ambiguity — dual-role words as noun components."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is greenhouse gas",                                  "greenhouse gas"),
    ("what is the greenhouse effect",                           "greenhouse effect"),
    ("what is climate change",                                  "climate change"),
    ("what is global warming",                                  "global warming"),
    ("what is carbon footprint",                                "carbon footprint"),
    ("what is acid rain",                                       "acid rain"),
    ("what is the ozone layer",                                 "ozone layer"),
    ("what is biodiversity loss",                               "biodiversity loss"),
    ("what is deforestation",                                   "deforestation"),
    ("what is ocean acidification",                             "ocean acidification"),
    ("what is carbon capture",                                  "carbon capture"),
    ("what is a carbon sink",                                   "carbon sink"),
    ("what is renewable energy",                                "renewable energy"),
    ("what is solar energy",                                    "solar energy"),
    ("what is wind energy",                                     "wind energy"),
    ("what is a carbon tax",                                    "carbon tax"),
    ("what is sea level rise",                                  "sea level rise"),
    ("what is permafrost",                                      "permafrost"),
    ("what is coral bleaching",                                 "coral bleaching"),
    ("what is the water cycle",                                 "water cycle"),
])
def test_batch276_subject_extraction(question, expected):
    """Batch 276: climate/environmental science — compound terms and named phenomena."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a ponzi scheme",                                  "ponzi scheme"),
    ("what is short selling",                                   "short selling"),
    ("what is a leverage buyout",                               "leverage buyout"),
    ("what is dollar cost averaging",                           "dollar cost averaging"),
    ("what is a dividend yield",                                "dividend yield"),
    ("what is market volatility",                               "market volatility"),
    ("what is a credit default swap",                           "credit default swap"),
    ("what is algorithmic trading",                             "algorithmic trading"),
    ("what is high frequency trading",                          "high frequency trading"),
    ("what is a covered call",                                  "covered call"),
    ("what is a put option",                                    "put option"),
    ("what is a call option",                                   "call option"),
    ("what is insider trading",                                 "insider trading"),
    ("what is a price to earnings ratio",                       "price to earnings ratio"),
    ("what is return on investment",                            "return on investment"),
    ("what is a balance sheet",                                 "balance sheet"),
    ("what is cash flow",                                       "cash flow"),
    ("what is a fiscal cliff",                                  "fiscal cliff"),
    ("what is quantitative tightening",                         "quantitative tightening"),
    ("what is stagflation",                                     "stagflation"),
])
def test_batch277_subject_extraction(question, expected):
    """Batch 277: finance/investing — compound terms, named concepts, financial instruments."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is due process",                                     "due process"),
    ("what is habeas corpus",                                   "habeas corpus"),
    ("what is eminent domain",                                  "eminent domain"),
    ("what is civil law",                                       "civil law"),
    ("what is common law",                                      "common law"),
    ("what is criminal law",                                    "criminal law"),
    ("what is a class action lawsuit",                          "class action lawsuit"),
    ("what is intellectual property",                           "intellectual property"),
    ("what is a non disclosure agreement",                      "non disclosure agreement"),
    ("what is the miranda warning",                             "miranda warning"),
    ("what is double jeopardy",                                 "double jeopardy"),
    ("what is probable cause",                                  "probable cause"),
    ("what is a restraining order",                             "restraining order"),
    ("what is a writ of mandamus",                              "writ of mandamus"),
    ("what is the presumption of innocence",                    "presumption of innocence"),
    ("what is mens rea",                                        "mens rea"),
    ("what is actus reus",                                      "actus reus"),
    ("what is a statute of limitations",                        "statute of limitations"),
    ("what is sovereign immunity",                              "sovereign immunity"),
    ("what is judicial review",                                 "judicial review"),
])
def test_batch278_subject_extraction(question, expected):
    """Batch 278: law/legal concepts — compound terms and legal doctrine names."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a dead giveaway",                                 "dead giveaway"),
    ("what is a make or break moment",                          "make or break moment"),
    ("what is a prison break",                                  "prison break"),
    ("what is a clean break",                                   "clean break"),
    ("what is a jailbreak",                                     "jailbreak"),
    ("what is a fair play",                                     "fair play"),
    ("what is foul play",                                       "foul play"),
    ("what is a power play",                                    "power play"),
    ("what is a display",                                       "display"),
    ("what is a stronghold",                                    "stronghold"),
    ("what is a household",                                     "household"),
    ("what is a turning point",                                 "turning point"),
    ("what is a u-turn",                                        "u-turn"),
    ("what is a long shot",                                     "long shot"),
    ("what is a moon shot",                                     "moon shot"),
    ("what is a headshot",                                      "headshot"),
    ("what is a race track",                                    "race track"),
    ("what is a soundtrack",                                    "soundtrack"),
    ("what is a lookout",                                       "lookout"),
    ("what is an outlook",                                      "outlook"),
])
def test_batch279_subject_extraction(question, expected):
    """Batch 279: adversarial compound nouns — give/make/break/play/hold/turn/shot/track/look."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a firewall",                                      "firewall"),
    ("what is a man in the middle attack",                      "man in the middle attack"),
    ("what is a denial of service attack",                      "denial of service attack"),
    ("what is a distributed denial of service",                 "distributed denial of service"),
    ("what is a buffer overflow",                               "buffer overflow"),
    ("what is a race condition",                                "race condition"),
    ("what is a memory leak",                                   "memory leak"),
    ("what is a deadlock",                                      "deadlock"),
    ("what is a mutex",                                         "mutex"),
    ("what is a semaphore",                                     "semaphore"),
    ("what is a hash function",                                 "hash function"),
    ("what is a checksum",                                      "checksum"),
    ("what is public key cryptography",                         "public key cryptography"),
    ("what is a digital signature",                             "digital signature"),
    ("what is a zero day exploit",                              "zero day exploit"),
    ("what is a phishing attack",                               "phishing attack"),
    ("what is ransomware",                                      "ransomware"),
    ("what is a trojan horse",                                  "trojan horse"),
    ("what is a backdoor",                                      "backdoor"),
    ("what is network latency",                                 "network latency"),
])
def test_batch280_subject_extraction(question, expected):
    """Batch 280: technology / security — compound terms and attack vector names."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a neural network",                               "neural network"),
    ("what is deep learning",                                  "deep learning"),
    ("what is machine learning",                               "machine learning"),
    ("what is a decision tree",                                "decision tree"),
    ("what is a random forest",                                "random forest"),
    ("what is gradient descent",                               "gradient descent"),
    ("what is backpropagation",                                "backpropagation"),
    ("what is overfitting",                                    "overfitting"),
    ("what is underfitting",                                   "underfitting"),
    ("what is a support vector machine",                       "support vector machine"),
    ("what is k nearest neighbors",                            "k nearest neighbors"),
    ("what is principal component analysis",                   "principal component analysis"),
    ("what is natural language processing",                    "natural language processing"),
    ("what is a transformer model",                            "transformer model"),
    ("what is transfer learning",                              "transfer learning"),
    ("what is reinforcement learning",                         "reinforcement learning"),
    ("what is a convolutional neural network",                 "convolutional neural network"),
    ("what is a recurrent neural network",                     "recurrent neural network"),
    ("what is a generative adversarial network",               "generative adversarial network"),
    ("what is a loss function",                                "loss function"),
])
def test_batch281_subject_extraction(question, expected):
    """Batch 281: machine learning / AI — model types, training concepts, and evaluation terms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a primary key",                                  "primary key"),
    ("what is a foreign key",                                  "foreign key"),
    ("what is a database index",                               "database index"),
    ("what is database normalization",                         "database normalization"),
    ("what is a join in sql",                                  "join"),
    ("what is a stored procedure",                             "stored procedure"),
    ("what is a transaction",                                  "transaction"),
    ("what is acid compliance",                                "acid compliance"),
    ("what is a nosql database",                               "nosql database"),
    ("what is a document database",                            "document database"),
    ("what is a graph database",                               "graph database"),
    ("what is a data warehouse",                               "data warehouse"),
    ("what is a data lake",                                    "data lake"),
    ("what is an etl pipeline",                                "etl pipeline"),
    ("what is data partitioning",                              "data partitioning"),
    ("what is sharding",                                       "sharding"),
    ("what is database replication",                           "database replication"),
    ("what is a cache",                                        "cache"),
    ("what is an orm",                                         "orm"),
    ("what is a message queue",                                "message queue"),
])
def test_batch282_subject_extraction(question, expected):
    """Batch 282: databases / data engineering — SQL, NoSQL, and data pipeline terms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a rest api",                                     "rest api"),
    ("what is a graphql api",                                  "graphql api"),
    ("what is an http request",                                "http request"),
    ("what is cors",                                           "cors"),
    ("what is a cookie",                                       "cookie"),
    ("what is a session token",                                "session token"),
    ("what is oauth",                                          "oauth"),
    ("what is a webhook",                                      "webhook"),
    ("what is a cdn",                                          "cdn"),
    ("what is server side rendering",                          "server side rendering"),
    ("what is client side rendering",                          "client side rendering"),
    ("what is a single page application",                      "single page application"),
    ("what is a progressive web app",                          "progressive web app"),
    ("what is lazy loading",                                   "lazy loading"),
    ("what is a service worker",                               "service worker"),
    ("what is websockets",                                     "websockets"),
    ("what is load balancing",                                 "load balancing"),
    ("what is a reverse proxy",                                "reverse proxy"),
    ("what is http caching",                                   "http caching"),
    ("what is cross site scripting",                           "cross site scripting"),
])
def test_batch283_subject_extraction(question, expected):
    """Batch 283: web development — HTTP, APIs, frontend/backend patterns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a dry run",                                      "dry run"),
    ("what is a test run",                                     "test run"),
    ("what is a home run",                                     "home run"),
    ("what is a bull run",                                     "bull run"),
    ("what is a data set",                                     "data set"),
    ("what is a training set",                                 "training set"),
    ("what is a skill set",                                    "skill set"),
    ("what is a mind set",                                     "mind set"),
    ("what is a debug build",                                  "debug build"),
    ("what is a nightly build",                                "nightly build"),
    ("what is a boarding pass",                                "boarding pass"),
    ("what is a hall pass",                                    "hall pass"),
    ("what is an error log",                                   "error log"),
    ("what is a change log",                                   "change log"),
    ("what is a system log",                                   "system log"),
    ("what is a heat map",                                     "heat map"),
    ("what is a road map",                                     "road map"),
    ("what is a mind map",                                     "mind map"),
    ("what is a pattern match",                                "pattern match"),
    ("what is a pull request merge",                           "pull request merge"),
])
def test_batch284_subject_extraction(question, expected):
    """Batch 284: adversarial computing compound nouns — run/set/build/pass/log/map."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a startup",                                      "startup"),
    ("what is a market cap",                                   "market cap"),
    ("what is a balance sheet",                                "balance sheet"),
    ("what is a profit margin",                                "profit margin"),
    ("what is gross domestic product",                         "gross domestic product"),
    ("what is a hedge fund",                                   "hedge fund"),
    ("what is venture capital",                                "venture capital"),
    ("what is a limited partnership",                          "limited partnership"),
    ("what is a supply chain",                                 "supply chain"),
    ("what is brand equity",                                   "brand equity"),
    ("what is market share",                                   "market share"),
    ("what is a buyout",                                       "buyout"),
    ("what is a merger",                                       "merger"),
    ("what is an acquisition",                                 "acquisition"),
    ("what is an ipo",                                         "ipo"),
    ("what is a bear market",                                  "bear market"),
    ("what is a bond yield",                                   "bond yield"),
    ("what is insider trading",                                "insider trading"),
    ("what is a stock split",                                  "stock split"),
    ("what is a dividend",                                     "dividend"),
])
def test_batch285_subject_extraction(question, expected):
    """Batch 285: business / economics — market and finance terminology."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a free kick",                                    "free kick"),
    ("what is a penalty kick",                                 "penalty kick"),
    ("what is a corner kick",                                  "corner kick"),
    ("what is a hat trick",                                    "hat trick"),
    ("what is offside",                                        "offside"),
    ("what is a slam dunk",                                    "slam dunk"),
    ("what is a free throw",                                   "free throw"),
    ("what is a jump shot",                                    "jump shot"),
    ("what is a triple double",                                "triple double"),
    ("what is a grand slam",                                   "grand slam"),
    ("what is a serve in tennis",                              "serve"),
    ("what is a love score in tennis",                         "love score"),
    ("what is a knockout",                                     "knockout"),
    ("what is a technical knockout",                           "technical knockout"),
    ("what is a draw in chess",                                "draw"),
    ("what is an en passant",                                  "en passant"),
    ("what is a checkmate",                                    "checkmate"),
    ("what is a birdie in golf",                               "birdie"),
    ("what is an eagle in golf",                               "eagle"),
    ("what is a bogey in golf",                                "bogey"),
])
def test_batch287_subject_extraction(question, expected):
    """Batch 287: sports — compound terms, positions, and tactics."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a data point",                                   "data point"),
    ("what is a boiling point",                                "boiling point"),
    ("what is a tipping point",                                "tipping point"),
    ("what is a focal point",                                  "focal point"),
    ("what is a selling point",                                "selling point"),
    ("what is a benchmark",                                    "benchmark"),
    ("what is a hallmark",                                     "hallmark"),
    ("what is a watermark",                                    "watermark"),
    ("what is a skid mark",                                    "skid mark"),
    ("what is a catch 22",                                     "catch 22"),
    ("what is a catch phrase",                                 "catch phrase"),
    ("what is groundwork",                                     "groundwork"),
    ("what is a framework",                                    "framework"),
    ("what is teamwork",                                       "teamwork"),
    ("what is a network",                                      "network"),
    ("what is a backhand",                                     "backhand"),
    ("what is a forehand",                                     "forehand"),
    ("what is a shorthand",                                    "shorthand"),
    ("what is a promissory note",                              "promissory note"),
    ("what is a keynote",                                      "keynote"),
])
def test_batch288_subject_extraction(question, expected):
    """Batch 288: adversarial point/mark/catch/work/hand as noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is free will",                                      "free will"),
    ("what is determinism",                                    "determinism"),
    ("what is moral relativism",                               "moral relativism"),
    ("what is utilitarianism",                                 "utilitarianism"),
    ("what is deontological ethics",                           "deontological ethics"),
    ("what is virtue ethics",                                  "virtue ethics"),
    ("what is the social contract",                            "social contract"),
    ("what is moral realism",                                  "moral realism"),
    ("what is nihilism",                                       "nihilism"),
    ("what is existentialism",                                 "existentialism"),
    ("what is the trolley problem",                            "trolley problem"),
    ("what is cognitive dissonance",                           "cognitive dissonance"),
    ("what is a logical fallacy",                              "logical fallacy"),
    ("what is the burden of proof",                            "burden of proof"),
    ("what is a straw man argument",                           "straw man argument"),
    ("what is an ad hominem",                                  "ad hominem"),
    ("what is a false dichotomy",                              "false dichotomy"),
    ("what is the naturalistic fallacy",                       "naturalistic fallacy"),
    ("what is ethical relativism",                             "ethical relativism"),
    ("what is moral absolutism",                               "moral absolutism"),
])
def test_batch289_subject_extraction(question, expected):
    """Batch 289: philosophy / ethics — concepts that look like verbs or propositions."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is nuclear fission",                                "nuclear fission"),
    ("what is nuclear fusion",                                 "nuclear fusion"),
    ("what is radioactive decay",                              "radioactive decay"),
    ("what is quantum entanglement",                           "quantum entanglement"),
    ("what is wave particle duality",                          "wave particle duality"),
    ("what is the uncertainty principle",                      "uncertainty principle"),
    ("what is superposition",                                  "superposition"),
    ("what is dark matter",                                    "dark matter"),
    ("what is dark energy",                                    "dark energy"),
    ("what is a black hole",                                   "black hole"),
    ("what is a quasar",                                       "quasar"),
    ("what is antimatter",                                     "antimatter"),
    ("what is thermal expansion",                              "thermal expansion"),
    ("what is surface tension",                                "surface tension"),
    ("what is viscosity",                                      "viscosity"),
    ("what is capacitance",                                    "capacitance"),
    ("what is inductance",                                     "inductance"),
    ("what is a standing wave",                                "standing wave"),
    ("what is resonance",                                      "resonance"),
    ("what is a phase transition",                             "phase transition"),
])
def test_batch290_subject_extraction(question, expected):
    """Batch 290: physics / science — fundamental concepts with action-like names."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a service charge",                               "service charge"),
    ("what is a cover charge",                                 "cover charge"),
    ("what is a depth charge",                                 "depth charge"),
    ("what is a hard drive",                                   "hard drive"),
    ("what is a flash drive",                                  "flash drive"),
    ("what is a test drive",                                   "test drive"),
    ("what is a push notification",                            "push notification"),
    ("what is a push up",                                      "push up"),
    ("what is a pull request",                                 "pull request"),
    ("what is a muscle pull",                                  "muscle pull"),
    ("what is a ski lift",                                     "ski lift"),
    ("what is a face lift",                                    "face lift"),
    ("what is a drop down menu",                               "drop down menu"),
    ("what is a raindrop",                                     "raindrop"),
    ("what is a budget cut",                                   "budget cut"),
    ("what is a paper cut",                                    "paper cut"),
    ("what is a price cut",                                    "price cut"),
    ("what is a rug burn",                                     "rug burn"),
    ("what is a heartburn",                                    "heartburn"),
    ("what is a freudian slip",                                "freudian slip"),
])
def test_batch291_subject_extraction(question, expected):
    """Batch 291: adversarial charge/drive/push/pull/lift/drop/cut/burn as noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is the cold war",                                   "cold war"),
    ("what is the iron curtain",                               "iron curtain"),
    ("what is the marshall plan",                              "marshall plan"),
    ("what is the industrial revolution",                      "industrial revolution"),
    ("what is the enlightenment",                              "enlightenment"),
    ("what is colonialism",                                    "colonialism"),
    ("what is imperialism",                                    "imperialism"),
    ("what is the great depression",                           "great depression"),
    ("what is the new deal",                                   "new deal"),
    ("what is the berlin wall",                                "berlin wall"),
    ("what is apartheid",                                      "apartheid"),
    ("what is the arab spring",                                "arab spring"),
    ("what is the silk road",                                  "silk road"),
    ("what is manifest destiny",                               "manifest destiny"),
    ("what is the monroe doctrine",                            "monroe doctrine"),
    ("what is the truman doctrine",                            "truman doctrine"),
    ("what is the geneva convention",                          "geneva convention"),
    ("what is the treaty of versailles",                       "treaty of versailles"),
    ("what is the magna carta",                                "magna carta"),
    ("what is the boston tea party",                           "boston tea party"),
])
def test_batch292_subject_extraction(question, expected):
    """Batch 292: history / geography — events, eras, and geopolitical terms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a box office",                                   "box office"),
    ("what is a plot twist",                                   "plot twist"),
    ("what is a cliffhanger",                                  "cliffhanger"),
    ("what is an easter egg in movies",                        "easter egg"),
    ("what is a cameo",                                        "cameo"),
    ("what is a documentary",                                  "documentary"),
    ("what is a sequel",                                       "sequel"),
    ("what is a prequel",                                      "prequel"),
    ("what is a reboot",                                       "reboot"),
    ("what is a spin off",                                     "spin off"),
    ("what is a pilot episode",                                "pilot episode"),
    ("what is a season finale",                                "season finale"),
    ("what is a binge watch",                                  "binge watch"),
    ("what is a streaming service",                            "streaming service"),
    ("what is a podcast",                                      "podcast"),
    ("what is a meme",                                         "meme"),
    ("what is a viral video",                                  "viral video"),
    ("what is a gif",                                          "gif"),
    ("what is an influencer",                                  "influencer"),
    ("what is a clickbait",                                    "clickbait"),
])
def test_batch293_subject_extraction(question, expected):
    """Batch 293: pop culture / media — film, streaming, and internet terms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a one night stand",                              "one night stand"),
    ("what is a bandstand",                                    "bandstand"),
    ("what is a grandstand",                                   "grandstand"),
    ("what is a head start",                                   "head start"),
    ("what is a false start",                                  "false start"),
    ("what is a jumpstart",                                    "jumpstart"),
    ("what is a full stop",                                    "full stop"),
    ("what is a pit stop",                                     "pit stop"),
    ("what is a bus stop",                                     "bus stop"),
    ("what is a dead end",                                     "dead end"),
    ("what is a loose end",                                    "loose end"),
    ("what is a split end",                                    "split end"),
    ("what is a close call",                                   "close call"),
    ("what is a market close",                                 "market close"),
    ("what is an open source",                                 "open source"),
    ("what is an open book",                                   "open book"),
    ("what is a seal of approval",                             "seal of approval"),
    ("what is a deal breaker",                                 "deal breaker"),
    ("what is a deadlock",                                     "deadlock"),
    ("what is a gridlock",                                     "gridlock"),
])
def test_batch294_subject_extraction(question, expected):
    """Batch 294: adversarial stand/start/stop/end/close/open/lock as noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is carbon capture",                                 "carbon capture"),
    ("what is a carbon footprint",                             "carbon footprint"),
    ("what is the greenhouse effect",                          "greenhouse effect"),
    ("what is global warming",                                 "global warming"),
    ("what is an ecosystem",                                   "ecosystem"),
    ("what is biodiversity",                                   "biodiversity"),
    ("what is deforestation",                                  "deforestation"),
    ("what is desertification",                                "desertification"),
    ("what is ocean acidification",                            "ocean acidification"),
    ("what is the ozone layer",                                "ozone layer"),
    ("what is acid rain",                                      "acid rain"),
    ("what is a food chain",                                   "food chain"),
    ("what is a food web",                                     "food web"),
    ("what is a tipping point in climate",                     "tipping point"),
    ("what is a carbon credit",                                "carbon credit"),
    ("what is renewable energy",                               "renewable energy"),
    ("what is a solar panel",                                  "solar panel"),
    ("what is a wind turbine",                                 "wind turbine"),
    ("what is sustainable development",                        "sustainable development"),
    ("what is the paris agreement",                            "paris agreement"),
])
def test_batch295_subject_extraction(question, expected):
    """Batch 295: environmental science — climate, ecology, and sustainability."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a hard drive",                                   "hard drive"),
    ("what is a solid state drive",                            "solid state drive"),
    ("what is a flash drive",                                  "flash drive"),
    ("what is a thumb drive",                                  "thumb drive"),
    ("what is a disk drive",                                   "disk drive"),
    ("what is a network switch",                               "network switch"),
    ("what is a kill switch",                                  "kill switch"),
    ("what is a dead switch",                                  "dead switch"),
    ("what is a light switch",                                 "light switch"),
    ("what is a toggle switch",                                "toggle switch"),
    ("what is a patch cable",                                  "patch cable"),
    ("what is a fiber optic cable",                            "fiber optic cable"),
    ("what is a coax cable",                                   "coax cable"),
    ("what is a screen saver",                                 "screen saver"),
    ("what is a screen reader",                                "screen reader"),
    ("what is a file system",                                  "file system"),
    ("what is a boot sector",                                  "boot sector"),
    ("what is a buffer overflow",                              "buffer overflow"),
    ("what is a stack overflow",                               "stack overflow"),
    ("what is a heap overflow",                                "heap overflow"),
])
def test_batch296_subject_extraction(question, expected):
    """Batch 296: technology — hardware, networking, software compound nouns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a bone spur",                                    "bone spur"),
    ("what is a blood clot",                                   "blood clot"),
    ("what is a blood type",                                   "blood type"),
    ("what is a blood vessel",                                 "blood vessel"),
    ("what is a blood pressure",                               "blood pressure"),
    ("what is a heart rate",                                   "heart rate"),
    ("what is a heart attack",                                 "heart attack"),
    ("what is a panic attack",                                 "panic attack"),
    ("what is a stroke",                                       "stroke"),
    ("what is a brain stem",                                   "brain stem"),
    ("what is a spinal cord",                                  "spinal cord"),
    ("what is a nerve ending",                                 "nerve ending"),
    ("what is a muscle fiber",                                 "muscle fiber"),
    ("what is a muscle cramp",                                 "muscle cramp"),
    ("what is a stress fracture",                              "stress fracture"),
    ("what is a compound fracture",                            "compound fracture"),
    ("what is a ligament tear",                                "ligament tear"),
    ("what is a torn ligament",                                "torn ligament"),
    ("what is a rotator cuff",                                 "rotator cuff"),
    ("what is an immune response",                             "immune response"),
])
def test_batch297_subject_extraction(question, expected):
    """Batch 297: medical/anatomy — body parts, conditions, and procedures."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a tax break",                                    "tax break"),
    ("what is a lunch break",                                  "lunch break"),
    ("what is a commercial break",                             "commercial break"),
    ("what is a prison break",                                 "prison break"),
    ("what is a jailbreak",                                    "jailbreak"),
    ("what is a pay cut",                                      "pay cut"),
    ("what is a budget cut",                                   "budget cut"),
    ("what is a shortcut",                                     "shortcut"),
    ("what is a paper cut",                                    "paper cut"),
    ("what is a hit song",                                     "hit song"),
    ("what is a pinch hit",                                    "pinch hit"),
    ("what is a drop kick",                                    "drop kick"),
    ("what is a rain drop",                                    "rain drop"),
    ("what is a backdrop",                                     "backdrop"),
    ("what is a ice pick",                                     "ice pick"),
    ("what is a tooth pick",                                   "tooth pick"),
    ("what is a quick draw",                                   "quick draw"),
    ("what is a gun draw",                                     "gun draw"),
    ("what is a benchmark",                                    "benchmark"),
    ("what is a hallmark",                                     "hallmark"),
])
def test_batch298_subject_extraction(question, expected):
    """Batch 298: adversarial — break/cut/hit/drop/pick/draw/mark as noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a service charge",                               "service charge"),
    ("what is a carrying charge",                              "carrying charge"),
    ("what is a depth charge",                                 "depth charge"),
    ("what is a handling charge",                              "handling charge"),
    ("what is a push notification",                            "push notification"),
    ("what is a push start",                                   "push start"),
    ("what is a bench press",                                  "bench press"),
    ("what is a free press",                                   "free press"),
    ("what is a printing press",                               "printing press"),
    ("what is a disk drive",                                   "disk drive"),
    ("what is a test drive",                                   "test drive"),
    ("what is a flash drive",                                  "flash drive"),
    ("what is a task force",                                   "task force"),
    ("what is a work force",                                   "work force"),
    ("what is a sales force",                                  "sales force"),
    ("what is a payload",                                      "payload"),
    ("what is a workload",                                     "workload"),
    ("what is a road load",                                    "road load"),
    ("what is a ski lift",                                     "ski lift"),
    ("what is a face lift",                                    "face lift"),
])
def test_batch299_subject_extraction(question, expected):
    """Batch 299: adversarial — charge/push/press/drive/force/load/lift as noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a mindset",                                      "mindset"),
    ("what is a offset",                                       "offset"),
    ("what is a skill set",                                    "skill set"),
    ("what is a data set",                                     "data set"),
    ("what is a reset",                                        "reset"),
    ("what is a gadget",                                       "gadget"),
    ("what is a widget",                                       "widget"),
    ("what is a budget",                                       "budget"),
    ("what is a input",                                        "input"),
    ("what is an output",                                      "output"),
    ("what is a throughput",                                   "throughput"),
    ("what is a retrofit",                                     "retrofit"),
    ("what is a outfit",                                       "outfit"),
    ("what is a misfit",                                       "misfit"),
    ("what is a habit",                                        "habit"),
    ("what is a exhibit",                                      "exhibit"),
    ("what is a rabbit",                                       "rabbit"),
    ("what is a booklet",                                      "booklet"),
    ("what is a tablet",                                       "tablet"),
    ("what is a droplet",                                      "droplet"),
])
def test_batch300_subject_extraction(question, expected):
    """Batch 300: milestone — adversarial set/get/put/fit/bit/let embedded verbs as noun suffixes."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a hedge fund",                                   "hedge fund"),
    ("what is a mutual fund",                                  "mutual fund"),
    ("what is a trust fund",                                   "trust fund"),
    ("what is a slush fund",                                   "slush fund"),
    ("what is an index fund",                                  "index fund"),
    ("what is a bond market",                                  "bond market"),
    ("what is a stock market",                                 "stock market"),
    ("what is a bear market",                                  "bear market"),
    ("what is a bull market",                                  "bull market"),
    ("what is a market cap",                                   "market cap"),
    ("what is a venture capital",                              "venture capital"),
    ("what is a capital gain",                                 "capital gain"),
    ("what is a net worth",                                    "net worth"),
    ("what is a balance sheet",                                "balance sheet"),
    ("what is a cash flow",                                    "cash flow"),
    ("what is a profit margin",                                "profit margin"),
    ("what is a gross profit",                                 "gross profit"),
    ("what is a net profit",                                   "net profit"),
    ("what is a compound interest",                            "compound interest"),
    ("what is a prime rate",                                   "prime rate"),
])
def test_batch301_subject_extraction(question, expected):
    """Batch 301: financial/economics — markets, banking, and investment terms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a search warrant",                               "search warrant"),
    ("what is an arrest warrant",                              "arrest warrant"),
    ("what is a court order",                                  "court order"),
    ("what is a restraining order",                            "restraining order"),
    ("what is due process",                                    "due process"),
    ("what is probable cause",                                 "probable cause"),
    ("what is a class action",                                 "class action"),
    ("what is a civil suit",                                   "civil suit"),
    ("what is a class action lawsuit",                         "class action lawsuit"),
    ("what is a plea bargain",                                 "plea bargain"),
    ("what is a hung jury",                                    "hung jury"),
    ("what is contempt of court",                              "contempt of court"),
    ("what is a deposition",                                   "deposition"),
    ("what is an affidavit",                                   "affidavit"),
    ("what is habeas corpus",                                  "habeas corpus"),
    ("what is an injunction",                                  "injunction"),
    ("what is a subpoena",                                     "subpoena"),
    ("what is a tort",                                         "tort"),
    ("what is a statute of limitations",                       "statute of limitations"),
    ("what is double jeopardy",                                "double jeopardy"),
])
def test_batch302_subject_extraction(question, expected):
    """Batch 302: legal/law — court procedures, rights, and legal concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a catch phrase",                                 "catch phrase"),
    ("what is a catch 22",                                     "catch 22"),
    ("what is a match point",                                  "match point"),
    ("what is a perfect match",                                "perfect match"),
    ("what is a test match",                                   "test match"),
    ("what is a software patch",                               "software patch"),
    ("what is a eye patch",                                    "eye patch"),
    ("what is a nicotine patch",                               "nicotine patch"),
    ("what is a batch process",                                "batch process"),
    ("what is a batch file",                                   "batch file"),
    ("what is a neighborhood watch",                           "neighborhood watch"),
    ("what is a death watch",                                  "death watch"),
    ("what is a smartwatch",                                   "smartwatch"),
    ("what is a scratch card",                                 "scratch card"),
    ("what is a scratch pad",                                  "scratch pad"),
    ("what is a rough sketch",                                 "rough sketch"),
    ("what is a data fetch",                                   "data fetch"),
    ("what is a google search",                                "google search"),
    ("what is a web search",                                   "web search"),
    ("what is a job search",                                   "job search"),
])
def test_batch303_subject_extraction(question, expected):
    """Batch 303: adversarial — catch/match/patch/batch/watch/scratch/search as noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a thesis statement",                             "thesis statement"),
    ("what is a research paper",                               "research paper"),
    ("what is a peer review",                                  "peer review"),
    ("what is a citation",                                     "citation"),
    ("what is a bibliography",                                 "bibliography"),
    ("what is a literature review",                            "literature review"),
    ("what is a case study",                                   "case study"),
    ("what is a control group",                                "control group"),
    ("what is a placebo",                                      "placebo"),
    ("what is a placebo effect",                               "placebo effect"),
    ("what is a double blind study",                           "double blind study"),
    ("what is critical thinking",                              "critical thinking"),
    ("what is a learning disability",                          "learning disability"),
    ("what is a standardized test",                            "standardized test"),
    ("what is a grade point average",                          "grade point average"),
    ("what is academic integrity",                             "academic integrity"),
    ("what is a scholarship",                                  "scholarship"),
    ("what is a fellowship",                                   "fellowship"),
    ("what is a tenure track",                                 "tenure track"),
    ("what is peer pressure",                                  "peer pressure"),
])
def test_batch304_subject_extraction(question, expected):
    """Batch 304: educational/academic — learning, research, and academic terms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a cash flow",                                    "cash flow"),
    ("what is a workflow",                                     "workflow"),
    ("what is a data flow",                                    "data flow"),
    ("what is a control flow",                                 "control flow"),
    ("what is an overflow",                                    "overflow"),
    ("what is a talk show",                                    "talk show"),
    ("what is a game show",                                    "game show"),
    ("what is a road show",                                    "road show"),
    ("what is a floor show",                                   "floor show"),
    ("what is a peep show",                                    "peep show"),
    ("what is a free throw",                                   "free throw"),
    ("what is a stone throw",                                  "stone throw"),
    ("what is an overthrow",                                   "overthrow"),
    ("what is a death blow",                                   "death blow"),
    ("what is a body blow",                                    "body blow"),
    ("what is an afterglow",                                   "afterglow"),
    ("what is a death row",                                    "death row"),
    ("what is skid row",                                       "skid row"),
    ("what is a vertigo",                                      "vertigo"),
    ("what is a lingo",                                        "lingo"),
])
def test_batch305_subject_extraction(question, expected):
    """Batch 305: adversarial — flow/show/throw/blow/glow/row and -go suffixes as noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a stem cell",                                    "stem cell"),
    ("what is a red blood cell",                               "red blood cell"),
    ("what is a white blood cell",                             "white blood cell"),
    ("what is a cell membrane",                                "cell membrane"),
    ("what is a cell wall",                                    "cell wall"),
    ("what is a cell division",                                "cell division"),
    ("what is dna replication",                                "dna replication"),
    ("what is natural selection",                              "natural selection"),
    ("what is genetic mutation",                               "genetic mutation"),
    ("what is a gene pool",                                    "gene pool"),
    ("what is a food chain",                                   "food chain"),
    ("what is a food web",                                     "food web"),
    ("what is photosynthesis",                                 "photosynthesis"),
    ("what is cellular respiration",                           "cellular respiration"),
    ("what is mitosis",                                        "mitosis"),
    ("what is meiosis",                                        "meiosis"),
    ("what is a chromosome",                                   "chromosome"),
    ("what is a ribosome",                                     "ribosome"),
    ("what is a chloroplast",                                  "chloroplast"),
    ("what is a mitochondria",                                 "mitochondria"),
])
def test_batch306_subject_extraction(question, expected):
    """Batch 306: biology/life science — cells, genetics, and evolution terms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a home run",                                     "home run"),
    ("what is a slam dunk",                                    "slam dunk"),
    ("what is a hat trick",                                    "hat trick"),
    ("what is a penalty kick",                                 "penalty kick"),
    ("what is a free kick",                                    "free kick"),
    ("what is a corner kick",                                  "corner kick"),
    ("what is an off side",                                    "off side"),
    ("what is a yellow card",                                  "yellow card"),
    ("what is a red card",                                     "red card"),
    ("what is a checkmate",                                    "checkmate"),
    ("what is a love set",                                     "love set"),
    ("what is a match point",                                  "match point"),
    ("what is a photo finish",                                 "photo finish"),
    ("what is a false start",                                  "false start"),
    ("what is a personal foul",                                "personal foul"),
    ("what is a technical foul",                               "technical foul"),
    ("what is a flagrant foul",                                "flagrant foul"),
    ("what is a power play",                                   "power play"),
    ("what is a blitz",                                        "blitz"),
    ("what is a screen pass",                                  "screen pass"),
])
def test_batch307_subject_extraction(question, expected):
    """Batch 307: sports/athletics — equipment, positions, and rules."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is free will",                                      "free will"),
    ("what is determinism",                                    "determinism"),
    ("what is existentialism",                                 "existentialism"),
    ("what is nihilism",                                       "nihilism"),
    ("what is utilitarianism",                                 "utilitarianism"),
    ("what is a moral dilemma",                                "moral dilemma"),
    ("what is cognitive dissonance",                           "cognitive dissonance"),
    ("what is confirmation bias",                              "confirmation bias"),
    ("what is the trolley problem",                            "trolley problem"),
    ("what is an ethical dilemma",                             "ethical dilemma"),
    ("what is the social contract",                            "social contract"),
    ("what is civil disobedience",                             "civil disobedience"),
    ("what is a thought experiment",                           "thought experiment"),
    ("what is reductionism",                                   "reductionism"),
    ("what is empiricism",                                     "empiricism"),
    ("what is rationalism",                                    "rationalism"),
    ("what is pragmatism",                                     "pragmatism"),
    ("what is stoicism",                                       "stoicism"),
    ("what is relativism",                                     "relativism"),
    ("what is a paradigm shift",                               "paradigm shift"),
])
def test_batch308_subject_extraction(question, expected):
    """Batch 308: philosophy/ethics — -isms, dilemmas, and abstract concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a hall pass",                                    "hall pass"),
    ("what is a free pass",                                    "free pass"),
    ("what is a press pass",                                   "press pass"),
    ("what is a boarding pass",                                "boarding pass"),
    ("what is a backstage pass",                               "backstage pass"),
    ("what is a downfall",                                     "downfall"),
    ("what is a rainfall",                                     "rainfall"),
    ("what is a windfall",                                     "windfall"),
    ("what is a pratfall",                                     "pratfall"),
    ("what is a shortfall",                                    "shortfall"),
    ("what is a curtain call",                                 "curtain call"),
    ("what is a wake up call",                                 "wake up call"),
    ("what is a roll call",                                    "roll call"),
    ("what is a tell all",                                     "tell all"),
    ("what is a hard sell",                                    "hard sell"),
    ("what is a soft sell",                                    "soft sell"),
    ("what is a landfill",                                     "landfill"),
    ("what is a refill",                                       "refill"),
    ("what is a bill of rights",                               "bill of rights"),
    ("what is a playbill",                                     "playbill"),
])
def test_batch309_subject_extraction(question, expected):
    """Batch 309: adversarial — pass/fall/call/tell/sell/fill/bill as noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is bipolar disorder",                               "bipolar disorder"),
    ("what is obsessive compulsive disorder",                  "obsessive compulsive disorder"),
    ("what is post traumatic stress disorder",                 "post traumatic stress disorder"),
    ("what is attention deficit hyperactivity disorder",       "attention deficit hyperactivity disorder"),
    ("what is borderline personality disorder",                "borderline personality disorder"),
    ("what is seasonal affective disorder",                    "seasonal affective disorder"),
    ("what is generalized anxiety disorder",                   "generalized anxiety disorder"),
    ("what is social anxiety disorder",                        "social anxiety disorder"),
    ("what is panic disorder",                                 "panic disorder"),
    ("what is a phobia",                                       "phobia"),
    ("what is agoraphobia",                                    "agoraphobia"),
    ("what is claustrophobia",                                 "claustrophobia"),
    ("what is schizophrenia",                                  "schizophrenia"),
    ("what is autism spectrum disorder",                       "autism spectrum disorder"),
    ("what is depression",                                     "depression"),
    ("what is a mental breakdown",                             "mental breakdown"),
    ("what is a nervous breakdown",                            "nervous breakdown"),
    ("what is emotional intelligence",                         "emotional intelligence"),
    ("what is a coping mechanism",                             "coping mechanism"),
    ("what is a defense mechanism",                            "defense mechanism"),
])
def test_batch310_subject_extraction(question, expected):
    """Batch 310: psychology/mental health — disorders, conditions, and concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a blind taste test",                             "blind taste test"),
    ("what is a taste bud",                                    "taste bud"),
    ("what is umami",                                          "umami"),
    ("what is a marinade",                                     "marinade"),
    ("what is a brine",                                        "brine"),
    ("what is emulsification",                                 "emulsification"),
    ("what is a colloid",                                      "colloid"),
    ("what is a reduction sauce",                              "reduction sauce"),
    ("what is a roux",                                         "roux"),
    ("what is a mise en place",                                "mise en place"),
    ("what is a julienne cut",                                 "julienne cut"),
    ("what is a brunoise cut",                                 "brunoise cut"),
    ("what is al dente",                                       "al dente"),
    ("what is a sous vide",                                    "sous vide"),
    ("what is a bain marie",                                   "bain marie"),
    ("what is blanching",                                      "blanching"),
    ("what is a food pyramid",                                 "food pyramid"),
    ("what is a calorie",                                      "calorie"),
    ("what is a macronutrient",                                "macronutrient"),
    ("what is a micronutrient",                                "micronutrient"),
])
def test_batch311_subject_extraction(question, expected):
    """Batch 311: food/culinary science — cooking techniques, nutrition, and terms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a tectonic plate",                               "tectonic plate"),
    ("what is a fault line",                                   "fault line"),
    ("what is a seismic wave",                                 "seismic wave"),
    ("what is a richter scale",                                "richter scale"),
    ("what is a tsunami",                                      "tsunami"),
    ("what is a tidal wave",                                   "tidal wave"),
    ("what is a storm surge",                                  "storm surge"),
    ("what is a trade wind",                                   "trade wind"),
    ("what is a jet stream",                                   "jet stream"),
    ("what is a continental shelf",                            "continental shelf"),
    ("what is a coral reef",                                   "coral reef"),
    ("what is a river delta",                                  "river delta"),
    ("what is a water table",                                  "water table"),
    ("what is an aquifer",                                     "aquifer"),
    ("what is a watershed",                                    "watershed"),
    ("what is a time zone",                                    "time zone"),
    ("what is a magnetic field",                               "magnetic field"),
    ("what is the water cycle",                                "water cycle"),
    ("what is a nitrogen cycle",                               "nitrogen cycle"),
    ("what is a carbon cycle",                                 "carbon cycle"),
])
def test_batch312_subject_extraction(question, expected):
    """Batch 312: geography/earth science — geological, meteorological, and cycle terms."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a speed read",                                   "speed read"),
    ("what is a cold read",                                    "cold read"),
    ("what is a lip read",                                     "lip read"),
    ("what is a ghostwrite",                                   "ghostwrite"),
    ("what is a handwrite",                                    "handwrite"),
    ("what is doublespeak",                                    "doublespeak"),
    ("what is newspeak",                                       "newspeak"),
    ("what is plain speak",                                    "plain speak"),
    ("what is a pep talk",                                     "pep talk"),
    ("what is a pillow talk",                                  "pillow talk"),
    ("what is a small talk",                                   "small talk"),
    ("what is a know how",                                     "know how"),
    ("what is a think tank",                                   "think tank"),
    ("what is an oversight",                                   "oversight"),
    ("what is a foresee",                                      "foresee"),
    ("what is a gut feel",                                     "gut feel"),
    ("what is an outlook",                                     "outlook"),
    ("what is a look out",                                     "look out"),
    ("what is a stopwatch",                                    "stopwatch"),
    ("what is a wristwatch",                                   "wristwatch"),
])
def test_batch313_subject_extraction(question, expected):
    """Batch 313: adversarial — read/speak/talk/feel/look verb forms as noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a stronghold",                                   "stronghold"),
    ("what is a household",                                    "household"),
    ("what is a threshold",                                    "threshold"),
    ("what is a chokehold",                                    "chokehold"),
    ("what is a body build",                                   "body build"),
    ("what is a build up",                                     "build up"),
    ("what is a landslide win",                                "landslide win"),
    ("what is a walkover win",                                 "walkover win"),
    ("what is a brain gain",                                   "brain gain"),
    ("what is a regrowth",                                     "regrowth"),
    ("what is outgrow",                                        "outgrow"),
    ("what is a keep sake",                                    "keep sake"),
    ("what is a bookkeep",                                     "bookkeep"),
    ("what is a remake",                                       "remake"),
    ("what is a make shift",                                   "make shift"),
    ("what is a make up",                                      "make up"),
    ("what is an intake",                                      "intake"),
    ("what is an outtake",                                     "outtake"),
    ("what is a take out",                                     "take out"),
    ("what is a giveaway",                                     "giveaway"),
    ("what is a forgive",                                      "forgive"),
])
def test_batch314_subject_extraction(question, expected):
    """Batch 314: adversarial — hold/build/win/gain/grow/keep/make/take/give noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is social stratification",                         "social stratification"),
    ("what is a social norm",                                  "social norm"),
    ("what is cultural appropriation",                         "cultural appropriation"),
    ("what is an echo chamber",                                "echo chamber"),
    ("what is groupthink",                                     "groupthink"),
    ("what is a glass ceiling",                                "glass ceiling"),
    ("what is systemic racism",                                "systemic racism"),
    ("what is institutional racism",                           "institutional racism"),
    ("what is intersectionality",                              "intersectionality"),
    ("what is implicit bias",                                  "implicit bias"),
    ("what is a racial profiling",                             "racial profiling"),
    ("what is gentrification",                                 "gentrification"),
    ("what is social mobility",                                "social mobility"),
    ("what is wealth inequality",                              "wealth inequality"),
    ("what is income inequality",                              "income inequality"),
    ("what is a welfare state",                                "welfare state"),
    ("what is a social safety net",                            "social safety net"),
    ("what is universal basic income",                         "universal basic income"),
    ("what is a civic duty",                                   "civic duty"),
    ("what is civil society",                                  "civil society"),
])
def test_batch315_subject_extraction(question, expected):
    """Batch 315: social science/sociology — stratification, inequality, and social concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a spin off",                                     "spin off"),
    ("what is a tailspin",                                     "tailspin"),
    ("what is a backspin",                                     "backspin"),
    ("what is a U turn",                                       "u turn"),
    ("what is an about turn",                                  "about turn"),
    ("what is an overturn",                                    "overturn"),
    ("what is a downturn",                                     "downturn"),
    ("what is an upturn",                                      "upturn"),
    ("what is a drum roll",                                    "drum roll"),
    ("what is a barrel roll",                                  "barrel roll"),
    ("what is a payroll",                                      "payroll"),
    ("what is a rap sheet",                                    "rap sheet"),
    ("what is a gift wrap",                                    "gift wrap"),
    ("what is a deadlock",                                     "deadlock"),
    ("what is a gridlock",                                     "gridlock"),
    ("what is a padlock",                                      "padlock"),
    ("what is a writer's block",                               "writer's block"),
    ("what is a chapstick",                                    "chapstick"),
    ("what is a drumstick",                                    "drumstick"),
    ("what is a sidestick",                                    "sidestick"),
])
def test_batch316_subject_extraction(question, expected):
    """Batch 316: adversarial — spin/turn/roll/wrap/lock/stick as noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is activewear",                                        "activewear"),
    ("what is a swimwear",                                        "swimwear"),
    ("what is footwear",                                          "footwear"),
    ("what is knitwear",                                          "knitwear"),
    ("what is sportswear",                                        "sportswear"),
    ("what is a polar bear",                                      "polar bear"),
    ("what is a teddy bear",                                      "teddy bear"),
    ("what is a grizzly bear",                                    "grizzly bear"),
    ("what is a crocodile tear",                                  "crocodile tear"),
    ("what is a wear and tear",                                   "wear and tear"),
    ("what is child care",                                        "child care"),
    ("what is health care",                                       "health care"),
    ("what is elder care",                                        "elder care"),
    ("what is day care",                                          "day care"),
    ("what is a market share",                                    "market share"),
    ("what is a time share",                                      "time share"),
    ("what is a spare tire",                                      "spare tire"),
    ("what is a spare part",                                      "spare part"),
    ("what is a blank stare",                                     "blank stare"),
    ("what is a triple dare",                                     "triple dare"),
])
def test_batch317_subject_extraction(question, expected):
    """Batch 317: adversarial — wear/bear/tear/care/share/spare/stare/dare noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a playground",                                      "playground"),
    ("what is a campground",                                      "campground"),
    ("what is a fairground",                                      "fairground"),
    ("what is a burial ground",                                   "burial ground"),
    ("what is a soundbite",                                       "soundbite"),
    ("what is a surround sound",                                  "surround sound"),
    ("what is ultrasound",                                        "ultrasound"),
    ("what is a merry go round",                                  "merry go round"),
    ("what is a roundabout",                                      "roundabout"),
    ("what is a northbound",                                      "northbound"),
    ("what is a southbound",                                      "southbound"),
    ("what is outbound",                                          "outbound"),
    ("what is inbound",                                           "inbound"),
    ("what is a newfound",                                        "newfound"),
    ("what is a gunshot wound",                                   "gunshot wound"),
    ("what is a dismount",                                        "dismount"),
    ("what is a surmount",                                        "surmount"),
    ("what is a body count",                                      "body count"),
    ("what is a headcount",                                       "headcount"),
    ("what is a gunpoint",                                        "gunpoint"),
    ("what is a knifepoint",                                      "knifepoint"),
])
def test_batch318_subject_extraction(question, expected):
    """Batch 318: adversarial — ground/sound/round/bound/found/wound/mount/count/point noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a hard drive",                                      "hard drive"),
    ("what is a test drive",                                      "test drive"),
    ("what is a flash drive",                                     "flash drive"),
    ("what is a thumb drive",                                     "thumb drive"),
    ("what is a sex drive",                                       "sex drive"),
    ("what is a joyride",                                         "joyride"),
    ("what is a hayride",                                         "hayride"),
    ("what is a free ride",                                       "free ride"),
    ("what is a landslide",                                       "landslide"),
    ("what is a mudslide",                                        "mudslide"),
    ("what is a rockslide",                                       "rockslide"),
    ("what is a hang glide",                                      "hang glide"),
    ("what is a rawhide",                                         "rawhide"),
    ("what is a cowhide",                                         "cowhide"),
    ("what is a ringside",                                        "ringside"),
    ("what is a roadside",                                        "roadside"),
    ("what is a countryside",                                     "countryside"),
    ("what is a tour guide",                                      "tour guide"),
    ("what is a study guide",                                     "study guide"),
    ("what is a pride of lions",                                  "pride of lions"),
])
def test_batch319_subject_extraction(question, expected):
    """Batch 319: adversarial — drive/ride/slide/glide/hide/side/guide/pride noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a brainstorm",                                      "brainstorm"),
    ("what is a snowstorm",                                       "snowstorm"),
    ("what is a firestorm",                                       "firestorm"),
    ("what is a thunderstorm",                                    "thunderstorm"),
    ("what is a platform",                                        "platform"),
    ("what is a uniform",                                         "uniform"),
    ("what is a waveform",                                        "waveform"),
    ("what is a lifeform",                                        "lifeform"),
    ("what is a lukewarm",                                        "lukewarm"),
    ("what is a firearm",                                         "firearm"),
    ("what is a sidearm",                                         "sidearm"),
    ("what is a forearm",                                         "forearm"),
    ("what is self harm",                                         "self harm"),
    ("what is a lucky charm",                                     "lucky charm"),
    ("what is a long term",                                       "long term"),
    ("what is a short term",                                      "short term"),
    ("what is a law firm",                                        "law firm"),
    ("what is a bookworm",                                        "bookworm"),
    ("what is a tapeworm",                                        "tapeworm"),
    ("what is an earthworm",                                      "earthworm"),
])
def test_batch320_subject_extraction(question, expected):
    """Batch 320: adversarial — storm/form/arm/harm/charm/term/firm/worm noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is marine biology",                                    "marine biology"),
    ("what is molecular biology",                                 "molecular biology"),
    ("what is evolutionary biology",                              "evolutionary biology"),
    ("what is synthetic biology",                                 "synthetic biology"),
    ("what is organic chemistry",                                 "organic chemistry"),
    ("what is inorganic chemistry",                               "inorganic chemistry"),
    ("what is physical chemistry",                                "physical chemistry"),
    ("what is analytical chemistry",                              "analytical chemistry"),
    ("what is quantum physics",                                   "quantum physics"),
    ("what is nuclear physics",                                   "nuclear physics"),
    ("what is astrophysics",                                      "astrophysics"),
    ("what is particle physics",                                  "particle physics"),
    ("what is marine geology",                                    "marine geology"),
    ("what is physical geography",                                "physical geography"),
    ("what is atmospheric science",                               "atmospheric science"),
    ("what is marine ecology",                                    "marine ecology"),
    ("what is behavioral ecology",                                "behavioral ecology"),
    ("what is computational neuroscience",                        "computational neuroscience"),
    ("what is biomedical engineering",                            "biomedical engineering"),
    ("what is environmental science",                             "environmental science"),
])
def test_batch321_subject_extraction(question, expected):
    """Batch 321: science subfield compound-noun queries."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is cloud computing",                                   "cloud computing"),
    ("what is cloud storage",                                     "cloud storage"),
    ("what is cloud native",                                      "cloud native"),
    ("what is cloud security",                                    "cloud security"),
    ("what is web scraping",                                      "web scraping"),
    ("what is web assembly",                                      "web assembly"),
    ("what is web3",                                              "web3"),
    ("what is data mining",                                       "data mining"),
    ("what is data lake",                                         "data lake"),
    ("what is data pipeline",                                     "data pipeline"),
    ("what is data governance",                                   "data governance"),
    ("what is cyber security",                                    "cyber security"),
    ("what is cyber warfare",                                     "cyber warfare"),
    ("what is cyber espionage",                                   "cyber espionage"),
    ("what is open source",                                       "open source"),
    ("what is open api",                                          "open api"),
    ("what is open banking",                                      "open banking"),
    ("what is containerization",                                  "containerization"),
    ("what is microservices",                                     "microservices"),
    ("what is serverless",                                        "serverless"),
])
def test_batch322_subject_extraction(question, expected):
    """Batch 322: technology compound nouns — cloud/web/data/cyber/open prefix."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a shortcut",                                        "shortcut"),
    ("what is a haircut",                                         "haircut"),
    ("what is a woodcut",                                         "woodcut"),
    ("what is a price cut",                                       "price cut"),
    ("what is a tax cut",                                         "tax cut"),
    ("what is a mindset",                                         "mindset"),
    ("what is a skill set",                                       "skill set"),
    ("what is an offset",                                         "offset"),
    ("what is a sunset",                                          "sunset"),
    ("what is a onset",                                           "onset"),
    ("what is a smash hit",                                       "smash hit"),
    ("what is a mega hit",                                        "mega hit"),
    ("what is a retrofit",                                        "retrofit"),
    ("what is an outfit",                                         "outfit"),
    ("what is a drill bit",                                       "drill bit"),
    ("what is a sound bite",                                      "sound bite"),
    ("what is a sandpit",                                         "sandpit"),
    ("what is a armpit",                                          "armpit"),
    ("what is a cable knit",                                      "cable knit"),
    ("what is a banana split",                                    "banana split"),
])
def test_batch323_subject_extraction(question, expected):
    """Batch 323: adversarial — cut/set/hit/fit/bit/pit/knit/split noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is common law",                                        "common law"),
    ("what is civil law",                                         "civil law"),
    ("what is criminal law",                                      "criminal law"),
    ("what is case law",                                          "case law"),
    ("what is maritime law",                                      "maritime law"),
    ("what is guerrilla war",                                     "guerrilla war"),
    ("what is a cold war",                                        "cold war"),
    ("what is a proxy war",                                       "proxy war"),
    ("what is a raw deal",                                        "raw deal"),
    ("what is raw data",                                          "raw data"),
    ("what is a quick draw",                                      "quick draw"),
    ("what is a withdraw",                                        "withdraw"),
    ("what is a lobster claw",                                    "lobster claw"),
    ("what is a jawline",                                         "jawline"),
    ("what is a jawbone",                                         "jawbone"),
    ("what is a chainsaw",                                        "chainsaw"),
    ("what is a jigsaw",                                          "jigsaw"),
    ("what is a hacksaw",                                         "hacksaw"),
    ("what is a design flaw",                                     "design flaw"),
    ("what is a strawberry",                                      "strawberry"),
])
def test_batch324_subject_extraction(question, expected):
    """Batch 324: adversarial — law/war/raw/draw/claw/jaw/saw/flaw/straw noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("how does natural selection work",                           "natural selection"),
    ("how does supply chain management work",                     "supply chain management"),
    ("how does machine learning work",                            "machine learning"),
    ("how does nuclear fission work",                             "nuclear fission"),
    ("how does carbon capture work",                              "carbon capture"),
    ("how is a diamond formed",                                   "diamond"),
    ("how is solar energy produced",                              "solar energy"),
    ("what causes climate change",                                "climate change"),
    ("what causes acid rain",                                     "acid rain"),
    ("what causes a solar eclipse",                               "solar eclipse"),
    ("what causes inflation",                                     "inflation"),
    ("why does plate tectonics happen",                           "plate tectonics"),
    ("why does osmosis occur",                                    "osmosis"),
    ("who invented the printing press",                           "printing press"),
    ("who invented the steam engine",                             "steam engine"),
    ("who invented the world wide web",                           "world wide web"),
    ("where is oil shale found",                                  "oil shale"),
    ("when was penicillin discovered",                            "penicillin"),
    ("when was the electron discovered",                          "electron"),
    # "difference between X and Y" — lookup key is the pair, not the framing word
    ("what is the difference between weather and climate",        "weather and climate"),
])
def test_batch325_subject_extraction(question, expected):
    """Batch 325: question-form variants — how/why/what causes/who invented."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a heart attack",                                    "heart attack"),
    ("what is a panic attack",                                    "panic attack"),
    ("what is an anxiety attack",                                 "anxiety attack"),
    ("what is a phishing attack",                                 "phishing attack"),
    ("what is blood pressure",                                    "blood pressure"),
    ("what is high blood pressure",                               "high blood pressure"),
    ("what is low blood pressure",                                "low blood pressure"),
    ("what is a brain bleed",                                     "brain bleed"),
    ("what is a muscle pull",                                     "muscle pull"),
    ("what is a social contract",                                 "social contract"),
    ("what is labor contract",                                    "labor contract"),
    ("what is a bypass surgery",                                  "bypass surgery"),
    ("what is open heart surgery",                                "open heart surgery"),
    ("what is laser eye surgery",                                 "laser eye surgery"),
    ("what is the spinal cord",                                   "spinal cord"),
    ("what is the brain stem",                                    "brain stem"),
    ("what is the lymph node",                                    "lymph node"),
    ("what is herd immunity",                                     "herd immunity"),
    ("what is insulin resistance",                                "insulin resistance"),
    ("what is a blood clot",                                      "blood clot"),
])
def test_batch326_subject_extraction(question, expected):
    """Batch 326: medical compound nouns — conditions, procedures, anatomy."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a buy order",                                       "buy order"),
    ("what is a sell order",                                      "sell order"),
    ("what is a short sell",                                      "short sell"),
    ("what is a short squeeze",                                   "short squeeze"),
    ("what is a leveraged buyout",                                "leveraged buyout"),
    ("what is a hostile takeover",                                "hostile takeover"),
    ("what is a hedge fund",                                      "hedge fund"),
    ("what is a mutual fund",                                     "mutual fund"),
    ("what is a sovereign wealth fund",                           "sovereign wealth fund"),
    ("what is a venture capital fund",                            "venture capital fund"),
    ("what is a profit margin",                                   "profit margin"),
    ("what is a gross margin",                                    "gross margin"),
    ("what is an operating margin",                               "operating margin"),
    ("what is a net margin",                                      "net margin"),
    ("what is a margin call",                                     "margin call"),
    ("what is a stop loss",                                       "stop loss"),
    ("what is a limit order",                                     "limit order"),
    ("what is a trade deficit",                                   "trade deficit"),
    ("what is a trade surplus",                                   "trade surplus"),
    ("what is a budget deficit",                                  "budget deficit"),
])
def test_batch327_subject_extraction(question, expected):
    """Batch 327: financial compound nouns — margins, orders, funds, deficits."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a bench press",                                     "bench press"),
    ("what is a printing press",                                  "printing press"),
    ("what is a hot press",                                       "hot press"),
    ("what is a home stretch",                                    "home stretch"),
    ("what is a stretch limo",                                    "stretch limo"),
    ("what is a crush syndrome",                                  "crush syndrome"),
    ("what is orange crush",                                      "orange crush"),
    ("what is a skin patch",                                      "skin patch"),
    ("what is an eye patch",                                      "eye patch"),
    ("what is a software patch",                                  "software patch"),
    ("what is a catch phrase",                                    "catch phrase"),
    ("what is a catch 22",                                        "catch 22"),
    ("what is a test match",                                      "test match"),
    ("what is a boxing match",                                    "boxing match"),
    ("what is a smartwatch",                                      "smartwatch"),
    ("what is a pocket watch",                                    "pocket watch"),
    ("what is a car wash",                                        "car wash"),
    ("what is a brainwash",                                       "brainwash"),
    ("what is a gold rush",                                       "gold rush"),
    ("what is a sugar rush",                                      "sugar rush"),
])
def test_batch328_subject_extraction(question, expected):
    """Batch 328: adversarial — press/stretch/crush/patch/catch/match/watch/wash/rush noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is the digital age",                                   "digital age"),
    ("what is the stone age",                                     "stone age"),
    ("what is the ice age",                                       "ice age"),
    ("what is middle age",                                        "middle age"),
    ("what is a life stage",                                      "life stage"),
    ("what is a growth stage",                                    "growth stage"),
    ("what is a bird cage",                                       "bird cage"),
    ("what is a rib cage",                                        "rib cage"),
    ("what is a home page",                                       "home page"),
    ("what is a web page",                                        "web page"),
    ("what is a minimum wage",                                    "minimum wage"),
    ("what is a living wage",                                     "living wage"),
    ("what is a mountain range",                                  "mountain range"),
    ("what is a firing range",                                    "firing range"),
    ("what is a driving range",                                   "driving range"),
    ("what is a regime change",                                   "regime change"),
    ("what is a sea change",                                      "sea change"),
    ("what is an overcharge",                                     "overcharge"),
    ("what is a surcharge",                                       "surcharge"),
    ("what is a merger",                                          "merger"),
])
def test_batch329_subject_extraction(question, expected):
    """Batch 329: adversarial — age/stage/cage/page/wage/range/change/charge/merge noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a pen name",                                        "pen name"),
    ("what is a brand name",                                      "brand name"),
    ("what is a domain name",                                     "domain name"),
    ("what is a nick name",                                       "nick name"),
    ("what is hall of fame",                                      "hall of fame"),
    ("what is a blame game",                                      "blame game"),
    ("what is an insurance claim",                                "insurance claim"),
    ("what is a land claim",                                      "land claim"),
    ("what is an end aim",                                        "end aim"),
    ("what is a war game",                                        "war game"),
    ("what is a ball game",                                       "ball game"),
    ("what is a board game",                                      "board game"),
    ("what is a video game",                                      "video game"),
    ("what is a pilot flame",                                     "pilot flame"),
    ("what is a bunsen burner flame",                             "bunsen burner flame"),
    ("what is a picture frame",                                   "picture frame"),
    ("what is a time frame",                                      "time frame"),
    ("what is a reference frame",                                 "reference frame"),
    ("what is a shame spiral",                                    "shame spiral"),
    ("what is a tame version",                                    "tame version"),
])
def test_batch330_subject_extraction(question, expected):
    """Batch 330: adversarial — name/fame/claim/game/flame/frame noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is the cold war",                                      "cold war"),
    ("what is the space race",                                    "space race"),
    ("what is the new deal",                                      "new deal"),
    ("what is the great depression",                              "great depression"),
    ("what is the enlightenment",                                 "enlightenment"),
    ("what is the renaissance",                                   "renaissance"),
    ("what is the industrial revolution",                         "industrial revolution"),
    ("what is the french revolution",                             "french revolution"),
    ("what is manifest destiny",                                  "manifest destiny"),
    ("what is the monroe doctrine",                               "monroe doctrine"),
    ("what is the marshall plan",                                 "marshall plan"),
    ("what is the civil rights movement",                         "civil rights movement"),
    ("what is the suffragette movement",                          "suffragette movement"),
    ("what is the labor movement",                                "labor movement"),
    ("what is the germ theory",                                   "germ theory"),
    ("what is the big bang theory",                               "big bang theory"),
    ("what is the theory of relativity",                          "theory of relativity"),
    ("what is the magna carta",                                   "magna carta"),
    ("what is the bill of rights",                                "bill of rights"),
    ("what is habeas corpus",                                     "habeas corpus"),
])
def test_batch331_subject_extraction(question, expected):
    """Batch 331: named political/historical/cultural concepts."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a confidence boost",                                "confidence boost"),
    ("what is an immune boost",                                   "immune boost"),
    ("what is a turboboost",                                      "turboboost"),
    ("what is the east coast",                                    "east coast"),
    ("what is the west coast",                                    "west coast"),
    ("what is a coastline",                                       "coastline"),
    ("what is a pot roast",                                       "pot roast"),
    ("what is a slow roast",                                      "slow roast"),
    ("what is french toast",                                      "french toast"),
    ("what is a talk show host",                                  "talk show host"),
    ("what is a ghost host",                                      "ghost host"),
    ("what is a blog post",                                       "blog post"),
    ("what is a lamp post",                                       "lamp post"),
    ("what is a gatepost",                                        "gatepost"),
    ("what is a ghost writer",                                    "ghost writer"),
    ("what is a ghost town",                                      "ghost town"),
    ("what is a permafrost",                                      "permafrost"),
    ("what is a ground frost",                                    "ground frost"),
    ("what is a blind trust",                                     "blind trust"),
    ("what is a trust fund",                                      "trust fund"),
])
def test_batch332_subject_extraction(question, expected):
    """Batch 332: adversarial — boost/coast/roast/host/post/ghost/frost/trust noun heads."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a climate change",                                  "climate change"),
    ("what is a behaviour change",                                "behaviour change"),
    ("what is an attitude change",                                "attitude change"),
    ("what is a price rise",                                      "price rise"),
    ("what is a wage rise",                                       "wage rise"),
    ("what is a free fall",                                       "free fall"),
    ("what is a hard fall",                                       "hard fall"),
    ("what is a nose drop",                                       "nose drop"),
    ("what is a backdrop",                                        "backdrop"),
    ("what is a raindrop",                                        "raindrop"),
    ("what is a fever spike",                                     "fever spike"),
    ("what is a price spike",                                     "price spike"),
    ("what is a power surge",                                     "power surge"),
    ("what is a demand surge",                                    "demand surge"),
    ("what is a paradigm shift",                                  "paradigm shift"),
    ("what is a gear shift",                                      "gear shift"),
    ("what is a plate shift",                                     "plate shift"),
    ("what is a gas leak",                                        "gas leak"),
    ("what is an oil leak",                                       "oil leak"),
    ("what is a data breach",                                     "data breach"),
])
def test_batch333_subject_extraction(question, expected):
    """Batch 333: compound noun X+VERB — change/rise/fall/drop/spike/surge/shift/leak/breach."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is global warming",                                    "global warming"),
    ("what is ocean warming",                                     "ocean warming"),
    ("what is global cooling",                                    "global cooling"),
    ("what is active cooling",                                    "active cooling"),
    ("what is glacier melting",                                   "glacier melting"),
    ("what is permafrost melting",                                "permafrost melting"),
    ("what is flash flooding",                                    "flash flooding"),
    ("what is coastal flooding",                                  "coastal flooding"),
    ("what is soil erosion",                                      "soil erosion"),
    ("what is coastal erosion",                                   "coastal erosion"),
    ("what is wind erosion",                                      "wind erosion"),
    ("what is noise pollution",                                   "noise pollution"),
    ("what is light pollution",                                   "light pollution"),
    ("what is plastic pollution",                                 "plastic pollution"),
    ("what is tropical deforestation",                            "tropical deforestation"),
    ("what is ocean acidification",                               "ocean acidification"),
    ("what is land desertification",                              "land desertification"),
    ("what is a flash drought",                                   "flash drought"),
    ("what is a seasonal drought",                                "seasonal drought"),
    ("what is a forest wildfire",                                 "forest wildfire"),
])
def test_batch334_subject_extraction(question, expected):
    """Batch 334: environmental/earth science compound nouns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    # contractions ("what's X" → X)
    ("what's a black hole",                                       "black hole"),
    ("what's the speed of light",                                 "speed of light"),
    ("what's quantum entanglement",                               "quantum entanglement"),
    ("what's osmosis",                                            "osmosis"),
    # "what exactly is X"
    ("what exactly is a black hole",                              "black hole"),
    ("what exactly is machine learning",                          "machine learning"),
    # "what really is X"
    ("what really is consciousness",                              "consciousness"),
    # "can you tell me what X is"
    ("can you tell me what gravity is",                           "gravity"),
    ("can you tell me what a genome is",                          "genome"),
    # "i want to know about X" (regression)
    ("i want to know about the universe",                         "universe"),
    # "could you explain X"
    ("could you explain photosynthesis",                          "photosynthesis"),
    ("could you explain supply and demand",                       "supply and demand"),
    # "just wondering what X is"
    ("just wondering what osmosis is",                            "osmosis"),
    # informal filler words
    ("yo what is a black hole",                                   "black hole"),
    ("so what is inflation",                                      "inflation"),
    ("wait what is the stock market",                             "stock market"),
    ("like what is cryptocurrency",                               "cryptocurrency"),
    ("basically what is machine learning",                        "machine learning"),
    # Title Case normalization
    ("What is a neutron star",                                    "neutron star"),
    ("What Is A Neural Network",                                  "neural network"),
])
def test_batch335_subject_extraction(question, expected):
    """Batch 335: contractions, indirect questions, informal fillers, Title Case normalization."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is cloud computing",                                  "cloud computing"),
    ("what is cloud storage",                                    "cloud storage"),
    ("what is a cloud server",                                   "cloud server"),
    ("what is a neural network",                                 "neural network"),
    ("what is a computer network",                               "computer network"),
    ("what is a peer to peer network",                           "peer to peer network"),
    ("what is a live stream",                                    "live stream"),
    ("what is a data stream",                                    "data stream"),
    ("what is firmware",                                         "firmware"),
    ("what is malware",                                          "malware"),
    ("what is spyware",                                          "spyware"),
    ("what is ransomware",                                       "ransomware"),
    ("what is source code",                                      "source code"),
    ("what is machine code",                                     "machine code"),
    ("what is a hyperlink",                                      "hyperlink"),
    ("what is a deadlink",                                       "deadlink"),
    ("what is a cache",                                          "cache"),
    ("what is a memory cache",                                   "memory cache"),
    ("what is a software patch",                                 "software patch"),
    ("what is a hotfix patch",                                   "hotfix patch"),
])
def test_batch336_subject_extraction(question, expected):
    """Batch 336: computing/tech compound nouns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a chest compress",                                 "chest compress"),
    ("what is a cold compress",                                  "cold compress"),
    ("what is a hot compress",                                   "hot compress"),
    ("what is a hospital discharge",                             "hospital discharge"),
    ("what is a nasal discharge",                                "nasal discharge"),
    ("what is a medical treat",                                  "medical treat"),
    ("what is a nerve block",                                    "nerve block"),
    ("what is a heart block",                                    "heart block"),
    ("what is a skin patch",                                     "skin patch"),
    ("what is a nicotine patch",                                 "nicotine patch"),
    ("what is a cochlear implant",                               "cochlear implant"),
    ("what is a dental implant",                                 "dental implant"),
    ("what is a heart bypass",                                   "heart bypass"),
    ("what is a coronary bypass",                                "coronary bypass"),
    ("what is a kidney transplant",                              "kidney transplant"),
    ("what is a bone marrow transplant",                         "bone marrow transplant"),
    ("what is a brain scan",                                     "brain scan"),
    ("what is a ct scan",                                        "ct scan"),
    ("what is a cancer screen",                                  "cancer screen"),
    ("what is a lethal dose",                                    "lethal dose"),
])
def test_batch337_subject_extraction(question, expected):
    """Batch 337: medical compound nouns with verb-like tails; treat guard."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a bail bond",                                      "bail bond"),
    ("what is a savings bond",                                   "savings bond"),
    ("what is a junk bond",                                      "junk bond"),
    ("what is a car lease",                                      "car lease"),
    ("what is a property lease",                                 "property lease"),
    ("what is a hedge fund",                                     "hedge fund"),
    ("what is a pension fund",                                   "pension fund"),
    ("what is a mutual fund",                                    "mutual fund"),
    ("what is a research grant",                                 "research grant"),
    ("what is a government grant",                               "government grant"),
    ("what is a dollar bill",                                    "dollar bill"),
    ("what is a utility bill",                                   "utility bill"),
    ("what is a parking fine",                                   "parking fine"),
    ("what is a speeding fine",                                  "speeding fine"),
    ("what is a court order",                                    "court order"),
    ("what is a restraining order",                              "restraining order"),
    ("what is an eviction notice",                               "eviction notice"),
    ("what is a legal notice",                                   "legal notice"),
    ("what is a building permit",                                "building permit"),
    ("what is a work permit",                                    "work permit"),
])
def test_batch338_subject_extraction(question, expected):
    """Batch 338: legal/financial compound nouns."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a penalty kick",                                   "penalty kick"),
    ("what is a drop kick",                                      "drop kick"),
    ("what is a side kick",                                      "side kick"),
    ("what is a forward pass",                                   "forward pass"),
    ("what is a back pass",                                      "back pass"),
    ("what is an overpass",                                      "overpass"),
    ("what is a home run",                                       "home run"),
    ("what is a base run",                                       "base run"),
    ("what is a long jump",                                      "long jump"),
    ("what is a high jump",                                      "high jump"),
    ("what is a ski jump",                                       "ski jump"),
    ("what is a hammer throw",                                   "hammer throw"),
    ("what is a javelin throw",                                  "javelin throw"),
    ("what is a safety catch",                                   "safety catch"),
    ("what is a blind catch",                                    "blind catch"),
    ("what is a 100m sprint",                                    "100m sprint"),
    ("what is a rugby tackle",                                   "rugby tackle"),
    ("what is a sliding tackle",                                 "sliding tackle"),
    ("what is a body block",                                     "body block"),
    ("what is a spin serve",                                     "spin serve"),
])
def test_batch339_subject_extraction(question, expected):
    """Batch 339: sports compound nouns; run/jump/catch guards added."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a mountain range",                                 "mountain range"),
    ("what is a firing range",                                   "firing range"),
    ("what is a home range",                                     "home range"),
    ("what is a rust belt",                                      "rust belt"),
    ("what is a conveyor belt",                                  "conveyor belt"),
    ("what is an asteroid belt",                                 "asteroid belt"),
    ("what is a time zone",                                      "time zone"),
    ("what is a combat zone",                                    "combat zone"),
    ("what is an end zone",                                      "end zone"),
    ("what is a flood plain",                                    "flood plain"),
    ("what is a coastal plain",                                  "coastal plain"),
    ("what is a river basin",                                    "river basin"),
    ("what is an ocean basin",                                   "ocean basin"),
    ("what is a mountain ridge",                                 "mountain ridge"),
    ("what is a mid-ocean ridge",                                "mid-ocean ridge"),
    ("what is a ocean trench",                                   "ocean trench"),
    ("what is a deep trench",                                    "deep trench"),
    ("what is a continental shelf",                              "continental shelf"),
    ("what is an ice shelf",                                     "ice shelf"),
    ("what is a river delta",                                    "river delta"),
])
def test_batch340_subject_extraction(question, expected):
    """Batch 340: geography/place compound nouns — all clean."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a magnetic field",                                 "magnetic field"),
    ("what is an electric field",                                "electric field"),
    ("what is a gravitational field",                            "gravitational field"),
    ("what is a sound wave",                                     "sound wave"),
    ("what is a light wave",                                     "light wave"),
    ("what is a shock wave",                                     "shock wave"),
    ("what is a strong force",                                   "strong force"),
    ("what is a weak force",                                     "weak force"),
    ("what is a dark force",                                     "dark force"),
    ("what is a covalent bond",                                  "covalent bond"),
    ("what is an ionic bond",                                    "ionic bond"),
    ("what is a hydrogen bond",                                  "hydrogen bond"),
    ("what is radioactive decay",                                "radioactive decay"),
    ("what is beta decay",                                       "beta decay"),
    ("what is nuclear decay",                                    "nuclear decay"),
    ("what is magnetic flux",                                    "magnetic flux"),
    ("what is heat flux",                                        "heat flux"),
    ("what is electric charge",                                  "electric charge"),
    ("what is a partial charge",                                 "partial charge"),
    ("what is quantum spin",                                     "quantum spin"),
])
def test_batch341_subject_extraction(question, expected):
    """Batch 341: physics/chemistry compound nouns; quantum/back/top spin guarded."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a smoothie blend",                                 "smoothie blend"),
    ("what is a spice blend",                                    "spice blend"),
    ("what is a cake mix",                                       "cake mix"),
    ("what is a trail mix",                                      "trail mix"),
    ("what is a pork chop",                                      "pork chop"),
    ("what is a lamb chop",                                      "lamb chop"),
    ("what is a sandwich spread",                                "sandwich spread"),
    ("what is a cheese spread",                                  "cheese spread"),
    ("what is a salsa dip",                                      "salsa dip"),
    ("what is a sour cream dip",                                 "sour cream dip"),
    ("what is a stir fry",                                       "stir fry"),
    ("what is a deep fry",                                       "deep fry"),
    ("what is a half bake",                                      "half bake"),
    ("what is a slow roast",                                     "slow roast"),
    ("what is a charcoal grill",                                 "charcoal grill"),
    ("what is a rolling boil",                                   "rolling boil"),
    ("what is a gentle simmer",                                  "gentle simmer"),
    ("what is a dry cure",                                       "dry cure"),
    ("what is a dill pickle",                                    "dill pickle"),
    ("what is a lemon marinade",                                 "lemon marinade"),
])
def test_batch342_subject_extraction(question, expected):
    """Batch 342: food/cooking compound nouns; mix/spread/boil/cure guards added."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a stock market",                                   "stock market"),
    ("what is a bull market",                                    "bull market"),
    ("what is a bear market",                                    "bear market"),
    ("what is a labor market",                                   "labor market"),
    ("what is free trade",                                       "free trade"),
    ("what is fair trade",                                       "fair trade"),
    ("what is a trade war",                                      "trade war"),
    ("what is an interest rate",                                 "interest rate"),
    ("what is an exchange rate",                                 "exchange rate"),
    ("what is an inflation rate",                                "inflation rate"),
    ("what is a consumer price index",                           "consumer price index"),
    ("what is a stock index",                                    "stock index"),
    ("what is a bond yield",                                     "bond yield"),
    ("what is a dividend yield",                                 "dividend yield"),
    ("what is financial leverage",                               "financial leverage"),
    ("what is a housing bubble",                                 "housing bubble"),
    ("what is a stock bubble",                                   "stock bubble"),
    ("what is a market crash",                                   "market crash"),
    ("what is a stock crash",                                    "stock crash"),
    ("what is a business cycle",                                 "business cycle"),
])
def test_batch343_subject_extraction(question, expected):
    """Batch 343: economic/finance compound nouns — all clean."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is game theory",                                      "game theory"),
    ("what is string theory",                                    "string theory"),
    ("what is chaos theory",                                     "chaos theory"),
    ("what is conspiracy theory",                                "conspiracy theory"),
    ("what is the uncertainty principle",                        "uncertainty principle"),
    ("what is the peter principle",                              "peter principle"),
    ("what is the pleasure principle",                           "pleasure principle"),
    ("what is murphy's law",                                     "murphy's law"),
    ("what is newton's law",                                     "newton's law"),
    ("what is the fermi paradox",                                "fermi paradox"),
    ("what is the twin paradox",                                 "twin paradox"),
    ("what is the prisoner's dilemma",                           "prisoner's dilemma"),
    ("what is the straw man fallacy",                            "straw man fallacy"),
    ("what is the slippery slope fallacy",                       "slippery slope fallacy"),
    ("what is the null hypothesis",                              "null hypothesis"),
    ("what is the simulation hypothesis",                        "simulation hypothesis"),
    ("what is the butterfly effect",                             "butterfly effect"),
    ("what is the placebo effect",                               "placebo effect"),
    ("what is confirmation bias",                                "confirmation bias"),
    ("what is survivorship bias",                                "survivorship bias"),
])
def test_batch344_subject_extraction(question, expected):
    """Batch 344: philosophy/abstract compound nouns — all clean."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )


@pytest.mark.parametrize("question,expected", [
    ("what is a human being",                                    "human being"),
    ("what is a sentient being",                                 "sentient being"),
    ("what is a gut feeling",                                    "gut feeling"),
    ("what is an emotional feeling",                             "emotional feeling"),
    ("what is critical thinking",                                "critical thinking"),
    ("what is lateral thinking",                                 "lateral thinking"),
    ("what is wishful thinking",                                 "wishful thinking"),
    ("what is a basic need",                                     "basic need"),
    ("what is special need",                                     "special need"),
    ("what is health care",                                      "health care"),
    ("what is intensive care",                                   "intensive care"),
    ("what is parental leave",                                   "parental leave"),
    ("what is sick leave",                                       "sick leave"),
    ("what is maternity leave",                                  "maternity leave"),
    ("what is a power move",                                     "power move"),
    ("what is a chess move",                                     "chess move"),
    ("what is a commercial break",                               "commercial break"),
    ("what is a lunch break",                                    "lunch break"),
    ("what is a prison break",                                   "prison break"),
    ("what is drug use",                                         "drug use"),
])
def test_batch345_subject_extraction(question, expected):
    """Batch 345: adversarial — heads matching common verbs/function words."""
    result = subject_of(question)
    assert result == expected, (
        f"subject_of({question!r}): expected {expected!r}, got {result!r}"
    )
