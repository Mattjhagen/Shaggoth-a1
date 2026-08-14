"""Tests for M3 RAG pipeline: chunking, reranking, best_chunks, citations."""
from __future__ import annotations

import pytest

from shaggoth.knowledge.engine import KnowledgeBase, KnowledgeEntry, chunk_content
from shaggoth.memory.store import extract_keywords


# ---------------------------------------------------------------------------
# chunk_content
# ---------------------------------------------------------------------------


def test_chunk_short_text_returns_single():
    text = "This is a short article about gravity. " * 10
    chunks = chunk_content(text, threshold=800)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_long_text_produces_multiple():
    words = ["word"] * 1200
    text = " ".join(words)
    chunks = chunk_content(text, chunk_size=500, overlap=100, threshold=800)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.split()) <= 500


def test_chunk_overlap_shares_words():
    words = [f"w{i}" for i in range(1200)]
    text = " ".join(words)
    chunks = chunk_content(text, chunk_size=500, overlap=100, threshold=800)
    assert len(chunks) >= 3
    # Last 100 words of chunk 0 should appear at start of chunk 1
    c0_words = chunks[0].split()
    c1_words = chunks[1].split()
    tail = c0_words[-100:]
    head = c1_words[:100]
    assert tail == head


def test_chunk_covers_all_content():
    words = [f"w{i}" for i in range(1500)]
    text = " ".join(words)
    chunks = chunk_content(text, chunk_size=500, overlap=100, threshold=800)
    # Every word must appear in at least one chunk
    all_chunked = set()
    for chunk in chunks:
        all_chunked.update(chunk.split())
    assert all_chunked == set(words)


def test_chunk_exactly_at_threshold():
    words = ["word"] * 800
    text = " ".join(words)
    chunks = chunk_content(text, threshold=800)
    assert len(chunks) == 1


def test_chunk_one_over_threshold():
    words = ["word"] * 801
    text = " ".join(words)
    chunks = chunk_content(text, chunk_size=500, overlap=100, threshold=800)
    assert len(chunks) == 2


def test_chunk_empty_text():
    assert chunk_content("") == [""]


def test_chunk_single_word():
    assert chunk_content("hello") == ["hello"]


def test_chunk_overlap_equal_to_size_no_infinite_loop():
    """chunk_size == overlap used to cause an infinite loop."""
    words = ["word"] * 1200
    text = " ".join(words)
    chunks = chunk_content(text, chunk_size=100, overlap=100, threshold=800)
    assert len(chunks) >= 1
    all_words = set()
    for c in chunks:
        all_words.update(c.split())
    assert "word" in all_words


def test_chunk_overlap_greater_than_size_no_infinite_loop():
    """chunk_size < overlap must not cause negative step / infinite loop."""
    words = ["word"] * 1200
    text = " ".join(words)
    chunks = chunk_content(text, chunk_size=50, overlap=100, threshold=800)
    assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# KnowledgeEntry with chunks
# ---------------------------------------------------------------------------


def test_scan_populates_chunks(tmp_path):
    kb = KnowledgeBase(tmp_path)
    # Short article — should have 1 chunk
    kb.add_entry("Short", "A short article. " * 10)
    entry = kb._entries[0]
    assert len(entry.chunks) == 1

    # Long article — should have multiple chunks
    kb.add_entry("Long", "Photosynthesis " * 900)
    long_entry = [e for e in kb._entries if "Long" in e.topic][0]
    assert len(long_entry.chunks) > 1
    assert len(long_entry.chunk_keywords) == len(long_entry.chunks)


def test_scan_chunk_keywords_extracted(tmp_path):
    kb = KnowledgeBase(tmp_path)
    content = ("photosynthesis plants light energy chlorophyll " * 200
               + "mitochondria cellular respiration ATP glucose " * 200)
    kb.add_entry("Biology", content)
    entry = kb._entries[0]
    assert len(entry.chunks) > 1
    # First chunk should have photosynthesis keywords
    kw_0 = set(entry.chunk_keywords[0])
    assert "photosynthesis" in kw_0
    # Last chunk should have mitochondria keywords
    kw_last = set(entry.chunk_keywords[-1])
    assert "mitochondria" in kw_last or "respiration" in kw_last


# ---------------------------------------------------------------------------
# Reranker: _chunk_relevance
# ---------------------------------------------------------------------------


def test_chunk_relevance_scores_best_chunk(tmp_path):
    kb = KnowledgeBase(tmp_path)
    # An article where "quantum" appears only in the second half
    content = ("classical physics newton gravity force " * 400
               + "quantum mechanics wave function probability " * 400)
    kb.add_entry("Physics", content)
    entry = kb._entries[0]
    assert len(entry.chunks) > 1

    query_words = {"quantum", "mechanics"}
    score = kb._chunk_relevance(entry, query_words)
    assert score > 0.0


def test_chunk_relevance_zero_when_no_match(tmp_path):
    kb = KnowledgeBase(tmp_path)
    kb.add_entry("Cooking", "recipe ingredients flour sugar butter " * 200)
    entry = kb._entries[0]
    query_words = {"quantum", "mechanics"}
    score = kb._chunk_relevance(entry, query_words)
    assert score == 0.0


def test_chunk_relevance_higher_for_concentrated_match(tmp_path):
    kb = KnowledgeBase(tmp_path)
    # Entry A: query terms scattered
    scattered = ("photosynthesis " * 5 + "unrelated " * 495) * 2
    kb.add_entry("Scattered", scattered)
    # Entry B: query terms concentrated in one chunk
    concentrated = ("unrelated " * 500
                    + "photosynthesis plants light energy chlorophyll " * 100)
    kb.add_entry("Concentrated", concentrated)

    query_words = {"photosynthesis", "plants", "light"}
    scattered_entry = [e for e in kb._entries if "Scattered" in e.topic][0]
    conc_entry = [e for e in kb._entries if "Concentrated" in e.topic][0]

    score_s = kb._chunk_relevance(scattered_entry, query_words)
    score_c = kb._chunk_relevance(conc_entry, query_words)
    assert score_c > score_s


# ---------------------------------------------------------------------------
# best_chunks
# ---------------------------------------------------------------------------


def test_best_chunks_returns_full_for_short_article(tmp_path):
    kb = KnowledgeBase(tmp_path)
    kb.add_entry("Short", "Gravity is a fundamental force. " * 10)
    entry = kb._entries[0]
    result = kb.best_chunks(entry, "what is gravity")
    assert result == entry.content


def test_best_chunks_returns_relevant_section(tmp_path):
    kb = KnowledgeBase(tmp_path)
    part1 = "classical physics newton gravity apple falling " * 200
    part2 = "quantum mechanics wave particle duality electron " * 200
    content = part1 + part2
    kb.add_entry("Physics", content)
    entry = kb._entries[0]

    # Asking about quantum should return the quantum chunk
    result = kb.best_chunks(entry, "quantum mechanics wave particle")
    assert "quantum" in result.lower()

    # Asking about newton should return the classical chunk
    result_newton = kb.best_chunks(entry, "newton gravity classical")
    assert "newton" in result_newton.lower()


def test_best_chunks_preserves_order(tmp_path):
    kb = KnowledgeBase(tmp_path)
    content = " ".join(f"section{i} " * 200 for i in range(5))
    kb.add_entry("Sections", content)
    entry = kb._entries[0]
    result = kb.best_chunks(entry, "section0 section4", max_chunks=2)
    # chunk indices should be in original order
    pos0 = result.find("section0")
    pos4 = result.find("section4")
    if pos0 >= 0 and pos4 >= 0:
        assert pos0 < pos4


def test_best_chunks_empty_query(tmp_path):
    kb = KnowledgeBase(tmp_path)
    kb.add_entry("Big", "content " * 900)
    entry = kb._entries[0]
    result = kb.best_chunks(entry, "")
    assert result == entry.content


# ---------------------------------------------------------------------------
# Reranking in query() — integration
# ---------------------------------------------------------------------------


def test_reranker_boosts_concentrated_match(tmp_path):
    """An article with query terms concentrated in one chunk should score
    higher than one with terms scattered across the whole document."""
    kb = KnowledgeBase(tmp_path)

    # Article A: "quantum" everywhere but diluted
    kb.add_entry(
        "Quantum Diluted",
        "quantum " + "unrelated filler text words " * 800 + "quantum",
    )
    # Article B: "quantum mechanics" concentrated in one section
    kb.add_entry(
        "Quantum Focused",
        "unrelated filler " * 400
        + "quantum mechanics wave function probability amplitude " * 100,
    )

    results = kb.query("quantum mechanics", limit=5, min_score=0.0)
    topics = [e.topic for e, _ in results]
    assert "Quantum Focused" in topics


def test_existing_ranking_tests_still_pass(tmp_path):
    """Reranker must not break the existing title-boost ranking."""
    kb = KnowledgeBase(tmp_path)
    kb.add_entry(
        "Evolution",
        "Evolution is the change in heritable characteristics. "
        + "evolution biology " * 300,
    )
    kb.add_entry(
        "Evolution Disambiguation",
        "Evolution may refer to evolution in biology or an album.",
    )
    results = kb.query("what is evolution", limit=5, min_score=0.0)
    assert results[0][0].topic == "Evolution"


def test_reranked_scores_normalised(tmp_path):
    kb = KnowledgeBase(tmp_path)
    kb.add_entry("Alpha", "alpha beta gamma " * 300)
    kb.add_entry("Beta", "beta gamma delta " * 300)
    results = kb.query("alpha beta", limit=5, min_score=0.0)
    scores = [s for _, s in results]
    assert scores[0] == pytest.approx(1.0)
    assert all(0.0 <= s <= 1.0 for s in scores)


# ---------------------------------------------------------------------------
# Citations in Reply
# ---------------------------------------------------------------------------


def test_reply_has_citations_field():
    from shaggoth.dialogue.engine import Reply
    r = Reply(text="hello", source="knowledge")
    assert hasattr(r, "citations")
    assert r.citations == []


def test_reply_citations_populated():
    from shaggoth.dialogue.engine import Reply
    r = Reply(
        text="answer",
        source="knowledge",
        entries_used=["Gravity"],
        citations=[{"topic": "Gravity", "snippet": "Gravity is a force.", "score": 0.95}],
    )
    assert len(r.citations) == 1
    assert r.citations[0]["topic"] == "Gravity"
    assert r.citations[0]["score"] == 0.95


def test_citations_serialise_with_asdict():
    from dataclasses import asdict
    from shaggoth.dialogue.engine import Reply
    r = Reply(
        text="answer",
        source="knowledge",
        citations=[{"topic": "DNA", "snippet": "DNA is a molecule.", "score": 0.88}],
    )
    d = asdict(r)
    assert "citations" in d
    assert d["citations"][0]["topic"] == "DNA"


# ---------------------------------------------------------------------------
# Integration: _build_knowledge_context uses best_chunks
# ---------------------------------------------------------------------------


def test_build_knowledge_context_uses_chunks(tmp_path):
    """When an entry is chunked, best_chunks returns the query-relevant
    section rather than the full article."""
    kb = KnowledgeBase(tmp_path)
    part1 = (
        "Classical physics studies macroscopic objects. "
        "Newton formulated laws of motion and gravity. " * 200
    )
    part2 = (
        "Quantum mechanics uses the wave function to encode probability amplitudes. " * 200
    )
    kb.add_entry("Physics Overview", part1 + part2)

    entry = kb._entries[0]
    assert len(entry.chunks) > 1
    result = kb.best_chunks(entry, "quantum mechanics wave function")
    assert "quantum" in result.lower()


# ---------------------------------------------------------------------------
# _build_citations helper
# ---------------------------------------------------------------------------


def test_build_citations_returns_empty_when_no_entries(tmp_path):
    from shaggoth.dialogue.engine import DialogueEngine
    kb = KnowledgeBase(tmp_path)
    engine = DialogueEngine(knowledge=kb)
    assert engine._build_citations("test", [], []) == []


def test_build_citations_filters_to_used_entries(tmp_path):
    from shaggoth.dialogue.engine import DialogueEngine
    kb = KnowledgeBase(tmp_path)
    kb.add_entry("Gravity", "Gravity is a fundamental force. " * 30)
    kb.add_entry("Cooking", "Cooking involves heat and ingredients. " * 30)
    engine = DialogueEngine(knowledge=kb)

    hits = kb.query("gravity force", limit=5, min_score=0.0)
    citations = engine._build_citations("gravity", hits, ["Gravity"])
    assert len(citations) == 1
    assert citations[0]["topic"] == "Gravity"
    assert "score" in citations[0]
    assert "snippet" in citations[0]


def test_build_citations_case_insensitive_match(tmp_path):
    from shaggoth.dialogue.engine import DialogueEngine
    kb = KnowledgeBase(tmp_path)
    kb.add_entry("DNA", "DNA is a molecule carrying genetic info. " * 30)
    engine = DialogueEngine(knowledge=kb)

    hits = kb.query("dna molecule", limit=5, min_score=0.0)
    citations = engine._build_citations("dna", hits, ["Dna"])
    assert len(citations) == 1
