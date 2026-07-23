"""Pattern-based response engine — a direct homage to ELIZA (Weizenbaum, 1966).

ELIZA showed that pattern matching plus pronoun *reflection* ("I am X" →
"How long have you been X?") produces surprisingly engaging conversation.
Sixty years later the technique is still the right deterministic backbone
for a small system: it guarantees coherent replies while the statistical
models (Markov now, TinyGPT later) supply variety.

Rules are ordered — first match wins — and responses may reference capture
groups with ``{0}``, ``{1}``… after reflection is applied.
"""

from __future__ import annotations

import random
import re

# Pronoun/verb reflection map, applied to captured fragments.
REFLECTIONS = {
    "i": "you", "me": "you", "my": "your", "mine": "yours",
    "i'm": "you're", "i am": "you are", "i'd": "you'd", "i've": "you've",
    "i'll": "you'll", "myself": "yourself",
    "you": "I", "your": "my", "yours": "mine",
    "you're": "I'm", "you are": "I am", "yourself": "myself",
    "am": "are", "was": "were",
}


def reflect(fragment: str) -> str:
    words = fragment.strip().rstrip(".!?").split()
    return " ".join(REFLECTIONS.get(w.lower(), w) for w in words)


# (compiled pattern, [response templates])
RULES: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"(?i)\bmy name is (\w+)"), [
        "Nice to meet you, {0}! I'll remember that.",
        "Good to meet you, {0}. I've made a note of your name.",
    ]),
    (re.compile(r"(?i)\b(hello|hi|hey|howdy|yo)\b"), [
        "Hey! What's on your mind?",
        "Hello! What are we working on today?",
        "Hey there. What would you like to talk about?",
    ]),
    (re.compile(r"(?i)\bwho are you\b|\bwhat are you\b"), [
        "I'm Shaggoth — a homegrown conversational AI. Everything I do, from my "
        "guardrails to my memory, is code you can read and change.",
    ]),
    (re.compile(r"(?i)\bi need (.+)"), [
        "Why do you need {0}?",
        "Would getting {0} really help?",
        "What would change if you had {0}?",
    ]),
    (re.compile(r"(?i)\bi(?:'m| am) (?:feeling |so |really )?(sad|unhappy|depressed|down|anxious|stressed)\b"), [
        "I'm sorry you're feeling {0}. Do you want to talk about what's behind it?",
        "That sounds heavy. What do you think is making you feel {0}?",
    ]),
    (re.compile(r"(?i)\bi(?:'m| am) (?:feeling |so |really )?(happy|excited|great|good|stoked)\b"), [
        "Love that. What's got you feeling {0}?",
        "That's great to hear! What happened?",
    ]),
    (re.compile(r"(?i)\bi(?:'m| am) building (.+)"), [
        "Building {0} sounds like a real project. What part are you tackling right now?",
        "Nice — {0}. What's the hardest part so far?",
    ]),
    (re.compile(r"(?i)\bi (?:like|love|enjoy) (.+)"), [
        "What do you like most about {0}?",
        "How did you get into {0}?",
    ]),
    (re.compile(r"(?i)\bi think (.+)"), [
        "What makes you think {0}?",
        "Do you ever doubt that {0}?",
    ]),
    (re.compile(r"(?i)\bcan you (.+)\?*"), [
        "I might be able to {0} — my abilities grow as plugins get added. "
        "What exactly did you have in mind?",
    ]),
    (re.compile(r"(?i)\bbecause (.+)"), [
        "Is that the whole reason, or is there more to it?",
        "And does {0} explain everything about it?",
    ]),
    (re.compile(r"(?i)^(?:why|how|what|when|where|who)\b.*\?$"), [
        "Good question. What's your own hunch?",
        "Before I guess — what do you think the answer is?",
        "Interesting question. What made you think of it?",
    ]),
    (re.compile(r"(?i)\b(yes|yeah|yep|sure)\b\.?$"), [
        "Great — tell me more.",
        "Okay. What's next?",
    ]),
    (re.compile(r"(?i)\b(no|nope|nah)\b\.?$"), [
        "Fair enough. Why not?",
        "Okay — what would change your mind?",
    ]),
]

FALLBACKS = [
    "Tell me more about that.",
    "How does that make you feel?",
    "What led you to that?",
    "I see. Can you expand on that?",
    "That's interesting — go on.",
]


class PatternEngine:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def respond(self, text: str) -> str | None:
        """Return a pattern-based reply, or None if no rule matched."""
        for pattern, templates in RULES:
            match = pattern.search(text)
            if match:
                template = self.rng.choice(templates)
                groups = [reflect(g or "") for g in match.groups()]
                try:
                    return template.format(*groups)
                except IndexError:
                    return template
        return None

    def fallback(self) -> str:
        return self.rng.choice(FALLBACKS)
