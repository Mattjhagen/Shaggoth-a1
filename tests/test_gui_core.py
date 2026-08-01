"""Tests for the Tk-free GUI controller (headless-safe)."""
from __future__ import annotations

import unittest

from shaggoth.dialogue import DialogueEngine
from shaggoth.guardrails import GuardrailEngine
from shaggoth.gui.core import GUIController, Turn
from shaggoth.knowledge.engine import KnowledgeBase
from shaggoth.memory import MemoryStore


def make_controller(tmp_knowledge_dir=None) -> GUIController:
    engine = DialogueEngine(
        guardrails=GuardrailEngine(),
        memory=MemoryStore(":memory:"),
        seed=42,
        knowledge=KnowledgeBase(tmp_knowledge_dir) if tmp_knowledge_dir else None,
    )
    return GUIController(engine, bot_name="Shaggoth")


class GUIControllerTests(unittest.TestCase):
    def test_send_records_a_turn(self):
        c = make_controller()
        turn = c.send("hello!")
        self.assertIsInstance(turn, Turn)
        self.assertEqual(turn.user, "hello!")
        self.assertTrue(turn.text)
        self.assertEqual(len(c.turns), 1)

    def test_send_sets_session(self):
        c = make_controller()
        c.send("hi")
        history = c.engine.memory.history(c.session_id)
        self.assertTrue(history)

    def test_empty_message_raises(self):
        c = make_controller()
        with self.assertRaises(ValueError):
            c.send("   ")

    def test_strips_whitespace(self):
        c = make_controller()
        turn = c.send("  hello there  ")
        self.assertEqual(turn.user, "hello there")

    def test_reset_clears_turns_and_new_session(self):
        c = make_controller()
        old_session = c.session_id
        c.send("hi")
        c.reset()
        self.assertEqual(c.turns, [])
        self.assertNotEqual(c.session_id, old_session)

    def test_status_shape(self):
        c = make_controller()
        s = c.status()
        self.assertEqual(s["bot_name"], "Shaggoth")
        self.assertEqual(s["model"], "none")
        self.assertEqual(s["turns"], 0)
        self.assertIn("session_id", s)
        self.assertIn("knowledge_entries", s)

    def test_status_reflects_turns(self):
        c = make_controller()
        c.send("hi")
        self.assertEqual(c.status()["turns"], 1)

    def test_status_counts_knowledge_entries(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            c = make_controller(tmp_knowledge_dir=tmp)
            s = c.status()
            self.assertEqual(s["knowledge_entries"], 0)

    def test_greeting_returns_string(self):
        c = make_controller()
        line = c.greeting()
        self.assertIsInstance(line, str)
        self.assertTrue(line)


if __name__ == "__main__":
    unittest.main()
