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
from typing import Any, Optional

from ..guardrails import GuardrailEngine
from ..knowledge.engine import KnowledgeBase
from ..memory.store import extract_keywords
from ..memory import MemoryStore
from ..models.base import LanguageModel
from ..personality.engine import PersonalityEngine
from ..plugins import PluginRegistry, default_registry
from .patterns import PatternEngine
from .reasoning import Reasoner
from ..curiosity.search import search_web


#: Associative mode. The Markov model may speak, the knowledge teaser may
#: fire, and past conversations may be woven back in. Answers wander.
DRIFT = "drift"

#: Grounded mode. Knowledge and patterns only -- no Markov generation, no
#: "want me to tell you about it?" teaser, no topic callbacks. Every reply
#: is either something Shaggoth actually knows or an honest admission that
#: it does not. This is the mode the IDE integration uses: a tangent in the
#: middle of a code answer is worse than no answer.
NO_DRIFT = "no_drift"

VALID_MODES = (DRIFT, NO_DRIFT)

#: Default when a request does not specify. Grounded, because the expensive
#: failure is a confident tangent, not a terse answer.
DEFAULT_MODE = NO_DRIFT


def normalize_mode(value, default: str = DEFAULT_MODE) -> str:
    """Coerce a caller-supplied mode into ``DRIFT`` or ``NO_DRIFT``.

    Accepts the literal mode names, and the booleans a JSON client is
    likely to send for a field named ``drift``. Anything unrecognised falls
    back to ``default`` rather than raising -- a malformed mode should not
    cost the user their answer.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return DRIFT if value else NO_DRIFT
    text = str(value).strip().lower()
    if text in VALID_MODES:
        return text
    if text in ("true", "1", "yes", "on", "wander", "free"):
        return DRIFT
    if text in ("false", "0", "no", "off", "strict", "grounded"):
        return NO_DRIFT
    return default


@dataclass
class Reply:
    text: str
    source: str  # guardrail | plugin | knowledge | pattern | model | fallback
    blocked: bool = False
    rule_id: str | None = None
    flag: str = "green"
    output_rules_applied: list[str] = field(default_factory=list)
    memory_triggers: list[str] = field(default_factory=list)
    new_facts: dict = field(default_factory=dict)
    mode: str = DEFAULT_MODE
    #: The steps taken when the answer required more than one lookup.
    reasoning: list = field(default_factory=list)
    #: Knowledge entries the answer was built from.
    entries_used: list = field(default_factory=list)


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
        mode: str = DEFAULT_MODE,
        deferred_questions: Optional[Any] = None,
        push_sender: Optional[Any] = None,
    ):
        self.guardrails = guardrails or GuardrailEngine()
        self.memory = memory or MemoryStore()
        self.model = model
        self.plugins = plugins if plugins is not None else default_registry()
        self.personality = personality or PersonalityEngine()
        self.knowledge = knowledge or KnowledgeBase()
        self.patterns = PatternEngine(seed=seed)
        self.reasoner = Reasoner(
            self.knowledge,
            summarize=summarize_entry_scored,
            sentences=_clean_sentences,
            search=search_web,
        )
        self.bot_name = bot_name
        self.recall_threshold = recall_threshold
        #: Instance-wide default, overridable per request.
        self.mode = normalize_mode(mode)
        self._recalled: dict[str, set[int]] = {}
        self.deferred_questions = deferred_questions
        self.push_sender = push_sender

    def respond(self, text: str, session_id: str = "default", mode=None) -> Reply:
        """Answer ``text``.

        ``mode`` selects :data:`DRIFT` or :data:`NO_DRIFT` for this request
        only, falling back to the engine's configured default. See the
        module constants for what each mode allows.
        """
        mode = normalize_mode(mode, default=self.mode)
        drift = mode == DRIFT

        text = text.strip()
        if not text:
            return Reply("Say something and I'll do my best.", source="fallback", mode=mode)

        # 1. Guardrails: input check.
        verdict = self.guardrails.check_input(text)
        if not verdict.allowed:
            reply = Reply(
                verdict.message or "I can't help with that.",
                source="guardrail",
                blocked=True,
                rule_id=verdict.rule_id,
                mode=mode,
            )
            self._persist(session_id, text, reply)
            return reply

        # 2. Conversation context: what has already been said here.
        #
        # Every reply used to be computed from the current message alone, so
        # "has it been a bit" had nothing to refer back to and fell through to
        # "Never heard of it".
        try:
            context = self.memory.conversation_context(session_id)
        except Exception:  # noqa: BLE001
            context = {}

        # 3. Knowledge: find relevant entries.
        knowledge_hits = self.knowledge.query(text, limit=6, min_score=0.25)
        knowledge_context = ""
        if knowledge_hits and self.model and self.model.is_trained():
            snippets = []
            for entry, score in knowledge_hits:
                # Only inject knowledge that actually matches the question.
                # Without this check, a Cold War article matched "Are there
                # Russians in Moscow?" by co-occurrence and GPT reported Cold War
                # history as the answer to a basic geography question.
                if not knowledge_is_relevant(entry.topic, text, entry.content):
                    continue
                snippet = entry.content[:300].strip()
                snippets.append(f"[Knowledge: {entry.topic}] {snippet}")
            if snippets:
                knowledge_context = "\n".join(snippets) + "\n\n"

        # 3. Plugins.
        plugin_response = self.plugins.dispatch(text, memory=self.memory)
        if plugin_response is not None:
            reply = self._finish(Reply(plugin_response, source="plugin", mode=mode))
            self._persist(session_id, text, reply)
            return reply

        # A turn with no subject is conversation, not a lookup. Answering it
        # from the knowledge base produced "Never heard of wanted chat" and,
        # because that came back as a fallback, kicked off curiosity research
        # on a phrase nobody meant as a topic.
        #
        # This runs *after* plugins: "what is 6 * 7?" and "what do you know
        # about me?" are made entirely of filler words but are real commands.
        if not has_subject(text):
            body = (
                follow_up_reply(context) if is_follow_up(text)
                else chitchat_reply(text, context)
            )
            reply = self._finish(Reply(body, source="pattern", mode=mode))
            self._persist(session_id, text, reply)
            return reply

        # 4. Memory: facts always; topic recall only when drifting. A
        # callback to an unrelated past conversation is the textbook
        # tangent NO_DRIFT exists to prevent.
        new_facts = self.memory.extract_and_store_facts(text)
        recalls = (
            self.memory.recall(
                text, current_session=session_id, limit=1,
                min_score=self.recall_threshold,
            )
            if drift
            else []
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
        reasoning_steps: list = []
        entries_used: list = []

        # 5a. Reasoning first, for questions a single entry cannot answer.
        # "what is the difference between aeroponics and hydroponics" used to
        # return the hydroponics article and never mention aeroponics.
        if _looks_like_question(text) and not is_follow_up(text):
            try:
                reasoned = self.reasoner.reason(text)
            except Exception as exc:  # noqa: BLE001
                print(f"[reasoning] failed on {text!r}: {exc}")
                reasoned = None
            if reasoned and len(reasoned.answer) >= 40:
                body = reasoned.answer
                source = "reasoning"
                answered_from_knowledge = True
                reasoning_steps = reasoned.trace
                entries_used = reasoned.entries_used

        if body is None and knowledge_hits and _looks_like_question(text) and not is_follow_up(text):
            # Walk the ranked hits and take the first whose *title* actually
            # matches the question. Rank alone is not evidence of relevance:
            # scores are normalized, so the top hit is always 1.0 even when
            # every candidate is off-topic.
            #
            # Two passes, and the order matters. Several articles can share a
            # title -- "DNA" the molecule and "DNA²" the manga both match the
            # word "dna" -- so a first pass takes only a candidate that yields
            # an actual *definition*, and the lenient pass runs only if no
            # candidate defines anything. Without the split, whichever
            # off-subject article happened to rank highest answered first.
            best_loose = None
            for candidate, _score in knowledge_hits:
                if not knowledge_is_relevant(candidate.topic, text, candidate.content):
                    continue
                summary, is_definition = summarize_entry_scored(
                    candidate.content, candidate.topic
                )
                if len(summary) < 60:
                    continue
                if is_definition:
                    body = summary
                    source = "knowledge"
                    answered_from_knowledge = True
                    entries_used = [candidate.topic]
                    reasoning_steps = [
                        f"intent: define -- one entry answers this",
                        f"lookup: {candidate.topic}",
                        "select: definitional lead sentence",
                    ]
                    break
                if best_loose is None:
                    best_loose = summary
            if body is None and best_loose is not None:
                body = best_loose
                source = "knowledge"
                answered_from_knowledge = True

        if body is None:
            body = self.patterns.respond(text)

        # 5b. GPT generation — preferred over Markov when available.
        # GPT can follow the prompt and stay in character, so it works in both
        # drift and no_drift modes. It's tried whenever the pattern engine and
        # knowledge base haven't produced an answer yet.
        from ..models.openai_model import OpenAIModel
        _gpt = self.model if isinstance(self.model, OpenAIModel) else None
        if body is None and _gpt is not None and _gpt.configured:
            # Build recent conversation history for GPT context.
            history = [
                {"role": m["role"], "content": m["content"]}
                for m in context.get("recent", [])
            ]
            generated = _gpt.generate_chat(
                user_message=text,
                knowledge_context=knowledge_context,
                conversation_history=history,
                personality_context=personality_context,
            ).strip()
            if generated:
                body, source = generated, "model"

        # 5c. Markov generation is DRIFT-only and runs only when GPT is absent.
        # The model stitches fragments from unrelated articles and cannot hold a
        # topic, so in NO_DRIFT it is skipped entirely — the turn falls through
        # to "fallback", which is the signal server.py uses to kick off curiosity
        # research on the topic.
        if drift and body is None and self.model is not None and self.model.is_trained() and _gpt is None:
            prompt = text
            if knowledge_context or personality_context:
                prompt = f"{personality_context}\n{knowledge_context}User: {text}\nAssistant:"
            generated = self.model.generate(prompt=prompt, max_tokens=40).strip()
            # Only accept generation that reads as a single coherent thought.
            if generated and markov_is_usable(generated, text):
                body, source = generated, "model"

        if body is None:
            if is_follow_up(text):
                # "why?" is not a research topic. Keep it in the conversation
                # rather than admitting ignorance of the word "why".
                body = follow_up_reply(context)
                source = "pattern"
            else:
                # Prefer a relevant "I don't know that yet" over a random
                # canned line, so the answer is at least about what was asked.
                body = describe_unknown(text)
                source = "fallback"

        # Personalize with remembered name and knowledge.
        name = self.memory.get_fact("name")
        if name and name.lower() not in body.lower() and len(body) < 80:
            if hash(text) % 4 == 0:
                body = f"{body[:-1]}, {name}{body[-1]}" if body[-1] in ".!?" else f"{body}, {name}"

        # Inject knowledge quirk if relevant. DRIFT-only: offering a tangent
        # instead of answering is precisely the "never completes a thought"
        # behaviour, and it has no place in a grounded reply.
        if (drift and not answered_from_knowledge and knowledge_hits
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
            Reply(body, source=source, memory_triggers=triggers,
                  new_facts=new_facts, mode=mode,
                  reasoning=reasoning_steps, entries_used=entries_used)
        )
        self._persist(session_id, text, reply)

        # Record deferred questions and notify when research starts
        if source == "fallback" and self.deferred_questions:
            from ..curiosity.topics import extract_topic_query
            topic = extract_topic_query(text)
            deferred = None
            if topic:
                deferred = self.deferred_questions.record(text, topic, session_id=session_id)
            if deferred and self.push_sender:
                # Notify user that we're researching their question
                try:
                    self.push_sender.notify_session(
                        session_id,
                        title="Researching Your Question",
                        body=f"Looking into: {text[:60]}{'...' if len(text) > 60 else ''}",
                        tag="research_started",
                    )
                except Exception:
                    pass  # Push notification is optional

        return reply

    # ------------------------------------------------------------------
    def _finish(self, reply: Reply) -> Reply:
        reply.text, reply.output_rules_applied = self.guardrails.filter_output(reply.text)
        return reply

    def _persist(self, session_id: str, user_text: str, reply: Reply) -> None:
        self.memory.add_message(session_id, "user", user_text)
        self.memory.add_message(session_id, "assistant", reply.text)
        # Fold older turns into a summary once the session is long enough.
        # Best-effort: losing a compaction is not worth failing the reply.
        try:
            self.memory.maybe_compact(session_id)
        except Exception as exc:  # noqa: BLE001
            print(f"[memory] compaction failed: {exc}")


_rng = random.Random()

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Wikipedia-derived articles open with navigation cruft and pipe tables; a
# usable sentence has real prose shape and no leftover markup.
#
# NOTE: the escapes here are single-backslash on purpose. An earlier revision
# had `\\s`/`\\b`/`\\(` inside these raw strings -- doubled by a heredoc during
# editing -- which in a raw string is a *literal backslash* followed by the
# letter. That silently killed the entire anchored lead-in group (it could only
# match a sentence beginning with a backslash), which is why "For other uses,
# see ..." kept leaking through into answers.
_NOISE = re.compile(
    # Lead-in cruft: only noise when a sentence opens with it.
    r"(^\s*(part of a series|from left to right|outline index|this article|"
    r"see also|redirect|for other uses|not to be confused|the term is also|"
    r"look up|for the [a-z ]+, see|adapted from|main article|listen)\b)"
    # Structural junk and citation debris, anywhere.
    r"|[|{}]|\(disambiguation\)|redirects here|wiktionary|"
    r"displaystyle|^\W*$"
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

# Encyclopedia scaffolding that can never appear in a genuine conversational
# reply. The Markov model is trained on the scraped corpus, so when it stitches
# fragments together it drags this along with them -- navbox controls ("v t e"),
# citation apparatus, and reference-list furniture. Any hit means the output is
# corpus debris rather than a sentence, and the turn is better off degrading to
# a fallback (which is also what lets curiosity research kick in).
_ARTIFACTS = re.compile(
    r"\bv\s+t\s+e\b|\[\s*edit\s*\]|\[\s*citation needed\s*\]|"
    r"\bretrieved from\b|\barchived from the original\b|\bmain article\b|"
    r"\bsee also\b|\bdisambiguation\b|\bISBN\b|\bdoi:|\bet al\.|"
    r"\bpp?\.\s*\d|\bISSN\b|\bcategories?:|\bjump to\b|\bmove to sidebar\b|"
    r"\^\s*a\s+b\b|\bhttps?://",
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
_CITATION = re.compile(
    r"\[\s*(?:\d+|note\s*\d+|citation needed|edit(?:\s+on\s+wikidata)?|"
    r"nb\s*\d+|a|b|c)\s*\]",
    re.I,
)


def _scrub(sentence: str) -> str:
    """Remove citation/footnote scaffolding and tidy the spacing it leaves."""
    s = _CITATION.sub("", sentence)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


# Wikipedia navbox terminators. "v t e" is the view/talk/edit control that
# closes a navigation template; the lead paragraph starts immediately after it
# with no punctuation in between.
_NAVBOX_END = re.compile(
    r"\b(v\s+t\s+e|Glossary\s+v\s+t\s+e|Contents\s+move to sidebar|"
    # Infobox field labels. The infobox is inlined as running text with no
    # punctuation, so without a break here it swallows the lead paragraph:
    # "Brain Brain of a chimpanzee ... Identifiers Latin cerebrum ... MeSH
    # D001921 The brain is an organ ..." becomes one unusable blob.
    r"Anatomical terminology|Anatomical terms of\s+\w+)\b"
)

# A definition restarting mid-blob. Figure captions are inlined with no
# terminal punctuation and get welded onto the sentence that follows:
# "The darker green marks the Amazon's drainage basin or watershed A river is
# a natural stream of fresh water ...". The weld is detectable because an
# article-led definition ("A river is", "The brain is") begins immediately
# after a lowercase word -- prose does not do that.
_DEFINITION_RESTART = re.compile(
    r"(?<=[a-z0-9])\s+(?=(?:A|An|The)\s+[a-z][\w-]*\s+(?:is|are|was|were)\b)"
)


def _break_navboxes(content: str) -> str:
    """Insert sentence boundaries where navigation furniture ends."""
    content = _NAVBOX_END.sub(". ", content)
    return _DEFINITION_RESTART.sub(". ", content)


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
    r"is defined as|is a type of|is a form of|also known as|also called|"
    # Compositional definitions. "An atom consists of a nucleus of protons..."
    # is the lead sentence of the Atom article and was not recognised, so the
    # answer fell back to an image caption further up the page.
    r"consists? of|consist of|comprises?|comprise|is composed of|"
    r"is made up of|is made of|comprising|consisting of)\b",
    re.I,
)

# Encyclopedia leads routinely scope the definition before naming the subject:
# "In physics, gravity ... is ...", "In biology, evolution is ...". Stripping the
# scoping clause lets the subject still count as leading the sentence.
_SCOPE_PREFIX = re.compile(
    r"^(?:in|within|according to|under)\s+[\w\s-]{2,30}?,\s+", re.I
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

# Catalogue entries: "Gravity, a 1952 mixed-media artwork by M. C. Escher",
# "Gravity, a 2013 film". A work described by year-and-medium is an index row,
# not a definition.
_WORK_ENTRY = re.compile(
    # Up to three genre words may sit between the year and the medium
    # ("a 2013 science fiction film", "a 1952 mixed-media artwork").
    r"\b(?:an?|the)\s+\d{4}\s+(?:[\w-]+\s+){0,3}"
    r"(?:artwork|painting|sculpture|drawing|lithograph|print|film|movie|novel|"
    r"book|album|song|single|play|opera|poem|comic|series|episode|video game)\b",
    re.I,
)

# Wikipedia index furniture that survives sentence splitting.
_INDEX_FURNITURE = re.compile(
    r"\ball pages with titles\b|\btopics referred to by the same term\b|"
    r"\bthis disambiguation page\b|\bindex of articles\b|\blist of articles\b|"
    # The standard disambiguation footer. It reads like a sentence, mentions
    # nothing, and was being returned verbatim as the definition of
    # "evolution".
    r"\bif an internal link\b|\bled you here\b|"
    r"\bchange the link to point directly\b|\bintended article\b",
    re.I,
)


def _is_list_debris(sentence: str) -> bool:
    """True for disambiguation runs and index rows rather than prose."""
    if len(_LIST_DEBRIS.findall(sentence)) >= 2:
        return True
    # Quote-heavy fragments are track listings, not sentences.
    if sentence.count('"') >= 4:
        return True
    if _WORK_ENTRY.search(sentence):
        return True
    if _INDEX_FURNITURE.search(sentence):
        return True

    # A closing bracket with no opener means the sentence splitter cut into
    # the middle of a parenthetical -- the fragment is the tail of something
    # else. This is what produced the trailing
    # "Escher) or Gravity, a 1952 mixed-media artwork by M." on the gravity
    # answer: "M. C. Escher" split on "M." and orphaned the rest.
    if sentence.count(")") > sentence.count("("):
        return True

    # ... and a sentence that *ends* on an initial was cut mid-name.
    if re.search(r"\b[A-Z]\.$", sentence.strip()):
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

    # Drop a leading scope clause so "In physics, gravity ... is ..." is judged
    # on "gravity ... is ...", which is the definition it actually contains.
    sentence = _SCOPE_PREFIX.sub("", sentence, count=1)

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
    """Build a coherent answer by positively selecting definitional prose."""
    return summarize_entry_scored(content, topic, max_sentences, max_chars)[0]


def summarize_entry_scored(
    content: str,
    topic: str = "",
    max_sentences: int = 4,
    max_chars: int = 700,
) -> tuple[str, bool]:
    """As :func:`summarize_entry`, but also reports whether the opening
    sentence was an actual definition.

    Callers ranking several candidate articles need this. Title overlap alone
    cannot tell "DNA" the molecule from "DNA²" the manga -- both articles are
    legitimately titled "DNA" -- but only one of them contains a sentence that
    *defines* DNA. Preferring the candidate that produced a definition is what
    routes around a mis-seeded corpus entry.

    Takes whole sentences only, so the reply always ends on a complete thought
    rather than being truncated mid-clause.
    """
    sentences = _clean_sentences(content)
    if not sentences:
        return "", False

    topic_words = _topic_tokens_for(topic)

    # 1. Prefer a real definition.
    start_idx = None
    is_definition = False
    for i, s in enumerate(sentences):
        if _is_definitional(s, topic_words):
            start_idx = i
            is_definition = True
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

    return " ".join(picked).strip(), is_definition


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

    # A reply that opens on punctuation is a fragment sliced out of the middle
    # of a corpus sentence, e.g. ", creoles, pidgins and sign languages are in
    # relative motion." Nothing that starts that way is a thought.
    if not text[0].isalpha():
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
    if not content:
        # The prompt carried no content word at all ("you", "hi", "ofjds").
        # There is nothing for the output to be *about*, so relevance cannot
        # be established and the model gets no say. Chit-chat belongs to the
        # pattern engine, which at least answers in character.
        return False
    reply_words = {w.lower().strip(".,;:!?()") for w in words}
    if not (content & reply_words):
        return False

    # A real sentence ends like one.
    if text[-1] not in ".!?":
        return False
    return True


# Words that never constitute a subject. A turn made only of these is
# conversation, not a lookup.
_NO_SUBJECT = _FILLER | {
    "a", "an", "the", "and", "but", "or", "so", "then", "just", "really",
    "very", "chat", "talk", "talking", "hello", "hey", "hi", "yes", "no",
    "yeah", "nah", "ok", "okay", "sure", "thanks", "please", "was", "were",
    "been", "being", "have", "has", "had", "will", "would", "could", "should",
    "can", "did", "does", "doing", "with", "from", "that", "this", "these",
    "those", "there", "here", "what", "when", "where", "why", "how", "who",
    "bit", "while", "again", "still", "back", "now", "today", "tonight",
    "wanted", "want", "wants", "think", "thought", "feel", "guess", "mean",
    "chatting", "chats", "chatted", "talks", "talked", "speak", "speaking",
    "lets", "let", "gonna", "wanna", "gotta", "maybe", "perhaps", "anyway",
    "actually", "basically", "literally", "kinda", "sorta", "alright",
    "hello", "hiya", "sup", "morning", "evening", "night", "bye", "later",
    "keep", "keeping", "kept", "going", "goes", "went", "start", "started",
    "stop", "stopped", "carry", "continue", "more", "less", "some", "any",
    # "why does that matter" retrieved an article about *matter*; "my name is
    # Matt" made "name matt" the conversation's subject.
    "matter", "matters", "name", "named", "called", "point", "sense", "idea",
    "it", "its", "them", "they", "him", "her", "his", "hers", "we", "us",
    "our", "ours", "i", "me", "my", "mine", "you", "your", "yours", "he",
    "she", "is", "are", "am", "be",
}

# Turns that only make sense against what was just said.
# NOTE: bare "why" only. "why does photosynthesis need light" names its own
# subject and must reach the reasoner -- an unbounded `why\b` prefix matched
# every why-question and answered them all with "ask me something specific".
_FOLLOW_UP = re.compile(
    # Bare "why" only. An unbounded `why\b` prefix matched every why-question,
    # so "why does photosynthesis need light" was answered with "ask me
    # something specific" instead of reaching the reasoner.
    #
    # The $-anchored alternatives are in their own group with no trailing \b:
    # a word boundary after "why?" can never match, which silently broke the
    # plainest follow-up there is.
    r"^(?:and |but |so |ok(?:ay)?[,. ]*)?"
    r"(?:(?:why|how come|really|and|go on|more|then what|prove it|"
    r"keep going|continue|say more|tell me more)[?.!]*$"
    r"|(?:why not|what about (?:it|that|this)|says who|since when|has it|"
    r"have you|did you|do you|are you sure|explain that)\b)",
    re.I,
)

# A question whose subject is a pronoun pointing at the previous turn:
# "why does that matter", "what does this mean", "how does it work".
# Anchored at the start and requiring the pronoun to be the grammatical
# subject of the question verb. An unanchored version also swallowed
# "what is the thing THAT plants use to make sugar", where "that" opens a
# relative clause and the question names its own subject perfectly well.
_ANAPHORIC = re.compile(
    r"^(?:and |but |so |ok(?:ay)?[,. ]*)?"
    r"(?:why|what|how|when|who)\s+"
    r"(?:does|do|did|is|are|was|were|would|should|could)\s+"
    r"(?:that|this|it|those|they)\b",
    re.I,
)

# "my name is Matt", "i'm a plumber" -- the user telling Shaggoth about
# themselves. Recorded as a fact, but not what the conversation is *about*,
# so it must not become the subject a follow-up resolves against.
_FACT_STATEMENT = re.compile(
    r"^(?:my name is|i(?:'m| am)\b|call me|you can call me|i live|i work|"
    r"remember (?:that )?my)\b",
    re.I,
)


def has_subject(text: str) -> bool:
    """Whether a message is *about* anything Shaggoth could look up.

    "i wanted to chat" and "has it been a bit" are conversation. Routing them
    through knowledge retrieval produced the reply "Never heard of wanted
    chat", which is both wrong and rude about a perfectly normal thing to say.
    """
    words = {
        w.strip(".,;:!?'\"") .lower()
        for w in (text or "").split()
    }
    return bool({w for w in words if len(w) > 2} - _NO_SUBJECT)


def is_follow_up(text: str) -> bool:
    """Whether the turn refers back rather than introducing a subject.

    Covers both the bare forms ("why?", "go on") and the anaphoric ones
    ("why does that matter"), which read like questions but whose subject is
    a pronoun pointing at the previous turn. Treating those as lookups sent
    "why does that matter" to an article about *matter*.
    """
    text = (text or "").strip()
    return bool(_FOLLOW_UP.search(text) or _ANAPHORIC.search(text))


_CHITCHAT_REPLIES = (
    "Then talk. I'm not going to start it for you.",
    "Go on then. Pick something.",
    "I'm here. That's about as warm as it gets.",
    "Sure. What about?",
    "Fine by me. Say something worth answering.",
)


def chitchat_reply(text: str, context: dict | None = None) -> str:
    """A conversational reply for a turn with no subject in it.

    Uses what the session has actually been about when there is something,
    so it reads as continuing a conversation rather than resetting one.
    """
    subject = last_subject(context)
    if not subject:
        topics = [t for t in (context or {}).get("topics", []) if len(t) > 3][:1]
        subject = topics[0] if topics else ""
    if subject and _rng.random() < 0.6:
        return _rng.choice((
            f"We were on {subject}. Still are, unless you've got something better.",
            f"You brought up {subject} earlier. Want to keep pulling on that?",
            f"Last thing you cared about was {subject}. Pick that back up or pick something new.",
        ))
    return _rng.choice(_CHITCHAT_REPLIES)


def last_subject(context: dict | None = None) -> str:
    """The most recent thing the user actually raised.

    Deliberately *recency*, not frequency. Ranking the session's keywords by
    count answered "why?" with "On chat?" after a conversation that had said
    "chat" three times in passing and "photosynthesis" once on purpose --
    the follow-up belongs to the last real subject, not the most repeated word.
    """
    for message in reversed((context or {}).get("recent", [])):
        if message.get("role") != "user":
            continue
        text = message.get("content", "")
        if not has_subject(text) or _FACT_STATEMENT.match(text.strip()):
            continue
        words = [
            w.strip(".,;:!?'\"").lower()
            for w in text.split()
        ]
        subject = [w for w in words if len(w) > 3 and w not in _NO_SUBJECT]
        if subject:
            return " ".join(subject[:3])
    return ""


def follow_up_reply(context: dict | None = None) -> str:
    """A reply to 'why?' / 'go on' that names what is being followed up."""
    subject = last_subject(context)
    if subject:
        return (
            f"On {subject}? Ask me something specific and I'll give you a "
            "specific answer."
        )
    recent = (context or {}).get("recent", [])
    if any(m.get("role") == "assistant" for m in recent):
        return "That's as far as I got. Ask me something narrower."
    return "Follow up on what? You haven't given me anything yet."


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


def knowledge_is_relevant(topic: str, text: str, content: str = "") -> bool:
    """True when an article genuinely matches what was asked.

    Normalized BM25 always ranks *something* first, so rank alone cannot tell
    "this is the answer" from "this is the least-bad of 350 irrelevant
    articles". Title overlap can: articles are named after their subject, so a
    question whose content words appear in the title is on-topic, and one whose
    words do not is a miss worth admitting to.

    Title overlap alone is too strict for anything *inside* a long document,
    though. A character in a novel is discussed at length in a chapter whose
    title never mentions them, so "who is Ellie Finch" found nothing at all
    while the answer sat in the body of six chapters.

    So there is a second, deliberately narrow route: every content word of the
    question appears in the body, and there are at least two of them. Requiring
    two keeps a single common word from matching half the corpus, while a
    multi-word name -- which is exactly the case title matching cannot serve --
    still gets through.
    """
    asked = _content_words(text)
    if not asked:
        return False
    if asked & _topic_words(topic):
        return True
    if len(asked) < 2 or not content:
        return False
    return _body_discusses(content, asked)


def _body_discusses(content: str, asked: set[str]) -> bool:
    """True when every question word appears together in one sentence.

    Deliberately stricter than "appears somewhere in the document" on two axes.

    Word boundaries: the previous substring test let "ice" match "device" and
    "service", so a three-letter word matched most of the corpus.

    Co-occurrence: words scattered across a long article are evidence of
    nothing -- an encyclopedia entry contains most common words eventually.
    Appearing in the same sentence is what distinguishes "this document
    discusses the subject" from "these words happen to be in here".
    """
    for sentence in _SENTENCE_SPLIT.split(content):
        tokens = set(re.findall(r"[a-z0-9]+", sentence.lower()))
        if not tokens:
            continue
        if all(
            any(_stem_match(word, token) for token in tokens)
            for word in asked
        ):
            return True
    return False


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
