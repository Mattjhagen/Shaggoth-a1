"""Corpus hygiene: plan and apply the removal of duplicate title variants.

The acquisition path used to name entries after the *query string* rather than
the subject, so asking "why is the sky blue" could create "Why Is The Sky Blue
(part N)" right alongside the properly-named "The Sky Blue (part N)" from a
plain "sky" lookup. Both score a perfect title match in
:mod:`shaggoth.knowledge.engine`'s BM25 ranking, so the query-named duplicate
-- usually scraped from a worse search on the literal question text -- can
outrank the honest entry instead of losing to it.

:func:`shaggoth.curiosity.topics.strip_question_prefix` stops this growing
going forward; this module cleans up what already accumulated, and is a no-op
on a clean corpus.

This lived in ``scripts/dedupe_corpus.py``, which the wheel deliberately does
not ship (only ``shaggoth/`` does). The curator agent needs it at runtime, so
the logic lives here and the script imports it for its CLI -- otherwise the
curator would work from a checkout and be permanently skipped in an installed
copy, which is the harder failure to notice.

**Nothing here deletes.** Losing variants are *moved* to a quarantine
directory, so any run can be undone by moving them back.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..curiosity.topics import base_topic, canonical_subject, is_question_topic

_FRAGMENT_SUFFIX = re.compile(r"-part-[0-9]+$", re.I)

#: Directory name used for quarantined duplicates, as a sibling of the
#: knowledge directory. Kept out of the knowledge dir itself so a re-scan does
#: not pick the removed files straight back up.
QUARANTINE_DIRNAME = "knowledge_dedup_removed"


@dataclass
class Variant:
    """One title variant of a subject.

    All the "Aeroponic Farming Part N" chunks share a variant; "Why Is
    Aeroponic Farming Part N" is a second, separate variant of the same
    subject -- collapsing part-N chunk suffixes but keeping everything else,
    so a multi-chunk article is graded as one unit rather than file by file.
    """

    label: str
    paths: list = field(default_factory=list)
    word_count: int = 0

    @property
    def is_question(self) -> bool:
        return is_question_topic(self.label)


@dataclass
class DedupGroup:
    subject: str
    keep: Variant
    remove: list


def group_entries(entries) -> dict:
    """Group knowledge entries by canonical subject, then by title variant.

    Returns {subject: {variant_label: Variant}}.
    """
    groups: dict = {}
    for entry in entries:
        subject = canonical_subject(entry.topic)
        variant_label = base_topic(entry.topic)
        bucket = groups.setdefault(subject, {})
        variant = bucket.setdefault(variant_label, Variant(label=variant_label))
        variant.paths.append(entry.path)
        variant.word_count += entry.word_count
    return groups


def _choose_keeper(variants: list) -> Variant:
    """A non-question title wins outright; among ties, the larger one does.

    Preferring "more content" over "more files" means a single meaty article
    is not discarded in favor of three thin ones purely on file count.
    """
    return sorted(variants, key=lambda v: (v.is_question, -v.word_count, v.label))[0]


def plan_dedup(entries) -> list:
    """Every subject with more than one title variant, and what to do about it.

    ``entries`` is anything with ``.topic`` (str), ``.path`` (str), and
    ``.word_count`` (int) -- KnowledgeEntry satisfies this, and so does any
    fake used in tests.
    """
    plan = []
    for subject, variants_by_label in group_entries(entries).items():
        variants = list(variants_by_label.values())
        if len(variants) <= 1:
            continue
        keep = _choose_keeper(variants)
        remove = [v for v in variants if v is not keep]
        plan.append(DedupGroup(subject=subject, keep=keep, remove=remove))
    return plan


def is_fragment(path: str) -> bool:
    """Whether a knowledge file is a ``-part-N`` chunk of a larger article."""
    return bool(_FRAGMENT_SUFFIX.search(Path(path).stem))


def plan_summary(plan: list) -> dict:
    """Counts for a plan, without touching the filesystem."""
    files = sum(len(v.paths) for g in plan for v in g.remove)
    words = sum(v.word_count for g in plan for v in g.remove)
    return {
        "duplicate_subjects": len(plan),
        "files": files,
        "words": words,
        "subjects": [g.subject for g in plan[:20]],
    }


def quarantine(plan: list, quarantine_dir: Path) -> list:
    """Move every losing variant's files into *quarantine_dir*.

    Returns the paths actually moved. A file that has already gone (a
    concurrent re-scan, a previous partial run) is skipped rather than raising
    -- half a plan applied is a worse outcome than a plan that steps over a
    file someone else moved.
    """
    quarantine_dir = Path(quarantine_dir)
    moved: list[str] = []
    for group in plan:
        for variant in group.remove:
            for raw_path in variant.paths:
                src = Path(raw_path)
                if not src.exists():
                    continue
                quarantine_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(quarantine_dir / src.name))
                moved.append(str(src))
    return moved
