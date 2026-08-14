"""Tenant crawl: the verification gate, the bounds, and the skip reasons."""

import pytest

from shaggoth.sites.crawl import MAX_PAGE_BYTES, CrawlNotPermitted, crawl_site
from shaggoth.sites.registry import SiteRegistry


class StubPage:
    def __init__(self, text, title="Page"):
        self.text = text
        self.title = title
        self.word_count = len(text.split())


class StubScraper:
    """Stands in for ScraperEngine so the skip paths are testable offline."""

    def __init__(self, pages=None, disallowed=(), html=""):
        self.pages = pages or {}
        self.disallowed = set(disallowed)
        self.respect_robots = True
        self._last_html = html
        self.fetched = []

    def robots_allows(self, url):
        return url not in self.disallowed

    def fetch_page(self, url, timeout=15):
        self.fetched.append(url)
        return self.pages.get(url)


@pytest.fixture
def verified_site(tmp_path):
    reg = SiteRegistry(tmp_path)
    rec = reg.register("https://example.com")
    reg.mark_verified(rec.site_id, "dns")
    return reg, reg.get(rec.site_id)


class TestVerificationGate:
    def test_unverified_site_is_refused(self, tmp_path):
        reg = SiteRegistry(tmp_path)
        rec = reg.register("https://example.com")
        with pytest.raises(CrawlNotPermitted, match="not verified"):
            crawl_site(reg, rec.site_id)

    def test_unknown_site_is_refused(self, tmp_path):
        with pytest.raises(CrawlNotPermitted, match="no such site"):
            crawl_site(SiteRegistry(tmp_path), "nope")

    def test_nothing_is_fetched_when_refused(self, tmp_path):
        reg = SiteRegistry(tmp_path)
        rec = reg.register("https://example.com")
        scraper = StubScraper()
        with pytest.raises(CrawlNotPermitted):
            crawl_site(reg, rec.site_id, scraper=scraper)
        assert scraper.fetched == []


class TestCrawlLandsInTheRightCorpus:
    def test_content_reaches_only_this_sites_knowledge_base(self, verified_site, tmp_path):
        reg, rec = verified_site
        other = reg.register("https://other.com")

        scraper = StubScraper({
            "https://example.com/": StubPage("Example sells industrial widgets.", "Home"),
        })
        report = crawl_site(reg, rec.site_id, scraper=scraper)

        assert report.pages_fetched == 1
        assert reg.knowledge_base(rec.site_id).query("industrial widgets")
        # The other tenant learned nothing.
        assert reg.knowledge_base(other.site_id).query("industrial widgets") == []

    def test_report_records_the_crawl_on_the_record(self, verified_site):
        reg, rec = verified_site
        scraper = StubScraper({"https://example.com/": StubPage("Hello there world.")})
        crawl_site(reg, rec.site_id, scraper=scraper)
        assert reg.get(rec.site_id).pages_indexed == 1
        assert reg.get(rec.site_id).last_crawl_at > 0


class TestSkipReasons:
    def _reasons(self, report):
        return {p.url: p.reason for p in report.pages if p.status == "skipped"}

    def test_robots_disallow_is_reported_by_name(self, verified_site):
        reg, rec = verified_site
        scraper = StubScraper(
            pages={"https://example.com/": StubPage("Root page text here.")},
            disallowed={"https://example.com/"},
        )
        report = crawl_site(reg, rec.site_id, scraper=scraper)
        assert self._reasons(report)["https://example.com/"] == "robots.txt disallow"
        assert scraper.fetched == []  # never even requested

    def test_off_domain_links_are_not_followed(self, verified_site):
        reg, rec = verified_site
        scraper = StubScraper(
            pages={"https://example.com/": StubPage("Root.")},
            html='<a href="https://elsewhere.com/x">x</a>',
        )
        report = crawl_site(reg, rec.site_id, scraper=scraper)
        assert self._reasons(report).get("https://elsewhere.com/x") == "off-domain"

    def test_non_html_assets_are_skipped(self, verified_site):
        reg, rec = verified_site
        scraper = StubScraper(
            pages={"https://example.com/": StubPage("Root.")},
            html='<a href="/brochure.pdf">pdf</a><a href="/style.css">css</a>',
        )
        report = crawl_site(reg, rec.site_id, scraper=scraper)
        reasons = self._reasons(report)
        assert reasons["https://example.com/brochure.pdf"] == "non-HTML"
        assert reasons["https://example.com/style.css"] == "non-HTML"

    def test_duplicate_content_is_skipped_once_seen(self, verified_site):
        reg, rec = verified_site
        same = "Identical body copy on two different urls."
        scraper = StubScraper(
            pages={
                "https://example.com/": StubPage(same, "Home"),
                "https://example.com/index.html": StubPage(same, "Home again"),
            },
            html='<a href="/index.html">again</a>',
        )
        report = crawl_site(reg, rec.site_id, scraper=scraper)
        assert report.pages_fetched == 1
        assert self._reasons(report)["https://example.com/index.html"] == "duplicate content"

    def test_oversized_pages_are_skipped(self, verified_site):
        reg, rec = verified_site
        scraper = StubScraper({
            "https://example.com/": StubPage("x " * (MAX_PAGE_BYTES // 2 + 10)),
        })
        report = crawl_site(reg, rec.site_id, scraper=scraper)
        assert self._reasons(report)["https://example.com/"] == "too large"


class TestBounds:
    def test_page_cap_stops_the_crawl(self, verified_site):
        reg, rec = verified_site
        pages = {
            f"https://example.com/p{i}": StubPage(f"Distinct page number {i} content.")
            for i in range(10)
        }
        pages["https://example.com/"] = StubPage("Root page distinct content.")
        links = "".join(f'<a href="/p{i}">{i}</a>' for i in range(10))
        scraper = StubScraper(pages=pages, html=links)

        report = crawl_site(reg, rec.site_id, scraper=scraper, max_pages=3)
        assert report.pages_fetched == 3
        assert "page limit" in report.stopped_reason

    def test_depth_zero_does_not_follow_links(self, verified_site):
        reg, rec = verified_site
        scraper = StubScraper(
            pages={
                "https://example.com/": StubPage("Root."),
                "https://example.com/deep": StubPage("Deep."),
            },
            html='<a href="/deep">deep</a>',
        )
        report = crawl_site(reg, rec.site_id, scraper=scraper, max_depth=0)
        assert report.pages_fetched == 1
