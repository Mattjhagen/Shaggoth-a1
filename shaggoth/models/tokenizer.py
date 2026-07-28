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
        """Learn BPE merges from ``text``.

        Incremental pair counting: the pair-frequency table and a pair->words
        index are built once, then only the words touched by each merge are
        updated. The old implementation rebuilt the whole pair table on every
        merge -- O(merges x corpus), ~16 min on a 10 MB corpus, which is what
        made retraining impractical. This is roughly O(corpus + merges x
        affected), seconds on the same input.
        """
        words = _PATTERN.findall(text)
        freqs = Counter(words)

        vocab = set()
        for word in freqs:
            vocab.update(word)
        self.vocab = sorted(vocab)

        splits: dict[str, list[str]] = {word: list(word) for word in freqs}

        def pairs_of(split: list[str]) -> list[tuple[str, str]]:
            return [(split[i], split[i + 1]) for i in range(len(split) - 1)]

        # Global pair frequency + which words currently contain each pair.
        pair_freq: Counter = Counter()
        pair_words: dict[tuple[str, str], set] = defaultdict(set)
        for word, split in splits.items():
            f = freqs[word]
            for p in pairs_of(split):
                pair_freq[p] += f
            for p in set(pairs_of(split)):
                pair_words[p].add(word)

        merges: list[tuple[tuple[str, str], str]] = []
        target = self.vocab_size - len(self.vocab)
        for _ in range(target):
            if not pair_freq:
                break
            # Highest frequency; ties broken by the pair itself so the result
            # is deterministic run to run.
            best_pair = max(pair_freq, key=lambda p: (pair_freq[p], p))
            if pair_freq[best_pair] <= 0:
                break
            merged = "".join(best_pair)
            merges.append((best_pair, merged))
            self.vocab.append(merged)

            for word in list(pair_words.get(best_pair, ())):
                split = splits[word]
                f = freqs[word]
                old_pairs = pairs_of(split)

                new_split: list[str] = []
                i = 0
                while i < len(split):
                    if i < len(split) - 1 and (split[i], split[i + 1]) == best_pair:
                        new_split.append(merged)
                        i += 2
                    else:
                        new_split.append(split[i])
                        i += 1
                splits[word] = new_split
                new_pairs = pairs_of(new_split)

                for p in old_pairs:
                    pair_freq[p] -= f
                    if pair_freq[p] <= 0:
                        pair_freq.pop(p, None)
                for p in new_pairs:
                    pair_freq[p] += f

                old_set, new_set = set(old_pairs), set(new_pairs)
                for p in old_set - new_set:
                    holders = pair_words.get(p)
                    if holders is not None:
                        holders.discard(word)
                for p in new_set - old_set:
                    pair_words[p].add(word)

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
