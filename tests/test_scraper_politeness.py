"""Scraper politeness: identify honestly, and obey robots.txt.

The scraper crawls other people's servers, so these are correctness tests,
not style ones. A generic User-Agent is what Reddit was rejecting with
"HTTP Error 403: Blocked", and until now robots.txt was not consulted at all.
"""
from __future__ import annotations

import urllib.robotparser

import pytest

from shaggoth.scraper.engine import USER_AGENT, ScraperEngine


@pytest.fixture
def scraper(tmp_path):
    return ScraperEngine(db_path=str(tmp_path / "scraper.db"))


def _robots(text: str) -> urllib.robotparser.RobotFileParser:
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(text.splitlines())
    return parser


# --------------------------------------------------------------------------
# User-Agent
# --------------------------------------------------------------------------


def test_user_agent_identifies_the_bot_and_a_contact():
    """Reddit rejects generic agents outright; several other hosts do too."""
    assert "ShaggothBot" in USER_AGENT
    assert "http" in USER_AGENT          # a URL someone can follow
    assert "bot" in USER_AGENT.lower()   # honest about being automated
    assert len(USER_AGENT) > 30          # not the bare default


# --------------------------------------------------------------------------
# robots.txt
# --------------------------------------------------------------------------


def test_disallowed_path_is_refused(scraper):
    scraper._robots_cache["https://example.com"] = (
        _robots("User-agent: *\nDisallow: /private/"), 1e12,
    )
    assert not scraper.robots_allows("https://example.com/private/secret")
    assert scraper.robots_allows("https://example.com/public/page")


def test_blanket_disallow_is_honoured(scraper):
    scraper._robots_cache["https://example.com"] = (
        _robots("User-agent: *\nDisallow: /"), 1e12,
    )
    assert not scraper.robots_allows("https://example.com/anything")


def test_rule_targeting_our_agent_specifically_is_honoured(scraper):
    scraper._robots_cache["https://example.com"] = (
        _robots("User-agent: ShaggothBot\nDisallow: /no-bots/"), 1e12,
    )
    assert not scraper.robots_allows("https://example.com/no-bots/page")


def test_missing_robots_txt_allows(scraper):
    """Fail open: no robots.txt means no restrictions, per the standard."""
    scraper._robots_cache["https://example.com"] = (None, 1e12)
    assert scraper.robots_allows("https://example.com/anything")


def test_unreachable_robots_txt_does_not_stall_learning(scraper, monkeypatch):
    """A transient network error must not be read as 'disallowed'."""
    def boom(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert scraper.robots_allows("https://unreachable.example/page")


def test_non_http_urls_are_not_gated(scraper):
    assert scraper.robots_allows("ftp://example.com/file")
    assert scraper.robots_allows("not a url at all")


def test_fetch_page_refuses_disallowed_urls_and_logs_it(scraper, monkeypatch):
    """A blocked seed must be visible in the logs, not silently missing."""
    scraper._robots_cache["https://example.com"] = (
        _robots("User-agent: *\nDisallow: /"), 1e12,
    )

    def should_not_run(*args, **kwargs):
        raise AssertionError("fetched a URL robots.txt disallows")

    monkeypatch.setattr("urllib.request.urlopen", should_not_run)

    assert scraper.fetch_page("https://example.com/page") is None
    logs = scraper.recent_logs(limit=5)
    assert any("robots" in (entry.get("message") or "") for entry in logs)


def test_robots_can_be_disabled_for_tests(tmp_path, monkeypatch):
    """The switch exists so tests can bypass it -- production leaves it on."""
    scraper = ScraperEngine(db_path=str(tmp_path / "s.db"), respect_robots=False)
    scraper._robots_cache["https://example.com"] = (
        _robots("User-agent: *\nDisallow: /"), 1e12,
    )
    calls = []
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: calls.append(1) or (_ for _ in ()).throw(OSError("stop")),
    )
    scraper.fetch_page("https://example.com/page")
    assert calls, "robots gate should have been skipped"


def test_robots_is_on_by_default(tmp_path):
    assert ScraperEngine(db_path=str(tmp_path / "s.db")).respect_robots is True


def test_robots_result_is_cached_per_origin(scraper, monkeypatch):
    """One robots.txt fetch per origin, not one per page."""
    fetches = []

    class FakeResponse:
        def read(self):
            return b"User-agent: *\nDisallow: /private/"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout=None):
        fetches.append(getattr(request, "full_url", request))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    for path in ("/a", "/b", "/c"):
        scraper.robots_allows("https://example.com" + path)
    assert len(fetches) == 1


# ---------------------------------------------------------------------------
# HTML entity decoding — invalid codepoints must not crash the scraper
# ---------------------------------------------------------------------------

def test_html_entity_decodes_numeric():
    from shaggoth.scraper.engine import _html_to_text
    assert "'" in _html_to_text("it&#39;s fine")


def test_html_entity_decodes_hex():
    from shaggoth.scraper.engine import _html_to_text
    assert "'" in _html_to_text("it&#x27;s fine")


def test_html_entity_surrogate_does_not_crash():
    from shaggoth.scraper.engine import _html_to_text
    result = _html_to_text("bad&#55296;stuff")
    assert "bad" in result
    assert "stuff" in result


def test_html_entity_zero_does_not_crash():
    from shaggoth.scraper.engine import _html_to_text
    result = _html_to_text("null&#0;byte")
    assert "null" in result


# ---------------------------------------------------------------------------
# Charset extraction from Content-Type header
# ---------------------------------------------------------------------------

def test_charset_extraction_basic():
    from shaggoth.scraper.engine import _extract_charset
    assert _extract_charset("text/html; charset=iso-8859-1") == "iso-8859-1"


def test_charset_extraction_quoted():
    from shaggoth.scraper.engine import _extract_charset
    assert _extract_charset('text/html; charset="utf-8"') == "utf-8"


def test_charset_extraction_missing_defaults_to_utf8():
    from shaggoth.scraper.engine import _extract_charset
    assert _extract_charset("text/html") == "utf-8"
    assert _extract_charset("") == "utf-8"


def test_charset_extraction_case_insensitive():
    from shaggoth.scraper.engine import _extract_charset
    assert _extract_charset("text/html; Charset=WINDOWS-1252") == "WINDOWS-1252"
