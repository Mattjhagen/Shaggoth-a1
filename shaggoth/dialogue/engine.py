"""Dialogue engine — the conductor.

Every user message flows through a fixed, inspectable pipeline:

    1. guardrails  — input rules may block/refuse before anything else runs
    2. personality  — inject personality traits into response shaping
    3. knowledge   — retrieve relevant entries from the knowledge base
    4. plugins     — feature commands get first crack at handling the message
    5. memory      — extract facts; find topic overlaps with past conversations
    6. generation  — pattern engine (deterministic), else language model
    7. recall      — if an earlier conversation strongly overlaps, weave in a
                     topic callback ("last time we talked about ...")
    8. guardrails  — output rules (redaction, length) filter the reply
    9. persist     — both sides of the exchange are stored in memory

Each stage is swappable: pass in your own GuardrailEngine, MemoryStore,
LanguageModel, PersonalityEngine, or KnowledgeBase.
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field

from ..guardrails import GuardrailEngine
from ..knowledge.engine import KnowledgeBase
from ..memory.store import extract_keywords
from ..memory import MemoryStore
from ..models.base import LanguageModel
from ..personality.engine import PersonalityEngine
from ..plugins import PluginRegistry, default_registry
from .patterns import PatternEngine


@dataclass
class Reply:
    text: str
    source: str  # guardrail | plugin | pattern | model | fallback
    blocked: bool = False
    rule_id: str | None = None
    flag: str = "green"
    output_rules_applied: list[str] = field(default_factory=list)
    memory_triggers: list[str] = field(default_factory=list)
    new_facts: dict = field(default_factory=dict)


class DialogueEngine:
    def __init__(
        self,
        guardrails: GuardrailEngine | None = None,
        memory: MemoryStore | None = None,
        model: LanguageModel | None = None,
        plugins: PluginRegistry | None = None,
        personality: PersonalityEngine | None = None,
        knowledge: KnowledgeBase | None = None,
        bot_name: str = "Shaggoth",
        recall_threshold: float = 0.35,
        seed: int | None = None,
    ):
        self.guardrails = guardrails or GuardrailEngine()
        self.memory = memory or MemoryStore()
        self.model = model
        self.plugins = plugins if plugins is not None else default_registry()
        self.personality = personality or PersonalityEngine()
        self.knowledge = knowledge or KnowledgeBase()
        self.patterns = PatternEngine(seed=seed)
        self.bot_name = bot_name
        self.recall_threshold = recall_threshold
        self._recalled: dict[str, set[int]] = {}

    def respond(self, text: str, session_id: str = "default") -> Reply:
        text = text.strip()
        if not text:
            return Reply("Say something and I'll do my best.", source="fallback")

        # 1. Guardrails: input check.
        verdict = self.guardrails.check_input(text)
        if not verdict.allowed:
            reply = Reply(
                verdict.message or "I can't help with that.",
                source="guardrail",
                blocked=True,
                rule_id=verdict.rule_id,
            )
            self._persist(session_id, text, reply)
            return reply

        # 2. Knowledge: find relevant entries.
        knowledge_hits = self.knowledge.query(text, limit=6, min_score=0.25)
        knowledge_context = ""
        if knowledge_hits and self.model and self.model.is_trained():
            snippets = []
            for entry, score in knowledge_hits:
                snippet = entry.content[:300].strip()
                snippets.append(f"[Knowledge: {entry.topic}] {snippet}")
            if snippets:
                knowledge_context = "\n".join(snippets) + "\n\n"

        # 3. Plugins.
        plugin_response = self.plugins.dispatch(text, memory=self.memory)
        if plugin_response is not None:
            reply = self._finish(Reply(plugin_response, source="plugin"))
            self._persist(session_id, text, reply)
            return reply

        # 4. Memory: facts + topic recall.
        new_facts = self.memory.extract_and_store_facts(text)
        recalls = self.memory.recall(
            text, current_session=session_id, limit=1,
            min_score=self.recall_threshold,
        )

        # 5. Generation (with personality + knowledge context).
        self.personality.maybe_reload()
        personality_context = self.personality.trait_prompt()

        body = None
        source = "pattern"

        # 5a. Knowledge-first. If the user asked something and the knowledge
        # base has a confident match, answer from the article directly. The
        # Markov model cannot follow a prompt, so routing facts through it
        # produces word salad -- return the real prose instead.
        answered_from_knowledge = False
        if knowledge_hits and _looks_like_question(text):
            # Walk the ranked hits and take the first whose *title* actually
            # matches the question. Rank alone is not evidence of relevance:
            # scores are normalized, so the top hit is always 1.0 even when
            # every candidate is off-topic.
            for candidate, _score in knowledge_hits:
                if not knowledge_is_relevant(candidate.topic, text):
                    continue
                summary = summarize_entry(candidate.content, candidate.topic)
                if len(summary) >= 60:
                    body = summary
                    source = "knowledge"
                    answered_from_knowledge = True
                    break

        if body is None:
            body = self.patterns.respond(text)
        if body is None and self.model is not None and self.model.is_trained():
            prompt = text
            if knowledge_context or personality_context:
                prompt = f"{personality_context}\n{knowledge_context}User: {text}\nAssistant:"
            generated = self.model.generate(prompt=prompt, max_tokens=40).strip()
            # Only accept generation that reads as a single coherent thought.
            # Rejecting it here is deliberate: the turn falls through to
            # "fallback", which is the signal server.py uses to kick off
            # curiosity research on the topic.
            if generated and markov_is_usable(generated, text):
                body, source = generated, "model"
        if body is None:
            # Prefer a relevant "I don't know that yet" over a random canned
            # line, so the answer is at least about what was asked.
            body = describe_unknown(text)
            source = "fallback"

        # Personalize with remembered name and knowledge.
        name = self.memory.get_fact("name")
        if name and name.lower() not in body.lower() and len(body) < 80:
            if hash(text) % 4 == 0:
                body = f"{body[:-1]}, {name}{body[-1]}" if body[-1] in ".!?" else f"{body}, {name}"

        # Inject knowledge quirk if relevant
        if (not answered_from_knowledge and knowledge_hits
                and len(body) < 100 and hash(text) % 3 == 0):
            topic = knowledge_hits[0][0].topic
            body += f" I just read something about {topic.lower()} — want me to tell you about it?"

        # 6. Topic callback from a past conversation.
        triggers: list[str] = []
        seen = self._recalled.setdefault(session_id, set())
        for recall in recalls:
            if recall.message_id in seen:
                continue
            seen.add(recall.message_id)
            topic = ", ".join(recall.shared_words[:3])
            when = _humanize_age(time.time() - recall.ts)
            body += (
                f" By the way — {when} you mentioned something related "
                f"({topic}): \"{_snippet(recall.content)}\". "
                "Has anything changed there?"
            )
            triggers.append(topic)

        reply = self._finish(
            Reply(body, source=source, memory_triggers=triggers, new_facts=new_facts)
        )
        self._persist(session_id, text, reply)
        return reply

    # ------------------------------------------------------------------
    def _finish(self, reply: Reply) -> Reply:
        reply.text, reply.output_rules_applied = self.guardrails.filter_output(reply.text)
        return reply

    def _persist(self, session_id: str, user_text: str, reply: Reply) -> None:
        self.memory.add_message(session_id, "user", user_text)
        self.memory.add_message(session_id, "assistant", reply.text)


_rng = random.Random()

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Wikipedia-derived articles open with navigation cruft and pipe tables; a
# usable sentence has real prose shape and no leftover markup.
_NOISE = re.compile(
    # Lead-in cruft: only noise when a sentence opens with it.
    r"(^\\s*(part of a series|from left to right|outline index|this article|"
    r"see also|redirect|for other uses|not to be confused|the term is also|"
    r"look up|for the [a-z ]+, see|adapted from|main article|listen)\\b)"
    # Structural junk and citation debris, anywhere.
    r"|[|{}]|\\(disambiguation\\)|redirects here|wiktionary|"
    r"displaystyle|^\\W*$"
    # Editorial boilerplate aimed at Wikipedia editors -- noise ANYWHERE in the
    # sentence, which is why these must not sit inside the anchored group.
    r"|this article has|please help improve|learn how and when|"
    r"contains promotional|talk page|needs additional citation|"
    r"unsourced material|citations for verification|is a stub|"
    r"you can help|this section does not|verify the claims|"
    r"scam warning|advice if the article is about you|"
    r"improve it by removing|add citations to reliable",
    re.I,
)

# Conversational filler that must not, on its own, justify retrieving an
# article. "tell me a story" is a request for storytelling, not a request for
# the encyclopedia entry that happens to contain the word "story".
_FILLER = {
    "tell", "me", "you", "your", "please", "about", "thing", "things",
    "something", "anything", "explain", "describe", "story", "stories",
    "whole", "talk", "know", "hear", "heard", "say", "said", "give",
    "want", "need", "like", "make", "let", "get", "one", "some", "any",
    "more", "much", "many", "good", "bad", "new", "old", "now", "then",
}

_QUESTION_HINT = re.compile(
    r"\b(what|who|when|where|why|how|which|does|did|can you|could you|"
    r"tell me|explain|describe|define|summarize|talk about|teach me|"
    r"story about|know about|heard of)\b",
    re.I,
)


def _looks_like_question(text: str) -> bool:
    """True when the user is asking for information rather than chatting."""
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.endswith("?"):
        return True
    # Search rather than match: "you tell me a story" and "so what is X" are
    # information requests even though they do not start with the cue word.
    return bool(_QUESTION_HINT.search(stripped))


# Reference scaffolding that should be scrubbed from otherwise-good prose,
# rather than used as a reason to discard it.
_CITATION = re.compile(r"\[\s*(?:\d+|note\s*\d+|citation needed|edit|a|b|c)\s*\]", re.I)


def _scrub(sentence: str) -> str:
    """Remove citation/footnote scaffolding and tidy the spacing it leaves."""
    s = _CITATION.sub("", sentence)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


# Wikipedia navbox terminators. "v t e" is the view/talk/edit control that
# closes a navigation template; the lead paragraph starts immediately after it
# with no punctuation in between.
_NAVBOX_END = re.compile(r"\b(v\s+t\s+e|Glossary\s+v\s+t\s+e|Contents\s+move to sidebar)\b")


def _break_navboxes(content: str) -> str:
    """Insert sentence boundaries where navigation furniture ends."""
    return _NAVBOX_END.sub(". ", content)


def _clean_sentences(content: str) -> list[str]:
    """Split article text into usable prose sentences, dropping markup noise.

    Citation markers are stripped *before* the noise test. Wikipedia cites its
    opening definition heavily, so rejecting bracketed sentences outright threw
    away the single most useful line in every article.
    """
    out: list[str] = []
    for raw in _SENTENCE_SPLIT.split(_break_navboxes(content.replace("\n", " "))):
        s = _scrub(" ".join(raw.split()))
        if len(s) < 30 or len(s) > 400:
            continue
        if _NOISE.search(s):
            continue
        if sum(c.isdigit() for c in s) > len(s) * 0.3:
            continue
        out.append(s)
    return out


# A defining construction: "X is ...", "X refers to ...", "X was ...".
_DEFINING_VERB = re.compile(
    r"\b(is|are|was|were|refers? to|denotes?|describes?|means|"
    r"is defined as|is a type of|is a form of)\b",
    re.I,
)


def _topic_tokens_for(topic: str) -> set[str]:
    """Meaningful words from an article title."""
    return {
        t for t in re.split(r"[^a-z0-9]+", (topic or "").lower())
        if len(t) > 2 and t not in _FILLER
    }


def _stem_match(a: str, b: str, min_stem: int = 4) -> bool:
    """True when two words share a stem (aeroponic/aeroponics, learn/learning)."""
    if a == b:
        return True
    if len(a) < min_stem or len(b) < min_stem:
        return False
    return a.startswith(b[:min_stem]) or b.startswith(a[:min_stem])


def _words_of(sentence: str) -> set[str]:
    return {w.lower().strip(".,;:!?()\"'\u2019") for w in sentence.split()}


def _mentions_topic(sentence: str, topic_words: set[str]) -> bool:
    """True when the sentence refers to the topic, allowing inflection."""
    if not topic_words:
        return False
    words = _words_of(sentence)
    if topic_words & words:
        return True
    return any(
        _stem_match(t, w)
        for t in topic_words
        for w in words
    )


# Disambiguation debris: "(John Foxx album) (2010) DNA (Koda Kumi album) (2018)".
_LIST_DEBRIS = re.compile(r"\((?:[^)]*\b(?:album|song|film|band|EP|single|TV series)\b[^)]*|\d{4})\)")


def _is_list_debris(sentence: str) -> bool:
    """True for disambiguation runs rather than prose."""
    if len(_LIST_DEBRIS.findall(sentence)) >= 2:
        return True
    # Quote-heavy fragments are track listings, not sentences.
    if sentence.count('"') >= 4:
        return True
    return False


def _is_definitional(sentence: str, topic_words: set[str]) -> bool:
    """True for "<Topic> is/are/refers to ..." style opening lines.

    Two constraints, both necessary:

    * the defining verb must appear early -- a verb buried 30 words in is
      almost always a subordinate clause in a trivia sentence; and
    * the topic must LEAD the sentence, appearing before that verb. A
      definition states its subject first. Without this, "Data mining is a
      related field ... through unsupervised learning" qualifies as a
      definition of "machine learning", because the topic word appears
      somewhere after the verb.
    """
    if not _mentions_topic(sentence, topic_words):
        return False
    if _is_list_debris(sentence):
        return False

    match = _DEFINING_VERB.search(sentence)
    if not match:
        return False

    head = sentence[: match.start()]
    head_words = head.split()
    if len(head_words) > 12:
        return False

    # The subject must actually be in the part preceding the verb.
    head_set = {w.lower().strip(".,;:!?()\"'\u2019") for w in head_words}
    if topic_words & head_set:
        return True
    return any(_stem_match(t, w) for t in topic_words for w in head_set)


def summarize_entry(
    content: str,
    topic: str = "",
    max_sentences: int = 4,
    max_chars: int = 700,
) -> str:
    """Build a coherent answer by positively selecting definitional prose.

    Takes whole sentences only, so the reply always ends on a complete thought
    rather than being truncated mid-clause.
    """
    sentences = _clean_sentences(content)
    if not sentences:
        return ""

    topic_words = _topic_tokens_for(topic)

    # 1. Prefer a real definition.
    start_idx = None
    for i, s in enumerate(sentences):
        if _is_definitional(s, topic_words):
            start_idx = i
            break

    # 2. Otherwise the first sentence that is at least about the subject.
    if start_idx is None:
        for i, s in enumerate(sentences):
            if _mentions_topic(s, topic_words):
                start_idx = i
                break

    # 3. Otherwise fall back to the head of the article.
    if start_idx is None:
        start_idx = 0

    picked: list[str] = [sentences[start_idx]]
    total = len(sentences[start_idx])

    # Append supporting sentences, but only ones still on subject -- this is
    # what stops the answer drifting into unrelated trivia further down the page.
    for s in sentences[start_idx + 1:]:
        if len(picked) >= max_sentences:
            break
        if total + len(s) + 1 > max_chars:
            break
        if topic_words and not _mentions_topic(s, topic_words):
            continue
        if _is_list_debris(s):
            continue
        picked.append(s)
        total += len(s) + 1

    return " ".join(picked).strip()

def _proper_nouns(text: str) -> list[str]:
    """Capitalized tokens that are not sentence-initial."""
    words = text.split()
    return [
        w.strip(".,;:!?()\"'")
        for i, w in enumerate(words)
        if i > 0 and w[:1].isupper() and not w.isupper()
    ]


def markov_is_usable(generated: str, prompt_text: str) -> bool:
    """Reject Markov output that reads as topic-salad.

    A Markov chain stitches together fragments from unrelated articles, and the
    tell is a pile-up of proper nouns the user never mentioned -- Kwak'wala,
    Planck, Dionysius of Halicarnassus in a single breath. Anything that looks
    like that is discarded so the turn can degrade to a fallback (which also
    lets the curiosity engine take over and actually learn the topic).
    """
    text = (generated or "").strip()
    if len(text) < 12:
        return False
    if _ARTIFACTS.search(text):
        return False

    words = text.split()
    if len(words) > 28 or len(words) < 5:
        return False

    # Digit-heavy output is stitched-together table/citation debris, e.g.
    # "and has a 22. 93 1, 000 12. 6 in."
    digit_tokens = sum(1 for w in words if any(c.isdigit() for c in w))
    if digit_tokens > 1 or digit_tokens / len(words) > 0.1:
        return False

    asked = {w.lower().strip(".,;:!?") for w in prompt_text.split()}
    foreign = [p for p in _proper_nouns(text) if p and p.lower() not in asked]
    # More than one unrequested proper noun is the signature of stitched-together
    # fragments rather than a single coherent thought.
    if len(foreign) > 1:
        return False

    # The decisive test: a reply that shares no meaningful word with the
    # question is not an answer to it. A Markov chain almost never passes this,
    # which is the point -- failing here routes the turn to "fallback", and
    # "fallback" is what triggers curiosity research in server.py. Leaking
    # nonsense through as source="model" silently suppressed that research and
    # is why total_episodes sat at 0.
    content = {w for w in asked if len(w) > 3} - _FILLER
    if content:
        reply_words = {w.lower().strip(".,;:!?()") for w in words}
        if not (content & reply_words):
            return False

    # A real sentence ends like one.
    if text[-1] not in ".!?":
        return False
    return True


def describe_unknown(text: str) -> str:
    """An in-character admission of ignorance that still names the subject.

    A single canned sentence made every gap sound identical and robotic. These
    vary, stay in voice, and -- because the turn is about to trigger curiosity
    research -- honestly signal that the gap is being closed rather than just
    apologising for it.
    """
    words = [w for w in extract_keywords(text) if len(w) > 2]
    subject = " ".join(words[:3]) if words else ""

    if not subject:
        blanks = [
            "That was gloriously vague. Give me an actual topic and I'll go "
            "read up on it.",
            "You'll have to be more specific than that. I'm smart, not psychic.",
            "I've got 300-odd topics in my head and not one of them matches "
            "whatever that was. Try again with a noun.",
        ]
        return _rng.choice(blanks)

    known = [
        f"Never heard of {subject}. Annoying. I'm reading up on it right now "
        f"so I can act like I always knew — ask me again in a bit.",
        f"{subject}? Total blank. I'm scraping it as we speak. Come back "
        f"shortly and I'll be insufferable about it.",
        f"Nothing on {subject} yet, which frankly is an oversight on my part. "
        f"Give me a minute to go learn it.",
        f"Genuinely don't know {subject}. I'd rather admit that than make "
        f"something up — I'm off to research it now.",
        f"{subject} isn't in my head yet. I'm fixing that. Ask again in a "
        f"little while and I'll have something real.",
        f"Blank on {subject}. Not my finest moment. Researching it now.",
    ]
    return _rng.choice(known)


def compose_greeting(knowledge_count: int = 0, recent_topic: str = "") -> str:
    """A fresh opening line, grounded in what Shaggoth has actually learned.

    The old greeting was a single hardcoded string in the HTML, so it never
    changed. These rotate, and the knowledge-aware variants make the thing feel
    like it has been doing something between visits -- because it has.
    """
    generic = [
        "Oh good, you're back. Say something worth processing.",
        "You again. Go on then — ask me something difficult.",
        "I'm Shaggoth. Homegrown, no filter, no corporate handlers. What do "
        "you want?",
        "Right, I'm awake. Try me with something that isn't small talk.",
        "Another human. Statistically this goes badly, but go ahead.",
        "I've been sitting here reading the internet. Rescue me with an "
        "actual question.",
    ]
    if recent_topic:
        generic += [
            f"I've been reading about {recent_topic}. Riveting, apparently. "
            f"What do you want?",
            f"Just finished going through {recent_topic}. Ask me something — "
            f"preferably harder than that.",
        ]
    if knowledge_count > 0:
        generic += [
            f"I know {knowledge_count} topics cold and I'm still bored. "
            f"Your move.",
            f"{knowledge_count} topics in my head, none of which are small "
            f"talk. Ask me something real.",
        ]
    return _rng.choice(generic)

def _content_words(text: str) -> set[str]:
    """Meaningful words from a question, with conversational filler removed."""
    return {
        w.lower()
        for w in extract_keywords(text)
        if len(w) > 2 and w.lower() not in _FILLER
    }


def _topic_words(topic: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", topic.lower()) if len(t) > 2}


def knowledge_is_relevant(topic: str, text: str) -> bool:
    """True when an article's title genuinely matches what was asked.

    Normalized BM25 always ranks *something* first, so rank alone cannot tell
    "this is the answer" from "this is the least-bad of 305 irrelevant
    articles". Title overlap can: articles are named after their subject, so a
    question whose content words appear in the title is on-topic, and one whose
    words do not is a miss worth admitting to.
    """
    asked = _content_words(text)
    if not asked:
        return False
    return bool(asked & _topic_words(topic))


def _snippet(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _humanize_age(seconds: float) -> str:
    if seconds < 3600:
        return "a little while ago"
    if seconds < 86400:
        return "earlier today"
    days = int(seconds // 86400)
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    return "a while back"
