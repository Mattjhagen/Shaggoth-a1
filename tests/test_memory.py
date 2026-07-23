import unittest

from shaggoth.memory import MemoryStore


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_messages_and_history(self):
        self.store.add_message("s1", "user", "hello there")
        self.store.add_message("s1", "assistant", "hi!")
        history = self.store.history("s1")
        self.assertEqual([m["role"] for m in history], ["user", "assistant"])

    def test_fact_extraction(self):
        facts = self.store.extract_and_store_facts("Hey, my name is Matt and I like synthwave.")
        self.assertEqual(facts.get("name"), "Matt")
        self.assertEqual(self.store.get_fact("likes"), "synthwave")

    def test_fact_update_overwrites(self):
        self.store.extract_and_store_facts("my name is Matt")
        self.store.extract_and_store_facts("actually, call me Matthew")
        self.assertEqual(self.store.get_fact("name"), "Matthew")

    def test_recall_finds_related_past_conversation(self):
        self.store.add_message("old-session", "user", "I've been rebuilding my homelab server rack")
        self.store.add_message("old-session", "user", "the weather is nice")
        recalls = self.store.recall("thinking about my homelab again", current_session="new-session")
        self.assertTrue(recalls)
        self.assertIn("homelab", recalls[0].shared_words)

    def test_recall_excludes_current_session(self):
        self.store.add_message("same", "user", "my homelab is great")
        recalls = self.store.recall("tell me about my homelab", current_session="same")
        self.assertEqual(recalls, [])

    def test_recall_ignores_stopword_only_overlap(self):
        self.store.add_message("old", "user", "what do you think about the thing")
        recalls = self.store.recall("what do you think", current_session="new")
        self.assertEqual(recalls, [])


if __name__ == "__main__":
    unittest.main()
