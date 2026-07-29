"""Corpus dedup: query-named duplicates must lose to the honest entry.

AGENTS.md §NN's exact bug shape: asking a question the acquisition path
didn't normalize creates an entry titled after the whole question
("Why Is The Sky Blue") right alongside the properly-named one from a plain
lookup ("The Sky Blue"). Both score a perfect title match, so the
query-named duplicate can outrank the honest entry instead of losing to it.
This only tests the planning logic (group_entries / plan_dedup) -- no
filesystem is touched.
"""
from __future__ import annotations

from dataclasses import dataclass

from scripts.dedupe_corpus import group_entries, plan_dedup


@dataclass
class FakeEntry:
    topic: str
    path: str
    word_count: int = 500


def test_a_clean_and_a_question_named_duplicate_are_one_subject():
    entries = [
        FakeEntry("The Sky Blue", "data/knowledge/the-sky-blue-part-1.md"),
        FakeEntry("The Sky Blue Part 2", "data/knowledge/the-sky-blue-part-2.md"),
        FakeEntry("Why Is The Sky Blue", "data/knowledge/why-is-the-sky-blue-part-1.md"),
    ]
    groups = group_entries(entries)
    assert len(groups) == 1
    ((subject, variants),) = groups.items()
    assert subject == "The Sky Blue"
    assert set(variants) == {"The Sky Blue", "Why Is The Sky Blue"}


def test_plan_keeps_the_clean_variant_and_flags_the_question_one():
    entries = [
        FakeEntry("The Sky Blue", "data/knowledge/the-sky-blue-part-1.md"),
        FakeEntry("The Sky Blue Part 2", "data/knowledge/the-sky-blue-part-2.md"),
        FakeEntry("Why Is The Sky Blue", "data/knowledge/why-is-the-sky-blue-part-1.md"),
    ]
    plan = plan_dedup(entries)
    assert len(plan) == 1
    group = plan[0]
    assert group.subject == "The Sky Blue"
    assert group.keep.label == "The Sky Blue"
    assert sorted(group.keep.paths) == [
        "data/knowledge/the-sky-blue-part-1.md",
        "data/knowledge/the-sky-blue-part-2.md",
    ]
    assert [v.label for v in group.remove] == ["Why Is The Sky Blue"]
    assert group.remove[0].paths == ["data/knowledge/why-is-the-sky-blue-part-1.md"]


def test_a_lone_entry_is_never_flagged():
    entries = [FakeEntry("Photosynthesis", "data/knowledge/photosynthesis.md")]
    assert plan_dedup(entries) == []


def test_two_question_variants_with_no_clean_counterpart_keeps_the_bigger_one():
    """Neither title is the "right" one, so more content wins -- and it is
    still better than shipping two overlapping, half-covering duplicates."""
    entries = [
        FakeEntry(
            "Why Is Gravity", "data/knowledge/why-is-gravity-part-1.md",
            word_count=300,
        ),
        FakeEntry(
            "What Is Gravity", "data/knowledge/what-is-gravity-part-1.md",
            word_count=900,
        ),
    ]
    plan = plan_dedup(entries)
    assert len(plan) == 1
    assert plan[0].keep.label == "What Is Gravity"
    assert [v.label for v in plan[0].remove] == ["Why Is Gravity"]


def test_multiple_unrelated_subjects_are_independent():
    entries = [
        FakeEntry("The Sky Blue", "data/knowledge/the-sky-blue-part-1.md"),
        FakeEntry("Why Is The Sky Blue", "data/knowledge/why-is-the-sky-blue-part-1.md"),
        FakeEntry("Photosynthesis", "data/knowledge/photosynthesis.md"),
    ]
    plan = plan_dedup(entries)
    assert len(plan) == 1
    assert plan[0].subject == "The Sky Blue"


def test_a_group_where_every_variant_is_a_question_still_keeps_only_one():
    entries = [
        FakeEntry("Why Is The Sky Blue", "data/knowledge/why-is-the-sky-blue-part-1.md", word_count=200),
        FakeEntry("What Is The Sky Blue", "data/knowledge/what-is-the-sky-blue-part-1.md", word_count=200),
    ]
    plan = plan_dedup(entries)
    assert len(plan) == 1
    # Tied on word count and is_question; label breaks the tie deterministically.
    assert plan[0].keep.label in ("What Is The Sky Blue", "Why Is The Sky Blue")
    assert len(plan[0].remove) == 1
