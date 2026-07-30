import unittest

from shaggoth.dialogue import DialogueEngine
from shaggoth.dialogue.engine import (
    DRIFT, NO_DRIFT,
    chitchat_reply, compose_greeting, describe_unknown, has_subject, is_follow_up,
)
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

    def test_greeting_cold_start_never_cites_zero_topics(self):
        for _ in range(20):
            line = compose_greeting(0, "")
            self.assertNotIn("0 topic", line)

    def test_greeting_zero_knowledge_researching_no_crash(self):
        # knowledge_count == 0 with is_researching=True must not divide by
        # zero computing the stale-ratio situational clause.
        for _ in range(20):
            line = compose_greeting(0, "", is_researching=True, research_topic="x")
            self.assertTrue(line)

    def test_greeting_cites_live_state(self):
        seen = {"stale": False, "repair": False, "researching": False}
        for _ in range(200):
            line = compose_greeting(
                100, "gravity",
                stale_count=90, episodes=5, repair_queue=3,
                is_researching=True, research_topic="quantum entanglement",
            )
            if "stale" in line:
                seen["stale"] = True
            if "flagged wrong" in line:
                seen["repair"] = True
            if "quantum entanglement" in line:
                seen["researching"] = True
        self.assertTrue(all(seen.values()), seen)

    def test_greeting_is_varied(self):
        lines = {compose_greeting(50, "algebra") for _ in range(50)}
        self.assertGreater(len(lines), 10)

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


class ConversationFlowTests(unittest.TestCase):
    """Regression tests for the three conversation-flow bugs in the screenshot.

    Bug 1: "Hello" resurrected stale context from a prior session.
    Bug 2: "Okay pick something" crashed the engine with a 500 error.
    Bug 3: "Lol what fell over?" was scraped for topics, producing
           "Blank on lol fell. Not my finest moment. Researching it now."
    """

    # ------------------------------------------------------------------ Bug 1
    def test_greeting_does_not_inject_stale_context(self):
        engine = make_engine()
        # Seed a prior session with a topic.
        engine.respond("what is polarity in chemistry?", session_id="old")
        # A fresh greeting must NOT echo "Last thing you cared about was polarity".
        reply = engine.respond("Hello", session_id="new")
        self.assertNotIn("Last thing you cared about", reply.text)
        self.assertNotIn("polarity", reply.text)

    def test_greeting_gets_pattern_response(self):
        engine = make_engine()
        reply = engine.respond("hi", session_id="s1")
        # Pattern engine handles greetings; source stays "pattern".
        self.assertEqual(reply.source, "pattern")
        # It must NOT be the stale-context injection.
        self.assertNotIn("Last thing you cared about", reply.text)
        self.assertNotIn("You brought up", reply.text)

    # ------------------------------------------------------------------ Bug 2
    def test_okay_pick_something_does_not_crash(self):
        engine = make_engine()
        # Must not raise; must return a usable reply.
        reply = engine.respond("okay pick something", session_id="s1")
        self.assertIsNotNone(reply)
        self.assertTrue(reply.text)
        self.assertNotEqual(reply.source, "error")

    def test_pick_is_not_a_research_subject(self):
        # "okay pick something" contains only non-subject words now.
        self.assertFalse(has_subject("okay pick something"))

    def test_social_words_are_not_subjects(self):
        self.assertFalse(has_subject("lol"))
        self.assertFalse(has_subject("haha"))
        self.assertFalse(has_subject("omg"))

    # ------------------------------------------------------------------ Bug 3
    def test_social_prefix_is_follow_up(self):
        self.assertTrue(is_follow_up("lol what fell over?"))
        self.assertTrue(is_follow_up("haha that's funny"))
        self.assertTrue(is_follow_up("omg seriously?"))

    def test_lol_what_fell_over_does_not_trigger_unknown_topic(self):
        engine = make_engine()
        reply = engine.respond("lol what fell over?", session_id="s1")
        # Must be handled as a follow-up, not a "blank on lol fell" fallback.
        self.assertNotIn("Blank on", reply.text)
        self.assertNotIn("lol fell", reply.text)
        self.assertNotEqual(reply.source, "fallback")

    def test_describe_unknown_filters_social_words(self):
        result = describe_unknown("lol what fell over")
        # Social word must not appear as the subject of the ignorance reply.
        self.assertNotIn("lol fell", result)
        self.assertNotIn("Blank on lol", result)

    def test_what_about_that_is_follow_up(self):
        self.assertTrue(is_follow_up("what about that"))
        self.assertTrue(is_follow_up("what about this?"))
        self.assertTrue(is_follow_up("what about it"))

    def test_what_about_new_topic_is_not_follow_up(self):
        self.assertFalse(is_follow_up("what about quantum computing"))
        self.assertFalse(is_follow_up("what about the new telescope?"))

    def test_social_prefix_with_real_topic_is_not_follow_up(self):
        """'lol what is quantum computing' should reach the knowledge pipeline."""
        self.assertFalse(is_follow_up("lol what is quantum computing"))
        self.assertFalse(is_follow_up("wtf is photosynthesis"))
        self.assertFalse(is_follow_up("omg tell me about DNA"))

    def test_describe_unknown_no_research_promise_when_flag_false(self):
        for _ in range(20):
            result = describe_unknown("what is quantum computing", researching=False)
            self.assertNotIn("research", result.lower())
            self.assertNotIn("looking into", result.lower())
            self.assertNotIn("reading up", result.lower())
            self.assertNotIn("pulling information", result.lower())

    def test_describe_unknown_promises_research_by_default(self):
        found_research = False
        for _ in range(50):
            result = describe_unknown("what is quantum computing")
            if "research" in result.lower() or "looking into" in result.lower():
                found_research = True
                break
        self.assertTrue(found_research)

    def test_engine_without_curiosity_does_not_promise_research(self):
        """When curiosity_available is False, the fallback reply must not
        promise research that will never happen."""
        engine = make_engine()
        # Default: curiosity_available is False
        self.assertFalse(engine.curiosity_available)
        for _ in range(20):
            reply = engine.respond("what is quantum computing", session_id="t1")
            if reply.source == "fallback":
                self.assertNotIn("research", reply.text.lower())
                self.assertNotIn("looking into", reply.text.lower())
                self.assertNotIn("reading up", reply.text.lower())

    def test_engine_with_curiosity_flag_promises_research(self):
        """When curiosity_available is True, describe_unknown receives
        researching=True so fallback replies can promise research."""
        from unittest.mock import patch
        engine = make_engine()
        engine.curiosity_available = True
        with patch("shaggoth.dialogue.engine.describe_unknown",
                   return_value="Researching quantum computing now.") as mock_du:
            reply = engine.respond("what is quantum computing", session_id="t2")
        self.assertEqual(reply.source, "fallback")
        mock_du.assert_called_once()
        _args, kwargs = mock_du.call_args
        self.assertTrue(kwargs.get("researching", _args[1] if len(_args) > 1 else False))


if __name__ == "__main__":
    unittest.main()
