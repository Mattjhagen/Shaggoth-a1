"""Drift toggle: DRIFT may wander, NO_DRIFT may not.

The IDE integration runs in NO_DRIFT, so the guarantees asserted here are
load-bearing: no Markov generation, no "want me to tell you about it?"
teaser, and no callbacks to unrelated past conversations.
"""
from __future__ import annotations

import pytest

from shaggoth.dialogue.engine import (
    DEFAULT_MODE,
    DRIFT,
    NO_DRIFT,
    DialogueEngine,
    markov_is_usable,
    normalize_mode,
)


# --------------------------------------------------------------------------
# Mode parsing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("drift", DRIFT),
        ("no_drift", NO_DRIFT),
        ("DRIFT", DRIFT),
        ("  no_drift  ", NO_DRIFT),
        (True, DRIFT),
        (False, NO_DRIFT),
        ("true", DRIFT),
        ("false", NO_DRIFT),
        ("on", DRIFT),
        ("off", NO_DRIFT),
        ("grounded", NO_DRIFT),
        ("wander", DRIFT),
    ],
)
def test_normalize_mode_accepts_the_spellings_clients_actually_send(value, expected):
    assert normalize_mode(value) == expected


def test_normalize_mode_falls_back_instead_of_raising():
    """A typo in the mode must not cost the user their answer."""
    assert normalize_mode("sideways") == DEFAULT_MODE
    assert normalize_mode(None) == DEFAULT_MODE
    assert normalize_mode("sideways", default=DRIFT) == DRIFT


def test_default_mode_is_grounded():
    """The expensive failure is a confident tangent, not a terse answer."""
    assert DEFAULT_MODE == NO_DRIFT


# --------------------------------------------------------------------------
# Engine behaviour
# --------------------------------------------------------------------------


class LoudModel:
    """A model that always returns a usable-looking sentence about the ask.

    Crafted to pass markov_is_usable so the tests prove the *mode* is what
    silences it, not the quality gate.
    """

    def __init__(self):
        self.calls = 0

    def is_trained(self):
        return True

    def generate(self, prompt="", max_tokens=40):
        self.calls += 1
        return "Photosynthesis is something the model wanted to say here."


@pytest.fixture
def engine_factory(tmp_path):
    def build(mode=DEFAULT_MODE, model=None):
        from shaggoth.memory import MemoryStore

        return DialogueEngine(
            memory=MemoryStore(str(tmp_path / f"mem-{mode}-{id(model)}.db")),
            model=model,
            mode=mode,
        )

    return build


def test_no_drift_never_calls_the_model(engine_factory):
    model = LoudModel()
    engine = engine_factory(mode=NO_DRIFT, model=model)
    reply = engine.respond("photosynthesis", session_id="s1")
    assert model.calls == 0
    assert reply.source != "model"


def test_drift_lets_the_model_speak(engine_factory):
    model = LoudModel()
    engine = engine_factory(mode=DRIFT, model=model)
    engine.respond("photosynthesis", session_id="s1")
    assert model.calls > 0


def test_per_request_mode_overrides_the_engine_default(engine_factory):
    model = LoudModel()
    engine = engine_factory(mode=NO_DRIFT, model=model)
    engine.respond("photosynthesis", session_id="s1", mode=DRIFT)
    assert model.calls > 0

    quiet = LoudModel()
    drifty = engine_factory(mode=DRIFT, model=quiet)
    drifty.respond("photosynthesis", session_id="s2", mode=NO_DRIFT)
    assert quiet.calls == 0


def test_reply_reports_the_mode_it_ran_in(engine_factory):
    engine = engine_factory(mode=NO_DRIFT)
    assert engine.respond("hello", session_id="s1").mode == NO_DRIFT
    assert engine.respond("hello", session_id="s1", mode=DRIFT).mode == DRIFT


def test_no_drift_suppresses_topic_callbacks(engine_factory, monkeypatch):
    """A callback to an unrelated past chat is the textbook tangent."""
    engine = engine_factory(mode=NO_DRIFT)

    called = []
    monkeypatch.setattr(
        engine.memory, "recall", lambda *a, **k: called.append(1) or []
    )
    engine.respond("photosynthesis", session_id="s1")
    assert not called


def test_drift_still_consults_recall(engine_factory, monkeypatch):
    engine = engine_factory(mode=DRIFT)
    called = []
    monkeypatch.setattr(
        engine.memory, "recall", lambda *a, **k: called.append(1) or []
    )
    engine.respond("photosynthesis", session_id="s1", mode=DRIFT)
    assert called


def test_no_drift_never_offers_instead_of_answering(engine_factory):
    """The teaser is what made it 'never complete a thought'."""
    engine = engine_factory(mode=NO_DRIFT)
    for i in range(40):
        reply = engine.respond(f"tell me thing {i}", session_id="s1")
        assert "want me to tell you about it" not in reply.text.lower()


def test_empty_message_still_carries_the_mode(engine_factory):
    engine = engine_factory(mode=NO_DRIFT)
    assert engine.respond("   ", mode=DRIFT).mode == DRIFT


# --------------------------------------------------------------------------
# The quality gate that runs inside DRIFT
# --------------------------------------------------------------------------


def test_markov_gate_rejects_mid_sentence_fragments():
    """Real leak: ', creoles, pidgins and sign languages are in relative motion.'"""
    assert not markov_is_usable(
        ", creoles, pidgins and sign languages are in relative motion.", "you"
    )


def test_markov_gate_rejects_when_the_prompt_has_no_content_word():
    """'you' / 'hi' / 'ofjds' give the output nothing to be about."""
    for prompt in ("you", "hi", "ofjds", "uiou"):
        assert not markov_is_usable(
            "Photosynthesis is the process used by plants to convert light.", prompt
        )


def test_markov_gate_rejects_encyclopedia_artifacts():
    for junk in (
        "Photosynthesis v t e is a process used by plants to make food.",
        "Photosynthesis is a process [citation needed] used by plants here.",
        "Photosynthesis is described at https://example.com/page and elsewhere.",
    ):
        assert not markov_is_usable(junk, "what is photosynthesis")


def test_markov_gate_rejects_irrelevant_output():
    assert not markov_is_usable(
        "Gravity is the force that attracts two bodies toward each other.",
        "what is photosynthesis",
    )


def test_markov_gate_accepts_a_relevant_coherent_sentence():
    assert markov_is_usable(
        "Photosynthesis is the process plants use to turn light into sugar.",
        "what is photosynthesis",
    )


def test_markov_gate_requires_terminal_punctuation():
    assert not markov_is_usable(
        "Photosynthesis is the process plants use to turn light into sugar",
        "what is photosynthesis",
    )


# --------------------------------------------------------------------------
# Answer hygiene: disambiguation debris must not trail a definition
# --------------------------------------------------------------------------


def test_list_debris_rejects_orphaned_parenthetical():
    """The real leak on the gravity answer.

    "M. C. Escher" split on "M." and orphaned the remainder, which then got
    appended to an otherwise clean definition.
    """
    from shaggoth.dialogue.engine import _is_list_debris

    assert _is_list_debris("Escher) or Gravity, a 1952 mixed-media artwork by M.")


def test_list_debris_rejects_catalogue_entries():
    from shaggoth.dialogue.engine import _is_list_debris

    assert _is_list_debris("Gravity, a 1952 mixed-media artwork by M. C. Escher")
    assert _is_list_debris("Gravity is a 2013 science fiction film directed by someone")
    assert _is_list_debris("Evolution, a 2001 comedy movie about aliens")


def test_list_debris_rejects_index_furniture():
    from shaggoth.dialogue.engine import _is_list_debris

    assert _is_list_debris("All pages with titles beginning with Gravity")
    assert _is_list_debris("This disambiguation page lists articles about the topic")


def test_list_debris_rejects_sentences_cut_mid_name():
    from shaggoth.dialogue.engine import _is_list_debris

    assert _is_list_debris("The work was produced by M.")


def test_list_debris_keeps_real_definitions():
    """The filter must not eat the sentence it is protecting."""
    from shaggoth.dialogue.engine import _is_list_debris

    for good in (
        "Gravity, or gravitation, is the mass-proportionate mutual attraction "
        "between all things that have mass.",
        "Photosynthesis is the process used by plants to convert light energy "
        "into chemical energy.",
        "Machine learning (ML) is a field of study in artificial intelligence.",
        "DNA, or deoxyribonucleic acid, is a molecule that carries genetic "
        "information in living organisms.",
    ):
        assert not _is_list_debris(good), good


def test_compositional_definitions_are_recognised():
    """"An atom consists of a nucleus..." is the lead of the Atom article."""
    from shaggoth.dialogue.engine import _is_definitional, _topic_tokens_for

    tokens = _topic_tokens_for("Atom")
    assert _is_definitional(
        "An atom consists of a nucleus of protons and generally neutrons, "
        "surrounded by an electromagnetically bound swarm of electrons.",
        tokens,
    )


def test_other_compositional_forms():
    from shaggoth.dialogue.engine import _is_definitional, _topic_tokens_for

    tokens = _topic_tokens_for("Water")
    for lead in (
        "Water is composed of hydrogen and oxygen atoms bonded together.",
        "Water comprises two hydrogen atoms and one oxygen atom.",
        "Water is made up of hydrogen and oxygen in a fixed ratio.",
    ):
        assert _is_definitional(lead, tokens), lead


def test_a_caption_still_does_not_count_as_a_definition():
    from shaggoth.dialogue.engine import _is_definitional, _topic_tokens_for

    tokens = _topic_tokens_for("Atom")
    assert not _is_definitional(
        "The black bar is one angstrom ( 10 -10 m or 100 pm ).", tokens
    )


# --------------------------------------------------------------------------
# Model selection
# --------------------------------------------------------------------------


def test_auto_does_not_silently_prefer_an_untrained_tinygpt(tmp_path, monkeypatch):
    """A checkpoint appearing on disk is not evidence that it is any good.

    A finished-but-undertrained TinyGPT run would otherwise downgrade every
    drift reply on the next restart, with nothing in the logs to say why.
    """
    from shaggoth import __main__ as cli

    calls = []
    monkeypatch.setattr(cli, "_load_tinygpt", lambda s: calls.append("tinygpt"))
    monkeypatch.setattr(cli, "_load_markov", lambda s: calls.append("markov"))
    monkeypatch.setattr(cli, "ensure_dirs", lambda: None)
    monkeypatch.setattr(cli, "DialogueEngine", lambda **kw: kw)

    settings = {
        "model": "auto",
        "guardrails_path": str(tmp_path / "g.json"),
        "db_path": ":memory:",
        "bot_name": "Shaggoth",
        "memory_recall_threshold": 0.35,
    }
    cli.build_engine(settings)
    assert "tinygpt" not in calls
    assert "markov" in calls


def test_tinygpt_is_still_available_when_asked_for_explicitly(tmp_path, monkeypatch):
    from shaggoth import __main__ as cli

    calls = []
    monkeypatch.setattr(cli, "_load_tinygpt", lambda s: calls.append("tinygpt"))
    monkeypatch.setattr(cli, "_load_markov", lambda s: calls.append("markov"))
    monkeypatch.setattr(cli, "ensure_dirs", lambda: None)
    monkeypatch.setattr(cli, "DialogueEngine", lambda **kw: kw)

    cli.build_engine({
        "model": "tinygpt",
        "guardrails_path": str(tmp_path / "g.json"),
        "db_path": ":memory:",
        "bot_name": "Shaggoth",
        "memory_recall_threshold": 0.35,
    })
    assert "tinygpt" in calls
