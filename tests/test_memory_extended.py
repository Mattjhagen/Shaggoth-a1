"""Tests for extended memory: confidence-scored facts, preferences, projects."""
from __future__ import annotations

import pytest

from shaggoth.memory.store import MemoryStore


@pytest.fixture
def mem():
    return MemoryStore(":memory:")


# ---------------------------------------------------------------------------
# Facts with confidence and source
# ---------------------------------------------------------------------------


def test_set_fact_with_confidence(mem):
    mem.set_fact("name", "Matt", confidence=0.9, source="user")
    meta = mem.get_fact_with_meta("name")
    assert meta is not None
    assert meta["value"] == "Matt"
    assert meta["confidence"] == 0.9
    assert meta["source"] == "user"


def test_set_fact_defaults(mem):
    mem.set_fact("color", "blue")
    meta = mem.get_fact_with_meta("color")
    assert meta["confidence"] == 0.5
    assert meta["source"] == "pattern"


def test_get_fact_still_returns_string(mem):
    mem.set_fact("name", "Alice", confidence=0.8, source="pattern")
    assert mem.get_fact("name") == "Alice"


def test_all_facts_with_meta(mem):
    mem.set_fact("name", "Matt", confidence=0.9, source="user")
    mem.set_fact("location", "Colorado", confidence=0.7, source="pattern")
    meta = mem.all_facts_with_meta()
    assert "name" in meta
    assert meta["name"]["confidence"] == 0.9
    assert meta["location"]["source"] == "pattern"


def test_all_facts_backward_compat(mem):
    mem.set_fact("likes", "coding", confidence=0.8, source="pattern")
    facts = mem.all_facts()
    assert facts == {"likes": "coding"}


def test_extract_facts_sets_confidence(mem):
    found = mem.extract_and_store_facts("my name is Alice")
    assert found == {"name": "Alice"}
    meta = mem.get_fact_with_meta("name")
    assert meta["confidence"] == 0.9
    assert meta["source"] == "pattern"


def test_extract_facts_likes_confidence(mem):
    found = mem.extract_and_store_facts("I really like hiking")
    assert "likes" in found
    meta = mem.get_fact_with_meta("likes")
    assert meta["confidence"] == 0.7


def test_update_fact_replaces_confidence(mem):
    mem.set_fact("name", "Bob", confidence=0.5, source="pattern")
    mem.set_fact("name", "Bobby", confidence=1.0, source="user")
    meta = mem.get_fact_with_meta("name")
    assert meta["value"] == "Bobby"
    assert meta["confidence"] == 1.0
    assert meta["source"] == "user"


# ---------------------------------------------------------------------------
# Preferences (profile memory)
# ---------------------------------------------------------------------------


def test_set_and_get_preference(mem):
    mem.set_preference("communication", "verbosity", "concise",
                       confidence=0.8, source="inferred")
    assert mem.get_preference("communication", "verbosity") == "concise"


def test_preference_not_found(mem):
    assert mem.get_preference("communication", "tone") is None


def test_preferences_by_category(mem):
    mem.set_preference("interests", "topic1", "AI")
    mem.set_preference("interests", "topic2", "robotics")
    mem.set_preference("communication", "style", "casual")
    prefs = mem.preferences_by_category("interests")
    assert prefs == {"topic1": "AI", "topic2": "robotics"}


def test_all_preferences(mem):
    mem.set_preference("interests", "ai", "yes")
    mem.set_preference("communication", "tone", "direct")
    all_prefs = mem.all_preferences()
    assert "interests" in all_prefs
    assert "communication" in all_prefs
    assert all_prefs["interests"]["ai"] == "yes"


def test_preference_upsert(mem):
    mem.set_preference("comm", "style", "formal")
    mem.set_preference("comm", "style", "casual")
    assert mem.get_preference("comm", "style") == "casual"


def test_user_profile_context_empty(mem):
    assert mem.user_profile_context() == ""


def test_user_profile_context_with_data(mem):
    mem.set_fact("name", "Matt")
    mem.set_preference("interests", "topic", "AI")
    ctx = mem.user_profile_context()
    assert "Matt" in ctx
    assert "AI" in ctx
    assert "Interests" in ctx


# ---------------------------------------------------------------------------
# Project memory
# ---------------------------------------------------------------------------


def test_add_and_get_project(mem):
    pid = mem.add_project("Shaggoth", description="AI chatbot")
    assert pid > 0
    proj = mem.get_project("Shaggoth")
    assert proj is not None
    assert proj["name"] == "Shaggoth"
    assert proj["description"] == "AI chatbot"
    assert proj["status"] == "active"


def test_project_not_found(mem):
    assert mem.get_project("nonexistent") is None


def test_list_projects_active(mem):
    mem.add_project("Alpha")
    mem.add_project("Beta")
    mem.update_project("Beta", status="completed")
    active = mem.list_projects(status="active")
    assert len(active) == 1
    assert active[0]["name"] == "Alpha"


def test_list_projects_all(mem):
    mem.add_project("A")
    mem.add_project("B")
    mem.update_project("B", status="completed")
    all_proj = mem.list_projects(status=None)
    assert len(all_proj) == 2


def test_update_project(mem):
    mem.add_project("MyProj")
    assert mem.update_project("MyProj", description="updated desc", status="paused")
    proj = mem.get_project("MyProj")
    assert proj["description"] == "updated desc"
    assert proj["status"] == "paused"


def test_update_nonexistent_project(mem):
    assert not mem.update_project("nope", description="x")


def test_project_upsert(mem):
    mem.add_project("Dup", description="v1")
    mem.add_project("Dup", description="v2")
    proj = mem.get_project("Dup")
    assert proj["description"] == "v2"


def test_project_context_empty(mem):
    assert mem.project_context() == ""


def test_project_context_with_data(mem):
    mem.add_project("Shaggoth", description="AI chatbot")
    mem.add_project("WebApp", description="React frontend")
    ctx = mem.project_context()
    assert "Shaggoth" in ctx
    assert "WebApp" in ctx
    assert "Active projects" in ctx


# ---------------------------------------------------------------------------
# Integration: profile + project context in one call
# ---------------------------------------------------------------------------


def test_full_profile_and_project_context(mem):
    mem.set_fact("name", "Matt", confidence=1.0, source="user")
    mem.set_preference("communication", "style", "direct")
    mem.add_project("Shaggoth", "AI platform")

    profile = mem.user_profile_context()
    assert "Matt" in profile
    assert "direct" in profile

    proj = mem.project_context()
    assert "Shaggoth" in proj


def test_user_profile_context_capped(mem):
    for i in range(200):
        mem.set_fact(f"fact_{i}", "x" * 50, confidence=0.9, source="user")
    ctx = mem.user_profile_context()
    assert len(ctx) <= mem._PROFILE_MAX_CHARS
    assert ctx.endswith("…")


def test_add_project_upsert_returns_correct_id(mem):
    pid1 = mem.add_project("Alpha", description="v1")
    pid2 = mem.add_project("Alpha", description="v2")
    assert pid1 == pid2
    proj = mem.get_project("Alpha")
    assert proj["description"] == "v2"
