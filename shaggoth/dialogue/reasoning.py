"""Multi-step reasoning over the knowledge base and web search.

Retrieval answers "what is X" by finding the best entry and quoting it. That
is all Shaggoth could do: ask it to *compare* two things and it returned one
of them and ignored the other -- "what is the difference between aeroponics
and hydroponics" answered with the hydroponics article and never mentioned
aeroponics.

This module does the part retrieval cannot: work out what a question is
actually asking for, gather the *several* pieces needed, and combine them.
It can also perform web searches when the knowledge base is insufficient.

    compare   -- two subjects, both retrieved, definitions contrasted
    contrast  -- same, but stated as what they share
    causal    -- "why does X ..." -> sentences in X that explain rather than define
    enumerate -- "what are the types of X" -> the enumerating sentences

What it is not: a language model reasoning in free text. There is nothing here
capable of that, and inventing a plausible-sounding chain would be worse than
admitting the limit. Every sentence it emits is one that exists in the corpus;
the reasoning is in *which* sentences it selects and how they are assembled.

Every result carries a trace of the steps taken, so a wrong answer can be
read back to the entry that caused it rather than guessed at.
"""
from __future__ import annotations

import random
import re
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional, Any


class Intent:
    """What a question is asking to be done, beyond simple lookup."""

    DEFINE = "define"
    COMPARE = "compare"
    CONTRAST = "contrast"
    CAUSAL = "causal"
    ENUMERATE = "enumerate"


@dataclass
class Step:
    """One move in the chain, recorded so the answer can be audited."""

    action: str
    detail: str

    def __str__(self) -> str:
        return f"{self.action}: {self.detail}"


@dataclass
class Reasoned:
    answer: str
    intent: str
    steps: list = field(default_factory=list)
    entries_used: list = field(default_factory=list)

    @property
    def trace(self) -> list:
        return [str(s) for s in self.steps]


# -- question classification ----------------------------------------------

_COMPARE = re.compile(
    r"\b(?:difference|differences|differ|distinguish(?:es|ed|ing)?|distinction)\b"
    # "compare X to Y" puts the subject between the verb and the preposition,
    # so this cannot require them to be adjacent.
    r"|\bcompare[ds]?\b.*\b(?:to|with|against)\b|\bcompare[ds]?\b"
    r"|\bversus\b|\bvs\.?\b"
    r"|\b(?:relate|hold[s]?\s+up|stack[s]?\s+up)\b.*\b(?:to|against|next to)\b"
    # "why is X different from Y" is a comparison that happens to open with
    # "why"; classify() checks COMPARE first precisely so it lands here.
    r"|\b(?:how|why|in what way(?:s)?) (?:is|are|does|do) .+ different\b"
    # "what separates X from Y", "what sets X apart from Y"
    r"|\bseparate[sd]?\b|\bsets?\b.+\bapart\b"
    # "is Python faster than JavaScript", "are solar panels better than coal"
    # Any "is/are X [comparative adjective -er] than Y" construction.
    r"|\b(?:is|are)\b.+\b\w+er\b.+\bthan\b"
    # "which is faster/better X or Y", "which is more popular Python or Java"
    r"|\bwhich (?:is|are|was|were)\b.+\bor\b",
    re.I,
)
_CONTRAST = re.compile(
    r"\b(?:similar|similarity|similarities|in common|alike|same as|"
    # "related to" requires the preposition; plain "related" is enough for
    # "how are X and Y related" which asks about their connection, not difference.
    r"related\b|relationship between|connection between)\b",
    re.I,
)
_CAUSAL = re.compile(
    r"^\s*(?:and |but |so )?why\b|\bwhat (?:has\s+|have\s+|had\s+|is\s+)?caus(?:ing|e[ds]?)\b"
    r"|\bhow (?:\w+\s+)?(?:is|are|do|does|did|can|could|would|should) .+"
    r"|\bwhat (?:is|are) the (?:\w+\s+)?(?:cause|process|mechanism|effect|result|purpose|role|function|"
    r"impact|consequence)s? (?:of|behind|in)\b"
    r"|\bwhat (?:leads?|led|trigger[sd]?|triggers|drove|drives?|prompts?|"
    r"start(?:ed|s)?|end(?:ed|s)?|spark(?:ed|s)?|stop(?:ped|s)?|brought\s+about) .+\b"
    r"|\bwhat happens\b|\bwhat makes\b|\breason (?:for|why)\b"
    # Enabling/blocking verbs — the mechanism rather than the definition
    r"|\bwhat (?:enables?|allows?|permits?|prevents?|blocks?|stops?|inhibits?)\b"
    # Responsibility and necessity ("what is responsible for X", "what is needed for X")
    r"|\bwhat (?:is|are)\s+(?:responsible\s+for|needed\s+for|required\s+for|necessary\s+for)\b"
    # "what is behind X" in the explanatory/causal sense
    r"|\bwhat (?:is|are|lies?)\s+behind\b"
    # "what do/does plants need to grow" / "what do organisms require for energy"
    # — asking for requirements is asking for causation.
    r"|\bwhat (?:do|does|did)\b.+\b(?:need|require|use|depend on)\b"
    # Historical "when" questions: "when did X", "when was X built"
    r"|\bwhen (?:did|was|were)\b",
    re.I,
)
_ENUMERATE = re.compile(
    r"\b(?:types? of|kinds? of|sorts? of|categories of|examples? of|"
    r"forms? of|list of|list (?:the|all|some) |what are (?:(?:all|some|any|a few)\s+)?the)\b"
    # "how many X" asks for a count or list of items
    r"|\bhow many\b"
    # "what renewable energy sources are there" / "what languages exist"
    r"|\bwhat .+(?:are|is|were|was)\s+(?:there|available|possible|common)\b"
    # "name all the continents", "give me the main organs", "show me the planets"
    r"|\b(?:name|give|show)\s+(?:me\s+)?(?:all|some|the|main|major|key)\b"
    # "what elements are in water", "what gases are found in the atmosphere"
    r"|\bwhat (?:\w+\s+){0,2}(?:are|were|is)\s+(?:in|inside|within|found in|part of)\b",
    re.I,
)

#: Two subjects joined. "and" is deliberately last: "difference between X and
#: Y" is far more common than "X vs Y", but "and" also appears inside subject
#: names, so the more explicit joiners get first refusal.  "from" and "to"
#: are weakest: only reached after the lead-in verb phrase is stripped (e.g.
#: "compare X to Y" → "X to Y"; "what distinguishes X from Y" → "X from Y").
_JOINERS = (
    r"\s+versus\s+", r"\s+vs\.?\s+",
    r"\s+compared?\s+to\s+",       # "compare to" and "compared to"
    r"\s+compared?\s+with\s+",     # "compare with" and "compared with"
    r"\s+against\s+",
    r"\s+different\s+(?:from|to)\s+",  # "X different from Y"
    r"\s+\w+er\s+than\s+",         # "X faster than Y" after "is" lead-in strip
    r"\s+and\s+",
    r"\s+or\s+",                   # "X or Y" after "which is better" lead-in strip
    r"\s+apart\s+from\s+",         # "sets X apart from Y" after lead-in strip
    r"\s+from\s+",                 # after "what distinguishes" lead-in strip
    r"\s+to\s+",                   # after "compare" lead-in strip
)

# Alternation order matters. Every group in the first branch is optional, so
# it happily matches the empty string at position 0 -- which meant the
# "how are ..." branch was never reached and "how are aeroponics and
# hydroponics similar" yielded the subject "how are aeroponics".
_LEAD_IN = re.compile(
    # "how are X and Y related/similar" — optional adjective between "how" and
    # the auxiliary handles "how similar are TCP and UDP".
    r"^how (?:\w+\s+)?(?:is|are|does|do)\s+"
    r"|^what do\s+"
    r"|^what distinguishes\s+"
    r"|^what sets\s+"
    r"|^what separates\s+"
    r"|^in what way(?:s)?\s+(?:is|are|do|does)\s+"
    # "compare X and Y" / "compare X to Y" as an imperative opens with the
    # verb "compare"; stripping it lets the joiner split correctly.
    r"|^compare[ds]?\s+"
    # "is Python faster than JavaScript" / "are X and Y similar"
    r"|^(?:is|are)\s+"
    # "why is/are/does X different from Y" — including "why is not X ..." from
    # "why isn't X" after contraction expansion.
    r"|^why (?:is|are|was|were|does|do|did)\s+(?:not\s+)?"
    # "which is faster X or Y" — strip "which is [adjective]" leaving subjects
    # Limited to one optional degree word ("more"/"less") plus one adjective.
    r"|^which (?:is|are|was|were)\s+(?:(?:more|less)\s+)?\w+\s+"
    # "what is the difference/similarity/relationship/connection between X and Y"
    r"|^(?:what(?:'s| is| are)?\s+)?(?:the\s+)?"
    r"(?:difference|differences|distinction|similarity|similarities|relationship|connection)?\s*"
    r"(?:between\s+)?",
    re.I,
)
_TRAILING = re.compile(
    r"\s*(?:different|differ|similar|similar to each other|alike|in common|have in common|"
    r"compare|from each other|to each other|related|related to each other)\s*\??\s*$",
    re.I,
)


def classify(question: str) -> str:
    """What kind of work the question needs. Order matters.

    Comparison is checked before causation because "why is X different from
    Y" is a comparison that happens to start with "why".
    """
    text = _expand_contractions((question or "").strip())
    if _COMPARE.search(text):
        return Intent.COMPARE
    if _CONTRAST.search(text):
        return Intent.CONTRAST
    if _ENUMERATE.search(text):
        return Intent.ENUMERATE
    if _CAUSAL.search(text):
        return Intent.CAUSAL
    return Intent.DEFINE


def split_subjects(question: str) -> list:
    """Pull the two things being compared out of a question.

    Returns ``[]`` when it cannot find two, which the caller treats as "this
    is not really a comparison" rather than guessing at one.
    """
    text = _LEAD_IN.sub("", _expand_contractions((question or "").strip()), count=1)
    # Strip the comparison/relation verb that can appear between the first subject
    # and the joiner after the lead-in is removed:
    # "how does DNA differ from RNA" → "DNA differ from RNA" → "DNA from RNA"
    # "how does X relate to Y" → "X relate to Y" → "X to Y"
    text = re.sub(r"\s+(?:differs?|relates?|contrasts?)\b", "", text, flags=re.I)
    text = _TRAILING.sub("", text).strip(" ?.")
    for joiner in _JOINERS:
        parts = re.split(joiner, text, maxsplit=1, flags=re.I)
        if len(parts) == 2:
            left, right = (p.strip(" ?.,") for p in parts)
            if left and right and len(left) > 1 and len(right) > 1:
                return [left, right]
    return []


_CONTRACTIONS = [
    # Negative contractions of auxiliary verbs
    (re.compile(r"\bdon't\b", re.I), "do not"),
    (re.compile(r"\bdoesn't\b", re.I), "does not"),
    (re.compile(r"\bdidn't\b", re.I), "did not"),
    (re.compile(r"\bisn't\b", re.I), "is not"),
    (re.compile(r"\baren't\b", re.I), "are not"),
    (re.compile(r"\bwasn't\b", re.I), "was not"),
    (re.compile(r"\bweren't\b", re.I), "were not"),
    (re.compile(r"\bcan't\b", re.I), "can not"),
    (re.compile(r"\bcouldn't\b", re.I), "could not"),
    (re.compile(r"\bwouldn't\b", re.I), "would not"),
    (re.compile(r"\bshouldn't\b", re.I), "should not"),
    (re.compile(r"\bwon't\b", re.I), "will not"),
    (re.compile(r"\bhaven't\b", re.I), "have not"),
    (re.compile(r"\bhasn't\b", re.I), "has not"),
    (re.compile(r"\bhadn't\b", re.I), "had not"),
    # Question-word contractions ("what's causing X", "how's X different from Y")
    (re.compile(r"\bwhat's\b", re.I), "what is"),
    (re.compile(r"\bwhat're\b", re.I), "what are"),
    (re.compile(r"\bhow's\b", re.I), "how is"),
    (re.compile(r"\bwhy's\b", re.I), "why is"),
    (re.compile(r"\bwhere's\b", re.I), "where is"),
    # Apostrophe-free contractions (informal/mobile typing): "dont", "doesnt", etc.
    (re.compile(r"\bwhats\b", re.I), "what is"),
    (re.compile(r"\bhows\b", re.I), "how is"),
    (re.compile(r"\bwhys\b", re.I), "why is"),
    (re.compile(r"\bwheres\b", re.I), "where is"),
    (re.compile(r"\bdont\b", re.I), "do not"),
    (re.compile(r"\bdoesnt\b", re.I), "does not"),
    (re.compile(r"\bdidnt\b", re.I), "did not"),
    (re.compile(r"\bisnt\b", re.I), "is not"),
    (re.compile(r"\barent\b", re.I), "are not"),
    (re.compile(r"\bwasnt\b", re.I), "was not"),
    (re.compile(r"\bwerent\b", re.I), "were not"),
    (re.compile(r"\bcant\b", re.I), "can not"),
    (re.compile(r"\bcouldnt\b", re.I), "could not"),
    (re.compile(r"\bwouldnt\b", re.I), "would not"),
    (re.compile(r"\bshouldnt\b", re.I), "should not"),
    (re.compile(r"\bhavent\b", re.I), "have not"),
    (re.compile(r"\bhasnt\b", re.I), "has not"),
]


def _expand_contractions(text: str) -> str:
    """Expand common English contractions so the regex strips in classify(),
    split_subjects(), and subject_of() see canonical forms.

    "why doesn't ice float" → "why does not ice float" → strips correctly
    to subject "ice" rather than leaving "doesn't" as a spurious word.
    """
    for pattern, replacement in _CONTRACTIONS:
        text = pattern.sub(replacement, text)
    return text


def subject_of(question: str) -> str:
    """The single subject of a causal or enumerating question."""
    text = _expand_contractions((question or "").strip(" ?."))
    _original = text  # preserved for intent-specific guards below
    text = re.sub(
        r"^(?:and |but |so )?(?:why|what|how|who|when|where)\s+"
        # Optional degree/temporal word after "how"/"what": "how many X", "how long does X",
        # "how fast does X", "how quickly does X" (any -ly adverb), "what year was X".
        r"(?:(?:many|much|long|far|old|often|fast|deep|wide|tall|large|small|high|low|"
        r"big|huge|tiny|heavy|hot|cold|strong|hard|dense|loud|quiet|thick|thin|bright|dark|"
        r"year|century|decade|date|ago)\b|\w+ly)?\s*"
        r"(?:is|are|was|were|has|have|had|does|do|did|can|could|would|should|caus(?:ing|e[ds]?)|makes?|happens?)?\s*",
        "", text, flags=re.I,
    )
    # "at what temperature does water freeze" → "water freeze" (QW strip missed "at what NOUN does")
    text = re.sub(
        r"^at\s+what\s+\w+(?:\s+\w+)?\s+(?:does|do|did|is|are|was|were)\s+",
        "", text, flags=re.I,
    )
    # Residual "not" after stripping the auxiliary: "why does not ice float" →
    # strips "why does " → "not ice float" → strip leading "not" → "ice float"
    text = re.sub(r"^not\s+", "", text, flags=re.I)
    # "how far away is X" → after "how far" stripped, "away" leads: strip it.
    text = re.sub(r"^away\s+", "", text, flags=re.I)
    # After stripping "who"/"what", attribution and trigger verbs head the remainder:
    # "who invented the telephone" → "invented the telephone" → "the telephone"
    # "what started the industrial revolution" → "started the ..." → "the ..."
    # "brought about" is two words so must be listed separately.
    text = re.sub(
        r"^(?:invented?|discover(?:ed|s)?|found(?:ed|s)?|built|creat(?:ed|es?)|"
        r"wrote|written|painted?|composed?|designed?|develop(?:ed|s)?|"
        r"won|ruled|fought|signed|explored|colonized?|commanded?|"
        r"start(?:ed|s)?|end(?:ed|s)?|spark(?:ed|s)?|trigger(?:ed|s)?|stop(?:ped|s)?|"
        r"caus(?:ed|es?)|brought\s+about|coined|named|"
        # "what affects/determines/produces/controls/influences/allows X" → X
        r"affect(?:ed|s)?|determine[sd]?|produce[sd]?|control[sd]?|influence[sd]?|allow[sd]?)\s+",
        "", text, flags=re.I,
    )
    # "who was the first person to walk on the moon" → after QW strip:
    # "the first person to walk on the moon" → strip "the first NOUN to VERB [prep] [the]" → "moon"
    # "who was the first woman to win the nobel prize" → "nobel prize"
    text = re.sub(
        r"^(?:the\s+)?first\s+\w+(?:\s+\w+)?\s+to\s+\w+\s+(?:(?:on|in|at|from)\s+(?:the\s+)?|the\s+|a\s+)",
        "", text, flags=re.I,
    )
    # Imperative enumeration: "list the planets" / "name the types of X"
    # Also handle "give me examples of X" / "show me some types of X",
    # "tell me about different types of X", "explain X", "describe X".
    text = re.sub(
        r"^(?:name|list|give(?:\s+me)?|show(?:\s+me)?|"
        r"tell(?:\s+me)?(?:\s+about)?|explain|describe|discuss|define|compare)"
        r"\s+(?:(?:the|all|some|any|different|a few|various)\s+)?",
        "", text, flags=re.I,
    )
    # "give me information about X" → after "give me " stripped, "information about X" remains
    text = re.sub(r"^information\s+about\s+", "", text, flags=re.I)
    # After the imperative strip, a question word may be newly exposed:
    # "explain how X Y" → strip "explain " → "how X Y" → re-strip "how " → "X Y"
    text = re.sub(
        r"^(?:why|what|how|who|when|where)\s+"
        r"(?:(?:many|much|long|far|old|often|fast|deep|wide|tall|large|small|high|low|"
        r"big|huge|tiny|heavy|hot|cold|strong|hard|dense|loud|quiet|thick|thin|bright|dark|"
        r"year|century|decade|date|ago)\b|\w+ly)?\s*"
        r"(?:is|are|was|were|has|have|had|does|do|did|can|could|would|should|caus(?:ing|e[ds]?)|makes?|happens?)?\s*",
        "", text, flags=re.I,
    )
    text = re.sub(r"^not\s+", "", text, flags=re.I)
    # Bare yes/no or modal opener: "do humans have tails" → "humans have tails",
    # "can fish drown" → "fish drown", "is the earth flat" → "earth flat",
    # "will the sun explode" → "the sun explode" → "sun explode".
    text = re.sub(r"^(?:is|are|was|were|does|do|did|can|could|would|should|will)\s+(?:a\s+|an\s+|the\s+)?", "", text, flags=re.I)
    # "which planet is closest to the sun" → "planet"; "which country has the largest population" → "country"
    _m_which = re.match(r"^which\s+(.+?)\s+(?:is|are|was|were|has|have|had|does|do|did)\b", text, re.I)
    if _m_which:
        text = _m_which.group(1)
    # After "how long" is stripped, "ago" sometimes leads: "how long ago did X Y"
    # → "ago did X Y". Strip "ago" plus any following auxiliary in one shot so the
    # bare-opener strip doesn't need to run twice.
    text = re.sub(r"^ago\s+(?:did|does|was|were|has|have|had|do)?\s*", "", text, flags=re.I)
    # Leading bare quantifier/qualifier left after stripping "what are":
    # "what are some programming languages" → "some programming languages" →
    # strip "some " → "programming languages".
    # Also handles "what are all the planets" → "all the planets" → "the planets" → "planets".
    # "what are the different blood types" → "different blood types" → "blood types".
    # Early article strip so numeric/qualifier strips below see past "the/a/an".
    # "the 3 states of matter" → "3 states of matter"; "the main X" → "main X".
    # The end-of-function strip is kept as a second pass for subjects that arrive
    # there via different code paths.
    text = re.sub(r"^(?:the|a|an)\s+", "", text, flags=re.I)
    # "coined the term photosynthesis" → after "coined " stripped → "the term photosynthesis"
    # → article strip → "term photosynthesis" → strip "term " → "photosynthesis"
    # Guard against "term for X" / "term of X" (prepositions = different pattern).
    text = re.sub(r"^(?:term|word|phrase)\s+(?!(?:for|of|is|are|was|were)\b)", "", text, flags=re.I)
    # Numeric quantifier: "3 states of matter" → "states of matter" → "matter";
    # "4 blood types" → "blood types". Also strips named quantifiers left after
    # stripping "what are".
    text = re.sub(r"^(?:some|any|various|several|a few|all|different|main|major|key|\d+)\s+", "", text, flags=re.I)
    # "difference between X and Y" / "similarity between X and Y" → "X and Y"
    text = re.sub(
        r"^(?:the\s+)?(?:difference|differences|distinction|similarity|similarities|"
        r"relationship|connection|comparison)\s+between\s+(?:the\s+)?",
        "", text, flags=re.I,
    )
    _before_scaffold_strip = text
    text = re.sub(
        # Allow up to two leading article/quantifier/modifier words:
        # "the different types of X", "long term effects of X", "health benefits of X"
        r"^(?:(?:a|an|the|some|any|all|various|different|main|major|key|primary|common|"
        r"long|short|term|health|mental|physical|environmental|economic|social|cultural|"
        r"potential|possible|adverse|negative|positive|general|overall|known|a few)\s+){0,3}"
        r"(?:types?|kinds?|sorts?|categories|examples?|forms?|states?|layers?|"
        r"components?|parts?|members?|sections?|elements?|"
        r"stages?|phases?|steps?|organs?|branches?|list|"
        # Overview/summary nouns: "give me an overview of X", "give me a summary of X"
        r"overview|summary|summaries|introduction|definition|explanation|description|"
        # Medical/descriptive noun scaffolding: "what are the symptoms of X" → "X"
        r"symptoms?|signs?|benefits?|causes?|effects?|features?|"
        r"properties|characteristics|risks?|advantages?|disadvantages?|uses?|"
        # Plural only: singular "law of X", "rule of X", "principle of X" etc. may be topic titles
        r"laws|rules|principles|theories|concepts|aspects|applications|facts)"
        r"\s+of\s+", "", text, flags=re.I
    )
    # When scaffold strip fired, trailing "on/in <context>" is scaffolding too:
    # "effects of caffeine on sleep" → "caffeine on sleep" → strip "on sleep"
    if text != _before_scaffold_strip:
        text = re.sub(r"\s+(?:in|on)\s+\w+(?:\s+\w+){0,2}\s*$", "", text, flags=re.I)
    _before_causal_noun_strip = text
    text = re.sub(
        # Accept an optional adjective ("main", "primary", "key") between
        # "the" and the noun: "the main cause of X" → "cause of X" → "X"
        r"^(?:the\s+)?(?:\w+\s+)?(?:cause|process|mechanism|effect|result|purpose|"
        r"role|function|impact|consequence|"
        # Historical/event nouns: "fall of the roman empire" → "roman empire"
        r"fall|collapse|rise|decline|end|defeat|death|birth|founding|"
        # Factual property nouns: "capital of france" → "france"
        r"capital|population|area|size|location|height|depth|width|length|"
        r"diameter|radius|circumference|velocity|acceleration|frequency|wavelength|pressure|charge|voltage|"
        r"distance|temperature|density|mass|weight|volume|age|name|"
        # Role/title nouns: "president of france" → "france"
        r"president|prime\s+minister|king|queen|ruler|leader|founder|director|"
        r"inventor|discoverer|author|composer|painter|creator|"
        r"history|future|meaning|definition|significance|importance|symbol|flag|currency|language|"
        # Measurement/property compounds: "boiling point of water" → "water"
        # "half life of carbon 14" → "carbon 14"
        r"point|rate|level|amount|number|count|percentage|quantity|fraction|proportion|"
        r"formula|structure|composition|"
        r"life|lifetime|lifespan|period|span|half.life)s?"
        r"\s+(?:of|behind|in|for)\s+", "", text, flags=re.I,
    )
    # When the causal-noun strip fired, a trailing "in/on <context>" phrase
    # is scaffolding (e.g. "role of chlorophyll in photosynthesis" → "chlorophyll"),
    # not part of the subject.  Guard on text-change so this strip only fires when
    # "role of" / "function of" etc. was just removed — not on bare phrases like
    # "planets in the solar system" where "in the solar system" belongs.
    if text != _before_causal_noun_strip:
        text = re.sub(r"\s+(?:in|on)\s+\w+(?:\s+\w+){0,2}\s*$", "", text, flags=re.I)
        # "percentage of the earth is water" → strip copula predicate after causal noun removed
        text = re.sub(r"\s+(?:is|are|was|were)\s+\w+\s*$", "", text, flags=re.I)
    # "speed of a cheetah" → "cheetah", "speed of the internet" → "internet",
    # but "speed of light" / "speed of sound" stay intact (no article = canonical constant).
    text = re.sub(r"^speed\s+of\s+(?:a|an|the)\s+", "", text, flags=re.I)
    # Leading temporal/locative/conditional conjunction left over after stripping
    # "what happens during/when/if X" → strip the conjunction.
    text = re.sub(r"^(?:during|when|if)\s+", "", text, flags=re.I)
    # "when you mix baking soda and vinegar" → strip "when " → "you mix baking soda ..."
    # → strip "you VERB " (generic pronoun + one verb) → "baking soda and vinegar".
    text = re.sub(r"^(?:you|we|they|people|someone|a\s+person)\s+\w+\s+", "", text, flags=re.I)
    # "what leads to X", "what led to X", "what triggers X" → X
    text = re.sub(
        r"^(?:leads?|led|trigger[sd]?|drove|drives?|prompts?)\s+(?:to\s+)?",
        "", text, flags=re.I,
    )
    # "what role does insulin play in the body" → after "what" stripped → "role does insulin play"
    # strip "role does ARTICLE?" leaving "insulin play" → "play" removed by trailing verb strip.
    text = re.sub(
        r"^(?:role|part|function|effect|impact|influence|language)\s+(?:does|do|did)\s+(?:the\s+|a\s+|an\s+)?",
        "", text, flags=re.I,
    )
    # Second-pass people/pronoun strip: fires after "language does/do" exposed a
    # "people in X VERB" construction. E.g. "what language do people in brazil speak"
    # → "language do " stripped → "people in brazil speak" → strip "people in " → "brazil speak"
    text = re.sub(r"^(?:you|we|they|people|someone|a\s+person)\s+\w+\s+", "", text, flags=re.I)
    # "what happens to X when/if it VERBS" → strip leading "to " → "X when it VERBS"
    # then strip trailing "when/if it VERB" clause.
    text = re.sub(r"^to\s+", "", text, flags=re.I)
    text = re.sub(r"\s+(?:when|if|once)\s+(?:it|they|you|we)\s+\w+\s*$", "", text, flags=re.I)
    # After "led to" is stripped, "the fall of the Roman Empire" remains.
    # Strip the event noun (fall/collapse/etc.) and its "of" connector so only
    # the core entity remains.  This is a second pass that can't be folded into
    # the earlier causal-noun strip because that fires before the led-to strip.
    text = re.sub(
        r"^(?:the\s+)?(?:fall|collapse|rise|decline|end|defeat|death|birth|"
        r"founding|discovery|invention|establishment|creation|formation|"
        r"extinction|expansion|adoption|rejection|abolition|unification|"
        r"start|beginning|victory|loss|destruction|liberation|emergence|"
        r"spread|growth|development)\s+of\s+(?:the\s+)?",
        "", text, flags=re.I,
    )
    # Causal verbs that head the remainder after stripping "what":
    # "what enables X" → "enables X" → "X"
    # "what would happen if X" → "happen if X" → strip "happen " → "if X" → strip "if " → "X"
    text = re.sub(
        r"^(?:enables?|allows?|permits?|prevents?|blocks?|stops?|inhibits?|"
        r"happen[s]?|caus(?:es?|ing))\s+",
        "", text, flags=re.I,
    )
    # Second-pass conjunction strip: "if X" exposed after "happen" or "leads to" was removed.
    text = re.sub(r"^(?:if|during|when)\s+", "", text, flags=re.I)
    # "what is responsible for X" → "responsible for X" → "X"
    # "what is needed for X" → "needed for X" → "X"
    # "what is behind X" → "behind X" → "X"
    text = re.sub(
        r"^(?:responsible|needed|required|necessary)\s+for\s+",
        "", text, flags=re.I,
    )
    text = re.sub(r"^behind\s+", "", text, flags=re.I)
    # "what elements are in water" → after "what " is stripped → "elements are in water"
    # → look up "water" (the container), not "elements" (the thing counted).
    # Guard: skip for "how many" count questions (e.g. "how many planets are in
    # the solar system") where the counted noun IS the desired lookup subject.
    _is_how_many = bool(re.match(r"^\s*(?:and |but |so )?how\s+many\b", _original, re.I))
    if not _is_how_many:
        _m = re.match(
            r"^(\w+(?:\s+\w+){0,2})\s+(?:are|were|is|was)\s+(?:in|inside|within|found in|part of)\s+(.+)$",
            text, re.I,
        )
        if _m:
            text = _m.group(2)
    # "what temperature does water boil" → "temperature does water boil" → "water boil"
    # → trailing verb strip removes "boil" → "water".
    # Catches any "MEASUREMENT does/do/did ENTITY VERB" form.
    _m_prop_does = re.match(
        r"^(?:temperature|speed|rate|pressure|altitude|depth|angle|"
        r"frequency|voltage|force|power|amount|level|distance|"
        r"calories?|grams?|kilograms?|pounds?|kilometers?|miles?|meters?|"
        r"liters?|gallons?|watts?|volts?|dollars?|hours?|days?|months?)\s+"
        r"(?:does|do|did)\s+(.+)$",
        text, re.I,
    )
    if _m_prop_does:
        text = _m_prop_does.group(1)
    # "what type of animal is a whale" → scaffold strip removes "type of" → "animal is a whale"
    # → "CATEGORY is/was X" → X.  "animal|plant|element|mineral|metal|country|..." are category nouns
    # that head this pattern after the scaffold strip fires.
    _m_cat_is = re.match(
        r"^(?:animal|plant|mammal|reptile|bird|fish|insect|element|mineral|metal|"
        r"substance|compound|molecule|chemical|gas|liquid|solid|energy|"
        r"country|city|continent|region|language|sport|food|drug|disease|"
        r"rock|mineral|gem|star|planet|galaxy|force|wave|particle|radiation|"
        r"nationality|genre|type|color|colour|shape|material|occupation|religion)\s+(?:is|was|are|were)\s+(?:a\s+|an\s+|the\s+)?(.+)$",
        text, re.I,
    )
    if _m_cat_is:
        _cat_captured = _m_cat_is.group(1)
        # Don't fire for "country is X in/on/at" — that's handled by _m_loc_noun later.
        # Don't fire when the capture is a predicate adjective phrase ("element is most abundant"):
        # group(1) would be "most abundant on earth", not a noun.
        if (not re.search(r"\s+(?:in|on|at)\s*$", _cat_captured, re.I)
                and not re.match(r"^(?:most|least|very|quite|so|more|less|too)\b", _cat_captured, re.I)):
            text = _cat_captured
    # "what does it mean when X VERB" → X  (physiological/behavioral signal questions)
    # e.g. "it mean when your heart races" → "heart"
    _m_mean_when = re.match(
        r"^it\s+means?\s+when\s+(?:your\s+|the\s+|a\s+|an\s+)?(.+?)\s+\w+\s*$", text, re.I
    )
    if _m_mean_when:
        text = _m_mean_when.group(1)
    # "how long does it take to boil water" → "water";
    # "how long does it take for a bone to heal" → "bone";
    # "how long does it take light to reach earth" → "light".
    _m_it_takes = re.match(r"^it\s+takes?\s+to\s+\w+\s+(.+)$", text, re.I)
    if _m_it_takes:
        text = _m_it_takes.group(1)
        # "to fly to the moon" → captures "to the moon"; strip leading "to [article]"
        text = re.sub(r"^to\s+(?:the\s+|a\s+|an\s+)?", "", text, flags=re.I)
    else:
        _m_it_takes_for = re.match(r"^it\s+takes?\s+for\s+(?:a|an|the\s+)?\s*(.+?)\s+to\s+\w+\s*$", text, re.I)
        if _m_it_takes_for:
            text = _m_it_takes_for.group(1)
        else:
            # "it take light to reach earth" → capture NOUN before "to VERB"
            _m_it_takes_subj = re.match(r"^it\s+takes?\s+(.+?)\s+to\s+\w+", text, re.I)
            if _m_it_takes_subj:
                text = _m_it_takes_subj.group(1)
    # "why do we dream" / "why do people yawn" → extract the activity, not the pronoun.
    # Restricted to pure generic pronouns (we/us/you/one/people) so that entity nouns
    # like "humans" fall through to the trailing-verb strip instead ("where did humans
    # originate" → verb strip removes "originate" → "humans").
    # Must fire BEFORE the trailing-verb strip, which would remove the verb first.
    _m_we = re.match(r"^(?:we|us|you|one|people)\s+(\w+)\s*$", text, re.I)
    if _m_we:
        text = _m_we.group(1)
    # "distance from X to Y" → X  (must fire before "to <verb>" strip below)
    _m_dist_from = re.match(r"^distance\s+from\s+(?:the\s+|a\s+)?(.+?)\s+to\b", text, re.I)
    if _m_dist_from:
        text = _m_dist_from.group(1)
    # "the temperature to rise" → strip "to <verb>" infinitive phrase at end
    text = re.sub(r"\s+to\s+\w+(?:ing)?\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+work[s]?\s*$", "", text, flags=re.I)
    # "what does caffeine do to the brain" → QW strip → "caffeine do to the brain"
    # Strip "do to [article] NOUN[S]" tail → "caffeine"
    text = re.sub(r"\s+do\s+to\s+(?:(?:the|a|an|your|our|your)\s+)?\w+(?:\s+\w+)?\s*$", "", text, flags=re.I)
    # "X does/do/did Y have" → X  (e.g. "how many moons does Jupiter have" → "moons")
    text = re.sub(r"\s+(?:does|do|did)\s+\w+(?:\s+\w+)?\s+have\s*$", "", text, flags=re.I)
    # "X are there [in Y]" → X  (e.g. "what kinds of algae are there" → "algae",
    # "what kinds of planets are there in the solar system" → "planets")
    # Also "X are in/on/at Y" (e.g. "how many planets are in the solar system" → "planets")
    text = re.sub(r"\s+are\s+(?:there\b|in\b|on\b|at\b).*$", "", text, flags=re.I)
    text = re.sub(
        r"\s+(?:need|needs|require|requires|use[sd]?|produce[sd]?|"
        r"happen(?:ed|s)?|occur(?:red|s)?|exist(?:ed|s)?|"
        r"made|created|formed|produced|prevented|caused|built|done|founded|"
        r"get\s+\w+ed|become|start|begin|"
        # Action verbs trailing the subject in "how do/does X [verb]" patterns
        r"form[s]?|make[s]?|replicate[s]?|train[s]?|take[s]?|"
        r"pump[s]?|process(?:es)?|connect[s]?|"
        r"filter[s]?|flow[s]?|carry|carries|digest[s]?|regulate[s]?|"
        r"detoxif(?:y|ies)?|exchange[s]?|ferment[s]?|attract[s]?|pull[s]?|"
        r"erupt[s]?|eat[s]?|feed[s]?|hunt[s]?|drink[s]?|mix(?:es)?|"
        r"come[s]?\s+from|get[s]?|navigate[sd]?|find[s]?|"
        r"purr[s]?|bark[s]?|meow[s]?|howl[s]?|chirp[s]?|sing[s]?|hum[s]?|roar[s]?|growl[s]?|"
        r"die[sd]?|dies|"
        # Sensory/cognitive/existence verbs
        r"feel[s]?|sense[s]?|think[s]?|perceive[s]?|drown[s]?|survive[sd]?|"
        r"appear[s]?|disappear(?:s|ed)?|vanish(?:es|ed)?|reproduct[s]?|reproduce[sd]?|"
        r"behave[sd]?|communicate[sd]?|"
        r"have\b|has\b|be\b|become[s]?|"
        r"grow[s]?|spread[s]?|evolve[s]?|"
        r"emit[s]?|absorb[s]?|reflect[s]?|refract[s]?|"
        # Causal/enabling verbs: "why don't vaccines cause autism" → "vaccines"
        r"cause[sd]?|enable[sd]?|allow[s]?|prevent[s]?|"
        # Electrical/physical process verbs: "how does water conduct electricity"
        r"conduct[s]?|generate[sd]?|transmit(?:ted|s)?|convert[s]?|transfer[s]?|"
        r"store[sd]?|release[sd]?|react[s]?|"
        # Immune/conflict/process verbs: "how does X fight Y", "how does X affect Y"
        r"fight[s]?|attack[s]?|defend[s]?|protect[s]?|affect[s]?|impact[s]?|"
        # Physical / chemical state-change verbs: "why does ice float", "what makes iron rust"
        r"float[s]?|sink[s]?|rust[s]?|boil[s]?|melt[s]?|freeze[sd]?|evaporate[sd]?|"
        r"condense[sd]?|expand[s]?|contract[s]?|ignite[sd]?|dissolve[sd]?|"
        # Migration / movement verbs: "how do birds migrate"
        r"migrate[sd]?|"
        # Passive attribution: "when was X invented", "where was Y discovered/located/born/found"
        r"invent(?:ed|s)?|discover(?:ed|s)?|develop(?:ed|s)?|design(?:ed|s)?|locat(?:ed|es)?|born|found\b|"
        # Assistance verbs: "how does sleep help the brain"
        r"help[s]?|assist[s]?|support[s]?|"
        # Comparison verbs: "how does X differ from Y" / "how does X compare to Y" → "X"
        r"differ[sd]?|compare[sd]?|"
        # Role verb: "what role does insulin play in the body" → after leading strip → "play"
        r"play(?:s|ed)?|"
        # Origin verb: "where did humans originate"
        r"originate[sd]?|"
        # Intransitive motion/perception/existence verbs: "why do stars twinkle",
        # "how fast does light travel", "why do we dream", "how does sound travel"
        r"twinkle[sd]?|travel[s]?|dream[s]?|sleep[s]?|yawn[s]?|learn[s]?|"
        r"mutate[sd]?|neutralize[sd]?|"
        r"swim[s]?|fly|flies|walk[s]?|run[s]?|jump[s]?|crawl[s]?|wag[s]?|beach(?:es|ed)?|speak[s]?|talk[s]?|colonize[sd]?|know[s]?|hold[s]?|go(?:es)?|come[s]?|"
        r"smell[s]?|taste[s]?|see[s]?|hear[s]?|sense[s]?|read[s]?|writ(?:e[s]?|ten)|coexist[s]?|"
        # Passive-participle verbs: "how is blood pressure measured" → "blood pressure"
        r"measure[sd]?|classif(?:ied|y|ies)?|call(?:ed|s)?|rank(?:ed|s)?|rate[sd]?|"
        r"turn[s]?|transform[sd]?|"
        r"shine[sd]?|glow[s]?|burn[s]?|move[sd]?|"
        r"orbit[s]?|revolve[sd]?|rotate[sd]?|spin[s]?|live[sd]?|breathe[sd]?|"
        r"stop(?:ped|s)?|end[s]?|explode[sd]?|collapse[sd]?(?!\s+of)|crash(?:es|ed)?|"
        r"cover(?:ed|s)?|surround(?:ed|s)?|fill(?:ed|s)?|consist[s]?|look[s]?|"
        # Duration/persistence verbs: "how long does pregnancy last" → "pregnancy"
        r"last[s]?|persist[s]?|remain[s]?|"
        # Extinction/movement verbs. Use negative lookahead (?!\s+of) so that
        # noun forms like "the fall of X" and "the collapse of Y" are preserved —
        # only the trailing verb use ("how did Rome fall") should be stripped.
        r"go\s+extinct|fall[s]?(?!\s+of)|collapse[sd]?(?!\s+of)|rise[sd]?(?!\s+of)"
        r")\b.*$",
        "", text, flags=re.I,
    )
    # "how does mitosis differ from meiosis" → verb strip removes "differ" (and "from meiosis"
    # via .*). "how is a virus different from a bacterium" — "different from" is not a verb,
    # strip it explicitly.
    text = re.sub(r"\s+different\s+from\s+.*$", "", text, flags=re.I)
    # "is the sun larger than the earth" → bare opener strips "is the" → "sun larger than the earth"
    # strip comparative adj + "than ..." tail → "sun"
    text = re.sub(
        r"\s+(?:larger|bigger|smaller|faster|slower|older|younger|higher|lower|heavier|lighter|"
        r"hotter|colder|brighter|darker|stronger|weaker|closer|farther|nearer|wider|narrower|"
        r"longer|shorter|deeper|shallower|thicker|thinner|louder|quieter|denser|rarer|"
        r"more|less)\s+(?:than\b|from\b).*$",
        "", text, flags=re.I,
    )
    # "sharks warm blooded" → strip compound blood-type adjectives
    text = re.sub(r"\s+(?:warm|cold|hot).?blooded\s*$", "", text, flags=re.I)
    # "birds to" (after "fly" was verb-stripped from "birds to fly") → "birds"
    text = re.sub(r"\s+to\s*$", "", text, flags=re.I)
    # "stress related to heart disease" → "stress"  (predicate adj + prepositional tail)
    text = re.sub(r"\s+related\s+to\b.*$", "", text, flags=re.I)
    # "virus the same as bacteria" → "virus"
    text = re.sub(r"\s+the\s+same\s+as\b.*$", "", text, flags=re.I)
    # "viruses and bacteria the same" → "viruses and bacteria"
    text = re.sub(r"\s+the\s+same\s*$", "", text, flags=re.I)
    # "dolphin a type of fish" → "dolphin"
    text = re.sub(r"\s+(?:a|an)\s+(?:type|kind|sort|form|example)\s+of\b.*$", "", text, flags=re.I)
    # "great wall of china called that" → "great wall of china"
    text = re.sub(r"\s+called\s+(?:that|it|so|this)\s*$", "", text, flags=re.I)
    # "einstein known for" → "einstein"
    text = re.sub(r"\s+known\s+for\b.*$", "", text, flags=re.I)
    # "eiffel tower named after" / "moon named after gustave eiffel" → "eiffel tower" / "moon"
    text = re.sub(r"\s+named\s+(?:after|for)\b.*$", "", text, flags=re.I)
    # "superman's real name" → "superman"  (possessive owner + generic attribute noun tail)
    text = re.sub(
        r"'s\s+(?:real\s+|secret\s+|true\s+|original\s+|actual\s+|full\s+|official\s+)?(?:name|age|"
        r"height|weight|birthday|birthdate|birthplace|nationality|occupation|job|career|"
        r"role|story|biography|background|origin|power|ability|weakness|identity|personality)\s*$",
        "", text, flags=re.I,
    )
    # "what if humans could photosynthesize" → after "what if" stripped, "humans could
    # photosynthesize". Trailing modal+verb: strip "could/would/can/might VERB" at end.
    text = re.sub(
        r"\s+(?:could|would|can|might|may|will|should)\s+\w+\s*$",
        "", text, flags=re.I,
    )
    # "how much water should you drink" → "water should you drink" →
    # strip the modal + generic pronoun/article+noun + verb tail → "water".
    # Also handles "sleep does a person need" → "sleep".
    text = re.sub(
        r"\s+(?:should|must|can|could|would|may|might|do|does|did)\s+"
        r"(?:(?:a|an)\s+\w+|you|we|one|people|someone|i|they|he|she)\s+\w+\s*$",
        "", text, flags=re.I,
    )
    # "is pluto a planet" → bare opener → "pluto a planet" → strip trailing "a/an NOUN" → "pluto".
    # "sleep does a person need" → verb strip → "sleep does a person" → strip "a person" → "sleep does"
    # → secondary strips below finish it off.
    # Guard: don't strip when result would end with bare "and" (e.g. "virus and a bacteria" → keep as-is)
    _before_an_strip = text
    text = re.sub(r"\s+(?:a|an)\s+\w+\s*$", "", text, flags=re.I)
    if re.search(r"\s+and\s*$", text, re.I):
        text = _before_an_strip
    # "water a good solvent" (after "what makes water" QW strip) → "water"
    # Only fire when the entire text is exactly ONE_WORD + "a/an ADJ NOUN" (4 tokens).
    # Guards against "I fix a leaky faucet" (5 tokens) which must stay intact.
    text = re.sub(r"^\s*(\w+)\s+(?:a|an)\s+\w+\s+\w+\s*$", r"\1", text, flags=re.I)
    # Secondary cleanup for residual "modal PRONOUN" (verb already stripped by main verb block):
    # "water should you" (drink was stripped) → "water".
    text = re.sub(
        r"\s+(?:should|must|can|could|would|may|might|do|does|did)\s+"
        r"(?:you|we|one|people|someone|i|they|he|she)\s*$",
        "", text, flags=re.I,
    )
    # Bare trailing auxiliary: "sleep does" → "sleep".
    text = re.sub(r"\s+(?:does|did|do|can|could|should|would|has|had|have)\s*$", "", text, flags=re.I)
    # "protein does the body" / "vitamins does the body" → "protein" / "vitamins"
    # (verb stripped by main block, but "does/do/did the/a/an NOUN" residue remains)
    text = re.sub(
        r"\s+(?:does|do|did|can|will|would|should|must)\s+(?:the|a|an)\s+\w+\s*$",
        "", text, flags=re.I,
    )
    # "bees important to the ecosystem" → "bees"  (adj with prepositional complement)
    text = re.sub(
        r"\s+(?:important|essential|critical|vital|useful|helpful|harmful|dangerous|safe|"
        r"beneficial|effective|necessary|good|bad|healthy|unhealthy)\s+(?:to|for)\b.*$",
        "", text, flags=re.I,
    )
    # "what does nasa stand for" → "nasa stand for" → strip "stand for" → "nasa"
    text = re.sub(r"\s+stands?\s+for\s*$", "", text, flags=re.I)
    # "gdp of" → "gdp"  (orphaned preposition after causal-noun strip)
    text = re.sub(r"\s+of\s*$", "", text, flags=re.I)
    # "what country/continent is X in/on" → X.
    # After "what " is stripped, text may be "country is tokyo in" etc.
    _m_loc_noun = re.match(
        r"^(?:country|city|state|province|continent|ocean|sea|river|lake|"
        r"mountain|island|planet|galaxy|star|time\s+zone|timezone)\s+(?:is|was|are|were)\s+(.+?)\s+(?:in|on|at)\s*$",
        text, re.I,
    )
    if _m_loc_noun:
        text = _m_loc_noun.group(1)
    # "X on <modifier>" → X  (e.g. "effect of gravity on time" → "gravity")
    # Only strip trailing "on <1-3 words>" — not "on" inside a topic name.
    text = re.sub(r"\s+on\s+\w+(?:\s+\w+){0,2}\s*$", "", text, flags=re.I)
    # "quantum physics in simple terms" → "quantum physics"  (explanation-register qualifier)
    text = re.sub(r"\s+in\s+(?:simple|plain|basic|easy|everyday|lay(?:man[\'s]*)?)\s+terms\s*$", "", text, flags=re.I)
    # "X in the <location>" → X  (e.g. "planets in the solar system" → "planets")
    # Require "in the" so bare "animals in water" is not affected.
    text = re.sub(r"\s+in\s+the\s+\w+(?:\s+\w+){0,2}\s*$", "", text, flags=re.I)
    # "X in <word>" → X  (e.g. "turbulence in planes" → "turbulence",
    # "pain in joints" → "pain"). Only strip a single word to avoid eating
    # compound subjects; "in the ..." is already handled above.
    text = re.sub(r"\s+in\s+(?!the\b)\w+\s*$", "", text, flags=re.I)
    # "X from <place>" → X  (e.g. "moon from earth" → "moon")
    text = re.sub(r"\s+from\s+\w+(?:\s+\w+){0,1}\s*$", "", text, flags=re.I)
    # Residual bare auxiliary after location-tail strips:
    # "insulin do in the body" → "in the body" stripped above → "insulin do" → "insulin"
    text = re.sub(r"\s+(?:do|does|did)\s*$", "", text, flags=re.I)
    # "moon at night" → "moon"  (time-of-day qualifier at tail)
    text = re.sub(
        r"\s+at\s+(?:night|day|dawn|dusk|noon|midnight|sunrise|sunset|daytime|nighttime)\s*$",
        "", text, flags=re.I,
    )
    # "oceans of the world" → "oceans", "continents of the world" → "continents".
    # Only fires when the causal-noun strip above did NOT already handle "of the X"
    # (e.g. "role of the king" → causal strip → "king" before we reach here).
    text = re.sub(r"\s+of\s+the\s+\w+(?:\s+\w+){0,1}\s*$", "", text, flags=re.I)
    # "is coffee bad for you" / "why is sleep important for life" → strip " for X" tail
    # so that trailing adj strip sees "bad"/"important" at end.
    text = re.sub(r"\s+for\s+(?:you|me|us|them|people|humans?|everyone|the\s+body|life|health|nature|society|animals?|plants?|the\s+environment|the\s+planet)\s*$", "", text, flags=re.I)
    # "element is most abundant [on earth]" → after location strip → "element is most abundant"
    # Strip superlative/intensified predicate adj: "is most/least/very ADJ" → nothing
    text = re.sub(r"\s+(?:is|are|was|were)\s+(?:most|least|very|quite|so|more|less)\s+\w+\s*$", "", text, flags=re.I)
    # Trailing state adjective in "why is X [adjective]" patterns.
    # e.g. "sky blue" → "sky", "gold so valuable" → "gold"
    text = re.sub(
        # State/property adjectives that trail a subject in "why is X [adj]" patterns.
        # Optional copula handles "blood sugar is low" as well as bare "ocean salty".
        # (?:so|most|least|very|quite) handles superlatives: "element is most abundant" → "element"
        # Exclude ambiguous words that are also common nouns (light, fast, hard, etc.).
        r"\s+(?:(?:is|are|was|were)\s+)?(?:(?:so|most|least|very|quite)\s+)?(?:blue|red|green|yellow|white|black|gray|grey|brown|orange|purple|pink|"
        r"hot|cold|warm|cool|wet|dry|soft|bright|dark|"
        r"low|high|normal|elevated|full|empty|alive|dead|active|inactive|"
        r"heavy|loud|quiet|dim|sharp|dull|"
        r"salty|sweet|sour|bitter|spicy|acidic|alkaline|toxic|magnetic|elastic|"
        r"conductive|insulating|semiconducting|superconducting|"
        r"transparent|opaque|flammable|volatile|reactive|inert|radioactive|"
        r"valuable|expensive|cheap|rare|common|strong|weak|dense|flat|round|curved|"
        r"sticky|slippery|rough|smooth|thin|thick|narrow|tall|short|"
        r"similar|different|related|connected|distinct|unique|identical|"
        r"dangerous|harmful|safe|harmless|poisonous|helpful|useful|effective|important|"
        r"good|bad|healthy|unhealthy|"
        r"hard|soft|tough|fragile|brittle|flexible|rigid|elastic|"
        # Behavioral/ecological adjectives: "why are animals nocturnal" → "animals"
        r"nocturnal|diurnal|crepuscular|aquatic|terrestrial|arboreal|"
        r"carnivorous|herbivorous|omnivorous|venomous|migratory|endangered|"
        r"solitary|social|colonial|sentient|conscious|intelligent|"
        r"renewable|organic|inorganic|synthetic|artificial|natural)\s*$",
        "", text, flags=re.I,
    )
    # Strip a trailing "not" that can remain after the negated auxiliary was
    # expanded and the verb phrase was stripped: "why does X not use Y" →
    # strips "why does " → "X not use Y" → trailing strip removes " use Y" →
    # "X not" → remove trailing " not" → "X".
    text = re.sub(r"\s+not\s*$", "", text, flags=re.I)
    # Strip a trailing bare copula: "blood sugar is" (after adj strip removed "low")
    # → "blood sugar". Only fires when nothing else could have consumed it.
    text = re.sub(r"\s+(?:is|are|was|were)\s*$", "", text, flags=re.I)
    # "what is bitcoin and how does it work" → "bitcoin and how does it" (verb strip took "work")
    # Strip second clause "and how/why/what does/do/did it VERB?" that remains.
    text = re.sub(
        r"\s+and\s+(?:how|why|what|where|when)\s+(?:does|do|did|is|are|can|could|will)\s+"
        r"(?:it|they|this|that|you)\s*\w*\s*$",
        "", text, flags=re.I,
    )
    # Strip orphaned adverbs that remain after the trailing-verb strip removed the verb:
    # "when did humans first appear" → "humans first appear" → verb strip → "humans first"
    # → strip trailing "first" → "humans".
    text = re.sub(r"\s+(?:first|last|now|still|already|yet|ever|always|never|once|again|eventually|soon|someday|sometime)\s*$", "", text, flags=re.I)
    # "leaves change color" → "leaves", "sun change seasons" → "sun".
    # Only fires when "change OBJECT" is at end of string (after location strips),
    # so "climate change" (no object) and "climate change affect X" (affect already
    # stripped by the verb list above) are not affected.
    text = re.sub(r"^(.+?)\s+change[s]?\s+\w+\s*$", r"\1", text, flags=re.I)
    # Strip a leading bare article that remains after all other strips:
    # "what is the speed of light" → after verb strip → "the speed of light" → "speed of light"
    # "how does the immune system work" → "the immune system" → "immune system"
    text = re.sub(r"^(?:the|a|an)\s+", "", text, flags=re.I)
    # Strip qualifier adjective exposed after the article: "the main programming languages"
    # → "main programming languages" → "programming languages".
    text = re.sub(r"^(?:different|main|major|key|various|multiple)\s+", "", text, flags=re.I)
    # Strip leading superlative/comparative adjective: "largest ocean" → "ocean",
    # "fastest animal" → "animal", "most common element" → "element".
    text = re.sub(
        r"^(?:largest?|biggest?|smallest?|tallest?|shortest?|longest?|fastest?|slowest?|"
        r"deepest?|widest?|narrowest?|lightest?|heaviest?|oldest?|youngest?|newest?|"
        r"most\s+\w+|least\s+\w+)\s+",
        "", text, flags=re.I,
    )
    # Bare "most/least" quantifier that superlative strip left because it had no
    # trailing content: "most wars" → "wars", "least developed" → "developed".
    # Fires after the superlative strip so "most common element" is already "element".
    text = re.sub(r"^(?:most|least)\s+", "", text, flags=re.I)
    return text.strip(" ?.,")



# -- sentence selection ----------------------------------------------------

_CAUSAL_MARKER = re.compile(
    r"\b(?:because|since|due to|owing to|as a result|therefore|thus|hence|"
    r"which causes|causes|caused by|results? in|results? from|so that|"
    r"in order to|allows?|enables?|requires?|depends? on|"
    r"leads? to|lead to|led to|stems? from|triggers?|"
    r"consequently|as a consequence|contribute[sd]? to)\b",
    re.I,
)
_ENUM_MARKER = re.compile(
    r"\b(?:include[sd]?|including|such as|categor(?:y|ies|ised|ized)|"
    r"classified|types?|kinds?|forms?|divided into|consists? of|"
    r"comprises?|namely|for example|e\.g\.|the following|there are)\b",
    re.I,
)


#: A sentence opening on a referring pronoun is still about the entry's
#: subject -- "It requires light because chlorophyll absorbs photons" is the
#: explanation, and demanding the literal topic word would discard it.
_REFERRING = re.compile(r"^\s*(?:it|its|they|their|these|those|this|such)\b", re.I)


#: Vocabulary of naming and branding: a sentence about what something is
#: *called*, not about why it behaves as it does.
_NAMING = re.compile(
    r"\b(known as|named after|nicknamed?|nickname|adopted|jersey|kit|strip|"
    r"logo|branding|abbreviated|refers to the name|so-called|dubbed)\b",
    re.I,
)


def _explanatory_score(sentence: str) -> int:
    """How much a sentence reads like an explanation rather than trivia.

    Used only as a tie-break, and only matters when the question offers no
    focus term to rank by -- at which point the previous scoring collapsed to
    document order and the first candidate entry always won.
    """
    score = 0

    # Proper nouns after the first word: the signature of naming trivia.
    propers = [
        word
        for index, word in enumerate(sentence.split())
        if index > 0 and word[:1].isupper() and not word.isupper()
    ]
    score -= min(len(propers), 6)

    if _NAMING.search(sentence):
        score -= 4

    # Four-digit years are almost always historical or sporting detail.
    score -= min(len(re.findall(r"\b(1[89]|20)\d{2}\b", sentence)), 3)

    return score


def _pick(sentences, marker, topic_words, limit, min_len=40, focus=None,
          bonus=None):
    """Sentences matching ``marker``, best first.

    The entry has already been selected as being about the subject, so a
    sentence that refers back with a pronoun counts. Requiring the literal
    topic word in every sentence threw away most real explanations, which are
    written exactly that way.

    ``focus`` is what the question asked *about* the subject -- the "light" in
    "why does photosynthesis need light". Ranking by it is what separates the
    sentence that answers the question from the merely-causal ones elsewhere
    in the article: without it, that question came back with bacterial
    membranes and leaf epidermis, both genuinely causal and neither an answer.

    ``bonus`` is an optional compiled regex; sentences matching it receive +2
    extra focus hits. Use it to reward sentences that directly answer the
    question -- e.g. "causes gravity" for "what causes gravity?" -- above those
    that merely contain the same causal marker.
    """
    focus = focus or set()
    scored = []
    for position, sentence in enumerate(sentences):
        if len(sentence) < min_len:
            continue
        if not marker.search(sentence):
            continue
        lowered = sentence.lower()
        tokens = set(re.findall(r"[a-z0-9]+", lowered))
        on_topic = (
            not topic_words
            or bool(topic_words & tokens)
            or _REFERRING.match(sentence)
        )
        if not on_topic:
            continue
        hits = sum(1 for word in focus if word in tokens)
        if bonus and bonus.search(sentence):
            hits += 2
        # Focus hits dominate. Explanatory quality only breaks ties -- but it
        # is the whole ranking when the question has no focus term, which is
        # when this previously degenerated to document order.
        # Earlier sentences win remaining ties: encyclopedia articles put the
        # load-bearing explanation near the top.
        scored.append((-hits, -_explanatory_score(sentence), position, sentence))

    scored.sort()
    # If anything actually addressed the question, do not dilute it with
    # sentences that merely contain a causal marker.
    if focus and scored and scored[0][0] < 0:
        scored = [row for row in scored if row[0] < 0]
    return [sentence for _hits, _quality, _pos, sentence in scored[:limit]]


#: Interrogative scaffolding and function words: present in the question but
#: carry no topical signal and must not skew focus-word scoring in _pick().
#: "and" is the most common offender — almost every English sentence contains
#: it, so leaving it in the focus set makes every sentence score one hit and
#: drowns out the words that actually matter.
_QUESTION_WORDS = {
    "what", "when", "where", "which", "why", "how", "does", "did", "do",
    "is", "are", "was", "were", "the", "types", "kinds", "sorts", "forms",
    "examples", "categories", "list", "there", "many", "much", "need",
    "needs",
    # Conjunctions that appear in multi-subject causal questions
    # ("why does X need both A and B") but contribute nothing to ranking.
    "and", "but", "nor", "yet", "both",
    # Imperative scaffolding verbs and quantifiers from enumerate questions
    # ("give me examples of X", "show me some types of X",
    #  "name the different types of X", "list some examples of X").
    # These words carry no topical signal about the subject domain.
    "give", "show", "name", "different", "some", "me", "of", "a", "an",
    "all", "any", "few",
}


_TOPIC_STOPWORDS = frozenset({
    "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is",
    "it", "me", "my", "no", "of", "on", "or", "so", "to", "up", "us", "we",
    # Definite/indefinite articles: "the temperature" and "temperature" must
    # produce the same topic words, otherwise "the" creates false overlaps
    # when candidate-entry titles start with "The" (e.g. "The Internet").
    "the",
    # Common conjunctions (3+ chars) not caught by the 2-char filter above.
    # Without these, subject_of("X and Y") keeps "and" in topic_words and
    # the on-topic check in _pick() fires on every sentence (all contain "and").
    "and", "but", "nor", "for", "yet",
})


def _topic_words(text: str) -> set:
    return {
        w for w in re.split(r"[^a-z0-9]+", (text or "").lower())
        if len(w) > 1 and w not in _TOPIC_STOPWORDS
    }


# -- the reasoner ----------------------------------------------------------

class Reasoner:
    """Answers questions that need more than one lookup.

    ``knowledge`` is a KnowledgeBase; ``summarize`` and ``sentences`` are
    passed in rather than imported so this module stays free of a circular
    dependency on the dialogue engine, and so both can be stubbed in tests.
    ``search`` is an optional callable that performs web search and returns
    SearchResult objects (url, title, snippet).
    """

    def __init__(
        self,
        knowledge,
        summarize: Callable[[str, str], tuple],
        sentences: Callable[[str], list],
        relevant: Optional[Callable[[str, str, str], bool]] = None,
        search: Optional[Callable[[str, int], list[Any]]] = None,
    ) -> None:
        self.knowledge = knowledge
        self.summarize = summarize
        self.sentences = sentences
        self.relevant = relevant
        self.search = search
        self._search_cache: dict[str, None] = {}
        self._search_cache_max = 500
        self._cache_lock = threading.Lock()
        self._rng = random.Random()

    # -- web search --------------------------------------------------------

    def _add_search_to_knowledge(self, query: str, results: list) -> None:
        """Add web search results to the knowledge base.

        Formats search results as a new knowledge entry to improve future answers.
        Avoids duplicates via query deduplication.
        """
        if not self.knowledge or not results:
            return

        with self._cache_lock:
            if query in self._search_cache:
                return
            self._search_cache[query] = None
            if len(self._search_cache) > self._search_cache_max:
                for _ in range(len(self._search_cache) // 2):
                    self._search_cache.pop(next(iter(self._search_cache)))

        # Format results as a knowledge entry
        formatted_results = []
        for result in results:
            if hasattr(result, 'title') and hasattr(result, 'snippet'):
                title = result.title
                snippet = result.snippet
                url = getattr(result, 'url', '')
            elif isinstance(result, dict):
                title = result.get('title', 'Result')
                snippet = result.get('snippet', '')
                url = result.get('url', '')
            else:
                continue

            if snippet:
                formatted_results.append(f"{title}: {snippet} (source: {url})")

        if formatted_results:
            content = "\n".join(formatted_results)
            try:
                self.knowledge.add_entry(f"Web Search: {query}", content)
            except Exception:
                pass

    def _search_web(self, query: str, limit: int = 3) -> tuple[list[str], list]:
        """Perform web search and return formatted snippets with sources.

        Returns (snippets, search_results) where snippets are formatted strings
        ready to include in an answer, and search_results are the raw results
        for tracking in the reasoning trace.
        """
        if not self.search:
            return [], []

        try:
            results = self.search(query, limit)
        except Exception:
            return [], []

        # Add search results to knowledge base for future use
        self._add_search_to_knowledge(query, results)

        snippets = []
        for result in results:
            if hasattr(result, 'snippet'):
                snippet = result.snippet
            elif isinstance(result, dict):
                snippet = result.get('snippet', '')
            else:
                continue

            if snippet:
                snippet = snippet.strip()
                # Ensure each snippet ends with sentence-terminal punctuation so
                # that joining them with a space doesn't produce run-together text.
                if snippet and snippet[-1] not in ".!?":
                    snippet += "."
                snippets.append(snippet)

        return snippets, results

    # -- entry lookup ------------------------------------------------------

    def _candidate_entries(self, subject: str, limit: int = 4) -> list:
        """Entries plausibly about ``subject``, best first.

        `_best_entry` returns only the top match, which is right for a
        comparison (one entry per side) but wrong for an explanation: several
        articles can match a subject's title equally well and only one of them
        actually explains anything. Pooling lets ranking decide, rather than
        letting retrieval order decide for it.
        """
        wanted = _topic_words(subject)
        if not wanted:
            return []
        out = []
        for entry, _score in self.knowledge.query(subject, limit=8, min_score=0.2):
            if wanted & _topic_words(entry.topic):
                out.append(entry)
                if len(out) >= limit:
                    break
        return out

    def _pick_across(self, entries: list, marker, subject: str, focus: set,
                     limit: int = 3, bonus=None):
        """Rank sentences from every candidate entry together.

        Returns (sentences, entry_topics_that_contributed).
        """
        pool: list = []
        owner: dict = {}
        for entry in entries:
            for sentence in self.sentences(entry.content):
                if sentence not in owner:
                    owner[sentence] = entry.topic
                    pool.append(sentence)
        picked = _pick(pool, marker, _topic_words(subject), limit=limit,
                       focus=focus, bonus=bonus)
        used = []
        for sentence in picked:
            topic = owner.get(sentence)
            if topic and topic not in used:
                used.append(topic)
        return picked, used

    def _best_entry(self, subject: str):
        """The entry actually about ``subject``, or None."""
        wanted = _topic_words(subject)
        if not wanted:
            return None
        for entry, _score in self.knowledge.query(subject, limit=5, min_score=0.2):
            title = _topic_words(entry.topic)
            # Require real overlap: a comparison built on the wrong article is
            # worse than admitting one side is unknown.
            if wanted & title:
                return entry
        return None

    def reason(self, question: str) -> Optional[Reasoned]:
        """Answer ``question`` if it needs reasoning. ``None`` if it does not."""
        intent = classify(question)
        if intent == Intent.DEFINE:
            return None
        if intent in (Intent.COMPARE, Intent.CONTRAST):
            return self._two_subjects(question, intent)
        if intent == Intent.CAUSAL:
            return self._causal(question)
        if intent == Intent.ENUMERATE:
            return self._enumerate(question)
        return None

    # -- comparison --------------------------------------------------------

    def _two_subjects(self, question: str, intent: str) -> Optional[Reasoned]:
        subjects = split_subjects(question)
        steps = [Step("intent", f"{intent} -- needs two subjects, not one")]
        if len(subjects) != 2:
            return None
        steps.append(Step("subjects", " / ".join(subjects)))

        found, missing, definitions = [], [], []
        for subject in subjects:
            entry = self._best_entry(subject)
            if entry is None:
                missing.append(subject)
                steps.append(Step("lookup", f"{subject}: nothing on file"))
                continue
            summary, _is_def = self.summarize(entry.content, entry.topic)
            # Take up to two lead sentences so thin one-liners get some depth.
            # If the first sentence is already long (≥100 chars) it stands alone.
            parts = [p.strip() for p in summary.split(". ") if p.strip()]
            if len(parts) >= 2 and len(parts[0]) < 100:
                first = parts[0] + ". " + parts[1]
            else:
                first = parts[0] if parts else ""
            if not first:
                missing.append(subject)
                continue
            found.append(entry.topic)
            definitions.append((entry.topic, first.rstrip(".") + "."))
            steps.append(Step("lookup", f"{subject} -> {entry.topic}"))

        # If we're missing a subject, try web search to fill the gap.
        # Iterate over a copy so we can remove from the original safely.
        if missing and self.search:
            for missing_subject in list(missing):
                search_snippets, search_results = self._search_web(missing_subject, limit=1)
                if search_snippets:
                    definitions.append((missing_subject, search_snippets[0]))
                    found.append(missing_subject)
                    steps.append(Step("web_search", f"{missing_subject} -> found {len(search_snippets)} result(s)"))
                    missing.remove(missing_subject)

        if not definitions:
            return None

        if len(definitions) == 1 and missing:
            # Honest partial answer: say which side is missing rather than
            # silently answering about one and pretending that was the ask.
            topic, definition = definitions[0]
            steps.append(Step("result", f"only one side known ({topic})"))
            return Reasoned(
                answer=(
                    f"I only know one half of that. {definition} "
                    f"I've got nothing on {missing[0]}, so I can't honestly "
                    f"compare them yet."
                ),
                intent=intent,
                steps=steps,
                entries_used=found,
            )

        if intent == Intent.COMPARE:
            joiner = self._rng.choice([
                "That's the core difference.",
                "So they're different approaches to similar territory.",
                "Different mechanisms, different trade-offs.",
            ])
        else:
            joiner = self._rng.choice([
                "That's what they have in common.",
                "So they're connected at the root.",
                "Different angles on the same idea.",
            ])
        steps.append(Step("combine", f"contrasted {len(definitions)} definitions"))
        body = " ".join(d for _, d in definitions)
        return Reasoned(
            answer=f"{body} {joiner}",
            intent=intent,
            steps=steps,
            entries_used=found,
        )

    # -- causation ---------------------------------------------------------

    def _causal(self, question: str) -> Optional[Reasoned]:
        subject = subject_of(question)
        if len(subject) < 2:
            return None
        steps = [Step("intent", "causal -- looking for explanation, not definition")]
        steps.append(Step("subject", subject))

        entries = self._candidate_entries(subject, limit=8)
        if not entries:
            # Try web search if knowledge base has nothing.
            if self.search:
                search_snippets, search_results = self._search_web(question, limit=2)
                if search_snippets:
                    steps.append(Step("lookup", f"{subject} -> web search"))
                    steps.append(Step("web_search", f"found {len(search_snippets)} result(s)"))
                    answer = " ".join(search_snippets)
                    return Reasoned(
                        answer=answer,
                        intent=Intent.CAUSAL,
                        steps=steps,
                        entries_used=[subject],
                    )
            return None
        steps.append(Step(
            "lookup",
            f"{subject} -> {', '.join(e.topic for e in entries)}",
        ))

        focus = _topic_words(question) - _topic_words(subject) - _QUESTION_WORDS
        if focus:
            steps.append(Step("focus", ", ".join(sorted(focus))))
        # For "what causes X" / "what makes X" questions, reward sentences
        # where X is in object position ("Y causes X") over sentences where X
        # is the agent ("X causes Y"). Without this, "what causes gravity"
        # picked "Black holes form when gravity causes..." over
        # "Mass causes gravity by curving spacetime..." because the Einstein
        # attribution gave the latter a proper-noun quality penalty.
        bonus = None
        _CAUSE_VERB_Q = re.compile(
            r"(?i)^(?:what|why)\s+"
            r"(?:causes?|makes?|produces?|creates?|generates?|triggers?|leads?\s+to)\s+",
        )
        if _CAUSE_VERB_Q.match(question):
            s = re.escape(subject)
            bonus = re.compile(
                # Active: "Y causes/triggers/leads to X"
                rf"\b(?:causes?|makes?|triggers?|generates?|produces?|creates?"
                rf"|leads?\s+to)\s+{s}\b"
                # Passive: "X is caused/triggered/led by Y"
                rf"|\b{s}\s+(?:is|are|was|were)\s+"
                rf"(?:caused|produced|generated|created|made|triggered|led)\s+by\b",
                re.I,
            )
        picked, used = self._pick_across(
            entries, _CAUSAL_MARKER, subject, focus, limit=3, bonus=bonus,
        )
        if not picked:
            steps.append(Step("result", "no explanatory sentences in any candidate"))
            # Try web search as fallback.
            if self.search:
                search_snippets, search_results = self._search_web(question, limit=2)
                if search_snippets:
                    steps.append(Step("web_search", f"found {len(search_snippets)} result(s)"))
                    answer = " ".join(search_snippets)
                    return Reasoned(
                        answer=answer,
                        intent=Intent.CAUSAL,
                        steps=steps,
                        entries_used=used or [subject],
                    )
            return None
        steps.append(Step(
            "select",
            f"{len(picked)} explanatory sentence(s) from {', '.join(used)}",
        ))
        return Reasoned(
            answer=" ".join(picked),
            intent=Intent.CAUSAL,
            steps=steps,
            entries_used=used,
        )

    # -- enumeration -------------------------------------------------------

    def _enumerate(self, question: str) -> Optional[Reasoned]:
        subject = subject_of(question)
        if len(subject) < 2:
            return None
        steps = [Step("intent", "enumerate -- looking for a list, not a definition")]
        steps.append(Step("subject", subject))

        entries = self._candidate_entries(subject, limit=8)
        if not entries:
            # Try web search if knowledge base has nothing.
            if self.search:
                search_snippets, search_results = self._search_web(question, limit=2)
                if search_snippets:
                    steps.append(Step("lookup", f"{subject} -> web search"))
                    steps.append(Step("web_search", f"found {len(search_snippets)} result(s)"))
                    answer = " ".join(search_snippets)
                    return Reasoned(
                        answer=answer,
                        intent=Intent.ENUMERATE,
                        steps=steps,
                        entries_used=[subject],
                    )
            return None
        steps.append(Step(
            "lookup",
            f"{subject} -> {', '.join(e.topic for e in entries)}",
        ))

        focus = _topic_words(question) - _topic_words(subject) - _QUESTION_WORDS
        picked, used = self._pick_across(
            entries, _ENUM_MARKER, subject, focus, limit=3,
        )
        if not picked:
            steps.append(Step("result", "nothing enumerating in any candidate"))
            # Try web search as fallback.
            if self.search:
                search_snippets, search_results = self._search_web(question, limit=2)
                if search_snippets:
                    steps.append(Step("web_search", f"found {len(search_snippets)} result(s)"))
                    answer = " ".join(search_snippets)
                    return Reasoned(
                        answer=answer,
                        intent=Intent.ENUMERATE,
                        steps=steps,
                        entries_used=used or [subject],
                    )
            return None
        steps.append(Step(
            "select",
            f"{len(picked)} enumerating sentence(s) from {', '.join(used)}",
        ))
        return Reasoned(
            answer=" ".join(picked),
            intent=Intent.ENUMERATE,
            steps=steps,
            entries_used=used,
        )
