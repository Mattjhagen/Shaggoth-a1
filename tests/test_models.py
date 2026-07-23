import tempfile
import unittest
from pathlib import Path

from shaggoth.models.markov import MarkovModel, detokenize, tokenize


class MarkovTests(unittest.TestCase):
    CORPUS = (
        "the cat sat on the mat. the cat ate the fish. "
        "the dog sat on the rug. the dog chased the cat."
    )

    def test_tokenize_roundtrip(self):
        tokens = tokenize("Hello, world! How are you?")
        self.assertIn("Hello", tokens)
        self.assertIn(",", tokens)
        text = detokenize(["hello", ",", "world", "!"])
        self.assertEqual(text, "Hello, world!")

    def test_untrained_model_reports_untrained(self):
        self.assertFalse(MarkovModel().is_trained())

    def test_train_and_generate(self):
        model = MarkovModel(order=2, seed=42)
        model.train(self.CORPUS)
        self.assertTrue(model.is_trained())
        out = model.generate("the cat", max_tokens=20)
        self.assertTrue(out)
        # Every generated word must come from the corpus vocabulary.
        vocab = set(tokenize(self.CORPUS.lower()))
        for word in tokenize(out.lower()):
            self.assertIn(word, vocab)

    def test_generate_with_unseen_prompt_still_produces_text(self):
        model = MarkovModel(order=2, seed=1)
        model.train(self.CORPUS)
        self.assertTrue(model.generate("quantum entanglement", max_tokens=10))

    def test_save_and_load(self):
        model = MarkovModel(order=2, seed=7)
        model.train(self.CORPUS)
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "model.json")
            model.save(path)
            loaded = MarkovModel()
            loaded.load(path)
            self.assertTrue(loaded.is_trained())
            self.assertEqual(loaded.order, 2)
            self.assertTrue(loaded.generate("the dog", max_tokens=10))


if __name__ == "__main__":
    unittest.main()
