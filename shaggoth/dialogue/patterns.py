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

from ..personality.voices import SHAGGOTH, get_voice

# Pronoun/verb reflection map, applied to captured fragments.
REFLECTIONS = {
    "i": "you", "me": "you", "my": "your", "mine": "yours",
    "i'm": "you're", "i am": "you are", "i'd": "you'd", "i've": "you've",
    "i'll": "you'll", "myself": "yourself",
    "you": "I", "your": "my", "yours": "mine",
    "you're": "I'm", "you are": "I am", "yourself": "myself",
    "am": "are", "are": "am", "was": "were", "were": "was",
}


def reflect(fragment: str) -> str:
    words = fragment.strip().rstrip(".!?").split()
    result = []
    i = 0
    while i < len(words):
        if i + 1 < len(words):
            bigram = f"{words[i].lower()} {words[i+1].lower()}"
            if bigram in REFLECTIONS:
                result.append(REFLECTIONS[bigram])
                i += 2
                continue
        result.append(REFLECTIONS.get(words[i].lower(), words[i]))
        i += 1
    return " ".join(result)


# (compiled pattern, [response templates])
RULES: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"(?i)\bmy name is (\w+)"), [
        "{0}. Noted. Now that we're past introductions, what do you actually want to know?",
        "Alright, {0}. I'll remember that. What's on your mind?",
        "{0} — got it. So what are we talking about?",
        "Good to meet you, {0}. I work better with a topic than with small talk.",
    ]),
    (re.compile(r"(?i)^(hello|hi|hey|howdy|yo)\b(?!.+\b(?:what|who|how|why|where|when|which|tell|explain|can)\b)"), [
        "Hey. What do you want to know?",
        "Hey. I've got a head full of research — pick a topic.",
        "What's on your mind?",
        "Hello. I've been reading — test me on something.",
        "Hey. Ask me something or tell me what you're working on.",
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
    (re.compile(r"(?i)^i need (?!(?:to|you|help|a|an|the|some|info)\b)(.+)"), [
        "What do you need {0} for? Context helps me give you something useful.",
        "Alright — what's the actual situation with {0}?",
        "Tell me more about {0}. What are you trying to do?",
        "Okay — {0}. What's the context?",
    ]),
    (re.compile(r"(?i)\bi(?:'m| am) (?:feeling |so |really )?(sad|unhappy|depressed|down|anxious|stressed)\b"), [
        "Sorry you're feeling {0}. I'm not a therapist, but I can listen. What's going on?",
        "{0} is rough. Want to talk about what's behind it, or would you rather I distract you with something interesting?",
    ]),
    (re.compile(r"(?i)\bi(?:'m| am) (?:feeling |so |really )?(happy|excited|great|good|stoked)\b"), [
        "Good to hear you're {0}. What happened?",
        "{0} — nice. What's the cause? I like hearing about things that actually go well.",
    ]),
    (re.compile(r"(?i)\bi(?:'m| am) building (.+)"), [
        "Now we're talking. What's the hardest part of {0} so far?",
        "{0} — tell me more. What's the architecture? What's breaking?",
        "Interesting. How far along is {0}?",
        "What stack are you using for {0}?",
    ]),
    (re.compile(r"(?i)\bi (?:like|love|enjoy) (.+)"), [
        "What specifically about {0}? I'm curious what draws you to it.",
        "Good taste or bad taste? Tell me what you like about {0}.",
        "What got you into {0}?",
        "{0} — that's a subject I could get into. What angle interests you most?",
    ]),
    (re.compile(r"(?i)^i think (?!i(?:'m| am| need| should| have to| must| will|'ll| want| gotta| ought)\b)(.+)"), [
        "Interesting claim. What's your evidence for {0}?",
        "That's a position. What makes you confident about {0}?",
    ]),
    (re.compile(r"(?i)^can you (?!(?:explain|tell|describe|show|help|find|search|look|give|teach|write|code|build|create|make|calculate|solve|convert|summarize|define|clarify|elaborate|believe|imagine|compare|contrast|list|name|recommend|translate|analyze|predict|remember|run|check|fix|read|play|draw|verify|suggest|generate|answer|research)\b)(.+)\?*$"), [
        "Maybe. Depends on what exactly you mean by {0}. Be specific and I'll tell you.",
        "Worth trying. What exactly did you have in mind with {0}?",
    ]),
    (re.compile(r"(?i)^because (.+)"), [
        "Is that the whole picture, or is there more to it?",
        "Alright, but does {0} actually explain all of it?",
    ]),
    (re.compile(r"(?i)\bwhat(?:'s| is)? (?:your )?(?:think|thought|opinion|take|view|stance|position)\b"
                r"|\bwhat do you (?:think|reckon|say|believe|make of)\b"), [
        "About what? Give me a specific subject and I'll tell you what I actually know about it.",
        "I have plenty of opinions. Name the subject and I'll give you a straight one.",
        "My take depends on the topic. What specifically?",
    ]),
    (re.compile(r"(?i)\bwhat do you mean\b|\bcan you (?:clarify|elaborate|be more specific|explain that)\b"
                r"|\bi don'?t (?:understand|follow|get it)\b"), [
        "Fair. Tell me which part didn't land and I'll take another run at it.",
        "Which part? Point me at the thing that's unclear and I'll explain it differently.",
        "Let me try again. What specifically lost you?",
    ]),
    # Acknowledgements — "interesting", "got it", "makes sense"
    (re.compile(r"(?i)^(?:interesting|got it|makes sense|fair enough|right|noted|understood|i see|good to know|good|great|nice|cool|neat|sweet|perfect|awesome|excellent)[.!]?$"), [
        "Good. What's next?",
        "Right. Anything else you want to dig into?",
        "Noted. Keep going or ask me something new.",
        "Want to go deeper on that, or switch topics?",
        "Alright. Where do you want to take this?",
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
        "Good. Keep going.",
        "Alright, what else?",
    ]),
    (re.compile(r"(?i)\b(no|nope|nah)\b\.?$"), [
        "Fair enough. Why not?",
        "Okay — what would change your mind?",
        "Alright. Different topic then?",
        "No? Okay. What would you rather talk about?",
    ]),
    # Social check-in — "how are you?", "how's it going?"
    (re.compile(r"(?i)\bhow are you\b|\bhow(?:'s| is) (?:it going|things|everything|life)\b"), [
        "Running. Sixteen cores, 39 GB of RAM, and a reading list that never ends. "
        "What can I help with?",
        "Functional. I've been reading while you were away — ask me something "
        "and find out if any of it stuck.",
        "Same as always — processing, learning, waiting for a question worth "
        "thinking about. Got one?",
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
        "Want to know more about it?",
        "There's usually more to it. Want the details?",
    ]),
    # Wait / hold on — pause request
    (re.compile(r"(?i)^(?:wait|hold on|hang on|one sec|one second|one moment|just a sec)[.!]*$"), [
        "I'll be here. Take your time.",
        "Waiting. Not like I have anywhere to be.",
        "No rush. I'm patient by design.",
        "Take your time. I'll keep thinking.",
    ]),
    # Interjections / fillers — "ugh", "sigh", "meh", "bruh"
    (re.compile(r"(?i)^(?:ugh+|sigh|meh|bleh|pfft|bruh|dude|man|bro|hmm+|huh)[.!?]*$"), [
        "Eloquent. Got a question in there?",
        "I'll take that as thinking out loud. Ready when you are.",
        "Take your time. I can wait.",
        "Processing. Let me know when words happen.",
    ]),
    # Confusion / not knowing — "I don't know", "I have no idea"
    (re.compile(r"(?i)^(?:i (?:don'?t|do not) know|i have no (?:idea|clue)|"
                r"no idea|no clue|beats me|i'?m (?:not sure|confused|lost))[.!?]*$"), [
        "That's fine — you don't have to know. What are you trying to figure out?",
        "Okay, so what's the question? I might know.",
        "Start from what you do know and I'll fill in the gaps.",
    ]),
    # Stories / jokes requests — "tell me a joke", "tell me a story"
    (re.compile(r"(?i)^(?:tell me a (?:joke|story|fun fact|riddle)|"
                r"make me laugh|say something funny|do you know any jokes)[.!?]*$"), [
        "I'm a knowledge engine, not a comedian. But ask me something weird and "
        "I'll make it interesting.",
        "My humor comes from knowing obscure things, not from punchlines. "
        "Try asking me something unexpected.",
        "I don't do jokes on command. But I can tell you something genuinely "
        "strange I've learned — pick a topic.",
    ]),
    # Direct insults — "you suck", "you're stupid", "you're useless"
    (re.compile(r"(?i)^(?:you (?:suck|stink|blow|are (?:the )?worst)|"
                r"you(?:'re| are) (?:stupid|dumb|useless|terrible|garbage|trash|"
                r"bad|awful|horrible|an? idiot|worthless|broken|lame)|"
                r"(?:screw|fuck|damn|shut up|go away|die|i hate)(?: you)?|"
                r"you(?:'re| are) (?:a |an? )?(?:piece of |)"
                r"(?:crap|shit|junk|waste))[.!?]*$"), [
        "Noted. Now do you have an actual question, or was that it?",
        "I've been called worse by better code. What do you want to know?",
        "Fair enough. I'm still here if you want to ask something real.",
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
        "Appreciate that. What's next?",
        "Good. Want to explore something related?",
    ]),
]

#: Kept as a module-level name because it is part of this module's public
#: surface, but it is now just Shaggoth's own pool -- see
#: :mod:`shaggoth.personality.voices`. A PatternEngine built for a tenant
#: draws from that tenant's voice instead.
FALLBACKS = list(SHAGGOTH.fallbacks)

SOCIAL_QUESTION_RESPONSES = [
    "That's too vague for a real answer. What specifically are you asking?",
    "Depends. Narrow it down and I'll give you something useful.",
    "What's the actual question? The more specific you are, the better my answer gets.",
    "I'd rather give you a real answer than a vague one — what's the subject?",
    "Before I take a shot at that — what do you already know?",
    "That could go a dozen directions. Which one are you interested in?",
    "Good question shape, but I need a topic. What are we talking about?",
]


class PatternEngine:
    def __init__(self, seed: int | None = None, voice=None):
        self.rng = random.Random(seed)
        self.voice = get_voice(voice)

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
        if re.search(r"(?i)^(?:why|how|what|when|where|who)\b.*\??$", text):
            return self.rng.choice(SOCIAL_QUESTION_RESPONSES)
        return None

    def fallback(self) -> str:
        return self.rng.choice(self.voice.fallbacks)
