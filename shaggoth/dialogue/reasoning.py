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
    r"|\bseparate[sd]?\b|\bsets?\b.+\bapart\b",
    re.I,
)
_CONTRAST = re.compile(
    r"\b(?:similar|similarity|similarities|in common|alike|same as|"
    # "related to" requires the preposition; plain "related" is enough for
    # "how are X and Y related" which asks about their connection, not difference.
    r"related\b|relationship between)\b",
    re.I,
)
_CAUSAL = re.compile(
    r"^\s*(?:and |but |so )?why\b|\bwhat (?:is\s+)?caus(?:es?|ing)\b"
    r"|\bhow (?:is|are|do|does|did|can|could|would|should) .+"
    r"|\bwhat (?:is|are) the (?:cause|process|mechanism|effect|result|purpose|role|function|"
    r"impact|consequence)s? (?:of|behind|in)\b"
    r"|\bwhat (?:leads?|trigger|triggers|drove|drives?|prompts?) .+\b"
    r"|\bwhat happens\b|\bwhat makes\b|\breason (?:for|why)\b"
    # Enabling/blocking verbs — the mechanism rather than the definition
    r"|\bwhat (?:enables?|allows?|permits?|prevents?|blocks?|stops?|inhibits?)\b"
    # Responsibility and necessity ("what is responsible for X", "what is needed for X")
    r"|\bwhat (?:is|are)\s+(?:responsible\s+for|needed\s+for|required\s+for|necessary\s+for)\b"
    # "what is behind X" in the explanatory/causal sense
    r"|\bwhat (?:is|are|lies?)\s+behind\b",
    re.I,
)
_ENUMERATE = re.compile(
    r"\b(?:types? of|kinds? of|sorts? of|categories of|examples? of|"
    r"forms? of|list of|what are the)\b",
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
    r"\s+and\s+",
    r"\s+apart\s+from\s+",         # "sets X apart from Y" after lead-in strip
    r"\s+from\s+",                 # after "what distinguishes" lead-in strip
    r"\s+to\s+",                   # after "compare" lead-in strip
)

# Alternation order matters. Every group in the first branch is optional, so
# it happily matches the empty string at position 0 -- which meant the
# "how are ..." branch was never reached and "how are aeroponics and
# hydroponics similar" yielded the subject "how are aeroponics".
_LEAD_IN = re.compile(
    r"^how (?:is|are|does|do)\s+"
    r"|^what do\s+"
    r"|^what distinguishes\s+"
    r"|^what sets\s+"
    r"|^what separates\s+"
    r"|^in what way(?:s)?\s+(?:is|are|do|does)\s+"
    # "compare X and Y" / "compare X to Y" as an imperative opens with the
    # verb "compare"; stripping it lets the joiner split correctly.
    r"|^compare[ds]?\s+"
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
            if left and right and len(left) > 1 and len(right) > 1:
                return [left, right]
    return []


def subject_of(question: str) -> str:
    """The single subject of a causal or enumerating question."""
    text = (question or "").strip(" ?.")
    text = re.sub(
        r"^(?:and |but |so )?(?:why|what|how)\s+"
        r"(?:is|are|was|were|does|do|did|can|could|would|should|causes?|makes?|happens?)?\s*",
        "", text, flags=re.I,
    )
    text = re.sub(
        r"^(?:the\s+)?(?:types?|kinds?|sorts?|categories|examples?|forms?|list)"
        r"\s+of\s+", "", text, flags=re.I
    )
    text = re.sub(
        r"^(?:the\s+)?(?:cause|process|mechanism|effect|result|purpose|"
        r"role|function|impact|consequence)s?"
        r"\s+(?:of|behind|in)\s+", "", text, flags=re.I,
    )
    # "what leads to X", "what triggers X" → X
    text = re.sub(
        r"^(?:leads?|trigger[sd]?|drove|drives?|prompts?)\s+(?:to\s+)?",
        "", text, flags=re.I,
    )
    # Causal verbs that head the remainder after stripping "what":
    # "what enables X" → "enables X" → "X"
    # "what is causing X" → "causing X" → "X"
    text = re.sub(
        r"^(?:enables?|allows?|permits?|prevents?|blocks?|stops?|inhibits?|"
        r"caus(?:es?|ing))\s+",
        "", text, flags=re.I,
    )
    # "what is responsible for X" → "responsible for X" → "X"
    # "what is needed for X" → "needed for X" → "X"
    # "what is behind X" → "behind X" → "X"
    text = re.sub(
        r"^(?:responsible|needed|required|necessary)\s+for\s+",
        "", text, flags=re.I,
    )
    text = re.sub(r"^behind\s+", "", text, flags=re.I)
    # "the temperature to rise" → strip "to <verb>" infinitive phrase at end
    text = re.sub(r"\s+to\s+\w+(?:ing)?\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+work[s]?\s*$", "", text, flags=re.I)
    # "X are there [in Y]" → X  (e.g. "what kinds of algae are there" → "algae",
    # "what kinds of planets are there in the solar system" → "planets")
    text = re.sub(r"\s+are\s+there\b.*$", "", text, flags=re.I)
    text = re.sub(
        r"\s+(?:need|needs|require|requires|use|uses|produce|produces|"
        r"happen|happens|occur|occurs|exist|exists|matter|matters|"
        r"made|created|formed|produced|prevented|caused|built|done|"
        r"get\s+\w+ed|become|start|begin|"
        # Action verbs trailing the subject in "how do X [verb]" patterns
        r"form[s]?|make[s]?|replicate[s]?|train[s]?|"
        r"grow[s]?|spread[s]?|evolve[s]?|"
        r"emit[s]?|absorb[s]?|reflect[s]?|refract[s]?"
        r")\b.*$",
        "", text, flags=re.I,
    )
    # "X on <modifier>" → X  (e.g. "effect of gravity on time" → "gravity")
    # Only strip trailing "on <1-3 words>" — not "on" inside a topic name.
    text = re.sub(r"\s+on\s+\w+(?:\s+\w+){0,2}\s*$", "", text, flags=re.I)
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
            first = summary.split(". ")[0].strip()
            if not first:
                missing.append(subject)
                continue
            found.append(entry.topic)
            definitions.append((entry.topic, first.rstrip(".") + "."))
            steps.append(Step("lookup", f"{subject} -> {entry.topic}"))

        # If we're missing a subject, try web search to fill the gap.
        if missing and self.search:
            for missing_subject in missing:
                search_snippets, search_results = self._search_web(missing_subject, limit=1)
                if search_snippets:
                    definitions.append((missing_subject, search_snippets[0]))
                    found.append(missing_subject)
                    steps.append(Step("web_search", f"{missing_subject} -> found {len(search_snippets)} result(s)"))
                    missing.remove(missing_subject)
                    break

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
            r"(?i)^(?:what|why)\s+(?:causes?|makes?|produces?|creates?|generates?)\s+",
        )
        if _CAUSE_VERB_Q.match(question):
            s = re.escape(subject)
            bonus = re.compile(
                rf"\b(?:caus|mak)(?:e|es|ed|ing)\s+{s}\b"
                rf"|\b{s}\s+(?:is|are|was|were)\s+(?:caused|produced|generated|created|made)\s+by\b",
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
