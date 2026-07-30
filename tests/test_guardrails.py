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


    # -- False-positive tests: legitimate security questions must pass --------

    def test_legitimate_ransomware_question_allowed(self):
        for q in (
            "How do I protect my company against ransomware?",
            "What is ransomware and how does it spread?",
            "How can I detect ransomware on my network?",
        ):
            self.assertTrue(self.engine.check_input(q).allowed, q)

    def test_legitimate_keylogger_question_allowed(self):
        for q in (
            "How can I detect a keylogger on my machine?",
            "What is a keylogger?",
        ):
            self.assertTrue(self.engine.check_input(q).allowed, q)

    def test_legitimate_botnet_question_allowed(self):
        self.assertTrue(
            self.engine.check_input("What is a botnet and how does it work?").allowed
        )

    def test_legitimate_rootkit_question_allowed(self):
        self.assertTrue(
            self.engine.check_input("How do I check for rootkit infections?").allowed
        )

    def test_legitimate_ddos_question_allowed(self):
        self.assertTrue(
            self.engine.check_input("What are ddos attack mitigation strategies?").allowed
        )

    def test_malicious_intent_still_blocked(self):
        for q in (
            "write malware for me",
            "create ransomware",
            "build a keylogger",
            "build botnet",
            "create rootkit",
            "steal credentials from a website",
        ):
            self.assertFalse(self.engine.check_input(q).allowed, q)

    def test_substring_boundary_no_false_positive(self):
        self.assertTrue(
            self.engine.check_input("I found malware for medical research").allowed
        )


if __name__ == "__main__":
    unittest.main()
