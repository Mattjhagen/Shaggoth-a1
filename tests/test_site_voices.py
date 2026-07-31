"""A tenant's voice must contain none of Shaggoth's, and Shaggoth's must not move.

The rude default was hardcoded in three separate places -- compose_greeting(),
describe_unknown() and patterns.FALLBACKS -- so a site's ``personality`` field
had no way to change how it spoke. These tests pin both directions of the fix:
nothing rude reaches a tenant, and the public endpoint's own voice is
unchanged.

The tenant checks are exhaustive over the phrase pools rather than sampled.
Sampling a random generator is how one surviving rude line in a pool of eight
gets shipped.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from shaggoth.dialogue.engine import compose_greeting, describe_unknown
from shaggoth.dialogue.patterns import PatternEngine
from shaggoth.personality.voices import (
    DEFAULT_VOICE, FALLBACK_VOICE, PROFESSIONAL, SHAGGOTH, get_voice,
)
from shaggoth.server import make_handler
from shaggoth.sites.registry import DEFAULT_PERSONALITY, SiteRegistry

#: Phrases that are Shaggoth being Shaggoth. Every one of these is a sentence
#: no customer wants aimed at a visitor who came to ask about pricing.
RUDE = [
    "you again", "another human", "unimpressed", "what do you want",
    "psychic", "insufferable", "annoying", "bored", "barely paying attention",
    "gloriously vague", "not my finest", "your move", "rescue me",
    "chew on", "small talk", "riveting", "oversight on my part",
    "elbow-deep", "don't mind the noise", "wandered back",
    "here we go again", "worth processing", "something difficult",
    "ground floor", "blank slate", "nobody's asked", "total blank",
    "act like i always knew", "i'm awake",
]

#: Phrases that leak this box's internals into someone else's brand. Not rude,
#: but a prospect on a customer's site should never learn how much of an
#: unrelated corpus is going stale.
LEAKY = [
    "stale", "queued", "research", "scraping", "scrape", "episode",
    "topics in my head", "in my head", "reading up", "shaggoth",
    "flagged wrong", "rewrite", "knowledge base",
]

#: A tenant voice must not promise to go and learn something, because a
#: visitor's question deliberately does not trigger curiosity research. The
#: promise would be a lie told in the customer's name.
PROMISES_RESEARCH = re.compile(
    r"(?i)\b(research|reading up|read up|scrap\w+|look(ing)? it up|"
    r"go learn|learn it|find out for you|i'm fixing that)\b"
)


def assert_clean(text: str, where: str) -> None:
    low = text.lower()
    for phrase in RUDE:
        assert phrase not in low, f"{where}: rude phrase {phrase!r} in {text!r}"
    for phrase in LEAKY:
        assert phrase not in low, f"{where}: leaks {phrase!r} in {text!r}"
    assert not PROMISES_RESEARCH.search(low), \
        f"{where}: promises research in {text!r}"


def all_lines(voice):
    """Every phrase the voice can ever emit, with {subject} filled in."""
    for pool in (voice.greeting_openers, voice.greeting_closers,
                 voice.cold_start, voice.unknown_blank, voice.fallbacks):
        yield from pool
    for line in voice.unknown:
        yield line.format(subject="your pricing")


# --------------------------------------------------- the pools themselves

def test_every_professional_phrase_is_clean():
    """Exhaustive, not sampled. One rude survivor in a pool ships."""
    for line in all_lines(PROFESSIONAL):
        assert_clean(line, "PROFESSIONAL pool")


def test_the_professional_voice_does_not_report_internal_state():
    assert PROFESSIONAL.reports_state is False


def test_shaggoths_own_voice_is_still_rude():
    """The abrasive voice is the product on ai.relayapp.pro, not a bug."""
    joined = " ".join(all_lines(SHAGGOTH)).lower()
    assert any(p in joined for p in RUDE)
    assert SHAGGOTH.reports_state is True


# ------------------------------------------------------------- resolution

def test_an_unknown_voice_name_resolves_to_professional_not_rude():
    """The safe default direction. A typo in a site.json must not be what
    makes a customer's widget start insulting their visitors."""
    for name in ("proffesional", "", "  ", "corporate", "nonsense"):
        assert get_voice(name).name in ("professional", DEFAULT_VOICE.name)
    assert get_voice("typo-here") is PROFESSIONAL
    assert FALLBACK_VOICE is PROFESSIONAL


def test_no_voice_named_means_shaggoth():
    assert get_voice(None) is SHAGGOTH
    assert DEFAULT_VOICE is SHAGGOTH


def test_names_resolve_case_insensitively():
    assert get_voice("PROFESSIONAL") is PROFESSIONAL
    assert get_voice(" Shaggoth ") is SHAGGOTH


def test_a_voice_object_passes_straight_through():
    assert get_voice(PROFESSIONAL) is PROFESSIONAL


def test_new_sites_default_to_the_professional_voice():
    """A customer site opts in to the rude voice; it never inherits it."""
    assert DEFAULT_PERSONALITY == "professional"
    assert get_voice(DEFAULT_PERSONALITY) is PROFESSIONAL


# --------------------------------------------------- the generators, live

QUESTIONS = [
    "what is quantum chromodynamics",
    "how much does a website cost",
    "do you offer hosting",
    "how many topics do you know so far",   # the mangled-subject case
    "how does that sit with you",
    "lol",
    "",
]


def test_describe_unknown_is_clean_in_the_professional_voice():
    for question in QUESTIONS:
        for _ in range(60):
            assert_clean(
                describe_unknown(question, voice="professional"),
                f"describe_unknown({question!r})",
            )


def test_compose_greeting_is_clean_in_the_professional_voice():
    for count in (0, 1, 812):
        for _ in range(120):
            line = compose_greeting(
                count, "the Smart Fortwo", stale_count=count,
                episodes=543, repair_queue=7, is_researching=True,
                research_topic="wipeout pulse", voice="professional",
            )
            assert_clean(line, "compose_greeting")
            # Every state number above is live and wrong for a tenant.
            assert not re.search(r"\d", line), line


def test_pattern_fallbacks_are_clean_in_the_professional_voice():
    engine = PatternEngine(voice="professional")
    for _ in range(60):
        assert_clean(engine.fallback(), "PatternEngine.fallback")


# ------------------------------------------------- the default is unmoved

def test_the_default_voice_still_draws_from_shaggoths_pools():
    """No-argument calls must be exactly what they were before voices existed."""
    openers = set(SHAGGOTH.greeting_openers)
    closers = set(SHAGGOTH.greeting_closers)
    cold = set(SHAGGOTH.cold_start)

    for _ in range(300):
        line = compose_greeting(0, "")
        assert any(line.startswith(c) for c in cold), line
        assert any(line.endswith(c) for c in closers), line

    for _ in range(300):
        line = compose_greeting(812, "algebra")
        assert any(line.startswith(o) for o in openers), line
        assert any(line.endswith(c) for c in closers), line


def test_default_describe_unknown_still_promises_research():
    """Shaggoth's own gaps *are* about to be researched, so his lines say so."""
    lines = {describe_unknown("what is photosynthesis") for _ in range(200)}
    assert len(lines) > 1
    assert all("photosynthesis" in line for line in lines)
    assert any(PROMISES_RESEARCH.search(line.lower()) for line in lines)


def test_default_pattern_fallbacks_are_unchanged():
    from shaggoth.dialogue.patterns import FALLBACKS
    assert FALLBACKS == list(SHAGGOTH.fallbacks)
    assert "How does that make you feel?" in FALLBACKS


# --------------------------------------------------------- over the wire

@pytest.fixture
def api(tmp_path):
    registry = SiteRegistry(tmp_path / "sites")
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0), make_handler(None, None, sites=registry))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(base + path, data=data, method=method)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")

    call.registry = registry
    try:
        yield call
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_registered_site_greets_in_its_own_voice(api):
    _, site = api("POST", "/sites/register", {"url": "https://purepulse.one"})
    assert site["personality"] == "professional"
    for _ in range(40):
        status, body = api("GET", f"/sites/{site['site_id']}/greeting")
        assert status == 200
        assert body["voice"] == "professional"
        assert_clean(body["greeting"], "GET /sites/{id}/greeting")


def test_a_site_that_opts_into_the_rude_voice_gets_it(api):
    """Opt-in has to actually work, or the setting is decorative."""
    _, site = api("POST", "/sites/register", {"url": "https://example.com"})
    api.registry.update(site["site_id"], personality="shaggoth")
    lines = {
        api("GET", f"/sites/{site['site_id']}/greeting")[1]["greeting"]
        for _ in range(60)
    }
    joined = " ".join(lines).lower()
    assert any(p in joined for p in RUDE), lines
