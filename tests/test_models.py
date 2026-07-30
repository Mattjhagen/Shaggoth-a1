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


class OpenAIHistoryBudgetTests(unittest.TestCase):
    """The OpenAI model trims old conversation turns to stay within budget."""

    def test_long_history_is_trimmed(self):
        from unittest.mock import MagicMock, patch
        from shaggoth.models.openai_model import OpenAIModel, _HISTORY_CHAR_BUDGET

        model = OpenAIModel(api_key="test-key")
        long_turn = "x" * (_HISTORY_CHAR_BUDGET // 2 + 1)
        history = [
            {"role": "user", "content": long_turn},
            {"role": "assistant", "content": long_turn},
            {"role": "user", "content": "recent question"},
            {"role": "assistant", "content": "recent answer"},
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test reply"

        with patch.object(model, "_client_instance") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            model.generate_chat(
                user_message="hello",
                conversation_history=history,
            )
            call_args = mock_client.return_value.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            contents = [m["content"] for m in messages if m["role"] in ("user", "assistant")]
            total_chars = sum(len(c) for c in contents)
            assert total_chars <= _HISTORY_CHAR_BUDGET + len("hello"), (
                f"History {total_chars} chars exceeds budget {_HISTORY_CHAR_BUDGET}"
            )
            assert "recent question" in contents
            assert "recent answer" in contents

    def test_short_history_is_preserved(self):
        from unittest.mock import MagicMock, patch
        from shaggoth.models.openai_model import OpenAIModel

        model = OpenAIModel(api_key="test-key")
        history = [
            {"role": "user", "content": "question 1"},
            {"role": "assistant", "content": "answer 1"},
            {"role": "user", "content": "question 2"},
            {"role": "assistant", "content": "answer 2"},
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test reply"

        with patch.object(model, "_client_instance") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            model.generate_chat(
                user_message="hello",
                conversation_history=history,
            )
            call_args = mock_client.return_value.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            hist_messages = [m for m in messages if m["role"] in ("user", "assistant")]
            # 4 history turns + 1 user_message = 5
            assert len(hist_messages) == 5


    def test_trimming_preserves_user_assistant_pairs(self):
        """Trimming should never orphan an assistant turn from its user turn."""
        from unittest.mock import MagicMock, patch
        from shaggoth.models.openai_model import OpenAIModel, _HISTORY_CHAR_BUDGET

        model = OpenAIModel(api_key="test-key")
        # First pair is just under budget, second pair is small
        big = "x" * (_HISTORY_CHAR_BUDGET - 100)
        history = [
            {"role": "user", "content": big},
            {"role": "assistant", "content": "old answer"},
            {"role": "user", "content": "new question"},
            {"role": "assistant", "content": "new answer"},
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test reply"

        with patch.object(model, "_client_instance") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            model.generate_chat(
                user_message="hello",
                conversation_history=history,
            )
            call_args = mock_client.return_value.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            hist = [m for m in messages if m["role"] in ("user", "assistant")
                    and m["content"] != "hello"]
            # The old pair should be dropped together, keeping the new pair
            roles = [m["role"] for m in hist]
            for i, role in enumerate(roles):
                if role == "assistant" and i > 0:
                    assert roles[i - 1] == "user", (
                        "Assistant turn orphaned without preceding user turn"
                    )


if __name__ == "__main__":
    unittest.main()
