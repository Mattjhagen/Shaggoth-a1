"""URL handling and mode parsing at the API boundary."""
from __future__ import annotations

import pytest

from shaggoth.dialogue.engine import DRIFT, NO_DRIFT
from shaggoth.server import _request_mode, extract_url, strip_url


# --------------------------------------------------------------------------
# URL extraction
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message,expected",
    [
        ("https://example.com/page", "https://example.com/page"),
        ("what do you make of https://example.com/a/b", "https://example.com/a/b"),
        ("read http://example.com then tell me", "http://example.com"),
        ("https://example.com/x?y=1&z=2", "https://example.com/x?y=1&z=2"),
    ],
)
def test_extract_url_finds_pasted_links(message, expected):
    assert extract_url(message) == expected


def test_extract_url_strips_trailing_sentence_punctuation():
    """People paste links mid-sentence; the '?' is not part of the URL."""
    assert extract_url("thoughts on https://example.com/page?") == "https://example.com/page"
    assert extract_url("see https://example.com/page.") == "https://example.com/page"
    assert extract_url("https://example.com/a, and also") == "https://example.com/a"


def test_extract_url_keeps_meaningful_query_strings():
    url = "https://example.com/search?q=1"
    assert extract_url(f"look at {url}") == url


def test_extract_url_ignores_bare_domains():
    """Prose mentioning a domain is not an instruction to fetch it."""
    assert extract_url("I was reading example.com earlier") == ""
    assert extract_url("no links here at all") == ""
    assert extract_url("") == ""
    assert extract_url(None) == ""


def test_extract_url_takes_the_first_of_several():
    assert extract_url(
        "https://one.example/a and https://two.example/b"
    ) == "https://one.example/a"


def test_strip_url_leaves_the_actual_question():
    message = "what do you make of https://example.com/page ?"
    url = extract_url(message)
    assert strip_url(message, url) == "what do you make of ?"


def test_strip_url_can_leave_nothing():
    """A bare link is a valid turn; the caller substitutes the page title."""
    assert strip_url("https://example.com", "https://example.com") == ""


# --------------------------------------------------------------------------
# Mode parsing at the request boundary
# --------------------------------------------------------------------------


def test_request_mode_reads_the_mode_field():
    assert _request_mode({"mode": "drift"}) == DRIFT
    assert _request_mode({"mode": "no_drift"}) == NO_DRIFT


def test_request_mode_accepts_a_boolean_drift_flag():
    assert _request_mode({"drift": True}) == DRIFT
    assert _request_mode({"drift": False}) == NO_DRIFT


def test_mode_field_wins_over_the_boolean():
    assert _request_mode({"mode": "no_drift", "drift": True}) == NO_DRIFT


def test_unspecified_mode_defers_to_the_engine():
    """None means 'not specified' -- the engine applies its own default."""
    assert _request_mode({}) is None
    assert _request_mode({"message": "hi"}) is None
    assert _request_mode(None) is None


# --------------------------------------------------------------------------
# Turning a pasted link into an answerable question
# --------------------------------------------------------------------------


def test_clean_page_title_strips_site_suffixes():
    from shaggoth.server import clean_page_title

    assert clean_page_title("Aeroponics - Wikipedia") == "Aeroponics"
    assert clean_page_title("Some Repo | GitHub") == "Some Repo"
    assert clean_page_title("Photosynthesis") == "Photosynthesis"


def test_question_for_page_substitutes_when_the_turn_has_no_subject():
    """"what do you make of <link>?" leaves nothing to retrieve on."""
    from shaggoth.server import question_for_page

    for empty in ("what do you make of ?", "thoughts?", "", "check this out", "read this"):
        assert question_for_page(empty, "Aeroponics - Wikipedia") == "what is Aeroponics"


def test_question_for_page_keeps_a_real_question():
    from shaggoth.server import question_for_page

    asked = "does this contradict photosynthesis"
    assert question_for_page(asked, "Aeroponics - Wikipedia") == asked


def test_question_for_page_without_a_title_returns_the_input():
    from shaggoth.server import question_for_page

    assert question_for_page("thoughts?", "") == "thoughts?"


# --------------------------------------------------------------------------
# Cache busting
# --------------------------------------------------------------------------


def test_cache_buster_versions_local_assets(tmp_path):
    """Cloudflare serves /app.js with max-age=14400 whatever the origin says,
    so after a deploy visitors keep running the previous JavaScript."""
    from shaggoth.server import add_cache_busters

    (tmp_path / "app.js").write_text("x")
    (tmp_path / "style.css").write_text("y")
    html = '<link rel="stylesheet" href="style.css"><script src="app.js"></script>'
    out = add_cache_busters(html, tmp_path)

    assert 'href="style.css?v=' in out
    assert 'src="app.js?v=' in out


def test_cache_buster_token_changes_when_the_file_does(tmp_path):
    import os

    from shaggoth.server import add_cache_busters

    asset = tmp_path / "app.js"
    asset.write_text("one")
    os.utime(asset, (1_000_000, 1_000_000))
    first = add_cache_busters('<script src="app.js"></script>', tmp_path)

    os.utime(asset, (2_000_000, 2_000_000))
    second = add_cache_busters('<script src="app.js"></script>', tmp_path)

    assert first != second


def test_cache_buster_is_stable_for_an_unchanged_file(tmp_path):
    """Unchanged assets keep their token and stay cached -- that is the point."""
    from shaggoth.server import add_cache_busters

    (tmp_path / "app.js").write_text("x")
    html = '<script src="app.js"></script>'
    assert add_cache_busters(html, tmp_path) == add_cache_busters(html, tmp_path)


def test_cache_buster_leaves_remote_and_non_asset_urls_alone(tmp_path):
    from shaggoth.server import add_cache_busters

    html = (
        '<script src="https://cdn.example/x.js"></script>'
        '<link href="//other.example/y.css">'
        '<link rel="manifest" href="manifest.json">'
        '<a href="#chat">Chat</a>'
    )
    assert add_cache_busters(html, tmp_path) == html


def test_cache_buster_tolerates_a_missing_file(tmp_path):
    from shaggoth.server import add_cache_busters

    out = add_cache_busters('<script src="gone.js"></script>', tmp_path)
    assert 'src="gone.js?v=0"' in out
