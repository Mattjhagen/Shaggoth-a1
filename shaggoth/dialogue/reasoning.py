"""Multi-step reasoning over the knowledge base.

Retrieval answers "what is X" by finding the best entry and quoting it. That
is all Shaggoth could do: ask it to *compare* two things and it returned one
of them and ignored the other -- "what is the difference between aeroponics
and hydroponics" answered with the hydroponics article and never mentioned
aeroponics.

This module does the part retrieval cannot: work out what a question is
actually asking for, gather the *several* pieces needed, and combine them.

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

import re
from dataclasses import dataclass, field
from typing import Callable, Optional


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
    r"\b(?:difference|differences|differ|distinguish|distinction)\b"
    # "compare X to Y" puts the subject between the verb and the preposition,
    # so this cannot require them to be adjacent.
    r"|\bcompare[ds]?\b.*\b(?:to|with|against)\b|^\s*compare\b"
    r"|\bversus\b|\bvs\.?\b|\bagainst\b"
    # "why is X different from Y" is a comparison that happens to open with
    # "why"; classify() checks COMPARE first precisely so it lands here.
    r"|\b(?:how|why|in what way(?:s)?) (?:is|are|does|do) .+ different\b",
    re.I,
)
_CONTRAST = re.compile(
    r"\b(?:similar|similarity|similarities|in common|alike|same as|"
    r"related to|relationship between)\b",
    re.I,
)
_CAUSAL = re.compile(
    r"^\s*(?:and |but |so )?why\b|\bwhat causes\b|\bhow does .+ work\b"
    r"|\bwhat makes\b|\breason (?:for|why)\b",
    re.I,
)
_ENUMERATE = re.compile(
    r"\b(?:types? of|kinds? of|sorts? of|categories of|examples? of|"
    r"forms? of|list of|what are the)\b",
    re.I,
)

#: Two subjects joined. "and" is deliberately last: "difference between X and
#: Y" is far more common than "X vs Y", but "and" also appears inside subject
#: names, so the more explicit joiners get first refusal.
_JOINERS = (
    r"\s+versus\s+", r"\s+vs\.?\s+", r"\s+compared\s+to\s+",
    r"\s+compared\s+with\s+", r"\s+against\s+", r"\s+and\s+",
)

# Alternation order matters. Every group in the first branch is optional, so
# it happily matches the empty string at position 0 -- which meant the
# "how are ..." branch was never reached and "how are aeroponics and
# hydroponics similar" yielded the subject "how are aeroponics".
_LEAD_IN = re.compile(
    r"^how (?:is|are|does|do)\s+"
    r"|^what do\s+"
    r"|^in what way(?:s)?\s+(?:is|are|do|does)\s+"
    r"|^(?:what(?:'s| is| are)?\s+)?(?:the\s+)?"
    r"(?:difference|differences|distinction|similarity|similarities)?\s*"
    r"(?:between\s+)?",
    re.I,
)
_TRAILING = re.compile(
    r"\s*(?:different|differ|similar|alike|in common|have in common|"
    r"compare|from each other|to each other)\s*\??\s*$",
    re.I,
)


def classify(question: str) -> str:
    """What kind of work the question needs. Order matters.

    Comparison is checked before causation because "why is X different from
    Y" is a comparison that happens to start with "why".
    """
    text = (question or "").strip()
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
    text = _LEAD_IN.sub("", (question or "").strip(), count=1)
    text = _TRAILING.sub("", text).strip(" ?.")
    for joiner in _JOINERS:
        parts = re.split(joiner, text, maxsplit=1, flags=re.I)
        if len(parts) == 2:
            left, right = (p.strip(" ?.,") for p in parts)
            if left and right and len(left) > 2 and len(right) > 2:
                return [left, right]
    return []


def subject_of(question: str) -> str:
    """The single subject of a causal or enumerating question."""
    text = (question or "").strip(" ?.")
    text = re.sub(
        r"^(?:and |but |so )?(?:why|what|how)\s+"
        r"(?:is|are|was|were|does|do|did|causes?|makes?)?\s*", "", text, flags=re.I
    )
    text = re.sub(
        r"^(?:the\s+)?(?:types?|kinds?|sorts?|categories|examples?|forms?|list)"
        r"\s+of\s+", "", text, flags=re.I
    )
    text = re.sub(r"\s+work[s]?\s*$", "", text, flags=re.I)
    # Trailing verb phrase: "photosynthesis need light" -> "photosynthesis".
    # The subject is what to look up; the rest is what to look *for*, and
    # carrying it into retrieval only dilutes the query.
    text = re.sub(
        r"\s+(?:need|needs|require|requires|use|uses|produce|produces|"
        r"happen|happens|occur|occurs|exist|exists|matter|matters)\b.*$",
        "", text, flags=re.I,
    )
    return text.strip(" ?.,")


# -- sentence selection ----------------------------------------------------

_CAUSAL_MARKER = re.compile(
    r"\b(?:because|since|due to|owing to|as a result|therefore|thus|hence|"
    r"which causes|causes|caused by|results? in|results? from|so that|"
    r"in order to|allows?|enables?|requires?|depends? on)\b",
    re.I,
)
_ENUM_MARKER = re.compile(
    r"\b(?:include[sd]?|including|such as|categor(?:y|ies|ised|ized)|"
    r"classified|types?|kinds?|forms?|divided into|consists? of|"
    r"comprises?|namely|for example|e\.g\.)\b",
    re.I,
)


#: A sentence opening on a referring pronoun is still about the entry's
#: subject -- "It requires light because chlorophyll absorbs photons" is the
#: explanation, and demanding the literal topic word would discard it.
_REFERRING = re.compile(r"^\s*(?:it|its|they|their|these|those|this|such)\b", re.I)


def _pick(sentences, marker, topic_words, limit, min_len=40):
    """Sentences matching ``marker`` that are still about the topic.

    The entry has already been selected as being about the subject, so a
    sentence that refers back with a pronoun counts. Requiring the literal
    topic word in every sentence threw away most real explanations, which
    are written exactly that way.
    """
    chosen = []
    for sentence in sentences:
        if len(sentence) < min_len:
            continue
        if not marker.search(sentence):
            continue
        lowered = sentence.lower()
        on_topic = (
            not topic_words
            or any(w in lowered for w in topic_words)
            or _REFERRING.match(sentence)
        )
        if not on_topic:
            continue
        chosen.append(sentence)
        if len(chosen) >= limit:
            break
    return chosen


def _topic_words(text: str) -> set:
    return {w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(w) > 3}


# -- the reasoner ----------------------------------------------------------

class Reasoner:
    """Answers questions that need more than one lookup.

    ``knowledge`` is a KnowledgeBase; ``summarize`` and ``sentences`` are
    passed in rather than imported so this module stays free of a circular
    dependency on the dialogue engine, and so both can be stubbed in tests.
    """

    def __init__(
        self,
        knowledge,
        summarize: Callable[[str, str], tuple],
        sentences: Callable[[str], list],
        relevant: Optional[Callable[[str, str, str], bool]] = None,
    ) -> None:
        self.knowledge = knowledge
        self.summarize = summarize
        self.sentences = sentences
        self.relevant = relevant

    # -- entry lookup ------------------------------------------------------

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
            first = summary.split(". ")[0].strip()
            if not first:
                missing.append(subject)
                continue
            found.append(entry.topic)
            definitions.append((entry.topic, first.rstrip(".") + "."))
            steps.append(Step("lookup", f"{subject} -> {entry.topic}"))

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

        joiner = (
            "The difference is in those two descriptions"
            if intent == Intent.COMPARE
            else "What they share is in those two descriptions"
        )
        steps.append(Step("combine", f"contrasted {len(definitions)} definitions"))
        body = " ".join(f"{t}: {d}" for t, d in definitions)
        return Reasoned(
            answer=f"{body} {joiner} — I'm laying them side by side, not "
                   f"interpreting them for you.",
            intent=intent,
            steps=steps,
            entries_used=found,
        )

    # -- causation ---------------------------------------------------------

    def _causal(self, question: str) -> Optional[Reasoned]:
        subject = subject_of(question)
        if len(subject) < 3:
            return None
        steps = [Step("intent", "causal -- looking for explanation, not definition")]
        steps.append(Step("subject", subject))

        entry = self._best_entry(subject)
        if entry is None:
            return None
        steps.append(Step("lookup", f"{subject} -> {entry.topic}"))

        picked = _pick(
            self.sentences(entry.content), _CAUSAL_MARKER, _topic_words(subject), limit=3
        )
        if not picked:
            steps.append(Step("result", "no explanatory sentences in that entry"))
            return None
        steps.append(Step("select", f"{len(picked)} explanatory sentence(s)"))
        return Reasoned(
            answer=" ".join(picked),
            intent=Intent.CAUSAL,
            steps=steps,
            entries_used=[entry.topic],
        )

    # -- enumeration -------------------------------------------------------

    def _enumerate(self, question: str) -> Optional[Reasoned]:
        subject = subject_of(question)
        if len(subject) < 3:
            return None
        steps = [Step("intent", "enumerate -- looking for a list, not a definition")]
        steps.append(Step("subject", subject))

        entry = self._best_entry(subject)
        if entry is None:
            return None
        steps.append(Step("lookup", f"{subject} -> {entry.topic}"))

        picked = _pick(
            self.sentences(entry.content), _ENUM_MARKER, _topic_words(subject), limit=3
        )
        if not picked:
            steps.append(Step("result", "nothing enumerating in that entry"))
            return None
        steps.append(Step("select", f"{len(picked)} enumerating sentence(s)"))
        return Reasoned(
            answer=" ".join(picked),
            intent=Intent.ENUMERATE,
            steps=steps,
            entries_used=[entry.topic],
        )
