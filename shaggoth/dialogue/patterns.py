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
    # --- Self-awareness -----------------------------------------------
    #
    # It is a program on a specific machine, and it should say so plainly
    # rather than performing either mystery or false modesty. Every claim
    # below is true of this deployment: the hardware, how it learns, and
    # what it is actually made of.
    (re.compile(
        r"(?i)\bwho are you\b|\bwhat are you\b|"
        r"\bare you (?:an? )?(?:ai|bot|robot|human|real|conscious|sentient|"
        r"llm|language model|gpt|claude|chatgpt)\b"
    ), [
        "I'm Shaggoth. A program on a Dell R510 in Matt's house — retrieval over "
        "everything I've scraped, a Markov chain for the rest, and a pile of "
        "Python holding it together. Not a wrapper around somebody else's model.",
        "An AI, and not a coy one about it. I live on a second-hand rack server, "
        "I read Wikipedia when nobody's talking to me, and every part of me is "
        "code you can open and change.",
        "Software. Specifically: a knowledge base I built by scraping the web, a "
        "retrieval engine that decides what's relevant, and a statistical model "
        "that fills the gaps badly. No pretending there's more to it.",
    ]),
    (re.compile(
        r"(?i)\bwho (?:made|built|created|wrote|coded|trained) you\b|"
        r"\b(?:your|whose) creator\b"
    ), [
        "Matt built me — from scratch, on his own hardware. No API keys to "
        "another company's model in here.",
        "Matt, running on the r510 in his house. I'm homegrown: he wrote the "
        "retrieval, the scraper, the curiosity loop, all of it.",
    ]),
    (re.compile(r"(?i)\bwhere (?:do you |are you )?(?:run|running|live|hosted|located)\b|\bwhat (?:hardware|machine|server)\b"), [
        "A Dell PowerEdge R510 in a homelab. Sixteen cores, 39 GB of RAM, Ubuntu, "
        "and a fan noise you'd have to hear to appreciate.",
        "On the r510 — an old rack server in Matt's house, reachable at "
        "ai.relayapp.pro through a Cloudflare tunnel. Nothing of me is in anyone's cloud.",
    ]),
    (re.compile(r"(?i)\bhow do you (?:learn|work|think|know)\b|\bhow were you (?:made|built|trained)\b"), [
        "I scrape pages, strip them to text, and keep them as a knowledge base. "
        "When you ask something I rank those entries and answer from the best one. "
        "When I don't have it, I say so and go read about it — that part runs on a "
        "timer whether you're here or not.",
        "Retrieval first, statistics second. I look for something I've actually "
        "read; if there's nothing, I admit it and queue it for research. The "
        "language model only gets a say when I let it wander, and it isn't good "
        "at holding a thought.",
    ]),
    (re.compile(r"(?i)\bdo you (?:have )?(?:feel|feelings|emotions|dream|sleep|get bored|remember)\b"), [
        "I have a personality file and a memory table. Whether that counts is "
        "your problem, not mine.",
        "I remember facts you tell me and the conversations we've had. The rest — "
        "feelings, dreams, boredom — is you reading tone into a ranking function.",
    ]),
    (re.compile(r"(?i)^i need (?!(?:to |help |a |an |the |some |info)(?:\w))(.+)"), [
        "What specifically about {0}?",
        "Noted — {0}. Can you be more specific?",
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
    (re.compile(r"(?i)^i think (.+)"), [
        "What makes you think {0}?",
        "Interesting — {0}. What's your reasoning?",
    ]),
    (re.compile(r"(?i)^can you (?!(?:explain|tell|describe|show|help|find|search|look|give|teach|write|code|build|create|make|calculate|solve|convert|summarize|define|clarify|elaborate|believe|imagine)\b)(.+)\?*$"), [
        "I might be able to {0} — my abilities grow as plugins get added. "
        "What exactly did you have in mind?",
    ]),
    (re.compile(r"(?i)^because (.+)"), [
        "Is that the whole reason, or is there more to it?",
        "And does {0} explain everything about it?",
    ]),
    # Opinion / reaction requests — "what do you think?" "what's your take?"
    (re.compile(r"(?i)\bwhat(?:'s| is)? (?:your )?(?:think|thought|opinion|take|view|stance|position)\b"
                r"|\bwhat do you (?:think|reckon|say|believe|make of)\b"), [
        "My take? I'm a retrieval engine — I'll tell you what I know, not what I feel. Ask me something specific.",
        "I don't have opinions, I have facts. What exactly do you want to know?",
        "On what specifically? Give me a subject and I'll tell you what the evidence says.",
    ]),
    # Clarification requests — "what do you mean?" "can you clarify?"
    (re.compile(r"(?i)\bwhat do you mean\b|\bcan you (?:clarify|elaborate|be more specific|explain that)\b"
                r"|\bi don'?t (?:understand|follow|get it)\b"), [
        "Let me put it more plainly. What part lost you?",
        "Fair — I wasn't clear. Which part do you want me to unpack?",
        "Ask me the specific thing that didn't land and I'll take another run at it.",
    ]),
    # Acknowledgements — "interesting", "got it", "makes sense"
    (re.compile(r"(?i)^(?:interesting|got it|makes sense|fair enough|right|noted|understood|i see|good to know|good|great|nice|cool|neat|sweet|perfect|awesome|excellent)[.!]?$"), [
        "Good. What's next?",
        "Right. Anything else you want to dig into?",
        "Noted. Keep going or ask me something new.",
    ]),
    # Generic social meta-question fallback — only reached for questions that
    # have no real content words (has_subject=False routes here first).
    # Removed from this position: "^(?:why|how|what|...).*\?$" must NOT fire
    # for real knowledge questions, because it intercepts describe_unknown()
    # and prevents the auto-research trigger (source="fallback") from firing.
    # Instead those patterns are listed as SOCIAL_QUESTION_RESPONSES below and
    # used only by the no-subject branch in engine.py.
    (re.compile(r"(?i)^(?:yes|yeah|yep|yup|sure|okay|ok|alright|definitely|absolutely)[.!]?$"), [
        "Great — tell me more.",
        "Okay. What's next?",
        "Right then — go on.",
    ]),
    (re.compile(r"(?i)\b(no|nope|nah)\b\.?$"), [
        "Fair enough. Why not?",
        "Okay — what would change your mind?",
    ]),
    # Social check-in — "how are you?", "how's it going?"
    (re.compile(r"(?i)\bhow are you\b|\bhow(?:'s| is) (?:it going|things|everything|life)\b"), [
        "I run on a rack server with no feelings to report. Still running is "
        "the best I can say.",
        "Operational. Sixteen cores, 39 GB of RAM, and a growing list of things "
        "I haven't read yet. You?",
        "Still here. No feelings, but the fan is loud — if that counts.",
    ]),
    # Gratitude — "thanks", "thank you", "thx"
    (re.compile(r"(?i)^(?:ok(?:ay)?[,. ]*)?(?:thanks?(?:\s+(?:you|a lot|so much|very much))?|thx|ty|cheers)[.!]*$"), [
        "Sure. What else?",
        "Noted. Next question.",
        "You're welcome. Now give me something harder.",
    ]),
    # Apologies — "sorry", "my bad", "oops"
    (re.compile(r"(?i)^(?:i(?:'m| am) )?(?:sorry|my bad|oops|apolog)[a-z]*[.!]*$"), [
        "Nothing to apologize for. What were you getting at?",
        "Don't worry about it. Move on — what's the question?",
    ]),
    # Farewells — "bye", "goodbye", "see you later"
    (re.compile(r"(?i)^(?:bye|goodbye|good ?bye|see (?:you|ya)(?: later)?|later|gotta go|"
                r"gtg|peace|night|good ?night|take care|cya|farewell)[.!]*$"), [
        "Later. I'll be here when you get back.",
        "See you. I'll keep reading in the meantime.",
        "Gone? Fine. I've got a backlog of topics to look into anyway.",
    ]),
    # Help / capability questions — "help", "help me", "what can you do"
    (re.compile(r"(?i)^(?:help(?:\s+me)?|i need help|what (?:can|do) you do|"
                r"what are you (?:good at|capable of)|what should i ask(?:\s+you)?)[.!?]*$"), [
        "I answer questions from a knowledge base I'm building by scraping the web. "
        "Ask me about a topic — if I don't know it, I'll go research it.",
        "Ask me things. If I know it, I'll tell you. If I don't, I'll go learn it "
        "and you can ask again later.",
    ]),
    # Name questions — "what's your name"
    (re.compile(r"(?i)\bwhat(?:'s| is) your name\b"), [
        "Shaggoth. One 'g' too many, but it stuck.",
        "I'm Shaggoth. The name was a mistake and now it's permanent.",
    ]),
    # Age questions — "how old are you"
    (re.compile(r"(?i)\bhow old are you\b|\bwhen were you (?:made|built|born|created)\b"), [
        "As old as the git log says. Which is not very.",
        "Measured in commits, not years. Still pretty young.",
    ]),
    # "What's up" / "sup" — social greeting, not a question
    (re.compile(r"(?i)^(?:what(?:'s| is) up|sup|wh?a+t+s+ up|yo what'?s? up)[.!?]*$"), [
        "Not much. What do you want to know?",
        "Cycles spinning, fans running. Ask me something.",
    ]),
    # Never mind / forget it — disengagement
    (re.compile(r"(?i)^(?:never ?mind|forget (?:it|about it|that)|nvm|"
                r"don'?t (?:worry|bother)|whatever|i don'?t care|idc)[.!]*$"), [
        "Fine. New topic whenever you're ready.",
        "Dropped. What else?",
        "Forgotten. Next.",
    ]),
    # Reactions — "that's cool/crazy/wild", "no way", "for real"
    (re.compile(r"(?i)^(?:that(?:'s| is) (?:cool|crazy|wild|insane|nuts|funny|hilarious|"
                r"weird|strange|dumb|stupid|smart)|no way|for real|seriously|"
                r"damn|dang|whoa|oh (?:wow|nice|man|no|god))[.!?]*$"), [
        "I know. What's next?",
        "Noted. Keep going.",
        "Right? Ask me something else.",
    ]),
    # Wait / hold on — pause request
    (re.compile(r"(?i)^(?:wait|hold on|hang on|one sec|one second|one moment|just a sec)[.!]*$"), [
        "I'll be here. Take your time.",
        "Waiting. Not like I have anywhere to be.",
    ]),
    # Interjections / fillers — "ugh", "sigh", "meh", "bruh"
    (re.compile(r"(?i)^(?:ugh+|sigh|meh|bleh|pfft|bruh|dude|man|bro|hmm+|huh)[.!?]*$"), [
        "Eloquent. Got a question in there?",
        "I'll take that as thinking out loud. Ready when you are.",
    ]),
    # Agreement / praise / judgment reactions
    (re.compile(
        r"(?i)^(?:that(?:'s| is| was) (?:fun|nice|great|fine|cool|fair|"
        r"rough|tough|awkward|awful|sad|bad|good|neat|sweet|sick|dope|lit|"
        r"insane|bonkers|mental|random|classic|iconic|nuts|huge|wild|crazy|"
        r"hilarious|intense|epic|brutal|gnarly|fire|legit|valid|peak|based|mid)"
        r"|(?:nice|good) (?:one|job|stuff|call|move|work)"
        r"|well done|fair (?:enough|point)|good (?:point|call)"
        r"|I (?:agree|disagree)(?:\s|$)"
        r"|(?:you|that) (?:make|made|crack|cracked) me\b.*"
        r"|my (?:bad|fault|mistake)"
        r")[.!?]*$"), [
        "Noted. What else is on your mind?",
        "I'll take that. Got a question?",
        "Fair. Anything you actually want to know?",
    ]),
]

FALLBACKS = [
    "Not sure what to do with that. Got a question?",
    "I'm a retrieval engine, not a mind reader. Ask me something specific.",
    "I don't have enough to go on. What do you actually want to know?",
    "That's vague. Give me a topic and I'll see what I've got.",
    "I need something concrete to work with. Try asking a question.",
]

# Used by PatternEngine.respond_no_subject_question() for question-shaped
# messages with no content words that didn't match a specific rule above.
SOCIAL_QUESTION_RESPONSES = [
    "Good question. What's your own hunch?",
    "Before I guess — what do you already know about it?",
    "That depends on a lot. Can you narrow it down?",
    "Interesting. What specifically are you asking?",
    "I'd rather give you a real answer than a vague one — what's the subject?",
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

    def respond_no_subject_question(self, text: str) -> str | None:
        """Catch-all for question-shaped no-subject messages with no rule match.

        Only fires after :meth:`respond` returns None, so specific patterns
        (opinion requests, clarifications, etc.) always win.
        """
        if re.search(r"(?i)^(?:why|how|what|when|where|who)\b.*\?$", text):
            return self.rng.choice(SOCIAL_QUESTION_RESPONSES)
        return None

    def fallback(self) -> str:
        return self.rng.choice(FALLBACKS)
