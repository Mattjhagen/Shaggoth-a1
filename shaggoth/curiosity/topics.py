"""Topic detection and knowledge-gap analysis.

Extracts candidate topics from user messages and checks whether the
knowledge base already covers them.
"""

from __future__ import annotations

import re
from ..memory.store import extract_keywords, STOPWORDS


# Patterns that indicate the user is asking about something specific
# we might not know yet. Groups capture the topic phrase.
TOPIC_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?i)\bwhat (?:is|are|do you know about|can you tell me about)\s+(.+?)[?.!]*$"),
    re.compile(r"(?i)\btell me about\s+(.+?)[?.!]*$"),
    re.compile(r"(?i)\bexplain\s+(.+?)[?.!]*$"),
    re.compile(r"(?i)\bhow (?:does|do|did|is|are|was|were)\s+(.+?)[?.!]*$"),
    re.compile(r"(?i)\bwhy (?:is|are|do|does|did|was|were)\s+(.+?)[?.!]*$"),
    re.compile(r"(?i)\bwho (?:is|are|was|were)\s+(.+?)[?.!]*$"),
    re.compile(r"(?i)\b(?:define|definition of)\s+(.+?)[?.!]*$"),
    re.compile(r"(?i)\b(?:difference between|versus|vs\.?)\s+(.+?)[?.!]*$"),
    re.compile(r"(?i)\b(?:movies|films|shows?|books?|articles?|news|updates?|information) (?:with|on|about|for|by)\s+(.+?)[?.!]*$"),
    re.compile(r"(?i)\bany (?:news|updates?|information) (?:on|about)\s+(.+?)[?.!]*$"),
]


_CONVERSATIONAL = frozenset(
    "hello hi hey howdy yo sup greetings bye goodbye cya seeya "
    "lol lmao haha hah heh wow omg wtf nah yep nope ok okay sure "
    "please thanks stop quit help".split()
)


def extract_topic_query(text: str) -> str | None:
    """Extract a searchable topic from a user message.

    Returns a clean query string suitable for web search, or None if
    the message doesn't look like a knowledge request.

    Bare nouns and short noun phrases ("photosynthesis", "quantum mechanics")
    are implicit lookups even though they lack question scaffolding.  Without
    this fallback, typing a bare topic hit ``describe_unknown`` in the dialogue
    engine but curiosity research was never triggered -- the knowledge gap was
    announced but never closed.
    """
    text = text.strip()
    if not text:
        return None

    for pattern in TOPIC_PATTERNS:
        match = pattern.search(text)
        if match:
            topic = match.group(1).strip()
            # Clean up the topic — remove trailing punctuation, pronouns
            topic = re.sub(r"[?.!,;:]+$", "", topic).strip()
            topic = re.sub(r"\b(?:please|thanks|thank you)\b", "", topic, flags=re.IGNORECASE).strip()
            if len(topic) > 1:
                return topic

    # Bare noun fallback: a short phrase whose words are all content words is
    # an implicit lookup.  Capped at 4 words so "I went to the store" does not
    # match, and every word must carry topical signal (not a stopword).
    words = text.split()
    if 1 <= len(words) <= 4:
        content = [w for w in words if w.lower().rstrip("?.!,") not in STOPWORDS
                   and w.lower().rstrip("?.!,") not in _CONVERSATIONAL
                   and len(w) > 1]
        if content and len(content) == len(words):
            topic = re.sub(r"[?.!,;:]+$", "", text).strip()
            if len(topic) > 1:
                return topic

    return None


# A chunk suffix written by CuriosityEngine.ingest_text when an article is
# split: "Aeroponic Farming (part 2)". add_entry strips the parentheses, so on
# the next scan it comes back as the plain topic "Aeroponic Farming Part 2" and
# is indistinguishable from a real article title.
_CHUNK_SUFFIX = re.compile(r"\s*\(?\bparts?\s+\d+\)?\s*$", re.I)


def base_topic(topic: str) -> str:
    """Strip chunk suffixes to recover the subject an entry is really about.

    "Aeroponic Farming Part 2" -> "Aeroponic Farming". Applied repeatedly,
    because the suffixes had been stacking: researching the chunk name
    produced "Aeroponic Farming Part 1 Part 1", then "... Part 1 Part 1
    Part 1", once per refresh cycle, forever.
    """
    previous = None
    current = (topic or "").strip()
    while current != previous:
        previous = current
        current = _CHUNK_SUFFIX.sub("", current).strip()
    return current


def is_chunk_topic(topic: str) -> bool:
    """True when ``topic`` names a slice of another entry, not a subject."""
    return base_topic(topic) != (topic or "").strip()


# A caller that stores a raw question as a topic (bypassing
# extract_topic_query) produces an entry titled after the *question*, not the
# subject: "Why Is The Sky Blue" next to the properly-named "The Sky Blue".
# Both score a perfect title match, so the query-named duplicate -- often
# scraped from a bad search on the literal question text -- can outrank the
# honest entry. This mirrors TOPIC_PATTERNS above (which extracts a topic
# from a full sentence) but strips only the interrogative lead-in, leaving
# whatever extract_topic_query would have captured untouched, so the result
# lines up with topics stored via the normal path.
_QUESTION_PREFIX = re.compile(
    r"^(?:why|what|how|who|where|when|which)\s+"
    r"(?:is|are|was|were|do|does|did|can|could|should|would)\s+"
    r"|^(?:define|definition of|tell me about|explain)\s+",
    re.I,
)


def strip_question_prefix(topic: str) -> str:
    """Strip a leading question phrase, recovering the subject underneath.

    "Why Is The Sky Blue" -> "The Sky Blue". "The Sky Blue" is returned
    unchanged -- there is no prefix to strip. Applied repeatedly in case a
    topic was double-processed ("What Is Why Is Gravity").
    """
    previous = None
    current = (topic or "").strip()
    while current != previous:
        previous = current
        current = _QUESTION_PREFIX.sub("", current, count=1).strip()
    return current


def is_question_topic(topic: str) -> bool:
    """True when ``topic`` is phrased as a question rather than a subject."""
    return strip_question_prefix(topic) != (topic or "").strip()


def canonical_subject(topic: str) -> str:
    """The subject a topic is really about, stripped of both a chunk suffix
    and a leading question phrase -- the key two differently-acquired
    entries for the same thing should collide under.
    """
    return base_topic(strip_question_prefix(base_topic(topic)))


def extract_keywords_from_topic(topic: str) -> list[str]:
    """Extract meaningful keywords from a topic string."""
    return extract_keywords(topic)


def is_known_topic(topic: str, known_keywords: set[str], min_overlap: float = 0.5) -> bool:
    """Check if a topic is already well-covered by known keywords.

    Returns True if more than ``min_overlap`` of the topic's keywords
    appear in the knowledge base.
    """
    keywords = extract_keywords_from_topic(topic)
    if not keywords:
        return False

    overlap = sum(1 for kw in keywords if kw in known_keywords)
    return (overlap / len(keywords)) >= min_overlap


def build_search_queries(topic: str, max_queries: int = 3) -> list[str]:
    """Generate search queries from a topic to maximize coverage.

    Uses Wikipedia-style and definitional queries rather than always
    appending "explained"/"tutorial", which produces bad results for
    people, places, and events ("Albert Einstein tutorial").
    """
    queries = [topic]
    if len(queries) < max_queries:
        queries.append(f"{topic} Wikipedia")
    if len(queries) < max_queries:
        queries.append(f"what is {topic}")

    return queries[:max_queries]
