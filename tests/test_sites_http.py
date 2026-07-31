"""The tenant endpoints, exercised over real HTTP.

These run against a live ``ThreadingHTTPServer`` rather than calling the route
methods directly, because two of the things being pinned here are properties
of the wire and not of the functions: the status codes, and the fact that a
verification *reason* survives serialisation instead of being flattened into
"could not verify".

The crawl runner is injected. Nothing in this file reaches the network.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from shaggoth import server as server_module
from shaggoth.server import _crawl_bounds, make_handler
from shaggoth.sites.crawl import MAX_DEPTH, MAX_PAGES
from shaggoth.sites.jobs import CrawlJobs
from shaggoth.sites.registry import SiteRegistry
from shaggoth.sites.verification import TXT_PREFIX, VerificationResult


class FakeRunner:
    """Stands in for crawl_site. Records calls; never touches the network."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.gate = threading.Event()
        self.gate.set()
        self.raises: Exception | None = None

    def __call__(self, registry, site_id, **bounds):
        self.calls.append((site_id, bounds))
        self.gate.wait(timeout=5)
        if self.raises:
            raise self.raises
        return {"site_id": site_id, "pages_fetched": 3, "bounds": bounds}


@pytest.fixture
def api(tmp_path, monkeypatch):
    """A live server on an ephemeral port, backed by a throwaway registry."""
    registry = SiteRegistry(tmp_path / "sites")
    runner = FakeRunner()
    jobs = CrawlJobs(runner=runner)

    # The limiter buckets are module-global and outlive a single test.
    monkeypatch.setattr(server_module, "RATE_LIMITS", {})

    handler = make_handler(None, None, sites=registry, crawl_jobs=jobs)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            base + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    call.registry = registry
    call.runner = runner
    call.jobs = jobs
    try:
        yield call
    finally:
        httpd.shutdown()
        httpd.server_close()


def _register(api, url="https://example.com"):
    status, body = api("POST", "/sites/register", {"url": url})
    assert status == 200, body
    return body


def _verify_result(**kw):
    base = dict(verified=False, method="dns", reason="no_record",
                detail="nothing yet", found=[])
    base.update(kw)
    return VerificationResult(**base)


# --------------------------------------------------------------- register

def test_register_returns_a_site_and_both_proofs(api):
    body = _register(api, "https://Example.com/pricing?x=1")
    assert body["domain"] == "example.com"
    assert body["status"] == "pending"
    assert body["verified"] is False
    assert body["verification"]["dns"]["type"] == "TXT"
    assert body["verification"]["dns"]["value"].startswith(TXT_PREFIX)
    assert body["verification"]["file"]["url"].endswith(
        "/.well-known/shaggoth-verify.txt"
    )
    assert body["verification"]["file"]["contents"] == body["token"]


def test_register_is_idempotent_per_domain(api):
    first = _register(api, "https://example.com")
    second = _register(api, "http://example.com/about")
    assert first["site_id"] == second["site_id"]


def test_register_requires_a_url(api):
    status, body = api("POST", "/sites/register", {})
    assert status == 400
    assert body["reason"] == "missing_url"


@pytest.mark.parametrize("bad", [
    "http://127.0.0.1/",
    "https://[::1]/",
    "localhost",
    "https://box.local",
    "ftp://example.com",
    "https://notadomain",
])
def test_register_refuses_what_must_not_be_crawled(api, bad):
    """The normaliser's refusals have to survive to the HTTP layer."""
    status, body = api("POST", "/sites/register", {"url": bad})
    assert status == 400, (bad, body)
    assert body["reason"] == "invalid_domain"
    assert body["error"]  # the owner-facing message, not a generic one


# ------------------------------------------------------------------ lookup

def test_get_site_returns_the_record(api):
    site = _register(api)
    status, body = api("GET", f"/sites/{site['site_id']}")
    assert status == 200
    assert body["site_id"] == site["site_id"]
    assert body["verification"]["dns"]["name"] == "example.com"


def test_get_unknown_site_is_404_with_a_reason(api):
    status, body = api("GET", "/sites/nosuchsite")
    assert status == 404
    assert body["reason"] == "unknown_site"


def test_site_id_cannot_climb_out_of_the_sites_directory(api):
    """``_site_dir`` refuses these; the route must turn that into a 404."""
    for evil in ("..", "%2e%2e", "..%2f..%2fetc"):
        status, body = api("GET", f"/sites/{evil}")
        assert status == 404, (evil, body)


def test_listing_carries_no_verification_tokens(api):
    """/sites is unauthenticated while SHAGGOTH_API_KEY is unset."""
    _register(api, "https://example.com")
    _register(api, "https://other.example.org")
    status, body = api("GET", "/sites")
    assert status == 200
    assert len(body["sites"]) == 2
    for entry in body["sites"]:
        assert "token" not in entry
        assert "support_email" not in entry
        assert entry["status"] == "pending"


# ------------------------------------------------------------------ verify

@pytest.mark.parametrize("reason,method", [
    ("nxdomain", "dns"),
    ("no_record", "dns"),
    ("wrong_value", "dns"),
    ("not_found", "file"),
    ("timeout", "dns"),
])
def test_verification_failure_reasons_survive_to_the_response(
    api, monkeypatch, reason, method
):
    """The distinct reasons are the whole point of the verification module.

    A failed check is a 200 carrying an answer, not a 4xx: the request was
    fine and the server did the work. Collapsing nxdomain, no_record and
    not_found into one error would discard the only part worth computing --
    they call for three different actions from the owner.
    """
    site = _register(api)
    # ``want`` shadows nothing: the lambda's own ``method`` is whatever the
    # route asked for, which is not what this test is pinning.
    monkeypatch.setattr(
        server_module, "verify",
        lambda d, t, method="any", want=method: _verify_result(
            reason=reason, method=want
        ),
    )
    status, body = api("POST", f"/sites/{site['site_id']}/verify", {})
    assert status == 200
    assert body["verified"] is False
    assert body["reason"] == reason
    assert body["method"] == method
    assert body["status"] == "pending"
    assert body["detail"]


def test_successful_verification_promotes_the_site(api, monkeypatch):
    site = _register(api)
    monkeypatch.setattr(
        server_module, "verify",
        lambda d, t, method="any": _verify_result(
            verified=True, reason="ok", method="file"
        ),
    )
    status, body = api("POST", f"/sites/{site['site_id']}/verify", {})
    assert status == 200
    assert body["verified"] is True
    assert body["status"] == "verified"
    assert api.registry.get(site["site_id"]).verified is True


def test_verify_rejects_an_unknown_method(api):
    site = _register(api)
    status, body = api("POST", f"/sites/{site['site_id']}/verify",
                       {"method": "telepathy"})
    assert status == 400
    assert body["reason"] == "bad_method"


def test_verify_passes_the_method_through(api, monkeypatch):
    site = _register(api)
    seen = {}

    def fake(domain, token, method="any"):
        seen["method"] = method
        return _verify_result()

    monkeypatch.setattr(server_module, "verify", fake)
    api("POST", f"/sites/{site['site_id']}/verify", {"method": "file"})
    assert seen["method"] == "file"


def test_verify_on_unknown_site_is_404(api):
    status, body = api("POST", "/sites/nosuchsite/verify", {})
    assert status == 404
    assert body["reason"] == "unknown_site"


# ------------------------------------------------------------------- crawl

def test_crawl_refuses_an_unverified_site(api):
    site = _register(api)
    status, body = api("POST", f"/sites/{site['site_id']}/crawl", {})
    assert status == 409
    assert body["reason"] == "not_verified"
    assert body["status"] == "pending"
    assert api.runner.calls == []


@pytest.mark.parametrize("payload", [
    {"verified": True},
    {"status": "verified"},
    {"force": True},
    {"skip_verification": True},
    {"bypass": 1, "admin": True, "override": "yes"},
    {"site": {"status": "verified", "verified": True}},
])
def test_no_request_body_can_talk_past_the_verification_gate(api, payload):
    """There is no bypass parameter, and adding one has to stay hard.

    The route reads the stored record rather than anything in the body, and
    crawl_site checks again inside the job thread. This asserts the outcome
    both ways: 409 out, and the runner provably never invoked.
    """
    site = _register(api)
    status, body = api("POST", f"/sites/{site['site_id']}/crawl", payload)
    assert status == 409, (payload, body)
    assert body["reason"] == "not_verified"
    assert api.runner.calls == []
    assert api.registry.get(site["site_id"]).status == "pending"


def test_registry_status_cannot_be_written_over_http(api):
    """No route exposes SiteRegistry.update, which takes arbitrary fields."""
    site = _register(api)
    sid = site["site_id"]
    for method, path in [
        ("POST", f"/sites/{sid}"),
        ("POST", f"/sites/{sid}/update"),
        ("POST", f"/sites/{sid}/status"),
        ("POST", f"/sites/{sid}/mark_verified"),
        ("POST", "/sites"),
        ("POST", "/sites/register/../verified"),
    ]:
        status, _ = api(method, path, {"status": "verified", "verified": True})
        assert status == 404, (method, path, status)
    assert api.registry.get(sid).status == "pending"


def _verified_site(api, monkeypatch, url="https://example.com"):
    site = _register(api, url)
    monkeypatch.setattr(
        server_module, "verify",
        lambda d, t, method="any": _verify_result(verified=True, reason="ok"),
    )
    api("POST", f"/sites/{site['site_id']}/verify", {})
    return site


def _await_state(api, site_id, want, tries=100):
    for _ in range(tries):
        _, body = api("GET", f"/sites/{site_id}/crawl")
        if body["state"] == want:
            return body
        threading.Event().wait(0.05)
    raise AssertionError(f"crawl never reached {want!r}: {body}")


def test_crawl_starts_for_a_verified_site_and_reports_its_result(api, monkeypatch):
    site = _verified_site(api, monkeypatch)
    # Held open, or the fake runner can finish before the 202 is serialised
    # and the "running" assertion becomes a coin flip. A real crawl takes
    # seconds; this is the state the caller is meant to see.
    api.runner.gate.clear()
    status, body = api("POST", f"/sites/{site['site_id']}/crawl", {})
    assert status == 202
    assert body["job"]["state"] == "running"
    api.runner.gate.set()
    done = _await_state(api, site["site_id"], "done")
    assert done["job"]["report"]["pages_fetched"] == 3
    assert api.runner.calls[0][0] == site["site_id"]


def test_crawl_state_is_idle_before_anything_has_run(api):
    site = _register(api)
    status, body = api("GET", f"/sites/{site['site_id']}/crawl")
    assert status == 200
    assert body["state"] == "idle"
    assert body["job"] is None


def test_a_failing_crawl_ends_as_failed_rather_than_running_forever(api, monkeypatch):
    site = _verified_site(api, monkeypatch)
    api.runner.raises = RuntimeError("host went away")
    api("POST", f"/sites/{site['site_id']}/crawl", {})
    done = _await_state(api, site["site_id"], "failed")
    assert "host went away" in done["job"]["error"]


def test_a_second_crawl_of_the_same_site_is_refused_not_queued(api, monkeypatch):
    site = _verified_site(api, monkeypatch)
    api.runner.gate.clear()          # hold the first crawl open
    try:
        first, _ = api("POST", f"/sites/{site['site_id']}/crawl", {})
        assert first == 202
        status, body = api("POST", f"/sites/{site['site_id']}/crawl", {})
        assert status == 409
        assert body["reason"] == "already_running"
        assert len(api.runner.calls) == 1
    finally:
        api.runner.gate.set()


def test_caller_supplied_bounds_are_clamped_to_the_ceilings(api, monkeypatch):
    site = _verified_site(api, monkeypatch)
    api("POST", f"/sites/{site['site_id']}/crawl",
        {"max_pages": 100000, "max_depth": 99})
    _await_state(api, site["site_id"], "done")
    _, bounds = api.runner.calls[0]
    assert bounds == {"max_pages": MAX_PAGES, "max_depth": MAX_DEPTH}


def test_crawl_on_unknown_site_is_404(api):
    status, body = api("POST", "/sites/nosuchsite/crawl", {})
    assert status == 404
    assert body["reason"] == "unknown_site"


# ------------------------------------------------------------ _crawl_bounds

def test_crawl_bounds_omits_what_was_not_asked_for():
    assert _crawl_bounds({}) == {}


def test_crawl_bounds_lets_a_smaller_crawl_through():
    assert _crawl_bounds({"max_pages": 3, "max_depth": 1}) == {
        "max_pages": 3, "max_depth": 1,
    }


def test_crawl_bounds_clamps_up_from_nonsense_and_down_from_greed():
    assert _crawl_bounds({"max_pages": -5})["max_pages"] == 1
    assert _crawl_bounds({"max_depth": -5})["max_depth"] == 0
    assert _crawl_bounds({"max_pages": 10**9})["max_pages"] == MAX_PAGES


def test_crawl_bounds_ignores_values_that_are_not_numbers():
    assert _crawl_bounds({"max_pages": "lots", "max_depth": None}) == {}
