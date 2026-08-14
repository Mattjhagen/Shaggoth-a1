"""Regressions for two bugs that were both silent in production.

Neither failure raised anything -- one served stale answers until the process
restarted, the other read keyword fragments back to the user as if they were a
topic. Both are cheap to assert and expensive to notice by hand.
"""

from shaggoth.dialogue.engine import describe_unknown
from shaggoth.knowledge.engine import KnowledgeBase


class TestMaybeReloadSeesDeletions:
    """maybe_reload() used to iterate only the files that still existed.

    Comparing mtimes across surviving files can never observe a removal, so a
    deleted entry stayed queryable until restart. It disappeared only by
    accident, when some *other* file was written and forced a full rescan.
    """

    def _corpus(self, tmp_path):
        (tmp_path / "alpha.md").write_text(
            "Alpha is a subject concerning alpha particles and physics."
        )
        (tmp_path / "beta.md").write_text(
            "Beta is a separate subject concerning beta decay and radiation."
        )
        return KnowledgeBase(tmp_path)

    def test_deletion_is_detected_with_no_other_file_touched(self, tmp_path):
        kb = self._corpus(tmp_path)
        assert kb.query("alpha particles")

        (tmp_path / "alpha.md").unlink()
        kb._last_check = 0  # bypass the check throttle, not the detection

        assert kb.maybe_reload() is True
        assert not any(e.topic == "Alpha" for e in kb._entries)
        assert kb.query("alpha particles") == []

    def test_addition_is_still_detected(self, tmp_path):
        kb = self._corpus(tmp_path)
        (tmp_path / "gamma.md").write_text(
            "Gamma is a third subject concerning gamma rays and shielding."
        )
        kb._last_check = 0

        assert kb.maybe_reload() is True
        assert any(e.topic == "Gamma" for e in kb._entries)

    def test_quiet_corpus_does_not_rescan(self, tmp_path):
        """An empty file must not read as a deletion on every check.

        _scan() skips empty files, so recording only the paths that produced
        entries would leave a permanent mismatch and rescan forever.
        """
        (tmp_path / "empty.md").write_text("")
        kb = self._corpus(tmp_path)
        kb._last_check = 0

        assert kb.maybe_reload() is False


class TestDescribeUnknownSubject:
    """It printed the first extracted keywords raw, with no check that they
    formed a subject -- so meta-questions and filler came back as nonsense."""

    def test_meta_question_does_not_echo_fragments(self):
        reply = describe_unknown("how many topics do you know so far")
        assert "topics far" not in reply.lower()

    def test_filler_question_does_not_echo_fragments(self):
        reply = describe_unknown("how does that sit with you")
        # "sit" is a verb here, never the subject of the question.
        assert "on sit" not in reply.lower()
        assert "of sit" not in reply.lower()

    def test_a_real_subject_is_still_named(self):
        assert "quantum chromodynamics" in describe_unknown(
            "what is quantum chromodynamics"
        ).lower()

    def test_a_single_strong_word_is_still_a_subject(self):
        # The guard filters by what the words are, not how many -- one good
        # noun is a perfectly good subject.
        assert "photosynthesis" in describe_unknown("what is photosynthesis").lower()
