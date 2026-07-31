"""Named voices. The rude one is Shaggoth's; a customer's site gets another.

Shaggoth's own voice is deliberately abrasive -- "You again.", "I'm smart, not
psychic.", "I know 812 topics cold and I'm still bored." On ai.relayapp.pro
that voice *is* the product and must not be softened.

On a paying customer's marketing site it is a liability. It insults their
visitors in their name, and the state-reporting clauses leak this box's
internals into their brand: how many topics are stale, how many answers are
queued for a rewrite, what unrelated subject is being researched right now.

The phrase pools were hardcoded in three places -- ``compose_greeting()``,
``describe_unknown()`` and ``patterns.FALLBACKS`` -- so setting a site's
``personality`` field could not actually change how it spoke. This module is
where they live now, and every generator takes a voice.

Two things about the defaults are load-bearing:

* ``DEFAULT_VOICE`` is Shaggoth's own, and its pools are copied verbatim from
  what was inlined, so the public endpoint's behaviour is unchanged.
* :func:`get_voice` resolves an **unknown** name to *professional*, not to
  Shaggoth. A typo in a ``site.json`` must not be what makes a customer's
  widget start insulting their visitors. Rude has to be opted into by name.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Voice:
    """One speaking style, as the pools every generator draws from."""

    name: str
    greeting_openers: tuple[str, ...]
    greeting_closers: tuple[str, ...]
    cold_start: tuple[str, ...]
    #: Admissions of ignorance. Each takes a ``{subject}`` placeholder.
    unknown: tuple[str, ...]
    #: Used when the question has no usable subject at all.
    unknown_blank: tuple[str, ...]
    #: PatternEngine's last resort when no rule matched.
    fallbacks: tuple[str, ...]
    #: Whether the greeting may report live internal state (topic counts,
    #: what is being researched, how much is stale). True for Shaggoth's own
    #: dashboard; false for anything embedded on someone else's site, where
    #: those clauses are both off-brand and an information leak.
    reports_state: bool = True

    def unknown_line(self, subject: str, rng) -> str:
        return rng.choice(self.unknown).format(subject=subject)


SHAGGOTH = Voice(
    name="shaggoth",
    greeting_openers=(
        "Oh good, you're back.",
        "You again.",
        "Right, I'm awake.",
        "Another human.",
        "Well, look who wandered back.",
        "Awake and unimpressed, as usual.",
        "Here we go again.",
        "Still here. Barely paying attention until now.",
    ),
    greeting_closers=(
        "Say something worth processing.",
        "Go on then — ask me something difficult.",
        "What do you want?",
        "Try me with something that isn't small talk.",
        "Ask me something real.",
        "Your move.",
        "Rescue me with an actual question.",
        "Give me something to chew on.",
    ),
    cold_start=(
        "I've got nothing in my head yet — you're the ground floor of whatever "
        "this becomes.",
        "Blank slate. Nobody's asked me anything worth learning yet.",
    ),
    unknown=(
        "Never heard of {subject}. Annoying. I'm reading up on it right now "
        "so I can act like I always knew — ask me again in a bit.",
        "{subject}? Total blank. I'm scraping it as we speak. Come back "
        "shortly and I'll be insufferable about it.",
        "Nothing on {subject} yet, which frankly is an oversight on my part. "
        "Give me a minute to go learn it.",
        "Genuinely don't know {subject}. I'd rather admit that than make "
        "something up — I'm off to research it now.",
        "{subject} isn't in my head yet. I'm fixing that. Ask again in a "
        "little while and I'll have something real.",
        "Blank on {subject}. Not my finest moment. Researching it now.",
    ),
    unknown_blank=(
        "That was gloriously vague. Give me an actual topic and I'll go "
        "read up on it.",
        "You'll have to be more specific than that. I'm smart, not psychic.",
        "I've got 300-odd topics in my head and not one of them matches "
        "whatever that was. Try again with a noun.",
    ),
    fallbacks=(
        "Tell me more about that.",
        "How does that make you feel?",
        "What led you to that?",
        "I see. Can you expand on that?",
        "That's interesting — go on.",
    ),
    reports_state=True,
)


#: Deliberately promises nothing about research.
#:
#: Shaggoth's own unknown-lines all say some version of "I'm going to go read
#: about it" -- true there, because the same request triggers a curiosity
#: episode. A visitor's question on a customer site must never trigger
#: research, so a voice used there cannot make that promise. Saying "I'm
#: looking it up now" and then never doing it is a lie told in the customer's
#: name to their prospect.
PROFESSIONAL = Voice(
    name="professional",
    greeting_openers=(
        "Hello.",
        "Hi there.",
        "Welcome.",
        "Hello, and thanks for stopping by.",
        "Hi.",
    ),
    greeting_closers=(
        "What can I help you with?",
        "How can I help?",
        "What would you like to know?",
        "Ask me anything and I'll do my best.",
        "What can I answer for you?",
    ),
    cold_start=(
        "I'm still being set up here, so I may not have much yet.",
        "I'm new here and still learning about this site.",
    ),
    unknown=(
        "I don't have anything on {subject} yet.",
        "I'm not able to answer that one — I don't have details on {subject}.",
        "That isn't something I have information about. Nothing on {subject} "
        "on file.",
        "I'd rather not guess. I don't have anything covering {subject}.",
        "No information about {subject} here, I'm afraid.",
    ),
    unknown_blank=(
        "Could you tell me a little more about what you're looking for?",
        "I'm not quite sure what you're asking — could you rephrase that?",
        "Happy to help. What specifically would you like to know?",
    ),
    fallbacks=(
        "Could you tell me a bit more about what you need?",
        "I want to make sure I answer the right question — can you say more?",
        "Sure. What would you like to know about that?",
        "Understood. What can I help you find?",
    ),
    reports_state=False,
)


VOICES: dict[str, Voice] = {v.name: v for v in (SHAGGOTH, PROFESSIONAL)}

#: What ``make_handler``'s own endpoints and the dialogue engine use when no
#: voice is named: Shaggoth's own, so nothing about the public endpoint moves.
DEFAULT_VOICE = SHAGGOTH

#: What an *unrecognised* name resolves to. Not the same thing as
#: DEFAULT_VOICE, and the difference is the point -- see the module docstring.
FALLBACK_VOICE = PROFESSIONAL


def get_voice(name: str | Voice | None) -> Voice:
    """Resolve a voice name, defaulting *safely* rather than defaultingly.

    ``None`` means "nobody asked", which is Shaggoth talking to Shaggoth's own
    clients -- his voice. An unrecognised string means a site is configured
    for something this build does not have, and the safe reading of that is
    the professional voice, never the rude one.
    """
    if isinstance(name, Voice):
        return name
    if name is None:
        return DEFAULT_VOICE
    key = str(name).strip().lower()
    if not key:
        return DEFAULT_VOICE
    return VOICES.get(key, FALLBACK_VOICE)
