"""Promotion gate for retrained TinyGPT checkpoints.

Why this exists
---------------
A retraining timer writes a fresh checkpoint on a schedule. AGENTS.md section
HH records the footgun this creates: ``build_engine`` once loaded TinyGPT
whenever the file existed, so *merely finishing a training run* silently
downgraded every drift reply on the next restart. Making ``auto`` mean Markov
fixed the implicit-load half. This module is the other half: nothing gets
promoted onto the live checkpoint path unless it clears an explicit quality
gate, and every decision is logged.

The gate has two independent checks and a candidate must pass BOTH:

1. **Coherence** (the important one). Perplexity can look fine while the text
   reads as garbage -- the 3000-step run in HH emitted non-words like
   ``symotential`` and ``authibiiktiological``. Those words never appear in the
   training corpus. So we generate samples and measure the fraction of emitted
   words that actually occur in the corpus. Subword salad scores near zero; a
   model that has learned the corpus scores high.

2. **Perplexity**: must not regress versus the currently-live checkpoint. With
   no live checkpoint to compare against, the candidate must beat an absolute
   ceiling instead.

This module has no torch dependency itself; callers pass in an already-loaded
model that exposes ``.generate(prompt, max_tokens)`` and ``.model`` /
``.tokenizer`` / ``.cfg`` (the TinyGPTModel interface). That keeps it unit
testable without training anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

# Fixed probes -- deliberately plain topics that are well covered in the
# knowledge corpus, so a model that learned the corpus has every chance to
# emit real words. If it still can't, that is signal.
DEFAULT_PROBES = (
    "the sky is",
    "photosynthesis is",
    "machine learning is",
    "water is",
    "the sun",
)

# A generated word counts as "known" if it appears in the corpus. 0.85 leaves
# headroom for the odd rare/proper-noun token while still rejecting the
# non-word salad the parked 3000-step checkpoint produced (measured ratio there
# was far below this).
MIN_KNOWN_WORD_RATIO = 0.85
# Need enough emitted words for the ratio to mean anything. A model that emits
# only punctuation / whitespace fails here rather than dividing by zero.
MIN_WORDS_EMITTED = 20
# When there is no live checkpoint to compare against, the candidate's
# perplexity must at least beat this. exp(6) ~= 400; anything worse than that on
# a 2048-token vocab has learned almost nothing.
ABSOLUTE_PPL_CEILING = 400.0
# Small tolerance so numerical noise between two eval runs doesn't reject an
# otherwise-equal candidate.
PPL_REGRESS_TOLERANCE = 1.02

_WORD_RE = re.compile(r"[a-z]{2,}")


def corpus_vocabulary(corpus_text: str) -> set[str]:
    """The set of real words (>=2 alpha chars, lowercased) seen in the corpus."""
    return set(_WORD_RE.findall(corpus_text.lower()))


@dataclass
class CoherenceReport:
    known_word_ratio: float
    words_emitted: int
    known_words: int
    samples: list[dict] = field(default_factory=list)
    passed: bool = False
    reason: str = ""


def coherence_report(
    model,
    corpus_vocab: set[str],
    probes: tuple[str, ...] = DEFAULT_PROBES,
    max_tokens: int = 40,
) -> CoherenceReport:
    """Generate from each probe and measure how many emitted words are real.

    ``model`` is anything with ``.generate(prompt, max_tokens) -> str`` -- the
    TinyGPTModel interface. Real corpus words = words in ``corpus_vocab``.
    """
    total = 0
    known = 0
    samples: list[dict] = []
    for probe in probes:
        try:
            out = model.generate(prompt=probe, max_tokens=max_tokens)
        except Exception as exc:  # a checkpoint that can't even generate fails
            samples.append({"probe": probe, "output": "", "error": str(exc)})
            continue
        words = _WORD_RE.findall(out.lower())
        n_known = sum(1 for w in words if w in corpus_vocab)
        total += len(words)
        known += n_known
        samples.append(
            {
                "probe": probe,
                "output": out,
                "words": len(words),
                "known": n_known,
            }
        )

    ratio = (known / total) if total else 0.0
    rep = CoherenceReport(
        known_word_ratio=round(ratio, 4),
        words_emitted=total,
        known_words=known,
        samples=samples,
    )
    if total < MIN_WORDS_EMITTED:
        rep.passed = False
        rep.reason = f"emitted only {total} words (need >= {MIN_WORDS_EMITTED})"
    elif ratio < MIN_KNOWN_WORD_RATIO:
        rep.passed = False
        rep.reason = (
            f"known-word ratio {ratio:.2f} < {MIN_KNOWN_WORD_RATIO} "
            f"(text reads as non-words)"
        )
    else:
        rep.passed = True
        rep.reason = f"known-word ratio {ratio:.2f} >= {MIN_KNOWN_WORD_RATIO}"
    return rep


@dataclass
class PromotionDecision:
    promote: bool
    reason: str
    candidate_ppl: float | None = None
    live_ppl: float | None = None
    coherence: dict | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        return d


def decide(
    candidate_ppl: float,
    coherence: CoherenceReport,
    live_ppl: float | None,
) -> PromotionDecision:
    """Combine the two checks into a single promote/reject decision.

    Both checks must pass. Coherence is checked first because a coherent-but-
    slightly-worse-perplexity model is still usable, whereas a low-perplexity
    garbage model is the exact trap this gate exists to stop.
    """
    coh = coherence.__dict__.copy()

    if not coherence.passed:
        return PromotionDecision(
            promote=False,
            reason=f"REJECT: incoherent -- {coherence.reason}",
            candidate_ppl=candidate_ppl,
            live_ppl=live_ppl,
            coherence=coh,
        )

    if candidate_ppl != candidate_ppl or candidate_ppl == float("inf"):  # NaN/inf
        return PromotionDecision(
            promote=False,
            reason=f"REJECT: candidate perplexity is {candidate_ppl}",
            candidate_ppl=candidate_ppl,
            live_ppl=live_ppl,
            coherence=coh,
        )

    if live_ppl is None:
        if candidate_ppl > ABSOLUTE_PPL_CEILING:
            return PromotionDecision(
                promote=False,
                reason=(
                    f"REJECT: no live checkpoint and perplexity "
                    f"{candidate_ppl:.1f} > ceiling {ABSOLUTE_PPL_CEILING}"
                ),
                candidate_ppl=candidate_ppl,
                live_ppl=None,
                coherence=coh,
            )
        return PromotionDecision(
            promote=True,
            reason=(
                f"PROMOTE: coherent ({coherence.reason}) and perplexity "
                f"{candidate_ppl:.1f} under ceiling with no live baseline"
            ),
            candidate_ppl=candidate_ppl,
            live_ppl=None,
            coherence=coh,
        )

    if candidate_ppl > live_ppl * PPL_REGRESS_TOLERANCE:
        return PromotionDecision(
            promote=False,
            reason=(
                f"REJECT: perplexity regressed {candidate_ppl:.1f} > "
                f"live {live_ppl:.1f} (x{PPL_REGRESS_TOLERANCE})"
            ),
            candidate_ppl=candidate_ppl,
            live_ppl=live_ppl,
            coherence=coh,
        )

    return PromotionDecision(
        promote=True,
        reason=(
            f"PROMOTE: coherent ({coherence.reason}) and perplexity "
            f"{candidate_ppl:.1f} <= live {live_ppl:.1f}"
        ),
        candidate_ppl=candidate_ppl,
        live_ppl=live_ppl,
        coherence=coh,
    )
