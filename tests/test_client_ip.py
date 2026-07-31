"""Rate limiting must see the real caller, not the tunnel.

Every public request reaches Shaggoth through cloudflared over loopback, so
keying the limiter on the socket address put the whole internet in one bucket.
These tests pin both halves of the fix: forwarded headers are honoured behind
the tunnel, and ignored everywhere else.
"""

import pytest

from shaggoth.server import _TRUSTED_PROXIES, _parse_ip


class FakeHandler:
    """Just enough of the request handler to exercise _client_ip."""

    def __init__(self, peer, headers=None):
        self.client_address = (peer, 51234)
        self.headers = headers or {}


@pytest.fixture
def client_ip():
    """The real _client_ip, called against a fake handler.

    make_handler only closes over its arguments to build the class, so None
    engine/learner are fine here -- _client_ip touches nothing but the
    request's own socket address and headers.
    """
    from shaggoth.server import make_handler

    handler_cls = make_handler(None, None)
    return lambda h: handler_cls._client_ip(h)


# --------------------------------------------------------- _parse_ip

def test_parse_ip_accepts_plain_v4():
    assert _parse_ip("203.0.113.7") == "203.0.113.7"


def test_parse_ip_accepts_v6():
    assert _parse_ip("2001:db8::1") == "2001:db8::1"


def test_parse_ip_strips_surrounding_whitespace():
    assert _parse_ip("  203.0.113.7 ") == "203.0.113.7"


def test_parse_ip_strips_appended_port():
    assert _parse_ip("203.0.113.7:51234") == "203.0.113.7"


def test_parse_ip_strips_bracketed_v6_port():
    assert _parse_ip("[2001:db8::1]:443") == "2001:db8::1"


@pytest.mark.parametrize("bad", ["", "   ", "not-an-ip", "999.1.1.1", "<script>"])
def test_parse_ip_rejects_garbage(bad):
    assert _parse_ip(bad) == ""


def test_parse_ip_rejects_overlong_value():
    # The result becomes a dict key held for the process lifetime; an
    # unbounded header must not become an unbounded key.
    assert _parse_ip("1" * 500) == ""


# --------------------------------------------------------- _client_ip

def test_loopback_peer_uses_cf_connecting_ip(client_ip):
    """The tunnel case: this is what was broken."""
    h = FakeHandler("127.0.0.1", {"CF-Connecting-IP": "203.0.113.7"})
    assert client_ip(h) == "203.0.113.7"


def test_two_visitors_through_tunnel_get_distinct_keys(client_ip):
    a = FakeHandler("127.0.0.1", {"CF-Connecting-IP": "203.0.113.7"})
    b = FakeHandler("127.0.0.1", {"CF-Connecting-IP": "198.51.100.4"})
    assert client_ip(a) != client_ip(b)


def test_untrusted_peer_headers_are_ignored(client_ip):
    """A LAN client must not be able to forge its way out of the bucket.

    Trusting this header from an arbitrary peer would be a worse hole than
    the shared-bucket bug: a fresh spoofed IP per request means no limit.
    """
    h = FakeHandler("192.168.1.50", {"CF-Connecting-IP": "203.0.113.7"})
    assert client_ip(h) == "192.168.1.50"


def test_spoofed_ip_from_untrusted_peer_cannot_shard_the_bucket(client_ip):
    """Same attacker, different forged headers -> still one bucket."""
    keys = {
        client_ip(FakeHandler("192.168.1.50", {"CF-Connecting-IP": f"203.0.113.{n}"}))
        for n in range(1, 20)
    }
    assert keys == {"192.168.1.50"}


def test_x_real_ip_used_when_cf_header_absent(client_ip):
    h = FakeHandler("127.0.0.1", {"X-Real-IP": "203.0.113.7"})
    assert client_ip(h) == "203.0.113.7"


def test_cf_header_wins_over_x_real_ip(client_ip):
    h = FakeHandler(
        "127.0.0.1",
        {"X-Real-IP": "198.51.100.4", "CF-Connecting-IP": "203.0.113.7"},
    )
    assert client_ip(h) == "203.0.113.7"


def test_forwarded_for_chain_takes_leftmost(client_ip):
    h = FakeHandler(
        "127.0.0.1", {"X-Forwarded-For": "203.0.113.7, 198.51.100.4, 192.0.2.9"}
    )
    assert client_ip(h) == "203.0.113.7"


def test_forwarded_for_skips_garbage_entries(client_ip):
    h = FakeHandler("127.0.0.1", {"X-Forwarded-For": "unknown, 203.0.113.7"})
    assert client_ip(h) == "203.0.113.7"


def test_garbage_headers_fall_back_to_peer(client_ip):
    h = FakeHandler("127.0.0.1", {"CF-Connecting-IP": "haha", "X-Forwarded-For": "nope"})
    assert client_ip(h) == "127.0.0.1"


def test_direct_loopback_without_headers_falls_back_to_peer(client_ip):
    """curl on the box, health checks: no headers, still a usable key."""
    h = FakeHandler("127.0.0.1", {})
    assert client_ip(h) == "127.0.0.1"


def test_ipv6_loopback_is_trusted(client_ip):
    h = FakeHandler("::1", {"CF-Connecting-IP": "203.0.113.7"})
    assert client_ip(h) == "203.0.113.7"


def test_trust_boundary_is_loopback_only():
    """Widening this set silently converts the fix into a bypass."""
    assert _TRUSTED_PROXIES == frozenset({"127.0.0.1", "::1"})
