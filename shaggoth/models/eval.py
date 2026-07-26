from __future__ import annotations

import math


def perplexity(model, text: str, tokenizer, block_size: int = 256) -> dict:
    import torch

    ids = tokenizer.encode(text)
    if len(ids) < block_size + 1:
        return {"perplexity": float("inf"), "loss": float("inf"), "tokens": len(ids), "error": "text too short"}

    device = next(model.parameters()).device
    losses = []
    total_tokens = 0
    stride = max(block_size // 2, 1)
    for i in range(0, len(ids) - block_size - 1, stride):
        chunk = ids[i : i + block_size + 1]
        x = torch.tensor([chunk[:-1]], dtype=torch.long, device=device)
        y = torch.tensor([chunk[1:]], dtype=torch.long, device=device)
        _, loss = model(x, y)
        losses.append(loss.item())
        total_tokens += block_size

    avg_loss = sum(losses) / len(losses)
    ppl = math.exp(avg_loss)

    return {
        "perplexity": round(ppl, 2),
        "loss": round(avg_loss, 4),
        "tokens_evaluated": total_tokens,
        "chunks": len(losses),
    }
