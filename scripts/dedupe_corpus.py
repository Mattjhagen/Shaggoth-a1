#!/usr/bin/env python3
"""Corpus hygiene: dedupe knowledge entries that differ only by how they were
acquired.

AGENTS.md §NN: the acquisition path used to name entries after the *query
string* rather than the subject, so asking "why is the sky blue" could create
"Why Is The Sky Blue (part N)" right alongside the properly-named "The Sky
Blue (part N)" from a plain "sky" lookup. Both score a perfect title match in
shaggoth/knowledge/engine.py's BM25 ranking, so the query-named duplicate --
usually scraped from a worse search on the literal question text -- can
outrank the honest entry instead of losing to it. By the last count on the
live corpus this shape was roughly half of everything on disk.

shaggoth/curiosity/engine.py now strips a leading question phrase before
ever storing a topic (see strip_question_prefix in curiosity/topics.py), so
this should stop growing going forward. This script cleans up what already
accumulated before that fix, and is safe to re-run any time -- it is a no-op
once a corpus is clean.

Usage:
    python3 scripts/dedupe_corpus.py                      # report only
    python3 scripts/dedupe_corpus.py --apply               # move duplicates
    python3 scripts/dedupe_corpus.py --data-dir path/to/knowledge --apply

Nothing is ever deleted. --apply moves the losing variant's files into a
quarantine directory (default: a sibling of --data-dir named
"knowledge_dedup_removed") so the run can be undone by moving them back.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shaggoth.curiosity.topics import base_topic, canonical_subject, is_question_topic
from shaggoth.knowledge.engine import DEFAULT_KNOWLEDGE_DIR, KnowledgeBase

_FRAGMENT_SUFFIX = re.compile(r"-part-[0-9]+$", re.I)


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


def _is_fragment(path: str) -> bool:
    return bool(_FRAGMENT_SUFFIX.search(Path(path).stem))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=None, help=f"knowledge dir (default: {DEFAULT_KNOWLEDGE_DIR})")
    parser.add_argument("--quarantine-dir", type=Path, default=None, help="where removed files go (default: <data-dir>/../knowledge_dedup_removed)")
    parser.add_argument("--apply", action="store_true", help="move duplicate files (default: dry run)")
    args = parser.parse_args(argv)

    directory = args.data_dir or DEFAULT_KNOWLEDGE_DIR
    quarantine = args.quarantine_dir or (directory.parent / "knowledge_dedup_removed")

    entries = KnowledgeBase(directory)._entries
    total_before = len(entries)
    fragments_before = sum(1 for e in entries if _is_fragment(e.path))

    plan = plan_dedup(entries)

    removed_files = 0
    removed_words = 0
    for group in plan:
        print(f"\n{group.subject}")
        print(f'  keep:   "{group.keep.label}" ({len(group.keep.paths)} file(s), {group.keep.word_count} words)')
        for variant in group.remove:
            print(f'  remove: "{variant.label}" ({len(variant.paths)} file(s), {variant.word_count} words)')
            removed_files += len(variant.paths)
            removed_words += variant.word_count
            if args.apply:
                quarantine.mkdir(parents=True, exist_ok=True)
                for raw_path in variant.paths:
                    src = Path(raw_path)
                    shutil.move(str(src), str(quarantine / src.name))

    verb = "Removed" if args.apply else "Would remove"
    print(f"\n{verb} {removed_files} file(s) ({removed_words} words) across {len(plan)} duplicate subject(s).")

    if total_before:
        pct_before = 100 * fragments_before / total_before
        print(f"Corpus before: {total_before} entries, {fragments_before} -part-N fragments ({pct_before:.0f}%).")
    if args.apply:
        remaining = KnowledgeBase(directory)._entries
        total_after = len(remaining)
        fragments_after = sum(1 for e in remaining if _is_fragment(e.path))
        pct_after = 100 * fragments_after / total_after if total_after else 0
        print(f"Corpus after:  {total_after} entries, {fragments_after} -part-N fragments ({pct_after:.0f}%).")
        print(f"Quarantined files are at {quarantine} -- move them back to undo.")
    elif plan:
        print(f"\nDry run -- no files were moved. Re-run with --apply to quarantine duplicates in {quarantine}.")
    else:
        print("Nothing to do -- no subject has more than one title variant.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
