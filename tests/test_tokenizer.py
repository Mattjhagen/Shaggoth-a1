"""BPE tokenizer: correctness of the incremental-merge rewrite.

train() was rewritten from an O(merges x corpus) full rescan to incremental
pair counting (AGENTS.md section SS) to make retraining finish in minutes
rather than ~16 min. These lock in that it still tokenizes correctly and
deterministically.
"""
from __future__ import annotations

from shaggoth.models.tokenizer import BPETokenizer

CORPUS = (
    "the sky is blue because shorter wavelengths scatter more. "
    "photosynthesis is how plants turn sunlight into sugar. "
    "the cat sat on the mat and the cat ate the fish. "
) * 40


def test_roundtrip_is_lossless():
    tok = BPETokenizer.from_text(CORPUS, vocab_size=512)
    for s in ["the sky is blue", "photosynthesis", "the cat sat on the mat."]:
        assert tok.decode(tok.encode(s)) == s


def test_merges_happen_when_vocab_exceeds_charset():
    tok = BPETokenizer.from_text(CORPUS, vocab_size=300)
    # A corpus with a small charset and vocab 300 must have learned merges,
    # so common sequences encode to fewer tokens than their character count.
    ids = tok.encode("the the the")
    assert len(ids) < len("the the the")
    assert len(tok.merges) > 0


def test_training_is_deterministic():
    a = BPETokenizer.from_text(CORPUS, vocab_size=400)
    b = BPETokenizer.from_text(CORPUS, vocab_size=400)
    assert a.vocab == b.vocab
    assert a.encode("the cat sat") == b.encode("the cat sat")


def test_save_load_roundtrip(tmp_path):
    tok = BPETokenizer.from_text(CORPUS, vocab_size=400)
    p = str(tmp_path / "tok.json")
    tok.save(p)
    loaded = BPETokenizer.load(p)
    assert loaded.vocab == tok.vocab
    assert loaded.encode("the sky is blue") == tok.encode("the sky is blue")


def test_unknown_chars_do_not_crash():
    tok = BPETokenizer.from_text(CORPUS, vocab_size=400)
    # A char never seen in training encodes via the "?" fallback rather than
    # raising; decode must still return a string.
    out = tok.decode(tok.encode("zz≈∆ unseen"))
    assert isinstance(out, str)
