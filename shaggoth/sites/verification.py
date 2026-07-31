"""Domain normalisation and ownership verification.

Ownership verification is the gate on crawling. Without it the server is an
open crawl-on-demand proxy: anyone registers any domain and this box fetches
it on their behalf, and the abuse report arrives at a residential IP.

Two proofs are accepted, because owners have different access:

* a DNS ``TXT`` record — works when they control DNS but not the document root
* a file under ``/.well-known/`` — works when they can upload but not edit DNS

Failures are reported specifically (NXDOMAIN vs. no record vs. wrong value vs.
timeout). "Could not verify" tells an owner nothing about what to fix, and the
three causes need three different actions.

No third-party packages: the project is dependency-free, so DNS goes through
``dig`` rather than dnspython.
"""

from __future__ import annotations

import ipaddress
import re
import secrets
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

#: Prefix for the TXT record value, so the record is self-describing in a zone
#: file that may hold verification tokens for several services.
TXT_PREFIX = "shaggoth-verify="

#: Path checked for the file proof.
WELL_KNOWN_PATH = "/.well-known/shaggoth-verify.txt"

_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


class DomainError(ValueError):
    """The submitted site URL cannot be used as a tenant domain."""


def new_token() -> str:
    """A fresh verification token. Unique per site, never reused."""
    return secrets.token_urlsafe(24)


def normalise_domain(raw: str) -> str:
    """Reduce a submitted site URL to a bare, lower-case hostname.

    Accepts ``example.com``, ``https://example.com/pricing?x=1`` and friends.
    Raises :class:`DomainError` with a usable message for anything that must
    not be crawled.
    """
    value = (raw or "").strip()
    if not value:
        raise DomainError("Enter a site address.")
    if "://" not in value:
        # Bare hostnames are the common paste; assume https for parsing only.
        value = "https://" + value

    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise DomainError(
            f"Only http and https are supported (got {parsed.scheme!r})."
        )

    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise DomainError("That address has no hostname in it.")

    # An IP literal cannot prove ownership by DNS TXT and is the shape used to
    # point a crawler at internal infrastructure. Refuse both families.
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise DomainError("Enter a domain name, not an IP address.")

    if host in ("localhost", "localhost.localdomain") or host.endswith(".localhost"):
        raise DomainError("localhost cannot be verified or crawled.")
    if "." not in host:
        raise DomainError(f"{host!r} is not a fully qualified domain name.")
    if host.endswith((".local", ".internal", ".test", ".invalid", ".localdomain")):
        raise DomainError(f"{host!r} is not a public domain.")

    labels = host.split(".")
    if any(not _LABEL.match(lbl) for lbl in labels):
        raise DomainError(f"{host!r} is not a valid domain name.")
    if len(host) > 253:
        raise DomainError("That domain name is too long.")
    return host


@dataclass
class VerificationResult:
    """Outcome of one verification attempt."""

    verified: bool
    method: str          # "dns" | "file"
    reason: str          # machine-readable: ok | nxdomain | no_record | ...
    detail: str          # what to tell the owner
    found: list[str]     # what was actually observed, for the UI

    def as_dict(self) -> dict:
        return {
            "verified": self.verified,
            "method": self.method,
            "reason": self.reason,
            "detail": self.detail,
            "found": self.found,
        }


def dns_instructions(domain: str, token: str) -> dict:
    return {
        "type": "TXT",
        "name": domain,
        "value": f"{TXT_PREFIX}{token}",
    }


def file_instructions(domain: str, token: str) -> dict:
    return {
        "url": f"https://{domain}{WELL_KNOWN_PATH}",
        "path": WELL_KNOWN_PATH,
        "contents": token,
    }


def verify_dns(domain: str, token: str, timeout: int = 6) -> VerificationResult:
    """Look for ``shaggoth-verify=<token>`` in the domain's TXT records."""
    want = f"{TXT_PREFIX}{token}"
    try:
        proc = subprocess.run(
            ["dig", "+tries=1", f"+time={timeout}", "TXT", domain],
            capture_output=True, text=True, timeout=timeout + 4,
        )
    except FileNotFoundError:
        return VerificationResult(
            False, "dns", "unavailable",
            "DNS lookups are unavailable on the server; use the file method.", [],
        )
    except subprocess.TimeoutExpired:
        return VerificationResult(
            False, "dns", "timeout",
            "The DNS lookup timed out. This is usually temporary — try again.", [],
        )

    out = proc.stdout
    if "status: NXDOMAIN" in out:
        return VerificationResult(
            False, "dns", "nxdomain",
            f"{domain} does not resolve. Check the domain is spelled correctly "
            f"and that its DNS is live.", [],
        )
    if "status: SERVFAIL" in out or "status: REFUSED" in out:
        return VerificationResult(
            False, "dns", "servfail",
            f"The nameservers for {domain} returned an error. This is a problem "
            f"at the DNS provider, not with the record.", [],
        )
    if ";; connection timed out" in out or not proc.stdout.strip():
        return VerificationResult(
            False, "dns", "timeout",
            "The DNS lookup timed out. This is usually temporary — try again.", [],
        )

    # Answer section lines look like:  example.com. 300 IN TXT "v=spf1 ..."
    found: list[str] = []
    for line in out.splitlines():
        if line.startswith(";") or "\tTXT\t" not in line.replace(" ", "\t"):
            continue
        for chunk in re.findall(r'"([^"]*)"', line):
            found.append(chunk)

    if not found:
        return VerificationResult(
            False, "dns", "no_record",
            f"{domain} resolves but has no TXT records yet. DNS changes can "
            f"take a few minutes to propagate.", [],
        )
    if want in found:
        return VerificationResult(
            True, "dns", "ok", "Ownership verified by DNS TXT record.", found,
        )
    ours = [f for f in found if f.startswith(TXT_PREFIX)]
    if ours:
        return VerificationResult(
            False, "dns", "wrong_value",
            "A shaggoth-verify record exists but its value does not match. "
            "Replace it with the exact value shown above.", ours,
        )
    return VerificationResult(
        False, "dns", "no_record",
        f"{domain} has TXT records, but none of them is the verification "
        f"record. Add the one shown above.", found,
    )


def verify_file(domain: str, token: str, timeout: int = 10) -> VerificationResult:
    """Look for the token at ``/.well-known/shaggoth-verify.txt``."""
    url = f"https://{domain}{WELL_KNOWN_PATH}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ShaggothBot/0.1 (ownership verification)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # A verification file is tiny; refuse to read a whole site into RAM
            # if the path serves something enormous.
            body = resp.read(4096).decode("utf-8", errors="replace").strip()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return VerificationResult(
                False, "file", "not_found",
                f"No file at {url} (404). Upload it, then check again.", [],
            )
        return VerificationResult(
            False, "file", "http_error",
            f"{url} returned HTTP {exc.code}.", [],
        )
    except urllib.error.URLError as exc:
        return VerificationResult(
            False, "file", "unreachable",
            f"Could not reach {url}: {exc.reason}.", [],
        )
    except (TimeoutError, OSError) as exc:
        return VerificationResult(
            False, "file", "timeout",
            f"Timed out fetching {url}: {exc}.", [],
        )

    if body == token:
        return VerificationResult(
            True, "file", "ok", "Ownership verified by file.", [body],
        )
    if not body:
        return VerificationResult(
            False, "file", "empty",
            f"{url} exists but is empty. It should contain only the token.", [],
        )
    return VerificationResult(
        False, "file", "wrong_value",
        "The file exists but its contents do not match the token. It should "
        "contain the token and nothing else.", [body[:120]],
    )


def verify(domain: str, token: str, method: str = "any") -> VerificationResult:
    """Try ``method`` ("dns", "file" or "any") and report the outcome.

    ``any`` reports the DNS failure when both fail, since DNS is the method
    most owners start with — but it does try the file first if DNS is not
    usable on this host.
    """
    if method == "dns":
        return verify_dns(domain, token)
    if method == "file":
        return verify_file(domain, token)

    dns_result = verify_dns(domain, token)
    if dns_result.verified:
        return dns_result
    file_result = verify_file(domain, token)
    if file_result.verified:
        return file_result
    return dns_result if dns_result.reason != "unavailable" else file_result
