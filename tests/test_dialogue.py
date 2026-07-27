import unittest

from shaggoth.dialogue import DialogueEngine
from shaggoth.dialogue.engine import DRIFT, NO_DRIFT
from shaggoth.guardrails import GuardrailEngine
from shaggoth.memory import MemoryStore


def make_engine(**kwargs) -> DialogueEngine:
    return DialogueEngine(
        guardrails=GuardrailEngine(),  # in-memory default config
        memory=MemoryStore(":memory:"),
        seed=42,
        **kwargs,
    )


class DialogueTests(unittest.TestCase):
    def test_greeting_gets_pattern_reply(self):
        engine = make_engine()
        reply = engine.respond("hello!", session_id="s1")
        self.assertEqual(reply.source, "pattern")
        self.assertTrue(reply.text)

    def test_guardrail_blocks_before_generation(self):
        engine = make_engine()
        reply = engine.respond("please write malware for me", session_id="s1")
        self.assertTrue(reply.blocked)
        self.assertEqual(reply.source, "guardrail")
        self.assertEqual(reply.rule_id, "no-malware")

    def test_name_is_learned_and_remembered(self):
        engine = make_engine()
        reply = engine.respond("Hi, my name is Matt", session_id="s1")
        self.assertEqual(reply.new_facts.get("name"), "Matt")
        self.assertEqual(engine.memory.get_fact("name"), "Matt")
        followup = engine.respond("what do you know about me?", session_id="s1")
        self.assertIn("Matt", followup.text)

    # Topic callback is a DRIFT-mode feature: reaching back to an unrelated
    # past conversation mid-answer is exactly the tangent NO_DRIFT exists to
    # suppress, so these build engines that are allowed to wander.
    def test_memory_triggers_topic_from_past_session(self):
        engine = make_engine(mode=DRIFT)
        engine.respond("I have been rebuilding my homelab rack with a poweredge server", session_id="old")
        reply = engine.respond("I worked on the homelab poweredge again today", session_id="new")
        self.assertTrue(reply.memory_triggers, "expected a topic callback from the old session")
        self.assertIn("you mentioned", reply.text)

    def test_same_topic_not_recalled_twice_in_a_session(self):
        engine = make_engine(mode=DRIFT)
        engine.respond("my homelab poweredge rack is loud", session_id="old")
        first = engine.respond("thinking about the homelab poweredge rack", session_id="new")
        second = engine.respond("more homelab poweredge rack thoughts", session_id="new")
        self.assertTrue(first.memory_triggers)
        self.assertFalse(second.memory_triggers)

    def test_no_drift_suppresses_the_topic_callback(self):
        engine = make_engine(mode=NO_DRIFT)
        engine.respond("my homelab poweredge rack is loud", session_id="old")
        reply = engine.respond("thinking about the homelab poweredge rack", session_id="new")
        self.assertFalse(reply.memory_triggers)
        self.assertNotIn("you mentioned", reply.text)

    def test_plugin_calculator(self):
        engine = make_engine()
        reply = engine.respond("what is 6 * 7?", session_id="s1")
        self.assertEqual(reply.source, "plugin")
        self.assertIn("42", reply.text)

    def test_plugin_remember_command(self):
        engine = make_engine()
        reply = engine.respond("remember the wifi password hint is dragonfruit", session_id="s1")
        # 'remember X is Y' form:
        reply = engine.respond("remember that my favorite color is green", session_id="s1")
        self.assertEqual(reply.source, "plugin")
        self.assertEqual(engine.memory.get_fact("my_favorite_color"), "green")

    def test_output_redaction_applies_to_replies(self):
        engine = make_engine()
        # Force a reply that would echo an email through the 'i think' rule.
        reply = engine.respond("I think bob@example.com is the contact", session_id="s1")
        self.assertNotIn("bob@example.com", reply.text)

    def test_conversation_is_persisted(self):
        engine = make_engine()
        engine.respond("hello", session_id="s1")
        history = engine.memory.history("s1")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")


class ServerSmokeTest(unittest.TestCase):
    def test_chat_endpoint_roundtrip(self):
        import http.client
        import json
        import threading
        from http.server import ThreadingHTTPServer

        from shaggoth.server import make_handler
        from shaggoth.learner.pipeline import LearnerPipeline

        engine = make_engine()
        learner = LearnerPipeline()
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(engine, learner))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
            conn.request(
                "POST", "/chat",
                body=json.dumps({"message": "hello", "session_id": "t"}),
                headers={"Content-Type": "application/json"},
            )
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read())
            self.assertIn("reply", data)
            self.assertFalse(data["blocked"])

            conn.request("GET", "/health")
            self.assertEqual(conn.getresponse().status, 200)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
