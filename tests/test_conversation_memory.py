"""Conversation memory: context, compaction, and not mistaking chat for a query.

The reported failure, verbatim from the UI:

    you  > i wanted to chat
    shag > Never heard of wanted chat. Annoying. I'm reading up on it right now
           [source: fallback -- curiosity research has been triggered]

Three things wrong at once: the reply is nonsense, the turn is recorded as a
knowledge gap, and curiosity then went and researched "wanted chat".
"""
from __future__ import annotations

import pytest

from shaggoth.dialogue.engine import (
    DialogueEngine,
    chitchat_reply,
    follow_up_reply,
    has_subject,
    is_follow_up,
)
from shaggoth.memory import MemoryStore


@pytest.fixture
def engine(tmp_path):
    return DialogueEngine(memory=MemoryStore(str(tmp_path / "m.db")), seed=1)


# --------------------------------------------------------------------------
# Subject detection
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "i wanted to chat",
    "you wanted to chat",
    "has it been a bit",
    "hey",
    "so what",
    "i think so",
    "yeah ok",
    "just talking",
])
def test_conversational_turns_have_no_subject(text):
    assert not has_subject(text)


@pytest.mark.parametrize("text", [
    "what is photosynthesis",
    "tell me about aeroponics",
    "who is Ellie Finch",
    "explain quantum mechanics",
    "gravity",
])
def test_real_questions_have_a_subject(text):
    assert has_subject(text)


def test_follow_ups_are_recognised():
    for text in ("why", "why?", "go on", "tell me more", "has it been a bit",
                 "and why?", "keep going", "are you sure"):
        assert is_follow_up(text), text


def test_a_new_question_is_not_a_follow_up():
    assert not is_follow_up("what is photosynthesis")


# --------------------------------------------------------------------------
# The reported bug
# --------------------------------------------------------------------------


def test_chitchat_does_not_come_back_as_a_knowledge_gap(engine):
    """source must not be 'fallback' -- that is what triggers research."""
    for text in ("i wanted to chat", "you wanted to chat", "has it been a bit"):
        reply = engine.respond(text, session_id="s1")
        assert reply.source != "fallback", (text, reply.text)


def test_chitchat_never_claims_ignorance_of_the_phrase(engine):
    for text in ("i wanted to chat", "you wanted to chat"):
        reply = engine.respond(text, session_id="s1")
        lowered = reply.text.lower()
        assert "never heard of" not in lowered, reply.text
        assert "blank on" not in lowered, reply.text
        assert "wanted chat" not in lowered, reply.text


def test_a_real_unknown_still_admits_ignorance(engine):
    """The honest fallback must survive -- it is how curiosity gets told."""
    reply = engine.respond("what is zorbulon dynamics", session_id="s1")
    assert reply.source == "fallback"


# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------


def test_context_carries_recent_turns(engine):
    engine.respond("what is photosynthesis", session_id="s1")
    engine.respond("what is gravity", session_id="s1")
    ctx = engine.memory.conversation_context("s1")
    assert ctx["message_count"] == 4
    assert any("photosynthesis" in m["content"] for m in ctx["recent"])
    assert ctx["last_user_message"] == "what is gravity"


def test_context_is_per_session(engine):
    engine.respond("what is photosynthesis", session_id="a")
    engine.respond("what is gravity", session_id="b")
    assert engine.memory.conversation_context("a")["message_count"] == 2
    assert "gravity" not in str(engine.memory.conversation_context("a")["recent"])


def test_session_topics_surface_what_was_discussed(engine):
    for _ in range(3):
        engine.respond("tell me about aeroponics", session_id="s1")
    engine.respond("what is photosynthesis", session_id="s1")
    topics = engine.memory.session_topics("s1")
    assert "aeroponics" in topics


def test_chitchat_refers_to_what_was_discussed():
    context = {"topics": ["aeroponics", "photosynthesis"], "recent": []}
    seen = {chitchat_reply("hey", context) for _ in range(40)}
    assert any("aeroponics" in reply for reply in seen)


def test_chitchat_copes_with_no_context():
    assert chitchat_reply("hey", {})
    assert chitchat_reply("hey", None)


def test_follow_up_reply_names_the_subject():
    context = {"recent": [{"role": "user", "content": "tell me about aeroponics"}]}
    assert "aeroponics" in follow_up_reply(context)


def test_follow_up_reply_without_context_says_so():
    assert follow_up_reply({}) 


# --------------------------------------------------------------------------
# Compaction
# --------------------------------------------------------------------------


def test_short_sessions_are_not_compacted(engine):
    engine.respond("what is gravity", session_id="s1")
    assert engine.memory.compact_session("s1") == ""


def test_long_sessions_are_compacted(engine):
    for i in range(30):
        engine.respond(f"tell me about aeroponics number {i}", session_id="s1")
    summary = engine.memory.compact_session("s1")
    assert summary
    assert "aeroponics" in summary
    assert "Earlier in this conversation" in summary


def test_compaction_is_idempotent(engine):
    for i in range(30):
        engine.respond(f"tell me about aeroponics {i}", session_id="s1")
    first = engine.memory.compact_session("s1")
    assert engine.memory.compact_session("s1") == first


def test_compaction_extends_as_the_conversation_grows(engine):
    for i in range(30):
        engine.respond(f"tell me about aeroponics {i}", session_id="s1")
    first = engine.memory.compact_session("s1")
    for i in range(30):
        engine.respond(f"tell me about photosynthesis {i}", session_id="s1")
    second = engine.memory.compact_session("s1")
    assert second != first
    assert "photosynthesis" in second


def test_context_exposes_the_summary(engine):
    for i in range(30):
        engine.respond(f"tell me about aeroponics {i}", session_id="s1")
    engine.memory.compact_session("s1")
    assert "aeroponics" in engine.memory.conversation_context("s1")["summary"]


def test_compaction_keeps_recent_turns_verbatim(engine):
    for i in range(30):
        engine.respond(f"tell me about aeroponics {i}", session_id="s1")
    engine.memory.compact_session("s1")
    ctx = engine.memory.conversation_context("s1")
    assert ctx["recent"], "recent turns must survive compaction"
    assert "aeroponics 29" in ctx["recent"][-2]["content"]


def test_summary_includes_remembered_facts(engine):
    engine.respond("my name is Matt", session_id="s1")
    for i in range(30):
        engine.respond(f"tell me about aeroponics {i}", session_id="s1")
    assert "Matt" in engine.memory.compact_session("s1")


def test_maybe_compact_waits_for_a_long_enough_session(engine):
    engine.respond("what is gravity", session_id="s1")
    assert engine.memory.maybe_compact("s1") == ""


def test_plugin_commands_are_not_swallowed_by_the_chitchat_gate(engine):
    """"what is 6 * 7?" is all filler words but is a real command."""
    assert engine.respond("what is 6 * 7?", session_id="s1").source == "plugin"


def test_fact_recall_is_not_swallowed_either(engine):
    engine.respond("my name is Matt", session_id="s1")
    reply = engine.respond("what do you know about me?", session_id="s1")
    assert "Matt" in reply.text


def test_follow_up_uses_the_most_recent_subject_not_the_most_frequent():
    """"why?" answered "On chat?" after a chat that mentioned photosynthesis
    once on purpose and "chat" three times in passing."""
    from shaggoth.dialogue.engine import last_subject

    context = {
        "recent": [
            {"role": "user", "content": "i wanted to chat"},
            {"role": "assistant", "content": "Sure. What about?"},
            {"role": "user", "content": "you wanted to chat"},
            {"role": "assistant", "content": "Then talk."},
            {"role": "user", "content": "what is photosynthesis"},
            {"role": "assistant", "content": "Photosynthesis is..."},
        ],
        "topics": ["chat", "photosynthesis"],
    }
    assert last_subject(context) == "photosynthesis"
    assert "photosynthesis" in follow_up_reply(context)


def test_last_subject_skips_turns_with_nothing_in_them():
    from shaggoth.dialogue.engine import last_subject

    context = {"recent": [
        {"role": "user", "content": "tell me about aeroponics"},
        {"role": "assistant", "content": "..."},
        {"role": "user", "content": "ok"},
        {"role": "user", "content": "hey"},
    ]}
    assert "aeroponics" in last_subject(context)


def test_last_subject_with_nothing_to_go_on():
    from shaggoth.dialogue.engine import last_subject

    assert last_subject({}) == ""
    assert last_subject({"recent": [{"role": "user", "content": "hey"}]}) == ""


@pytest.mark.parametrize("text", [
    "lets keep chatting", "just chatting", "wanna talk", "lets talk",
])
def test_more_conversational_phrasings_are_not_lookups(text):
    assert not has_subject(text)


@pytest.mark.parametrize("text", [
    "why does that matter",
    "what does this mean",
    "how does it work",
    "what about that",
    "why is that",
])
def test_anaphoric_questions_are_follow_ups(text):
    """Subject is a pronoun pointing at the previous turn, not a topic.

    "why does that matter" was being answered from an article about *matter*.
    """
    assert is_follow_up(text), text


def test_a_follow_up_is_never_answered_from_the_knowledge_base(engine):
    engine.respond("tell me about aeroponics", session_id="s1")
    reply = engine.respond("why does that matter", session_id="s1")
    assert reply.source != "knowledge", reply.text
    assert "aeroponics" in reply.text.lower()


def test_a_real_question_containing_that_is_still_a_lookup():
    """Do not over-fire: this names its own subject."""
    assert not is_follow_up("what is the thing that plants use to make sugar")


@pytest.mark.parametrize("text", [
    "what does this protein do",
    "how does this engine work",
    "what is this chemical",
    "why does that algorithm fail",
])
def test_determiner_this_that_is_not_follow_up(text):
    """'this/that' + noun is a determiner, not an anaphoric pronoun."""
    assert not is_follow_up(text), text


def test_fact_statements_do_not_become_the_conversation_subject():
    from shaggoth.dialogue.engine import last_subject

    context = {"recent": [
        {"role": "user", "content": "tell me about aeroponics"},
        {"role": "user", "content": "my name is Matt"},
    ]}
    assert "aeroponics" in last_subject(context)


# --------------------------------------------------------------------------
# Conversational messages that must never reach knowledge retrieval
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "thank you", "thanks", "thanks a lot", "thx",
    "sorry", "my bad",
    "goodbye", "see you later", "bye",
    "help", "help me",
    "never mind", "forget it", "whatever", "idc",
    "bruh", "dude", "ugh", "meh", "sigh",
    "damn", "dang", "hold on", "wait",
    "for real", "same", "true", "not really",
    "not much", "nothing much",
    "youre dumb", "youre awesome", "youre smart",
    "thats cool", "thats crazy", "thats wild",
    "I dont know", "I dont care",
    "whats up",
    "tell me something interesting",
    "I changed my mind", "forget about it",
    "that was fun", "nice one", "good job", "well done",
    "I agree", "I disagree", "fair enough", "fair point",
    "you make me laugh", "you crack me up", "good call",
    "my bad", "good point", "nice work",
])
def test_social_and_reactive_messages_have_no_subject(text):
    assert not has_subject(text), f"{text!r} should not be treated as a lookup"


@pytest.mark.parametrize("text", [
    "what is photosynthesis",
    "tell me about aeroponics",
    "who is Albert Einstein",
    "explain quantum mechanics",
    "gravity",
    "what is DNA",
    "how does evolution work",
    "tell me about machine learning",
])
def test_real_knowledge_questions_still_have_subjects(text):
    assert has_subject(text), f"{text!r} should be treated as a lookup"


def test_social_messages_never_trigger_fallback(engine):
    """None of these should produce source='fallback', which triggers research."""
    for text in ("thank you", "sorry", "goodbye", "never mind", "ugh",
                 "thats cool", "youre awesome", "whats up", "hold on"):
        reply = engine.respond(text, session_id="s1")
        assert reply.source != "fallback", f"{text!r} produced fallback: {reply.text}"


def test_bare_noun_answers_from_knowledge_when_available(tmp_path):
    """Typing just 'gravity' should answer from the KB, not claim ignorance."""
    from shaggoth.memory import MemoryStore

    engine = DialogueEngine(memory=MemoryStore(str(tmp_path / "m.db")), seed=1)
    engine.knowledge.add_entry(
        "Gravity",
        "Gravity is a fundamental force of nature. " * 20,
    )
    reply = engine.respond("gravity", session_id="s1")
    assert reply.source == "knowledge", f"expected knowledge, got {reply.source}: {reply.text}"


def test_bare_noun_not_in_kb_still_falls_through(tmp_path):
    from shaggoth.memory import MemoryStore

    engine = DialogueEngine(memory=MemoryStore(str(tmp_path / "m.db")), seed=1)
    reply = engine.respond("zorbulon", session_id="s1")
    assert reply.source == "fallback"


# --------------------------------------------------------------------------
# Conversational pushback — must not become research topics
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "you're lying", "you are lying", "that's wrong", "thats wrong",
    "no way", "bull", "not true", "nope", "nah",
])
def test_conversational_pushback_has_no_subject(text):
    assert not has_subject(text), f"{text!r} should not have a subject"


@pytest.mark.parametrize("text", [
    "can you elaborate", "please clarify", "repeat that",
    "summarize what you said", "rephrase that",
])
def test_meta_requests_have_no_subject(text):
    assert not has_subject(text), f"{text!r} should not be a lookup"


def test_describe_unknown_filters_filler_words():
    """describe_unknown should not include common words in the subject."""
    from shaggoth.dialogue.engine import describe_unknown
    reply = describe_unknown("can you elaborate on that interesting perspective")
    assert "elaborate" not in reply.lower()
    assert "perspective" not in reply.lower()


def test_short_definitional_article_not_repeated(tmp_path):
    """A short article should produce one sentence, not the same one 4x."""
    from shaggoth.memory import MemoryStore

    engine = DialogueEngine(memory=MemoryStore(str(tmp_path / "m.db")), seed=1)
    engine.knowledge.add_entry(
        "Gravity",
        "Gravity is a fundamental force of nature. " * 20,
    )
    reply = engine.respond("what is gravity", session_id="s1")
    count = reply.text.lower().count("fundamental force")
    assert count <= 1, f"Repeated {count} times: {reply.text}"
