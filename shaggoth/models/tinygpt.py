"""TinyGPT — a from-scratch GPT-style transformer, written to be read.

This is the "real" homegrown model: a decoder-only transformer in the
lineage of *Attention Is All You Need* (Vaswani et al., 2017) and GPT-1/2
(Radford et al., 2018/2019), at a scale a single machine like the R510 can
train from scratch on a small corpus. Character-level tokenization keeps the
whole pipeline dependency-free apart from PyTorch itself.

PyTorch is an *optional* dependency (``pip install shaggoth[gpt]`` or
``pip install torch``). Everything else in Shaggoth runs without it; the
dialogue engine falls back to the Markov model when torch is absent.

Train on the R510 (see docs/R510_SETUP.md):

    python3 -m shaggoth train --model tinygpt --corpus data/corpus/starter.txt \
        --steps 5000 --out data/tinygpt.pt
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .base import LanguageModel

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without torch
    TORCH_AVAILABLE = False


@dataclass
class GPTConfig:
    vocab_size: int = 128
    block_size: int = 128  # context length
    n_layer: int = 4
    n_head: int = 4
    n_embd: int = 128
    dropout: float = 0.1


class CharTokenizer:
    """Character-level tokenizer: simple, lossless, no external vocab files."""

    def __init__(self, text: str | None = None):
        self.chars: list[str] = sorted(set(text)) if text else []
        self.stoi = {c: i for i, c in enumerate(self.chars)}
        self.itos = dict(enumerate(self.chars))

    def encode(self, text: str) -> list[int]:
        return [self.stoi[c] for c in text if c in self.stoi]

    def decode(self, ids: list[int]) -> str:
        return "".join(self.itos.get(i, "") for i in ids)

    @property
    def vocab_size(self) -> int:
        return len(self.chars)


if TORCH_AVAILABLE:

    class CausalSelfAttention(nn.Module):
        def __init__(self, cfg: GPTConfig):
            super().__init__()
            assert cfg.n_embd % cfg.n_head == 0
            self.n_head = cfg.n_head
            self.qkv = nn.Linear(cfg.n_embd, 3 * cfg.n_embd)
            self.proj = nn.Linear(cfg.n_embd, cfg.n_embd)
            self.dropout = nn.Dropout(cfg.dropout)
            mask = torch.tril(torch.ones(cfg.block_size, cfg.block_size))
            self.register_buffer("mask", mask.view(1, 1, cfg.block_size, cfg.block_size))

        def forward(self, x):
            B, T, C = x.shape
            q, k, v = self.qkv(x).split(C, dim=2)
            # (B, n_head, T, head_dim)
            q = q.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
            k = k.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
            v = v.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
            att = (q @ k.transpose(-2, -1)) * (k.size(-1) ** -0.5)
            att = att.masked_fill(self.mask[:, :, :T, :T] == 0, float("-inf"))
            att = self.dropout(F.softmax(att, dim=-1))
            y = (att @ v).transpose(1, 2).contiguous().view(B, T, C)
            return self.dropout(self.proj(y))

    class Block(nn.Module):
        def __init__(self, cfg: GPTConfig):
            super().__init__()
            self.ln1 = nn.LayerNorm(cfg.n_embd)
            self.attn = CausalSelfAttention(cfg)
            self.ln2 = nn.LayerNorm(cfg.n_embd)
            self.mlp = nn.Sequential(
                nn.Linear(cfg.n_embd, 4 * cfg.n_embd),
                nn.GELU(),
                nn.Linear(4 * cfg.n_embd, cfg.n_embd),
                nn.Dropout(cfg.dropout),
            )

        def forward(self, x):
            x = x + self.attn(self.ln1(x))
            x = x + self.mlp(self.ln2(x))
            return x

    class GPT(nn.Module):
        def __init__(self, cfg: GPTConfig):
            super().__init__()
            self.cfg = cfg
            self.tok_emb = nn.Embedding(cfg.vocab_size, cfg.n_embd)
            self.pos_emb = nn.Embedding(cfg.block_size, cfg.n_embd)
            self.drop = nn.Dropout(cfg.dropout)
            self.blocks = nn.ModuleList(Block(cfg) for _ in range(cfg.n_layer))
            self.ln_f = nn.LayerNorm(cfg.n_embd)
            self.head = nn.Linear(cfg.n_embd, cfg.vocab_size, bias=False)

        def forward(self, idx, targets=None):
            B, T = idx.shape
            pos = torch.arange(T, device=idx.device)
            x = self.drop(self.tok_emb(idx) + self.pos_emb(pos))
            for block in self.blocks:
                x = block(x)
            logits = self.head(self.ln_f(x))
            loss = None
            if targets is not None:
                loss = F.cross_entropy(
                    logits.view(-1, logits.size(-1)), targets.view(-1)
                )
            return logits, loss

        @torch.no_grad()
        def sample(self, idx, max_new_tokens: int, temperature: float = 0.8):
            self.eval()
            for _ in range(max_new_tokens):
                ctx = idx[:, -self.cfg.block_size :]
                logits, _ = self(ctx)
                logits = logits[:, -1, :] / max(temperature, 1e-6)
                probs = F.softmax(logits, dim=-1)
                idx = torch.cat([idx, torch.multinomial(probs, 1)], dim=1)
            return idx


class TinyGPTModel(LanguageModel):
    """LanguageModel wrapper so the dialogue engine can use TinyGPT
    interchangeably with the Markov model."""

    name = "tinygpt"

    def __init__(self, cfg: GPTConfig | None = None):
        if not TORCH_AVAILABLE:
            raise RuntimeError(
                "TinyGPT needs PyTorch: pip install torch  (see docs/R510_SETUP.md)"
            )
        self.cfg = cfg or GPTConfig()
        self.tokenizer = CharTokenizer()
        self.model: "GPT | None" = None
        self._trained = False

    def is_trained(self) -> bool:
        return self._trained

    def train(
        self,
        text: str,
        steps: int = 2000,
        batch_size: int = 32,
        lr: float = 3e-4,
        log_every: int = 100,
        device: str | None = None,
    ) -> None:
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = CharTokenizer(text)
        self.cfg.vocab_size = self.tokenizer.vocab_size
        data = torch.tensor(self.tokenizer.encode(text), dtype=torch.long)
        if len(data) <= self.cfg.block_size + 1:
            raise ValueError("corpus too small for the configured block_size")

        self.model = GPT(self.cfg).to(device)
        opt = torch.optim.AdamW(self.model.parameters(), lr=lr)
        self.model.train()
        for step in range(steps):
            ix = torch.randint(len(data) - self.cfg.block_size - 1, (batch_size,))
            x = torch.stack([data[i : i + self.cfg.block_size] for i in ix]).to(device)
            y = torch.stack(
                [data[i + 1 : i + self.cfg.block_size + 1] for i in ix]
            ).to(device)
            _, loss = self.model(x, y)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            if log_every and step % log_every == 0:
                print(f"step {step:5d}  loss {loss.item():.4f}")
        self._trained = True

    def generate(self, prompt: str = "", max_tokens: int = 200) -> str:
        if self.model is None:
            raise RuntimeError("TinyGPT is not trained/loaded yet")
        device = next(self.model.parameters()).device
        ids = self.tokenizer.encode(prompt) or [0]
        idx = torch.tensor([ids], dtype=torch.long, device=device)
        out = self.model.sample(idx, max_new_tokens=max_tokens)
        return self.tokenizer.decode(out[0].tolist())[len(prompt) :]

    def save(self, path: str) -> None:
        if self.model is None:
            raise RuntimeError("nothing to save")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "config": asdict(self.cfg),
                "chars": self.tokenizer.chars,
                "state_dict": self.model.state_dict(),
            },
            path,
        )
        # Sidecar JSON so other tools can inspect the checkpoint without torch.
        with open(str(path) + ".json", "w", encoding="utf-8") as fh:
            json.dump({"config": asdict(self.cfg), "vocab_size": self.tokenizer.vocab_size}, fh)

    def load(self, path: str) -> None:
        ckpt = torch.load(path, map_location="cpu")
        self.cfg = GPTConfig(**ckpt["config"])
        self.tokenizer = CharTokenizer()
        self.tokenizer.chars = ckpt["chars"]
        self.tokenizer.stoi = {c: i for i, c in enumerate(self.tokenizer.chars)}
        self.tokenizer.itos = dict(enumerate(self.tokenizer.chars))
        self.model = GPT(self.cfg)
        self.model.load_state_dict(ckpt["state_dict"])
        self._trained = True
