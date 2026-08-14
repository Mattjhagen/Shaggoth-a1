"""Tenant registry and ownership verification.

The isolation test is the load-bearing one: it asserts the property that a
single global index cannot provide, and whose absence produced the live
"what is PurePulse" -> Smart Fortwo answer.
"""

import pytest

from shaggoth.sites.registry import SiteRegistry
from shaggoth.sites.verification import DomainError, normalise_domain


class TestNormaliseDomain:
    @pytest.mark.parametrize("raw,expect", [
        ("purepulse.one", "purepulse.one"),
        ("https://purepulse.one/pricing?x=1", "purepulse.one"),
        ("HTTP://Example.COM", "example.com"),
        ("relayapp.pro/", "relayapp.pro"),
        ("example.com.", "example.com"),
    ])
    def test_accepts_and_reduces(self, raw, expect):
        assert normalise_domain(raw) == expect

    @pytest.mark.parametrize("raw", [
        "127.0.0.1", "10.0.0.5", "http://192.168.0.169:8899", "http://[::1]/",
        "localhost", "myhost.local", "ftp://example.com", "", "notadomain",
    ])
    def test_rejects_what_must_not_be_crawled(self, raw):
        """IPs, loopback and private TLDs are how a crawler gets pointed at
        internal infrastructure, and none of them can prove ownership."""
        with pytest.raises(DomainError):
            normalise_domain(raw)


class TestRegistry:
    def test_register_starts_pending_so_the_crawl_is_gated(self, tmp_path):
        reg = SiteRegistry(tmp_path)
        rec = reg.register("https://example.com/")
        assert rec.status == "pending"
        assert rec.verified is False

    def test_new_sites_do_not_inherit_the_rude_voice(self, tmp_path):
        reg = SiteRegistry(tmp_path)
        assert reg.register("https://example.com").personality == "professional"

    def test_register_is_idempotent_per_domain(self, tmp_path):
        reg = SiteRegistry(tmp_path)
        first = reg.register("https://example.com/a")
        second = reg.register("example.com")
        assert first.site_id == second.site_id
        assert first.token == second.token

    def test_tokens_and_ids_are_unique_across_sites(self, tmp_path):
        reg = SiteRegistry(tmp_path)
        a = reg.register("https://alpha.com")
        b = reg.register("https://beta.com")
        assert a.site_id != b.site_id
        assert a.token != b.token

    def test_verification_flips_the_gate_and_persists(self, tmp_path):
        reg = SiteRegistry(tmp_path)
        rec = reg.register("https://example.com")
        reg.mark_verified(rec.site_id, "dns")

        reloaded = SiteRegistry(tmp_path).get(rec.site_id)
        assert reloaded.verified is True
        assert reloaded.verified_method == "dns"

    @pytest.mark.parametrize("bad", ["../etc", "a/b", "..", "x\\y"])
    def test_site_id_cannot_escape_the_sites_directory(self, tmp_path, bad):
        assert SiteRegistry(tmp_path).get(bad) is None


class TestCorpusIsolation:
    def test_one_sites_pages_never_answer_anothers_visitors(self, tmp_path):
        """The property a filtered global index cannot give you."""
        reg = SiteRegistry(tmp_path)
        a = reg.register("https://alpha.com")
        b = reg.register("https://beta.com")

        (tmp_path / a.site_id / "knowledge" / "pricing.md").write_text(
            "Alpha charges a flat fifty dollar deposit for every project."
        )
        (tmp_path / b.site_id / "knowledge" / "pricing.md").write_text(
            "Beta rents industrial welding equipment by the week."
        )

        kb_a = reg.knowledge_base(a.site_id)
        kb_b = reg.knowledge_base(b.site_id)

        assert [e.topic for e, _ in kb_a.query("deposit")] == ["Pricing"]
        assert "welding" not in kb_a._entries[0].content
        # Alpha's visitor asking about Beta's business gets nothing, rather
        # than Beta's page.
        assert kb_a.query("industrial welding equipment") == []
        assert kb_b.query("industrial welding equipment")

    def test_knowledge_base_is_built_once_per_site(self, tmp_path):
        reg = SiteRegistry(tmp_path)
        rec = reg.register("https://example.com")
        assert reg.knowledge_base(rec.site_id) is reg.knowledge_base(rec.site_id)

    def test_each_site_gets_a_distinct_corpus_object(self, tmp_path):
        reg = SiteRegistry(tmp_path)
        a = reg.register("https://alpha.com")
        b = reg.register("https://beta.com")
        assert reg.knowledge_base(a.site_id) is not reg.knowledge_base(b.site_id)
