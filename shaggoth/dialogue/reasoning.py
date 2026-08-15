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
    # "what is X like" / "what are X like" → X  (early-exit before location strips fire)
    _m_what_like = re.match(
        r"^(?:what|how)\s+(?:is|are|was|were)\s+(?:a\s+|an\s+|the\s+)?(.+?)\s+like\s*$",
        text, re.I,
    )
    if _m_what_like:
        captured = _m_what_like.group(1).strip()
        # "moon's surface like" → strip possessive → "moon"
        _mp = re.match(r"^(\w+(?:\s+\w+)?)'s\s+\w+(?:\s+\w+)?\s*$", captured, re.I)
        if _mp:
            captured = _mp.group(1)
        return captured
    text = re.sub(
        r"^(?:and |but |so )?(?:why|what|how|who|when|where)\s+"
        # Optional degree/temporal word after "how"/"what": "how many X", "how long does X",
        # "how fast does X", "how quickly does X" (any -ly adverb), "what year was X".
        r"(?:(?:many|much|long|far|old|often|fast|deep|wide|tall|large|small|high|low|"
        r"big|huge|tiny|heavy|hot|cold|strong|hard|dense|loud|quiet|thick|thin|bright|dark|"
        r"year|century|decade|date|ago)\b|\w+ly)?\s*"
        r"(?:is|are|was|were|has|have|had|does|do|did|can|could|would|should|caus(?:ing|e[ds]?)|makes?|happens?\b)?\s*",
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
    # "who holds the record for most home runs" → early return "home runs"
    # Must fire BEFORE the leading-verb strip; capturing the whole noun phrase here
    # prevents the trailing-verb strip from mangling compound sports nouns like "home runs".
    _m_record_for = re.match(
        r"^holds?\s+the\s+(?:world\s+|olympic\s+|national\s+|current\s+)?record\s+for\s+(?:most|fewest|least|the\s+(?:most|fewest|least)|a|an|the\s+)?\s*"
        r"(.+?)(?:\s+in\s+(?:(?:a|an|the)\s+)?\w+(?:\s+\w+)?)?\s*$",
        text, re.I,
    )
    if _m_record_for:
        return _m_record_for.group(1).strip()
    # "what happened at pearl harbor" / "what occurred in berlin" → PLACE
    # Must fire before the broad leading-verb strip so we capture the preposition+place together.
    _m_event_at = re.match(
        r"^(?:happen(?:ed|s)?|occur(?:red|s)?)\s+"
        r"(?:at|in|on|during|near)\s+(?:the\s+|a\s+|an\s+)?(.+)$",
        text, re.I,
    )
    if _m_event_at:
        text = _m_event_at.group(1)
    # After stripping "who"/"what", attribution and trigger verbs head the remainder:
    # "who invented the telephone" → "invented the telephone" → "the telephone"
    # "what started the industrial revolution" → "started the ..." → "the ..."
    # "brought about" is two words so must be listed separately.
    text = re.sub(
        r"^(?:invented?|discover(?:ed|s)?|found(?:ed|s)?|built|creat(?:ed|es?)|"
        r"wrote|written|painted?|composed?|designed?|develop(?:ed|s)?|prov(?:ed|en|es?)?|"
        r"won(?!\s+(?:the\s+)?most)|ruled|fought|signed|explored|colonized?|commanded?|"
        r"start(?:ed|s)?|end(?:ed|s)?|spark(?:ed|s)?|trigger(?:ed|s)?|stop(?:ped|s)?|"
        r"caus(?:ed|es?)|brought\s+about|coined|named|happen(?:ed|s)?|occur(?:red|s)?|"
        # Media/entertainment leading verbs: "who sang X" / "who directed X" → X
        r"sang|direct(?:ed|s)?|starred\s+in|"
        # Political/civic verbs: "who elects the president" → "president"
        r"elect(?:s|ed)?|appoint(?:s|ed)?|nominate[sd]?|impeach(?:es|ed)?|ratif(?:y|ied|ies)?|"
        # "what affects/determines/produces/controls/influences/allows X" → X
        r"affect(?:ed|s)?|determine[sd]?|produce[sd]?|control[sd]?|influence[sd]?|allow[sd]?)\s+",
        "", text, flags=re.I,
    )
    # "who sang yesterday by the beatles" → after verb strip → "yesterday by the beatles"
    # → strip trailing "by ARTIST" → "yesterday"
    # Only fire when the original was a title-attribution question (wrote/sang/directed/etc.)
    if re.search(
        r"\b(?:wrote?|written|directed?|composed?|painted?|sang|authored?|filmed?)\b",
        _original, re.I,
    ):
        text = re.sub(r"\s+by\s+(?:the\s+)?(?:\w+(?:\s+\w+){0,3})\s*$", "", text, flags=re.I)
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
    # "i want to know about X" / "i'd like to learn about X" → X
    text = re.sub(
        r"^(?:i|we)\s+(?:want|'d\s+like|would\s+like|need)\s+to\s+"
        r"(?:know|learn|understand|find\s+out|hear)\s+(?:more\s+)?(?:about\s+)?",
        "", text, flags=re.I,
    )
    # After the imperative strip, a question word may be newly exposed:
    # "explain how X Y" → strip "explain " → "how X Y" → re-strip "how " → "X Y"
    text = re.sub(
        r"^(?:why|what|how|who|when|where)\s+"
        r"(?:(?:many|much|long|far|old|often|fast|deep|wide|tall|large|small|high|low|"
        r"big|huge|tiny|heavy|hot|cold|strong|hard|dense|loud|quiet|thick|thin|bright|dark|"
        r"year|century|decade|date|ago)\b|\w+ly)?\s*"
        r"(?:is|are|was|were|has|have|had|does|do|did|can|could|would|should|caus(?:ing|e[ds]?)|makes?|happens?\b)?\s*",
        "", text, flags=re.I,
    )
    text = re.sub(r"^not\s+", "", text, flags=re.I)
    # Bare yes/no or modal opener: "do humans have tails" → "humans have tails",
    # "can fish drown" → "fish drown", "is the earth flat" → "earth flat",
    # "will the sun explode" → "the sun explode" → "sun explode".
    text = re.sub(r"^(?:is|are|was|were|does|do|did|can|could|would|should|will)\s+(?:a\s+|an\s+|the\s+)?", "", text, flags=re.I)
    # "which is the largest country in the world" → "country in the world" (then location strips clean up)
    # Handles "which is/are the SUPERLATIVE NOUN" — a different word order from _m_which below.
    _m_which_copula = re.match(
        r"^which\s+(?:is|are|was|were)\s+(?:the\s+|a\s+|an\s+)?"
        r"(?:largest?|biggest?|smallest?|tallest?|shortest?|longest?|fastest?|slowest?|"
        r"deepest?|widest?|narrowest?|lightest?|heaviest?|oldest?|youngest?|newest?|"
        r"most\s+\w+|least\s+\w+)\s+(.+)$",
        text, re.I,
    )
    if _m_which_copula:
        text = _m_which_copula.group(1)
    # "which planet is closest to the sun" → "planet"; "which country has the largest population" → "country"
    _m_which = re.match(r"^which\s+(.+?)\s+(?:is|are|was|were|has|have|had|does|do|did)\b", text, re.I)
    if _m_which:
        text = _m_which.group(1)
    # "how much of X is Y" / "how much of X are there" — after "how much" is stripped
    # by the QW strip, "of the X is Y" leads; extract X as the lookup subject.
    _m_of_fraction = re.match(
        r"^of\s+(?:the\s+|a\s+|an\s+)?(.+?)\s+(?:is|are|was|were)\s+\w[\w\s]*$",
        text, re.I,
    )
    if _m_of_fraction:
        text = _m_of_fraction.group(1)
    # "what time does X VERB" — after "what" stripped, "time does the X VERB" leads.
    # Extract X (the celestial/scheduled entity): "sun set" → "sun", "market close" → "market".
    _m_time_does = re.match(
        r"^time\s+(?:does|do|did|will|would|can|could)\s+(?:the\s+|a\s+|an\s+)?(.+?)\s+\w+\s*$",
        text, re.I,
    )
    if _m_time_does:
        _td_cap = _m_time_does.group(1)
        if re.match(r'^it\b', _td_cap, re.I):
            # "time does it take to learn piano" — dummy "it"; extract the object instead
            _m_it_to = re.match(
                r'^(?:\w+\s+){0,2}it\s+\S+\s+to\s+\w+\s+(.+)$', text, re.I
            )
            if _m_it_to:
                text = _m_it_to.group(1)
        else:
            text = _td_cap
    # "what temperature should chicken be cooked to" → after QW strip:
    # "temperature should chicken be cooked to" → "chicken"
    # Handles measurement-property questions where the property noun leads the sentence.
    _m_prop_should = re.match(
        r"^(?:temperature|speed|pressure|voltage|current|frequency|dose|level|amount|"
        r"quantity|rate|time|duration|distance|weight|size|age|height|depth|width)\s+"
        r"should\s+(?:a\s+|an\s+|the\s+)?(.+?)\s+(?:be\s+)?\w+(?:\s+\w+)?\s*$",
        text, re.I,
    )
    if _m_prop_should:
        text = _m_prop_should.group(1)
    # Targeted possessive strip — only fires for specific property patterns, NOT named
    # concepts ("alzheimer's disease", "darwin's theory") or owned entities ("earth's atmosphere").
    # Pattern A: ENTITY's [MODIFIER] MEASUREMENT_NOUN — "sun's core temperature" → "sun"
    _MEAS = (
        r"temperature|speed|velocity|acceleration|mass|weight|density|pressure|"
        r"volume|area|force|energy|power|charge|radius|diameter|circumference|"
        r"height|width|depth|breadth|length|frequency|wavelength|amplitude|"
        r"intensity|brightness|luminosity|magnitude|duration|age|distance|period|"
        r"span|rate|ratio|proportion|percentage|concentration|level|"
        r"capacity|efficiency|output|input|conductivity|viscosity|hardness|opacity"
    )
    _m_poss = re.match(
        rf"^(\w+(?:\s+\w+)?)'s\s+(?:\w+\s+)?(?:{_MEAS})s?\s*$",
        text, re.I,
    )
    if _m_poss:
        text = _m_poss.group(1)
    else:
        # Pattern B: ENTITY's RELATIONAL_NOUN in/of/for … — "bee's role in the ecosystem" → "bee"
        _m_poss_rel = re.match(
            r"^(\w+(?:\s+\w+)?)'s\s+"
            r"(?:role|function|purpose|place|position|significance|importance|"
            r"impact|effect|influence|contribution)\s+(?:in|of|for|on|at|to)\b",
            text, re.I,
        )
        if _m_poss_rel:
            text = _m_poss_rel.group(1)
        # Pattern C: possessive + abstract intellectual noun (no preposition required)
        # "plato's philosophy" → "plato", "nietzsche's worldview" → "nietzsche"
        _m_poss_abstract = re.match(
            r"^(\w+(?:\s+\w+)?)'s\s+"
            r"(?:philosophy|theory|doctrine|ideology|teaching|belief|"
            r"worldview|outlook|approach|opinion|view|thought|idea|"
            r"work|writing|legacy|contribution|method|methodology|"
            r"ethics|logic|rhetoric|politics|metaphysics|epistemology)\s*$",
            text, re.I,
        )
        if _m_poss_abstract:
            text = _m_poss_abstract.group(1)
    # After "how long" is stripped, "ago" sometimes leads: "how long ago did X Y"
    # → "ago did X Y". Strip "ago" plus any following auxiliary in one shot so the
    # bare-opener strip doesn't need to run twice.
    text = re.sub(r"^ago\s+(?:did|does|was|were|has|have|had|do)?\s*", "", text, flags=re.I)
    # "the origin of X" → X — requires "the" so "origin of species" (book title)
    # is NOT affected when it arrives without an article.
    text = re.sub(r"^the\s+origin\s+of\s+(?:the\s+|a\s+|an\s+)?", "", text, flags=re.I)
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
    # \d{1,3} only: 4-digit years/titles ("1984", "2001") are topics, not quantifiers.
    # "key" is protected when it forms a compound noun (key signature, key change).
    text = re.sub(r"^(?:some|any|various|several|a few|all|different|main|major|key(?!\s+(?:signature|change))|\d{1,3}(?!\s+percent\b))\s+", "", text, flags=re.I)
    # "difference between X and Y" / "similarity between X and Y" → "X and Y"
    _before_between = text
    text = re.sub(
        r"^(?:the\s+)?(?:difference|differences|distinction|similarity|similarities|"
        r"relationship|connection|comparison)\s+between\s+(?:the\s+)?",
        "", text, flags=re.I,
    )
    if text != _before_between:
        # "brain and the mind" → "brain and mind" (strip article after "and")
        text = re.sub(r"\s+and\s+(?:the|a|an)\s+", " and ", text, flags=re.I)
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
        r"laws|rules|principles|theories|concepts|aspects|applications|facts|"
        # Religion/ideology scaffold nouns: "beliefs of buddhism" → "buddhism"
        r"beliefs?|teachings?|tenets?|practices?|doctrines?|rituals?|"
        # Ecology/nature scaffold nouns: "predators of rabbits" → "rabbits"
        r"predators?|prey|habitat|diet|behavior|behaviour|lifecycle)"
        r"\s+(?:of|about)\s+", "", text, flags=re.I
    )
    # When scaffold strip fired, trailing "on/in <context>" is scaffolding too:
    # "effects of caffeine on sleep" → "caffeine on sleep" → strip "on sleep"
    if text != _before_scaffold_strip:
        text = re.sub(r"\s+(?:in|on)\s+\w+(?:\s+\w+){0,2}\s*$", "", text, flags=re.I)
    # "movie won the oscar for best picture" → "oscar for best picture" so the causal-noun
    # strip below can further reduce to "best picture".  Covers any THING that won/received
    # a named award; the leading noun phrase (1-3 words) is stripped along with "won [the]".
    text = re.sub(
        r"^\w+(?:\s+\w+){0,2}\s+(?:won|received|earned)\s+(?:the\s+)?"
        r"(?=(?:oscar|emmy|grammy|tony|bafta|award|prize|medal|trophy|pulitzer|nobel|booker)\b)",
        "", text, flags=re.I,
    )
    _before_causal_noun_strip = text
    text = re.sub(
        # Accept an optional adjective ("main", "primary", "key") between
        # "the" and the noun: "the main cause of X" → "cause of X" → "X"
        r"^(?:the\s+)?(?:\w+\s+)?(?:cause|process|mechanism|effect|result|purpose|"
        r"role|function(?!\s+in\b)|impact|consequence|"
        # Historical/event nouns: "fall of the roman empire" → "roman empire"
        r"fall|collapse|rise|decline|end|defeat|death|birth|founding|"
        # Factual property nouns: "capital of france" → "france"
        r"capital|population|area|size|location|height|depth|width|length|"
        r"diameter|radius|circumference|velocity|acceleration|frequency|wavelength|pressure|charge|voltage|"
        r"distance|temperature|density|mass|weight|volume|age|name|time\s+zone|timezone|force|"
        # Economic/financial property nouns: "value of the us dollar" → "us dollar"
        r"value|price|cost|worth|exchange\s+rate|interest\s+rate|"
        # Role/title nouns: "president of france" → "france"
        r"president|prime\s+minister|king|queen|ruler|leader|founder|director|"
        r"inventor|discoverer|author|composer|painter|creator|"
        r"history|future|meaning(?!\s+of\s+life)|definition|classification|taxonomy|categorization|"
        r"significance|importance|symbol|flag|currency|language|"
        # Literary/art property nouns: "theme of hamlet" → "hamlet", "plot of X" → X
        # "myth of sisyphus" → "sisyphus"; "legend of king arthur" → "king arthur"
        # "holy book of islam" → "islam" (with optional adjective "holy" captured above)
        r"theme|plot|story|narrative|myth|legend|fable|tale|lore|setting|style|genre|format|book|text|scripture|"
        # Measurement/property compounds: "boiling point of water" → "water"
        # "half life of carbon 14" → "carbon 14"
        r"point|rate|level|amount|number|count|percentage|quantity|fraction|proportion|"
        r"formula|structure|composition|"
        r"life|lifetime|lifespan|period|span|half.life|"
        # Ecology/biology property nouns: "habitat of the polar bear" → "polar bear"
        r"habitat|territory|diet|range|distribution|"
        # Medical/treatment nouns: "cure for diabetes" → "diabetes"
        r"cure|treatment|remedy|therapy|medication|symptom|cause|"
        # Food/cooking property nouns: "ingredients in pizza" → "pizza"
        r"ingredient|recipe|nutrition|calorie|flavor|taste|"
        # Award/accolade nouns: "oscar for best picture" → "best picture"; "prize for X" → X
        r"oscar|emmy|grammy|tony|bafta|award|prize|nomination|"
        # Film/media production nouns: "screenplay for casablanca" → "casablanca"
        r"screenplay|script|soundtrack|"
        # Mathematical property nouns: "square root of 144" → "144"
        r"root|"
        # Sport/game property nouns: "positions in baseball" → "baseball"; "offside rule in soccer" → "soccer"
        r"rule|position|formation|ranking|standing|stat|statistic)s?"
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
    # Math calculus property nouns: "derivative of x squared" → "x squared".
    # Only fires with "of" (not "in") to avoid "derivative in math" → wrong subject.
    text = re.sub(
        r"^(?:the\s+)?(?:derivative|integral|gradient|limit|quotient|product|sum|"
        r"expansion|factorization|simplification)\s+of\s+(?:the\s+|a\s+|an\s+)?",
        "", text, flags=re.I,
    )
    # "speed of a cheetah" → "cheetah", "speed of the internet" → "internet",
    # but "speed of light" / "speed of sound" stay intact (no article = canonical constant).
    text = re.sub(r"^speed\s+of\s+(?:a|an|the)\s+", "", text, flags=re.I)
    # Economic measurement acronyms: "gdp of china" → "china", "gdp of the usa" → "usa".
    # Guard: NOT "of a/an [category]" — those are concept queries ("gdp of a country" → "gdp").
    _m_econ = re.match(
        r"^(?:gdp|gnp|gni|cpi|ppi)\s+of\s+(?!a\s|an\s|any\s)(?:the\s+)?(.+)$",
        text, re.I,
    )
    if _m_econ:
        text = _m_econ.group(1)
    # Leading temporal/locative/conditional conjunction left over after stripping
    # "what happens during/when/if X" → strip the conjunction.
    text = re.sub(r"^(?:during|when|if)\s+", "", text, flags=re.I)
    # "ice is heated" / "steel is tempered" → strip trailing copula + past participle.
    # Fires after the "when" conjunction strip so "what happens when ice is heated" → "ice".
    # Restrict to -ed only: -en suffix (oxygen, frozen, kitchen) causes false positives.
    text = re.sub(r"\s+(?:is|are|was|were)\s+\w+ed\s*$", "", text, flags=re.I)
    # "how do I protect my computer from viruses" → "computer"
    # "I VERB [my/the] OBJECT [from/against/with X]" after QW strips "how do ".
    _m_first_person_action = re.match(
        r"^i\s+\w+\s+(?:(?:my|your|our|the|a|an)\s+)?(.+?)(?:\s+(?:from|against|with|for|to)\s+\w+(?:\s+\w+)*)?\s*$",
        text, re.I,
    )
    if _m_first_person_action:
        text = _m_first_person_action.group(1)
    # "when you mix baking soda and vinegar" → strip "when " → "you mix baking soda ..."
    # → strip "you VERB " (generic pronoun + one verb) → "baking soda and vinegar".
    text = re.sub(r"^(?:you|we|they|people|someone|a\s+person)\s+\w+\s+", "", text, flags=re.I)
    # Strip leading preposition orphaned by pronoun+verb strip:
    # "how do you deal with anxiety" → pronoun strip → "with anxiety" → "anxiety"
    text = re.sub(r"^(?:with|about|from|against|through|around|between)\s+", "", text, flags=re.I)
    # "what country has won the most world cups" → "world cups"
    # "who has won the most grand slams" → after QW strips "who", bare "has won the most X"
    # also matches (subject group is now optional).
    _m_has_won_most = re.match(
        r"^(?:\w+(?:\s+\w+)?\s+)?(?:ha(?:s|ve|d)\s+)?won\s+(?:the\s+)?most\s+(.+)$",
        text, re.I,
    )
    if _m_has_won_most:
        text = _m_has_won_most.group(1)
    # "who has the most super bowl wins" → QW strips "who has", article strips "the"
    # → text = "most super bowl wins" → superlative strip would wrongly eat "most super"
    # Guard on "who has/have/had" specifically so "who is the most streamed artist"
    # (where "most streamed" is a true superlative adjective) falls through untouched.
    elif re.match(r"^most\s+", text, re.I) and re.match(r"^who\s+ha[sd]\b", _original, re.I):
        text = re.sub(r"^most\s+", "", text, flags=re.I)
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
    # "what language is spoken/used in X" → X  (passive construction, must fire before _m_cat_is
    # which would otherwise capture "spoken in X" as the predicate)
    _m_lang_passive = re.match(
        r"^language\s+(?:is|are|was|were)\s+(?:spoken|used|official|common)\s+"
        r"(?:in|of|throughout|across)\s+(?:the\s+|a\s+|an\s+)?(.+)$",
        text, re.I,
    )
    if _m_lang_passive:
        text = _m_lang_passive.group(1)
    # Second-pass people/pronoun strip: fires after "language does/do" exposed a
    # "people in X VERB" construction. E.g. "what language do people in brazil speak"
    # → "language do " stripped → "people in brazil speak" → strip "people in " → "brazil speak"
    text = re.sub(r"^(?:you|we|they|people|someone|a\s+person)\s+\w+\s+", "", text, flags=re.I)
    # "what happens to X when/if it VERBS" → strip leading "to " → "X when it VERBS"
    # then strip trailing "when/if it VERB" clause.
    # Guard: "who wrote to kill a mockingbird" → don't strip "to " when it's a title infinitive.
    _title_attr_ctx = bool(re.search(
        r"\b(?:wrote?|written|directed?|composed?|painted?|sang|authored?|filmed?)\b",
        _original, re.I,
    )) or bool(re.match(
        # "what is to kill a mockingbird" — bare "what/who is to VERB" implies title lookup
        r"^(?:what|who)\s+(?:is|are|was|were)\s+to\b",
        _original, re.I,
    )) or bool(re.search(
        # "theme of to kill a mockingbird" — title starting with "To" after a property noun
        r"\bof\s+to\b",
        _original, re.I,
    ))
    if not (_title_attr_ctx and len(text.split()) >= 3):
        text = re.sub(r"^to\s+", "", text, flags=re.I)
    # "where in the world is X" / "where on earth is X" → after "where" stripped:
    # "in the world is X" → strip "in the world is [article]" → X.
    # Must fire BEFORE the generic ^in strip to consume the full idiom.
    text = re.sub(
        r"^(?:in\s+(?:the\s+)?(?:world|earth)|on\s+earth)\s+(?:is|are|was|were)\s+(?:the\s+|a\s+|an\s+)?",
        "", text, flags=re.I,
    )
    # "they speak in brazil" → pronoun+verb strip → "in brazil" → strip leading "in " → "brazil"
    # Safe: no subject begins with the preposition "in " (words like "insulin" have no space).
    text = re.sub(r"^in\s+(?:the\s+|a\s+|an\s+)?", "", text, flags=re.I)
    # "in what year was hamlet written" → "in " stripped above → "what year was hamlet written"
    # → trailing verb strips "written" → "what year was hamlet" → re-strip temporal QW residue.
    text = re.sub(
        r"^(?:why|what|how|who|when|where)\s+"
        r"(?:(?:year|century|decade|era|period|day|month|time|date|ago)\b|\w+ly)?\s*"
        r"(?:is|are|was|were|has|have|had|does|do|did|can|could|would|should)?\s*"
        r"(?:the\s+|a\s+|an\s+)?",
        "", text, flags=re.I,
    )
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
    # "what programming language is used for web development" → "web development"
    # "NOUN is/are used for/in/to PURPOSE" → PURPOSE (the use-case is the lookup subject)
    # Guard: requires "is/are/was/were" so "python used for" (no copula) falls through to
    # the trailing-verb strip which correctly strips "used for" → "python".
    _m_used_for = re.match(
        r"^.+?\s+(?:is|are|was|were)\s+(?:(?:mainly|primarily|commonly|often|usually)\s+)?"
        r"used\s+(?:for|in|to)\s+(.+)$",
        text, re.I,
    )
    if _m_used_for:
        text = _m_used_for.group(1)
    # "what foods are good for the heart" → "heart"
    # "NOUN is/are [adj] for TARGET" → TARGET (the beneficiary is the lookup subject)
    # Fires only when "is/are/was/were" is still present (copula not yet stripped),
    # so bare "vegetables good for X" falls through to the adj-for strip instead.
    _m_good_for = re.match(
        r"^.+?\s+(?:is|are|was|were)\s+(?:(?:very|quite|so)\s+)?"
        r"(?:good|bad|beneficial|healthy|helpful|important|essential|useful|harmful|dangerous|effective)"
        r"\s+(?:for|to)\s+(?:the\s+|a\s+|an\s+)?(.+)$",
        text, re.I,
    )
    if _m_good_for:
        text = _m_good_for.group(1)
    # "what foods contain vitamin c" → "vitamin c"; "what sources have protein" → "protein"
    # The searched-for substance/nutrient is the lookup subject, not the generic category.
    _m_cat_contain = re.match(
        r"^(?:foods?|items?|products?|sources?|ingredients?|things?)\s+"
        r"(?:contain|have|include|provide|offer)\s+(.+)$",
        text, re.I,
    )
    if _m_cat_contain:
        text = _m_cat_contain.group(1)
    # "what elements are in water" → after "what " is stripped → "elements are in water"
    # → look up "water" (the container), not "elements" (the thing counted).
    _is_how_many = bool(re.match(r"^\s*(?:and |but |so )?how\s+many\b", _original, re.I))
    if _is_how_many:
        # "how many tigers are left in the wild" → "tigers" (counted noun is the lookup target)
        _m_many_left = re.match(r"^(\w+(?:\s+\w+)?)\s+are\s+left\b", text, re.I)
        if _m_many_left:
            text = _m_many_left.group(1)
        else:
            # "how many players are in/on a soccer team" → "soccer" (sport, not "soccer team")
            # Must fire before the generic _m_many_in which would capture "soccer team".
            _m_many_team = re.match(
                r"^\w+(?:\s+\w+)?\s+are\s+(?:on|in)\s+(?:a|an|the|each)\s+(.+?)\s+"
                r"(?:team|squad|roster|side)\s*$",
                text, re.I,
            )
            if _m_many_team:
                text = _m_many_team.group(1)
            else:
                # "how many world cups has brazil won" → "brazil" (entity with the record)
                # Pattern: "PLURAL_NOUN has/have ENTITY VERB" → ENTITY
                _m_many_has = re.match(
                    r"^\w+(?:\s+\w+)?\s+ha[sd]\s+(.+?)\s+\w+\s*$",
                    text, re.I,
                )
                if _m_many_has:
                    text = _m_many_has.group(1)
                else:
                    # "how many oscars did titanic win" → after QW strip: "oscars did titanic win"
                    # Pattern: "PLURAL_NOUN did ENTITY VERB" → ENTITY
                    _m_many_did = re.match(
                        r"^\w+(?:\s+\w+)?\s+did\s+(?:a\s+|an\s+|the\s+)?(.+?)\s+\w+\s*$",
                        text, re.I,
                    )
                    if _m_many_did:
                        text = _m_many_did.group(1)
                    else:
                        # "how many bones are in the human body" → after QW strip: "bones are in the human body"
                        # → extract the container ("human body"), not the counted noun ("bones").
                        _m_many_in = re.match(
                            r"^\w+(?:\s+\w+)?\s+are\s+(?:in|inside|within)\s+(?:the\s+|a\s+|an\s+)?(.+)$",
                            text, re.I,
                        )
                        if _m_many_in:
                            text = _m_many_in.group(1)
                            # Strip leading unit/container nouns so "slice of pizza" → "pizza",
                            # "cup of rice" → "rice", "glass of water" → "water", etc.
                            text = re.sub(
                                r"^(?:slice|piece|cup|bowl|glass|bottle|can|jar|bag|box|scoop|"
                                r"serving|portion|helping|handful|spoonful|"
                                r"teaspoon|tablespoon|ounce|oz|gram|kilogram|kg|pound|lb|"
                                r"liter|litre|gallon|quart|pint|ml|"
                                r"bite|sip|drop|pinch|dash|stick|bar|block)\s+of\s+",
                                "", text, flags=re.I,
                            )
                        else:
                            # "how many cups in a gallon" → "gallon" (unit conversion, no "are")
                            _m_many_unit_in = re.match(
                                r"^\w+(?:\s+\w+)?\s+in\s+(?:a|an|one)\s+(.+)$",
                                text, re.I,
                            )
                            if _m_many_unit_in:
                                text = _m_many_unit_in.group(1)
                            else:
                                # "how many laps is a mile run" → "mile run" (copula form)
                                _m_many_unit_is = re.match(
                                    r"^\w+(?:\s+\w+)?\s+is\s+(?:a|an)\s+(.+)$",
                                    text, re.I,
                                )
                                if _m_many_unit_is:
                                    text = _m_many_unit_is.group(1)
                                else:
                                    # "how many branches of government are there" — the scaffold
                                    # strip ran before _is_how_many so "branches of" was lost.
                                    # Recover the counted-noun phrase from the pre-scaffold text.
                                    _pre_there = re.sub(
                                        r"\s+are\s+there\s*$", "",
                                        _before_scaffold_strip, flags=re.I,
                                    )
                                    if _pre_there != _before_scaffold_strip:
                                        text = _pre_there
    else:
        _m = re.match(
            r"^(\w+(?:\s+\w+){0,2})\s+(?:are|were|is|was)\s+(?:in|inside|within|found in|part of)\s+(.+)$",
            text, re.I,
        )
        if _m:
            text = _m.group(2)
        elif re.match(r"^\s*(?:and |but |so )?what\s+are\s+", _original, re.I):
            # "what are the notes in a c major scale" → "c major scale".
            # Only fire when container uses indefinite "a/an" — that signals the
            # container is the ENTITY being defined, not a well-known background
            # ("the solar system" uses "the", so planets stay as the subject).
            _m_parts_in = re.match(
                r"^\w+(?:\s+\w+)?\s+in\s+(?:a|an)\s+(.+)$",
                text, re.I,
            )
            if _m_parts_in:
                text = _m_parts_in.group(1)
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
        # "what temperature do you cook chicken at" → captured "you cook chicken at"
        # Strip pronoun+verb opener then strip trailing lone preposition.
        text = re.sub(r"^(?:you|we|they|people|someone)\s+\w+\s+", "", text, flags=re.I)
        text = re.sub(r"\s+(?:at|to|for|in|on|with)\s*$", "", text, flags=re.I)
    # "what type of animal is a whale" → scaffold strip removes "type of" → "animal is a whale"
    # → "CATEGORY is/was X" → X.  "animal|plant|element|mineral|metal|country|..." are category nouns
    # that head this pattern after the scaffold strip fires.
    # "what album is stairway to heaven on" → "stairway to heaven"
    # Media containment: "what MEDIUM is X on/from/by" → X (the song/film being asked about)
    _m_media_is = re.match(
        r"^(?:album|ep|track|film|movie|show|series|episode|chapter|book|game)\s+"
        r"(?:is|was)\s+(?:a\s+|an\s+|the\s+)?(.+?)\s+(?:on|from|by)\s*$",
        text, re.I,
    )
    if _m_media_is:
        text = _m_media_is.group(1)
    # "what planet is closest to the sun" → "planet".
    # After QW strips "what", "planet is closest to the sun" remains; _m_cat_is below would
    # capture "closest to the sun" instead of the category.  Guard it: when the predicate of
    # CATEGORY is SUPERLATIVE, return the category noun directly.
    _m_cat_is_super = re.match(
        r"^((?:planet|star|animal|country|city|language|sport|food|drink|"
        r"ocean|sea|lake|river|mountain|desert|forest|island|element|metal|mineral|"
        r"substance|species|mammal|reptile|bird|fish|insect|drug|disease|galaxy|"
        r"rock|gem|continent|region|nationality|organism|creature)(?:\s+\w+)?)\s+"
        r"(?:is|are|was|were)\s+(?:the\s+)?"
        r"(?:largest?|biggest?|smallest?|tallest?|shortest?|longest?|fastest?|slowest?|"
        r"highest?|lowest?|richest?|poorest?|hottest?|coldest?|brightest?|darkest?|"
        r"strongest?|weakest?|closest?|nearest?|farthest?|deepest?|widest?|narrowest?|"
        r"lightest?|heaviest?|oldest?|youngest?|newest?|most\s+\w+|least\s+\w+)\b",
        text, re.I,
    )
    if _m_cat_is_super:
        text = _m_cat_is_super.group(1)
    _m_cat_is = re.match(
        r"^(?:(?:programming|computer|natural|spoken|written|native|official|ancient|"
        r"modern|web|mobile|scripting|markup|query|functional|object|compiled|"
        r"interpreted|procedural)\s+)?"
        r"(?:animal|plant|mammal|reptile|bird|fish|insect|element|mineral|metal|"
        r"substance|compound|molecule|chemical|gas|liquid|solid|energy|"
        r"country|city|continent|region|language|sport|food|drug|disease|"
        r"ocean|sea|lake|river|mountain|desert|forest|island|peninsula|canyon|"
        r"rock|mineral|gem|star|planet|galaxy|force|wave|particle|radiation|"
        r"nationality|genre|style|medium|technique|movement|era|format|type|color|colour|shape|material|occupation|religion|position|role|title)\s+(?:is|was|are|were|does|did)\s+(?:a\s+|an\s+|the\s+)?(.+)$",
        text, re.I,
    )
    if _m_cat_is:
        _cat_captured = _m_cat_is.group(1)
        # Don't fire for "country is X in/on/at/from" — that's handled by _m_loc_noun later.
        # Don't fire when the capture is a predicate adjective phrase ("element is most abundant"
        # or "food is high in protein" — those are handled by _m_adj_in later).
        if (not re.search(r"\s+(?:in|on|at|from)\s*$", _cat_captured, re.I)
                and not re.match(
                    r"^(?:most|least|very|quite|so|more|less|too|"
                    r"high|low|rich|poor|lacking|deficient|abundant|dense|"
                    r"concentrated|elevated|depleted|packed|loaded|full|empty)\b",
                    _cat_captured, re.I)):
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
        _m_it_takes_for = re.match(r"^it\s+takes?\s+for\s+(?:a|an|the\s+)?\s*(.+?)\s+to\s+\w+", text, re.I)
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
    _m_we = re.match(r"^(?:we|you|one|people)\s+(\w+)\s*$", text, re.I)
    if _m_we:
        text = _m_we.group(1)
    # "it VERB in X" → X  (dummy-subject weather/frequency questions)
    # e.g. "how often does it rain in london" → "it rain in london" → "london"
    _m_it_in = re.match(r"^it\s+\w+\s+in\s+(?:the\s+|a\s+)?(.+)$", text, re.I)
    if _m_it_in:
        text = _m_it_in.group(1)
    # "distance from X to Y" → X  (must fire before "to <verb>" strip below)
    _m_dist_from = re.match(r"^distance\s+from\s+(?:the\s+|a\s+)?(.+?)\s+to\b", text, re.I)
    if _m_dist_from:
        text = _m_dist_from.group(1)
    # "the temperature to rise" → strip "to <verb>" infinitive phrase at end.
    # Require -ing suffix or a known action verb to avoid stripping titles like
    # "stairway to heaven" (heaven is a noun, not a verb).
    # Strip trailing "to WORD" infinitive or dative phrases.
    # Broad match (\w+(?:ing)?) but exclude known title/place nouns that follow "to"
    # in song/film titles (heaven, earth, nowhere, etc.) which are NOT verb infinitives.
    text = re.sub(
        r"\s+to\s+"
        r"(?!(?:heaven|earth|hell|paradise|nowhere|somewhere|anywhere|everywhere|"
        r"forever|infinity|glory|victory|defeat|love|war|peace|freedom|justice|"
        r"power|happiness|success|failure|life|death|nature|space|time|eternity)\b)"
        r"\w+(?:ing)?\s*$",
        "", text, flags=re.I,
    )
    text = re.sub(r"\s+work[s]?\s*$", "", text, flags=re.I)
    # "what does caffeine do to the brain" → QW strip → "caffeine do to the brain"
    # Strip "do to [article] NOUN[S]" tail → "caffeine"
    text = re.sub(r"\s+do\s+to\s+(?:(?:the|a|an|your|our|your)\s+)?\w+(?:\s+\w+)?\s*$", "", text, flags=re.I)
    # "NOUN does/do/did ENTITY possession-verb" → ENTITY (entity being described)
    # e.g. "legs does a spider have" → "spider"; "milk does a cow produce" → "cow"
    # Only fires when the final word is a possession/production verb so that
    # "insulin do in the body" (body ≠ verb) and similar are not affected.
    # Article group requires trailing space so "adults" is not split as "a" + "dults".
    _m_entity_have = re.match(
        r"^\w+(?:\s+\w+)?\s+(?:does|do|did)\s+(?:a\s+|an\s+|the\s+)?"
        r"(\w+(?:\s+\w+)?)\s+"
        r"(?:have|has|need[s]?|produce[sd]?|make[s]?|contain[sd]?|hold[s]?|"
        r"weigh[s]?|cost[s]?|generate[sd]?|carry|carries|consume[sd]?|use[sd]?)\s*$",
        text, re.I,
    )
    if _m_entity_have:
        text = _m_entity_have.group(1)
    # "how many players are on a basketball team" → after QW strip "players are on a basketball team"
    # → extract the sport/group noun before "team/squad/roster/side".
    _m_team_count = re.match(
        r"^\w+(?:\s+\w+)?\s+are\s+(?:on|in)\s+(?:a|an|the|each)\s+(.+?)\s+(?:team|squad|roster|side)\s*$",
        text, re.I,
    )
    if _m_team_count:
        text = _m_team_count.group(1)
    # "X are there [in Y]" → X  (e.g. "what kinds of algae are there" → "algae",
    # "what kinds of planets are there in the solar system" → "planets")
    # Also "X are in/on/at Y" (e.g. "how many planets are in the solar system" → "planets")
    text = re.sub(r"\s+are\s+(?:there\b|in\b|on\b|at\b).*$", "", text, flags=re.I)
    # "best way to store bread" → "bread"; "best way to ripen a banana" → "banana"
    # Pattern: "SUPERLATIVE way to VERB [article] OBJECT" → OBJECT.
    # Must fire before the trailing verb strip which would consume "store bread".
    _m_way_to = re.match(
        r"^(?:best|easiest|quickest|fastest|simplest|proper|right|correct|optimal|"
        r"most\s+\w+|safest|healthiest|cheapest)\s+way\s+to\s+\w+\s+"
        r"(?:(?:a|an|the)\s+)?(.+)$",
        text, re.I,
    )
    if _m_way_to:
        text = _m_way_to.group(1)
    # "healthiest food" → "food": leading superlative adj before a category noun.
    # Fires after trailing infinitive has been stripped, leaving "SUPERLATIVE CATEGORY".
    _m_super_cat_lead = re.match(
        r"^(?:best|worst|most\s+\w+|least\s+\w+|"
        r"largest?|biggest?|smallest?|tallest?|shortest?|longest?|"
        r"fastest?|slowest?|highest?|lowest?|richest?|poorest?|"
        r"hottest?|coldest?|brightest?|darkest?|strongest?|weakest?|"
        r"deepest?|widest?|heaviest?|lightest?|oldest?|newest?|"
        r"closest?|nearest?|cheapest?|safest?|healthiest?|tastiest?|"
        r"spiciest?|crispiest?|freshest?|warmest?|coolest?|sweetest?|"
        r"hardest?|softest?|easiest?|simplest?)\s+"
        r"((?:planet|star|animal|country|city|language|sport|food|drink|"
        r"ocean|sea|lake|river|mountain|desert|forest|island|element|"
        r"metal|mineral|substance|species|mammal|reptile|bird|fish|insect|"
        r"drug|disease|galaxy|rock|gem|continent|region|nationality|organism|"
        r"creature|thing|person|way|place|type|kind|diet|meal|fruit|vegetable|"
        r"grain|vitamin|nutrient|exercise|workout|treatment|remedy|medicine|"
        r"source|option|method|approach|strategy|solution|alternative|choice|"
        r"train|plane|car|vehicle|ship|boat|bridge|building|structure|tower)"
        r"(?:\s+\w+)?)\s*$",
        text, re.I,
    )
    if _m_super_cat_lead:
        text = _m_super_cat_lead.group(1)
    # "what sport uses a puck" → QW strips "what " → "sport uses a puck" → "puck"
    # When a category noun is the head and followed by a use/need verb and object,
    # the object is the real lookup target.
    _m_cat_uses = re.match(
        r"^(?:sport|game|activity|animal|plant|country|countries|language|instrument|drug|element|"
        r"machine|device|vehicle|tool|substance|compound|mineral|organism|creature|"
        r"ocean|sea|lake|river|mountain|city|cities|region|continent)\s+"
        r"(?:use[sd]?|need[sd]?|require[sd]?|involve[sd]?|contain[sd]?|produc(?:e[sd]?|es)|"
        r"emit[sd]?|release[sd]?|create[sd]?|generate[sd]?|"
        r"border[sd]?|surround[sd]?|adjoin[sd]?|divide[sd]?|separate[sd]?|"
        r"flow[sd]?\s+through)\s+"
        r"(?:(?:a|an|the)\s+)?(.+)$",
        text, re.I,
    )
    if _m_cat_uses:
        text = _m_cat_uses.group(1)
    # "what equipment do you need for cycling" → "cycling"
    # "NOUN do you need/want/use for ACTIVITY" → ACTIVITY
    _m_need_for_act = re.match(
        r"^\w+(?:\s+\w+)?\s+do\s+you\s+(?:need|want|use|require|get|wear|bring)\s+"
        r"(?:for|to\s+do|to\s+play|to\s+learn)\s+(.+)$",
        text, re.I,
    )
    if _m_need_for_act:
        text = _m_need_for_act.group(1)
    # Trailing passive progressive: "amazon rainforest being destroyed" → "amazon rainforest"
    # Fires before the main trailing-verb strip, which only matches single active verbs.
    text = re.sub(r"\s+being\s+\w+(?:ed|en)\s*$", "", text, flags=re.I)
    text = re.sub(
        # Negative lookbehind: don't strip "needs" in "hierarchy of needs" (noun phrase).
        r"(?<!of)\s+(?:need|needs|require|requires|use[sd]?|produce[sd]?|"
        r"happen(?:ed|s)?|occur(?:red|s)?|exist(?:ed|s)?|"
        r"made|created|formed|produced|compos(?:ed|es?)?|prevented|caused|built|done|founded|"
        # Irregular past-tense verbs common in hypothetical "if X lost/became Y" questions:
        r"los(?:t|e[sd]?)|becam(?:e|es?)|forgot(?:ten)?|gain(?:ed)?|"
        r"get\s+\w+ed|become|start|begin|"
        # Action verbs trailing the subject in "how do/does X [verb]" patterns
        r"form[s]?|make[s]?|replicate[s]?|(?<!bullet )(?<!maglev )(?<!steam )(?<!freight )(?<!commuter )(?<!fastest )train[s]?|take[s]?|"
        r"pump[s]?|(?<!due )process(?:es)?|connect[s]?|"
        r"filter[s]?|flow[s]?|carry|carries|digest[s]?|regulate[s]?|consume[sd]?|"
        r"detoxif(?:y|ies)?|exchange[s]?|ferment[s]?|attract[s]?|pull[s]?|"
        r"erupt[s]?|eat[s]?|feed[s]?|hunt[s]?|drink[s]?|mix(?:es)?|"
        r"come[s]?\s+from|get[s]?|navigate[sd]?|find[s]?|"
        r"purr[s]?|bark[s]?|meow[s]?|howl[s]?|chirp[s]?|sing[s]?|hum[s]?|roar[s]?|growl[s]?|"
        r"regrow[s]?|regenerate[sd]?|hibernate[sd]?|camouflage[sd]?|photosynthesize[sd]?|"
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
        # "attack" is also a medical compound noun ("asthma attack", "heart attack"):
        # protect those by requiring it not be preceded by a condition noun.
        r"fight[s]?|(?<!asthma\s)(?<!heart\s)(?<!panic\s)(?<!anxiety\s)attack[s]?|"
        r"defend[s]?|protect[s]?|affect[s]?|impact[s]?|"
        # Physical / chemical state-change verbs: "why does ice float", "what makes iron rust"
        r"float[s]?|sink[s]?|rust[s]?|boil[s]?|melt[s]?|freeze[sd]?|evaporate[sd]?|"
        r"condense[sd]?|expand[s]?|contract[s]?(?!\s+(?:theory|law|clause|principle|agreement))|ignite[sd]?|dissolve[sd]?|"
        # Mass/cost verbs: "how much does a blue whale weigh" → "blue whale"
        r"weigh[s]?|cost[s]?|"
        # Migration / movement verbs: "how do birds migrate"
        r"migrate[sd]?|"
        # Passive attribution: "when was X invented", "where was Y discovered/located/born/found"
        r"invent(?:ed|s)?|discover(?:ed|s)?|develop(?:ed|s)?|design(?:ed|s)?|sign(?:ed|s)?|locat(?:ed|es)?|born|found\b|establish(?:ed|es)?|practi(?:s|c)ed|worship(?:p?ed|s)?|celerat(?:ed|es)?|elect(?:ed|s)?|appoint(?:ed|s)?|"
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
        r"twinkle[sd]?|travel[s]?|dream[s]?|sleep[s]?|yawn[s]?|learn[s]?|strike[s]?|sweat[s]?|"
        r"mutate[sd]?|neutralize[sd]?|"
        r"swim[s]?|fly|flies|walk[s]?|"
        # Guard "run" against compound sports/activity nouns: "home run", "mile run",
        # "fun run", "dry run", "ski run", "test run" must not be stripped.
        r"(?<!home )(?<!mile )(?<!fun )(?<!dry )(?<!ski )(?<!test )(?<!long )run[s]?|"
        r"jump[s]?|crawl[s]?|wag[s]?|beach(?:es|ed)?|speak[s]?|talk[s]?|colonize[sd]?|know[s]?|hold[s]?|go(?:es)?|come[s]?|return[s]?|arrive[sd]?|(?<!the )(?<!arithmetic )mean[s]?|"
        r"smell[s]?|taste[s]?|see[s]?|hear[s]?|sense[s]?|read[s]?|writ(?:e[s]?|ten)|coexist[s]?|"
        # Passive-participle verbs: "how is blood pressure measured" → "blood pressure"
        # Note: bare "rate" is NOT here — it's almost always a noun (interest rate, poverty rate).
        # Only inflected forms "rated"/"rates" used as verbs are stripped.
        r"measure[sd]?|classif(?:ied|y|ies)?|call(?:ed|s)?|rank(?:ed|s)?|rat(?:ed|es)|treat(?:ed|s)?|cure[sd]?|publish(?:ed|es)?|diagnos(?:ed|es)?|believe[sd]?|paint(?:ed|s)?|compil(?:ed|es)?|sculpt(?:ed|s)?|say[s]?|said|claim(?:ed|s)?|argue[sd]?|assert(?:ed|s)?|teach(?:es|t)?|"
        r"turn[s]?|transform[sd]?|"
        r"shine[sd]?|glow[s]?|burn[s]?|move[sd]?|"
        r"orbit[s]?|revolve[sd]?|rotate[sd]?|spin[s]?|live[sd]?|breathe[sd]?|"
        r"stop(?:ped|s)?|end[s]?|explode[sd]?|collapse[sd]?(?!\s+of)|crash(?:es|ed)?|"
        r"cover(?:ed|s)?|surround(?:ed|s)?|fill(?:ed|s)?|consist[s]?|contain[s]?|look[s]?|"
        # Duration/persistence verbs: "how long does pregnancy last" → "pregnancy"
        r"last[s]?|persist[s]?|remain[s]?|"
        # Extinction/movement verbs. Use negative lookahead (?!\s+of) so that
        # noun forms like "the fall of X" and "the collapse of Y" are preserved —
        # only the trailing verb use ("how did Rome fall") should be stripped.
        r"go\s+extinct|fall[s]?(?!\s+of)|collapse[sd]?(?!\s+of)|rise[sd]?(?!\s+of)|"
        r"work[s]?"
        r")\b.*$",
        "", text, flags=re.I,
    )
    # Re-apply category-is pattern after trailing verb strip:
    # "what programming language is python written in" → trailing strip → "programming language is python"
    # First pass of _m_cat_is was blocked by the guard (capture ended with "in").
    # Now that trailing verbs are gone, try again.
    _m_cat_is2 = re.match(
        r"^(?:(?:programming|computer|natural|spoken|written|native|official|ancient|"
        r"modern|web|mobile|scripting|markup|query|functional|object|compiled|"
        r"interpreted|procedural)\s+)?"
        r"(?:animal|plant|mammal|reptile|bird|fish|insect|element|mineral|metal|"
        r"substance|compound|molecule|chemical|gas|liquid|solid|energy|"
        r"country|city|continent|region|language|sport|food|drug|disease|"
        r"ocean|sea|lake|river|mountain|desert|forest|island|peninsula|canyon|"
        r"rock|mineral|gem|star|planet|galaxy|force|wave|particle|radiation|"
        r"nationality|genre|style|medium|technique|movement|era|format|type|color|colour|shape|material|occupation|religion|position|role|title)\s+(?:is|was|are|were|does|did)\s+(?:a\s+|an\s+|the\s+)?(.+)$",
        text, re.I,
    )
    if _m_cat_is2:
        _cat2 = _m_cat_is2.group(1)
        if (not re.search(r"\s+(?:in|on|at|from)\s*$", _cat2, re.I)
                and not re.match(
                    r"^(?:most|least|very|quite|so|more|less|too|"
                    r"high|low|rich|poor|lacking|deficient|abundant|dense|"
                    r"concentrated|elevated|depleted|packed|loaded|full|empty)\b",
                    _cat2, re.I)):
            text = _cat2
    # Temporal prefix: "when will the next solar eclipse be" → verb strip → "next solar eclipse"
    # → strip leading "next"/"upcoming" → "solar eclipse". Safe: temporal modifiers add nothing
    # to a knowledge lookup; "next X" and "upcoming X" both look up the same concept.
    text = re.sub(r"^(?:next|upcoming)\s+", "", text, flags=re.I)
    # Orphaned "which" left when _m_which missed (aux verb absent) and trailing verb strip
    # removed the main verb: "which animal runs the fastest" → verb strip → "which animal"
    # → strip "which " → "animal".
    text = re.sub(r"^which\s+", "", text, flags=re.I)
    # After "which" strip, a copula + comparative may remain: "is better python or java".
    # Strip "is/are COMPARATIVE " to leave the compared subjects.
    text = re.sub(
        r"^(?:is|are|was|were)\s+"
        r"(?:better|worse|bigger|smaller|faster|slower|older|younger|cheaper|pricier|"
        r"more\s+\w+|less\s+\w+|best|worst|greatest|most\s+\w+|least\s+\w+|"
        r"larger|higher|lower|heavier|lighter|stronger|weaker)\s+",
        "", text, flags=re.I,
    )
    # Leading comparative adjective after QW stripped "what is"/"why is":
    # "bigger jupiter or saturn" → "jupiter or saturn"
    text = re.sub(
        r"^(?:bigger|smaller|faster|slower|better|worse|cheaper|pricier|"
        r"larger|higher|lower|older|younger)\s+(?=\w)",
        "", text, flags=re.I,
    )
    # "how does mitosis differ from meiosis" → verb strip removes "differ" (and "from meiosis"
    # via .*). "how is a virus different from a bacterium" — "different from" is not a verb,
    # strip it explicitly.
    text = re.sub(r"\s+different\s+from\s+.*$", "", text, flags=re.I)
    # "is the sun larger than the earth" → bare opener strips "is the" → "sun larger than the earth"
    # strip comparative adj + "than ..." tail → "sun"; also "better than" / "worse than"
    text = re.sub(
        r"\s+(?:larger|bigger|smaller|faster|slower|older|younger|higher|lower|heavier|lighter|"
        r"hotter|colder|brighter|darker|stronger|weaker|closer|farther|nearer|wider|narrower|"
        r"longer|shorter|deeper|shallower|thicker|thinner|louder|quieter|denser|rarer|"
        r"better|worse|cheaper|pricier|safer|healthier|tastier|easier|harder|simpler|"
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
    # Early predicate-adjective strip before the modal strip so that compound nouns
    # containing modal-shaped words are protected: "free will real" → "free will"
    # (without this, the modal strip would see "will real" and eat it → "free").
    text = re.sub(
        r"\s+(?:real|fake|genuine|authentic|imaginary|fictional|possible|impossible|"
        r"necessary|unnecessary|tangible|intangible|objective|subjective|valid|invalid|"
        r"rational|irrational|conscious|unconscious|mortal|immortal|infinite|finite)\s*$",
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
    # Guard: don't strip when in title-attribution context (e.g. "kill a mockingbird" should stay intact)
    _before_an_strip = text
    if not (_title_attr_ctx and len(text.split()) >= 3):
        # Preserve "X of a SHAPE" for known geometric/mathematical shapes so that
        # "area of a circle" → "area of a circle" (not "area") while still stripping
        # generic qualifiers like "pluto a planet" → "pluto", "gdp of a country" → "gdp".
        _m_geo_shape = re.search(
            r"\bof\s+(?:a|an)\s+"
            r"(?:circle|triangle|sphere|square|rectangle|cylinder|cone|cube|"
            r"polygon|ellipse|hexagon|pentagon|octagon|pyramid|prism)\s*$",
            text, re.I,
        )
        if not _m_geo_shape:
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
        r"mountain|island|planet|galaxy|star|time\s+zone|timezone)\s+(?:is|was|are|were)\s+(.+?)\s+(?:in|on|at|from)\s*$",
        text, re.I,
    )
    if _m_loc_noun:
        text = _m_loc_noun.group(1)
    # "temperature on mars" → "mars"; "gravity on the moon" → "moon"
    _m_prop_on = re.match(
        r"^(?:temperature|pressure|gravity|atmosphere|climate|weather|surface|"
        r"magnetic\s+field|day|night)\s+on\s+(?:the\s+)?(.+)$",
        text, re.I,
    )
    if _m_prop_on:
        text = _m_prop_on.group(1)
    # "there life on mars" (from "is there life on mars") → "mars".
    # The bare modal strip removes "is " leaving "there life on mars"; catch it before
    # the trailing "on X" strip would eat " on mars" and leave "there life".
    _m_existential = re.match(
        r"^there\s+\w+(?:\s+\w+)?\s+(?:on|in)\s+(?:the\s+)?(.+)$",
        text, re.I,
    )
    if _m_existential:
        text = _m_existential.group(1)
    # "X on <modifier>" → X  (e.g. "effect of gravity on time" → "gravity")
    # Only strip trailing "on <1-3 words>" — not "on" inside a topic name.
    text = re.sub(r"\s+on\s+\w+(?:\s+\w+){0,2}\s*$", "", text, flags=re.I)
    # "quantum physics in simple terms" → "quantum physics"  (explanation-register qualifier)
    text = re.sub(r"\s+in\s+(?:simple|plain|basic|easy|everyday|lay(?:man[\'s]*)?)\s+terms\s*$", "", text, flags=re.I)
    # "largest country in africa" / "most popular sport in brazil" / "tallest mountain in the world"
    # → location after "in [the]".  Must fire BEFORE the "in the <X>" strip below so that
    # superlative+category phrases don't lose their location context ("tallest mountain" → "mountain").
    # "largest country in africa" / "most popular sport in brazil" → location after "in".
    # Exclude "in the ..." (solar system, world, universe etc.) — those are universal
    # scope qualifiers, not meaningful lookup contexts; they're handled by the "in the" strip below.
    _m_super_in = re.match(
        r"^(?:most\s+\w+|\w+est)\s+\w+(?:\s+\w+)?\s+in\s+(?!the\b)(.+)$",
        text, re.I,
    )
    if _m_super_in:
        text = _m_super_in.group(1)
    # "X in the <location>" → X  (e.g. "planets in the solar system" → "planets")
    # Require "in the" so bare "animals in water" is not affected.
    text = re.sub(r"\s+in\s+the\s+\w+(?:\s+\w+){0,2}\s*$", "", text, flags=re.I)
    # Second-pass work[s] strip: "voting work" → "voting" when "in the X" was just removed.
    # The primary work strip at line 717 fires before location strips, so it misses this residue.
    text = re.sub(r"\s+work[s]?\s*$", "", text, flags=re.I)
    # "foods are high in protein" → "protein"; "milk is rich in calcium" → "calcium"
    # Pattern: "X is/are [adj] in NUTRIENT/CONTENT" → NUTRIENT (the content is the lookup target)
    # Must fire before the bare-in strip below which would strip " in protein" → "foods are high".
    _m_adj_in = re.match(
        r"^.+?\s+(?:is|are|was|were)\s+(?:(?:very|quite|extremely|so)\s+)?"
        r"(?:high|low|rich|poor|lacking|deficient|abundant|dense|concentrated|elevated|"
        r"depleted|packed|loaded|full|empty)\s+in\s+(?:the\s+|a\s+|an\s+)?(.+)$",
        text, re.I,
    )
    if _m_adj_in:
        text = _m_adj_in.group(1)
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
    # Guard: restrict the tail to known universal-scope words so that proper titles like
    # "phantom of the opera", "lord of the flies", "silence of the lambs" are preserved.
    _m_of_the = re.match(
        r"^(\w+)\s+of\s+the\s+"
        r"(?:world|earth|universe|solar\s+system|body|mind|internet|web|sky|sea|"
        r"galaxy|cosmos|globe|ocean|heavens?)\s*$",
        text, re.I,
    )
    if _m_of_the:
        text = _m_of_the.group(1)
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
        r"hot|(?<!common )cold|warm|cool|wet|dry|soft|bright|dark|"
        r"low|high|normal|elevated|full|empty|alive|dead|active|inactive|"
        r"heavy|loud|quiet|dim|sharp|dull|"
        r"salty|sweet|sour|bitter|spicy|acidic|alkaline|toxic|magnetic|elastic|"
        r"conductive|insulating|semiconducting|superconducting|"
        r"transparent|opaque|flammable|volatile|reactive|inert|radioactive|"
        r"valuable|expensive|cheap|rare|common|strong|weak|dense|flat|round|curved|"
        r"sticky|slippery|rough|smooth|thin|thick|narrow|tall|short|"
        r"similar|different|related|connected|distinct|unique|identical|"
        r"dangerous|harmful|safe|harmless|poisonous|helpful|useful|effective|important|"
        r"good|bad|healthy|unhealthy|contagious|infectious|transmissible|wrong|right|moral|immoral|ethical|unethical|illegal|legal|"
        r"hard|soft|tough|fragile|brittle|flexible|rigid|elastic|"
        # Behavioral/ecological adjectives: "why are animals nocturnal" → "animals"
        r"nocturnal|diurnal|crepuscular|aquatic|terrestrial|arboreal|"
        r"carnivorous|herbivorous|omnivorous|venomous|migratory|endangered|"
        r"solitary|social|colonial|sentient|conscious|intelligent|"
        r"renewable|organic|inorganic|synthetic|artificial|natural|"
        r"capable|able|unable|incapable|worthy|unworthy)\s*$",
        "", text, flags=re.I,
    )
    # "X capable of" → strip "capable of" tail (compound adj phrase)
    text = re.sub(r"\s+capable\s+of\s*$", "", text, flags=re.I)
    # "X responsible for" → strip "responsible for" tail
    text = re.sub(r"\s+responsible\s+for\s*$", "", text, flags=re.I)
    # Strip a trailing "not" that can remain after the negated auxiliary was
    # expanded and the verb phrase was stripped: "why does X not use Y" →
    # strips "why does " → "X not use Y" → trailing strip removes " use Y" →
    # "X not" → remove trailing " not" → "X".
    text = re.sub(r"\s+not\s*$", "", text, flags=re.I)
    # "are dolphins mammals" / "are viruses living organisms" → strip trailing classification tail
    text = re.sub(r"\s+living\s+(?:things?|organisms?|beings?|creatures?)\s*$", "", text, flags=re.I)
    _before_tax_strip = text
    text = re.sub(
        r"\s+(?:mammals?|reptiles?|amphibians?|arachnids?|crustaceans?|mollusks?|"
        r"insects?|invertebrates?|vertebrates?|primates?|carnivores?|herbivores?|"
        r"omnivores?|parasites?|predators?|scavengers?|plankton|fish)\s*$",
        "", text, flags=re.I,
    )
    # Revert if stripping left only a superlative adjective ("largest mammal" → "largest"):
    # the taxonomy word itself is the answer ("what is the largest mammal" → "mammal").
    if text != _before_tax_strip and re.match(
        r"^(?:largest?|biggest?|smallest?|tallest?|shortest?|longest?|fastest?|slowest?|"
        r"highest?|lowest?|richest?|poorest?|hottest?|coldest?|strongest?|weakest?|"
        r"oldest?|youngest?|newest?|most\s+\w+|least\s+\w+)\s*$",
        text, re.I,
    ):
        text = _before_tax_strip
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
    # "what is X about" → strip trailing " about" (topic preposition orphaned after QW strip)
    text = re.sub(r"\s+about\s*$", "", text, flags=re.I)
    # "greatest X of all time" → "X" — strip the superlative + temporal qualifier
    text = re.sub(r"\s+of\s+all\s+time\s*$", "", text, flags=re.I)
    # Guard: don't strip "best/greatest" when original was an award-category query.
    # "who won the oscar for best picture" → after causal-noun strip → "best picture";
    # "best" is part of the award name, not a modifier to remove.
    _is_award_ctx = bool(re.search(
        r"\b(?:oscar|emmy|grammy|tony|bafta|award|prize|nomination|trophy|medal)\b",
        _original, re.I,
    ))
    if not _is_award_ctx:
        text = re.sub(r"^(?:greatest|best|worst|most\s+\w+|least\s+\w+|top)\s+", "", text, flags=re.I)
    # "positions in baseball" / "formations in soccer" → "baseball"/"soccer".
    # These sport-scaffold nouns introduce a container that is the real topic.
    text = re.sub(
        r"^(?:positions?|formations?|lineup[s]?|rankings?|standings?|stats?|statistics?|"
        r"regulations?)\s+in\s+(?!the\b)(?:the\s+|a\s+|an\s+)?(.+)$",
        r"\1", text, flags=re.I,
    )
    # Strip orphaned adverbs that remain after the trailing-verb strip removed the verb:
    # "when did humans first appear" → "humans first appear" → verb strip → "humans first"
    # → strip trailing "first" → "humans".
    text = re.sub(r"\s+(?:first|last|now|still|already|yet|ever|always|never|once|again|eventually|soon|someday|sometime|fully|completely|partly|partially|finally|nearly|barely|rapidly|gradually|commonly|typically)\s*$", "", text, flags=re.I)
    # "leaves change color" → "leaves", "sun change seasons" → "sun".
    # Only fires when "change OBJECT" is at end of string (after location strips),
    # so "climate change" (no object) and "climate change affect X" (affect already
    # stripped by the verb list above) are not affected.
    text = re.sub(r"^(.+?)\s+change[s]?\s+\w+\s*$", r"\1", text, flags=re.I)
    # Strip trailing relative pronoun "that" orphaned by the verb strip:
    # "law that has been passed called" → verb strip removes " has been passed called" → "law that"
    text = re.sub(r"\s+that\s*$", "", text, flags=re.I)
    # Strip trailing "like" that remains after location strips ate the rest of the tail:
    # "what is the weather like in london" → location strip removes " in london"
    # → "the weather like" → strip " like" → "the weather" → article strip → "weather"
    # (The "what is X like" early-exit handles the simpler case where "like" is at the end
    # of the full question before any stripping; this handles residual "like" after stripping.)
    text = re.sub(r"\s+like\s*$", "", text, flags=re.I)
    # Strip a leading bare article that remains after all other strips:
    # "what is the speed of light" → after verb strip → "the speed of light" → "speed of light"
    # "how does the immune system work" → "the immune system" → "immune system"
    text = re.sub(r"^(?:the|a|an)\s+", "", text, flags=re.I)
    # Normalise article in compound subjects: "brain and the heart" → "brain and heart".
    # Trailing adj strip leaves the second article in place ("how are the brain and the heart
    # connected" → "brain and the heart"); remove it so both halves match bare noun form.
    text = re.sub(r"\s+and\s+(?:the|a|an)\s+", " and ", text, flags=re.I)
    # Strip qualifier adjective exposed after the article: "the main programming languages"
    # → "main programming languages" → "programming languages".
    text = re.sub(r"^(?:different|main|major|key(?!\s+(?:signature|change))|various|multiple)\s+", "", text, flags=re.I)
    # Strip leading superlative/comparative adjective: "largest ocean" → "ocean",
    # "fastest animal" → "animal", "most common element" → "element".
    _before_super = text
    text = re.sub(
        r"^(?:largest?|biggest?|smallest?|tallest?|shortest?|longest?|fastest?|slowest?|"
        r"highest?|lowest?|richest?|poorest?|hottest?|coldest?|brightest?|darkest?|"
        r"strongest?|weakest?|closest?|nearest?|farthest?|"
        r"deepest?|widest?|narrowest?|lightest?|heaviest?|oldest?|youngest?|newest?|"
        r"most\s+\w+|least\s+\w+)\s+",
        "", text, flags=re.I,
    )
    if text != _before_super:
        # Superlative context: trailing "to PLACE" is a distance qualifier, not a title suffix
        text = re.sub(r"\s+to\s+\w+(?:\s+\w+)?\s*$", "", text, flags=re.I)
    # Residual participial adjective after superlative strip:
    # "highest scoring sport" → "highest" stripped → "scoring sport" → strip "scoring " → "sport"
    # "highest grossing film" → "highest" stripped → "grossing film" → strip "grossing " → "film"
    text = re.sub(
        r"^(?:scoring|grossing|earning|selling|paying|growing|winning|losing|"
        r"performing|producing|consuming|emitting|generating|earning)\s+",
        "", text, flags=re.I,
    )
    # Bare "most/least" quantifier that superlative strip left because it had no
    # trailing content: "most wars" → "wars", "least developed" → "developed".
    # Fires after the superlative strip so "most common element" is already "element".
    text = re.sub(r"^(?:most|least)\s+", "", text, flags=re.I)
    # Late second-pass causal-noun strip: catches property-noun phrases exposed by
    # the late person-strip or the final article strip (both come after the main
    # causal-noun pass at the top of the function).  For example:
    # "how do you calculate the area of a circle"
    #   → person strip → "the area of a circle" → article strip → "area of a circle"
    #   → this strip → "circle"
    # Includes optional article after the preposition to handle "area of a circle" → "circle".
    text = re.sub(
        r"^(?:the\s+)?(?:\w+\s+)?(?:area|volume|perimeter|circumference|"
        r"formula|structure|composition|"
        r"root|"
        r"capital|population|size|location|height|depth|width|length|"
        r"diameter|radius|velocity|acceleration|frequency|wavelength|"
        r"distance|temperature|density|mass|weight|age|"
        r"value|price|cost|worth|"
        r"history|meaning(?!\s+of\s+life)|definition|"
        r"rule|position|stat|statistic)s?"
        r"\s+(?:of|behind|in|for)\s+(?:a\s+|an\s+|the\s+)?",
        "", text, flags=re.I,
    )
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
