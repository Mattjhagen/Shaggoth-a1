"""The promotion gate must be able to REJECT, not just wave things through.

A gate that has only ever seen passing input is not a gate. These tests feed
it the exact failure mode from AGENTS.md section HH -- a model emitting
non-words like "authibiiktiological" -- and confirm it refuses to promote.
No torch needed: the gate only calls model.generate() and does arithmetic.
"""
from __future__ import annotations

from shaggoth.models import promote as gate


CORPUS = (
    "the sky is blue because shorter wavelengths of light scatter more. "
    "photosynthesis is how plants turn sunlight into sugar. water is made of "
    "hydrogen and oxygen. machine learning is a field of study that gives "
    "computers the ability to learn from data. the sun is a star at the "
    "center of the solar system. "
) * 20


class FakeModel:
    """Returns a canned string for every prompt, ignoring it."""

    def __init__(self, output: str):
        self._output = output

    def generate(self, prompt: str = "", max_tokens: int = 40) -> str:
        return self._output


def test_rejects_nonword_salad_like_section_HH():
    vocab = gate.corpus_vocabulary(CORPUS)
    garbage = FakeModel("symotential authibiiktiological grelmoxian tworbing "
                        "flindasy quomplet nารบ blargh zzxq w!! ")
    rep = gate.coherence_report(garbage, vocab)
    assert not rep.passed
    assert rep.known_word_ratio < gate.MIN_KNOWN_WORD_RATIO
    decision = gate.decide(candidate_ppl=50.0, coherence=rep, live_ppl=None)
    assert decision.promote is False
    assert "incoherent" in decision.reason


def test_low_perplexity_does_not_rescue_garbage():
    """The trap this gate exists for: good ppl, garbage text."""
    vocab = gate.corpus_vocabulary(CORPUS)
    garbage = FakeModel("zzxq blargh quomplet flindasy grelmoxian tworbing " * 4)
    rep = gate.coherence_report(garbage, vocab)
    # Even with a *great* perplexity, coherence failure blocks promotion.
    decision = gate.decide(candidate_ppl=1.0, coherence=rep, live_ppl=1000.0)
    assert decision.promote is False


def test_accepts_coherent_output_when_no_live_baseline():
    vocab = gate.corpus_vocabulary(CORPUS)
    good = FakeModel("the sky is blue because light scatter and water is made "
                     "of hydrogen and oxygen and the sun is a star that plants "
                     "use for photosynthesis to learn from data")
    rep = gate.coherence_report(good, vocab)
    assert rep.passed, rep.reason
    decision = gate.decide(candidate_ppl=80.0, coherence=rep, live_ppl=None)
    assert decision.promote is True


def test_rejects_perplexity_regression_even_if_coherent():
    vocab = gate.corpus_vocabulary(CORPUS)
    good = FakeModel("the sky is blue and water is made of hydrogen and oxygen "
                     "and the sun is a star that plants use for photosynthesis")
    rep = gate.coherence_report(good, vocab)
    assert rep.passed
    # Coherent, but worse perplexity than the live checkpoint -> reject.
    decision = gate.decide(candidate_ppl=200.0, coherence=rep, live_ppl=100.0)
    assert decision.promote is False
    assert "regressed" in decision.reason


def test_rejects_when_no_baseline_and_perplexity_over_ceiling():
    vocab = gate.corpus_vocabulary(CORPUS)
    good = FakeModel("the sky is blue and water is made of hydrogen and oxygen "
                     "and the sun is a star that plants use for photosynthesis")
    rep = gate.coherence_report(good, vocab)
    assert rep.passed
    decision = gate.decide(candidate_ppl=9999.0, coherence=rep, live_ppl=None)
    assert decision.promote is False
    assert "ceiling" in decision.reason


def test_promotes_coherent_improvement_over_live():
    vocab = gate.corpus_vocabulary(CORPUS)
    good = FakeModel("the sky is blue and water is made of hydrogen and oxygen "
                     "and the sun is a star that plants use for photosynthesis")
    rep = gate.coherence_report(good, vocab)
    decision = gate.decide(candidate_ppl=90.0, coherence=rep, live_ppl=100.0)
    assert decision.promote is True


def test_empty_output_fails_rather_than_dividing_by_zero():
    vocab = gate.corpus_vocabulary(CORPUS)
    silent = FakeModel("")
    rep = gate.coherence_report(silent, vocab)
    assert not rep.passed
    assert "emitted only 0 words" in rep.reason
