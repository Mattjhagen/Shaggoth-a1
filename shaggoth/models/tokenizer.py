from __future__ import annotations

import json
import re
from collections import defaultdict, Counter
from pathlib import Path


_PATTERN = re.compile(r"""'(?:[sdmt]|ll|ve|re|ll|ve)| ?\w+| ?\S+""")


class BPETokenizer:
    def __init__(self, vocab_size: int = 2048):
        self.vocab_size = vocab_size
        self.merges: dict[tuple[str, str], str] = {}
        self.merge_priority: dict[tuple[str, str], int] = {}
        self.vocab: list[str] = []

    @classmethod
    def from_text(cls, text: str, vocab_size: int = 2048) -> BPETokenizer:
        tok = cls(vocab_size)
        tok.train(text)
        return tok

    def train(self, text: str) -> None:
        words = _PATTERN.findall(text)
        vocab = set()
        for word in words:
            for ch in word:
                vocab.add(ch)
        self.vocab = sorted(vocab)

        splits = {word: list(word) for word in set(words)}
        freqs = Counter(words)
        merges: list[tuple[tuple[str, str], str]] = []

        target = self.vocab_size - len(self.vocab)
        for _ in range(target):
            pairs = Counter()
            for word in set(splits.keys()):
                split = splits[word]
                for i in range(len(split) - 1):
                    pairs[(split[i], split[i + 1])] += freqs[word]
            if not pairs:
                break
            best_pair = pairs.most_common(1)[0][0]
            merged = "".join(best_pair)
            merges.append((best_pair, merged))
            self.vocab.append(merged)
            new_splits: dict[str, list[str]] = {}
            for word, split in splits.items():
                new_split = []
                i = 0
                while i < len(split):
                    if i < len(split) - 1 and (split[i], split[i + 1]) == best_pair:
                        new_split.append(merged)
                        i += 2
                    else:
                        new_split.append(split[i])
                        i += 1
                new_splits[word] = new_split
            splits = new_splits

        self.merges = dict(merges)
        self.merge_priority = {pair: i for i, (pair, _) in enumerate(merges)}

    def encode(self, text: str) -> list[int]:
        stoi = self.stoi
        words = _PATTERN.findall(text)
        tokens = []
        for word in words:
            split = list(word)
            changed = True
            while changed and len(split) > 1:
                changed = False
                best_pair = None
                best_priority = float("inf")
                for i in range(len(split) - 1):
                    pair = (split[i], split[i + 1])
                    pri = self.merge_priority.get(pair)
                    if pri is not None and pri < best_priority:
                        best_priority = pri
                        best_pair = pair
                if best_pair is None:
                    break
                merged = self.merges[best_pair]
                new_split = []
                i = 0
                while i < len(split):
                    if i < len(split) - 1 and (split[i], split[i + 1]) == best_pair:
                        new_split.append(merged)
                        i += 2
                    else:
                        new_split.append(split[i])
                        i += 1
                split = new_split
                changed = True
            tokens.extend(stoi.get(t, stoi.get("?", 0)) for t in split)
        return tokens

    def decode(self, ids: list[int]) -> str:
        itos = self.itos
        return "".join(itos.get(i, "") for i in ids)

    @property
    def stoi(self) -> dict[str, int]:
        return {c: i for i, c in enumerate(self.vocab)}

    @property
    def itos(self) -> dict[int, str]:
        return dict(enumerate(self.vocab))

    def save(self, path: str) -> None:
        Path(path).write_text(json.dumps({
            "vocab": self.vocab,
            "merges": [[list(k), v] for k, v in self.merges.items()],
            "vocab_size": self.vocab_size,
        }))

    @classmethod
    def load(cls, path: str) -> BPETokenizer:
        data = json.loads(Path(path).read_text())
        tok = cls(data["vocab_size"])
        tok.vocab = data["vocab"]
        tok.merges = {tuple(m[0]): m[1] for m in data["merges"]}
        tok.merge_priority = {pair: i for i, pair in enumerate(tok.merges)}
        return tok


if __name__ == "__main__":
    text = "Hello, world! This is a test of the BPE tokenizer."
    tok = BPETokenizer.from_text(text, vocab_size=64)
    ids = tok.encode(text)
    print(f"Input: {text!r}")
    print(f"Tokens ({len(ids)}): {ids}")
    print(f"Decoded: {tok.decode(ids)!r}")
