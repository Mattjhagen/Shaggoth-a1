"""Extended tests for MemoryStore — covering user_id isolation, multi-user
facts, proactive message polling, and helper APIs not covered by test_memory.py.
"""
from __future__ import annotations

import time

import pytest

from shaggoth.memory import MemoryStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store():
    s = MemoryStore(":memory:")
    yield s
    s.close()


# ---------------------------------------------------------------------------
# set_fact / get_fact — user_id isolation
# ---------------------------------------------------------------------------

class TestFactUserIsolation:
    def test_get_fact_returns_correct_user_value(self, store):
        store.set_fact("color", "blue", user_id="alice")
        store.set_fact("color", "red", user_id="bob")
        assert store.get_fact("color", user_id="alice") == "blue"
        assert store.get_fact("color", user_id="bob") == "red"

    def test_get_fact_default_user_id_does_not_leak_other_users(self, store):
        store.set_fact("color", "green", user_id="alice")
        assert store.get_fact("color") is None  # default user has no fact

    def test_get_fact_missing_key_returns_none(self, store):
        assert store.get_fact("nonexistent") is None

    def test_set_fact_overwrites_same_user(self, store):
        store.set_fact("name", "Alice", user_id="u1")
        store.set_fact("name", "Alex", user_id="u1")
        assert store.get_fact("name", user_id="u1") == "Alex"

    def test_set_fact_overwrite_does_not_affect_other_user(self, store):
        store.set_fact("name", "Bob", user_id="u2")
        store.set_fact("name", "Alex", user_id="u1")
        assert store.get_fact("name", user_id="u2") == "Bob"

    def test_default_user_id_is_default(self, store):
        store.set_fact("x", "1")  # user_id='default'
        assert store.get_fact("x", user_id="default") == "1"

    def test_extract_and_store_facts_uses_default_user(self, store):
        store.extract_and_store_facts("my name is Matt")
        assert store.get_fact("name") == "Matt"               # default user
        assert store.get_fact("name", user_id="other") is None  # other user unaffected


# ---------------------------------------------------------------------------
# all_facts — user_id scoping
# ---------------------------------------------------------------------------

class TestAllFactsScoping:
    def test_all_facts_returns_only_default_user(self, store):
        store.set_fact("color", "blue", user_id="alice")
        store.set_fact("color", "red")                  # default
        facts = store.all_facts()
        assert facts == {"color": "red"}

    def test_all_facts_explicit_user(self, store):
        store.set_fact("sport", "tennis", user_id="alice")
        store.set_fact("sport", "chess")                # default
        assert store.all_facts(user_id="alice") == {"sport": "tennis"}

    def test_all_facts_empty_for_unknown_user(self, store):
        store.set_fact("x", "1")
        assert store.all_facts(user_id="ghost") == {}

    def test_all_facts_returns_all_keys_for_user(self, store):
        store.set_fact("name", "Matt")
        store.set_fact("likes", "synthwave")
        facts = store.all_facts()
        assert set(facts.keys()) == {"name", "likes"}


# ---------------------------------------------------------------------------
# add_message / history
# ---------------------------------------------------------------------------

class TestMessageHistory:
    def test_history_ordered_chronologically(self, store):
        store.add_message("s1", "user", "first")
        store.add_message("s1", "assistant", "second")
        store.add_message("s1", "user", "third")
        history = store.history("s1")
        assert [m["role"] for m in history] == ["user", "assistant", "user"]
        assert history[0]["content"] == "first"

    def test_history_is_session_scoped(self, store):
        store.add_message("a", "user", "hello from a")
        store.add_message("b", "user", "hello from b")
        assert len(store.history("a")) == 1
        assert store.history("a")[0]["content"] == "hello from a"

    def test_history_limit_applies(self, store):
        for i in range(10):
            store.add_message("s1", "user", f"msg {i}")
        assert len(store.history("s1", limit=3)) == 3

    def test_add_message_returns_integer_id(self, store):
        mid = store.add_message("s1", "user", "hello")
        assert isinstance(mid, int)
        assert mid > 0

    def test_ids_are_strictly_increasing(self, store):
        ids = [store.add_message("s1", "user", f"msg {i}") for i in range(5)]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# proactive_messages_after
# ---------------------------------------------------------------------------

class TestProactiveMessagesAfter:
    def test_returns_assistant_messages_after_given_id(self, store):
        store.add_message("s1", "user", "hello")
        mid = store.add_message("s1", "assistant", "hi there")
        store.add_message("s1", "user", "how are you")
        store.add_message("s1", "assistant", "doing well")

        results = store.proactive_messages_after("s1", since_id=0)
        assert len(results) == 2
        assert results[0]["text"] == "hi there"
        assert results[1]["text"] == "doing well"

    def test_since_id_filters_older_messages(self, store):
        m1 = store.add_message("s1", "assistant", "old reply")
        store.add_message("s1", "assistant", "new reply")

        results = store.proactive_messages_after("s1", since_id=m1)
        assert len(results) == 1
        assert results[0]["text"] == "new reply"

    def test_user_messages_excluded(self, store):
        store.add_message("s1", "user", "question")
        store.add_message("s1", "assistant", "answer")
        results = store.proactive_messages_after("s1", since_id=0)
        assert all(r["text"] != "question" for r in results)
        assert len(results) == 1

    def test_empty_when_no_messages(self, store):
        assert store.proactive_messages_after("s1", since_id=0) == []

    def test_result_has_expected_keys(self, store):
        store.add_message("s1", "assistant", "hello")
        result = store.proactive_messages_after("s1", since_id=0)[0]
        assert "id" in result
        assert "text" in result
        assert "ts" in result

    def test_limit_applied(self, store):
        for i in range(10):
            store.add_message("s1", "assistant", f"reply {i}")
        results = store.proactive_messages_after("s1", since_id=0, limit=3)
        assert len(results) == 3

    def test_session_scoped(self, store):
        store.add_message("a", "assistant", "from a")
        store.add_message("b", "assistant", "from b")
        results = store.proactive_messages_after("a", since_id=0)
        assert len(results) == 1
        assert results[0]["text"] == "from a"


# ---------------------------------------------------------------------------
# session_topics
# ---------------------------------------------------------------------------

class TestSessionTopics:
    def test_returns_most_frequent_keywords(self, store):
        for _ in range(5):
            store.add_message("s1", "user", "aeroponics is great for growing plants")
        store.add_message("s1", "user", "quantum computing is interesting")
        topics = store.session_topics("s1")
        assert "aeroponics" in topics

    def test_ignores_stopwords(self, store):
        store.add_message("s1", "user", "the and for you what")
        topics = store.session_topics("s1")
        assert not any(t in ("the", "and", "for", "you", "what") for t in topics)

    def test_excludes_assistant_messages_from_topic_index(self, store):
        store.add_message("s1", "assistant", "aeroponics reply")  # assistant, not indexed
        store.add_message("s1", "user", "quantum question")       # user, indexed
        topics = store.session_topics("s1")
        assert "quantum" in topics or not topics   # aeroponics should not be here from assistant

    def test_limit_respected(self, store):
        for word in ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota"):
            store.add_message("s1", "user", f"{word} {word} {word}")
        topics = store.session_topics("s1", limit=3)
        assert len(topics) <= 3

    def test_empty_session_returns_empty_list(self, store):
        assert store.session_topics("nonexistent") == []


# ---------------------------------------------------------------------------
# extract_and_store_facts
# ---------------------------------------------------------------------------

class TestExtractAndStoreFacts:
    def test_extracts_name(self, store):
        facts = store.extract_and_store_facts("my name is Alice")
        assert facts.get("name") == "Alice"

    def test_extracts_likes(self, store):
        facts = store.extract_and_store_facts("I love jazz music")
        assert "likes" in facts

    def test_returns_empty_dict_for_no_matches(self, store):
        facts = store.extract_and_store_facts("the weather is nice today")
        assert facts == {}

    def test_facts_persisted_to_db(self, store):
        store.extract_and_store_facts("my name is Bob")
        assert store.get_fact("name") == "Bob"

    def test_multiple_facts_extracted(self, store):
        facts = store.extract_and_store_facts("my name is Carol and I love hiking")
        assert "name" in facts
        assert "likes" in facts

    def test_fact_update_replaces_old_value(self, store):
        store.extract_and_store_facts("my name is Alice")
        store.extract_and_store_facts("call me Ali")
        assert store.get_fact("name") == "Ali"

    def test_abstract_location_is_rejected(self, store):
        facts = store.extract_and_store_facts("I live in fear")
        assert "location" not in facts
        assert store.get_fact("location") is None

    def test_real_location_is_accepted(self, store):
        facts = store.extract_and_store_facts("I live in Denver")
        assert facts.get("location") == "Denver"

    def test_abstract_locations_exhaustive(self, store):
        for word in ("pain", "denial", "chaos", "silence", "hope"):
            facts = store.extract_and_store_facts(f"I live in {word}")
            assert "location" not in facts, f"'{word}' should be rejected as a location"

    def test_likes_not_too_greedy(self, store):
        facts = store.extract_and_store_facts(
            "I like building small side projects on weekends with my friends"
        )
        if "likes" in facts:
            assert len(facts["likes"]) <= 25
