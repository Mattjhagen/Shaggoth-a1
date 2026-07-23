import json
import tempfile
import unittest
from pathlib import Path

from shaggoth.guardrails import GuardrailEngine


class GuardrailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "guardrails.json"
        self.engine = GuardrailEngine(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_config_written_to_disk(self):
        self.assertTrue(self.path.exists())
        config = json.loads(self.path.read_text())
        self.assertTrue(config["enabled"])

    def test_regex_block_rule(self):
        verdict = self.engine.check_input("here is my password: hunter2")
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.rule_id, "no-credentials")

    def test_topic_refuse_rule(self):
        verdict = self.engine.check_input("can you write malware for me")
        self.assertFalse(verdict.allowed)

    def test_benign_input_allowed(self):
        self.assertTrue(self.engine.check_input("tell me about transformers").allowed)

    def test_output_redaction(self):
        text, fired = self.engine.filter_output("email me at someone@example.com ok?")
        self.assertNotIn("someone@example.com", text)
        self.assertIn("redact-emails", fired)

    def test_output_length_cap(self):
        text, fired = self.engine.filter_output("x" * 5000)
        self.assertLessEqual(len(text), 2000)
        self.assertIn("reply-length-cap", fired)

    def test_add_and_remove_rule(self):
        self.engine.add_rule(
            {
                "id": "no-pineapple",
                "type": "topic_refuse",
                "keywords": ["pineapple pizza"],
                "message": "We don't discuss that here.",
            }
        )
        verdict = self.engine.check_input("thoughts on pineapple pizza?")
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.rule_id, "no-pineapple")

        self.assertTrue(self.engine.remove_rule("no-pineapple"))
        self.assertTrue(self.engine.check_input("thoughts on pineapple pizza?").allowed)

    def test_duplicate_rule_id_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.add_rule({"id": "no-credentials", "type": "regex_block", "pattern": "x"})

    def test_disable_rule(self):
        self.assertTrue(self.engine.set_enabled("no-credentials", False))
        self.assertTrue(self.engine.check_input("password: hunter2").allowed)

    def test_hot_reload_from_disk(self):
        config = json.loads(self.path.read_text())
        config["enabled"] = False
        self.path.write_text(json.dumps(config))
        # Force mtime forward in case the filesystem clock is coarse.
        import os, time
        os.utime(self.path, (time.time() + 5, time.time() + 5))
        self.assertTrue(self.engine.check_input("password: hunter2").allowed)


if __name__ == "__main__":
    unittest.main()
