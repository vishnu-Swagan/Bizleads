"""Finding the email address a business publishes.

Almost every discovered lead arrived with no email. Three causes, all here:

  1. Only the homepage was fetched. Most businesses put the address behind a
     link called "Contact".
  2. Only mailto: hrefs were read. A great many sites print the address as
     plain text instead of linking it.
  3. Obfuscation was not decoded. Cloudflare's data-cfemail scrambling is
     ubiquitous on small-business sites, and to a scraper the page then looks
     as though it has no address at all.

Widening the scan reintroduces the risk the mailto:-only rule existed to
avoid: emailing a stranger about a business that is not theirs. The tests
below therefore pin both directions — what must now be found, and what must
still be refused.

There is no test asserting that every lead gets an email, because that is not
achievable honestly. A business with no website, or one that publishes only a
contact form, has no address to find, and inventing one is the fabrication
path this codebase deleted on purpose.
"""
import pytest

from services import qualification
from services.site_signals import _decode_cfemail, _first_email
from services.website_check import find_contact_urls


def _page(body: str) -> str:
    return f"<html><head><title>Acme</title></head><body>{body}</body></html>"


class TestAddressesThatMustNowBeFound:
    def test_a_mailto_link_still_works(self):
        html = _page('<a href="mailto:hello@acme.co.uk">Email us</a>')
        assert _first_email(html, "acme.co.uk") == "hello@acme.co.uk"

    def test_plain_text_address_on_the_sites_own_domain(self):
        """The common case the mailto:-only rule missed entirely."""
        html = _page("<p>Call us or email hello@acme.co.uk for a quote.</p>")
        assert _first_email(html, "www.acme.co.uk") == "hello@acme.co.uk"

    def test_a_consumer_mailbox_is_the_business_address_for_most_small_traders(self):
        """A sole trader's site says dave@gmail.com. That is the lead."""
        html = _page("<p>Contact: daves.plumbing@gmail.com</p>")
        assert _first_email(html, "davesplumbing.co.uk") == "daves.plumbing@gmail.com"

    def test_cloudflare_obfuscation_is_decoded(self):
        """Cloudflare replaces the address with hex; the plaintext is absent."""
        # "hi@acme.co.uk" XORed with key 0x2a, key byte first.
        plaintext = "hi@acme.co.uk"
        key = 0x2A
        encoded = format(key, "02x") + "".join(format(ord(c) ^ key, "02x") for c in plaintext)

        assert _decode_cfemail(encoded) == plaintext

        html = _page(f'<a href="/cdn-cgi/l/email-protection" data-cfemail="{encoded}">Email</a>')
        assert _first_email(html, "acme.co.uk") == "hi@acme.co.uk"

    def test_html_entity_encoded_address(self):
        html = _page("<p>&#104;ello&#64;acme.co.uk</p>")
        assert _first_email(html, "acme.co.uk") == "hello@acme.co.uk"

    def test_at_and_dot_obfuscation(self):
        html = _page("<p>Write to hello [at] acme [dot] co</p>")
        assert _first_email(html, "acme.co") == "hello@acme.co"

    def test_a_linked_address_is_trusted_on_any_domain(self):
        """A mailto: is an explicit publication, so the domain rule relaxes.

        An agency site whose contact link points at its owner's personal
        mailbox is still the right address to write to.
        """
        html = _page('<a href="mailto:studio@somewhereelse.net">Contact</a>')
        assert _first_email(html, "acme.co.uk") == "studio@somewhereelse.net"


class TestAddressesThatMustStillBeRefused:
    def test_a_third_party_address_in_page_text_is_somebody_elses(self):
        """The exact failure the mailto:-only restriction was protecting against."""
        html = _page("<p>Site built by Studio Nine — enquiries@studionine.net</p>")
        assert _first_email(html, "acme.co.uk") is None

    def test_tooling_and_cdn_addresses_are_not_the_business(self):
        html = _page("<p>report@sentry.io</p><p>abuse@cloudflare.com</p>")
        assert _first_email(html, "acme.co.uk") is None

    def test_addresses_inside_scripts_are_ignored(self):
        """Analytics config is full of @-shaped tokens that are not addresses."""
        html = _page('<script>var cfg={owner:"tracking@vendor-analytics.com"};</script>')
        assert _first_email(html, "acme.co.uk") is None

    def test_an_asset_filename_is_not_an_address(self):
        html = _page('<img src="logo@2x.png"><p>banner@3x.jpg</p>')
        assert _first_email(html, "acme.co.uk") is None

    def test_noreply_addresses_are_not_contactable(self):
        html = _page("<p>no-reply@acme.co.uk</p>")
        assert _first_email(html, "acme.co.uk") is None

    def test_a_page_with_no_address_yields_nothing(self):
        html = _page('<p>Use our <a href="/form">contact form</a>.</p>')
        assert _first_email(html, "acme.co.uk") is None

    def test_malformed_cfemail_does_not_raise(self):
        assert _decode_cfemail("zzzz") is None
        assert _decode_cfemail("") is None
        assert _decode_cfemail("2a") is None


class TestFindingTheContactPage:
    def test_a_contact_link_is_found(self):
        html = _page('<a href="/contact-us">Contact us</a><a href="/blog">Blog</a>')
        assert find_contact_urls(html, "https://acme.co.uk/") == ["https://acme.co.uk/contact-us"]

    def test_offsite_links_are_never_followed(self):
        """Following one would attribute another company's address to this lead."""
        html = _page('<a href="https://facebook.com/contact">Contact</a>')
        assert find_contact_urls(html, "https://acme.co.uk/") == []

    def test_contact_ranks_above_about(self):
        html = _page('<a href="/about">About</a><a href="/contact">Contact</a>')
        urls = find_contact_urls(html, "https://acme.co.uk/")
        assert urls[0] == "https://acme.co.uk/contact"

    def test_the_number_of_extra_fetches_is_capped(self):
        """This multiplies across every result in a search."""
        html = _page("".join(
            f'<a href="/contact-{i}">Contact {i}</a>' for i in range(10)
        ))
        assert len(find_contact_urls(html, "https://acme.co.uk/")) == 2

    def test_mailto_and_tel_links_are_not_pages(self):
        html = _page('<a href="mailto:a@b.com">Contact</a><a href="tel:123">Contact</a>')
        assert find_contact_urls(html, "https://acme.co.uk/") == []

    def test_relative_links_resolve_against_the_page(self):
        html = _page('<a href="pages/contact.html">Contact</a>')
        assert find_contact_urls(html, "https://acme.co.uk/en/") == [
            "https://acme.co.uk/en/pages/contact.html"
        ]


class TestTheContactPageCrawl:
    async def test_an_address_only_on_the_contact_page_is_found(self, monkeypatch):
        homepage = _page('<a href="/contact">Contact</a>')

        async def fake_fetch(url):
            assert url == "https://acme.co.uk/contact"
            return _page("<p>bookings@acme.co.uk</p>")

        monkeypatch.setattr(qualification, "fetch_page_html", fake_fetch)

        found = await qualification._email_from_contact_pages(homepage, "https://acme.co.uk/")

        assert found["email"] == "bookings@acme.co.uk"
        assert found["source_url"] == "https://acme.co.uk/contact"

    async def test_no_contact_links_means_no_extra_requests(self, monkeypatch):
        called = []

        async def fake_fetch(url):
            called.append(url)
            return None

        monkeypatch.setattr(qualification, "fetch_page_html", fake_fetch)

        result = await qualification._email_from_contact_pages(
            _page("<p>Nothing here.</p>"), "https://acme.co.uk/"
        )

        assert result is None
        assert called == []

    async def test_the_search_stops_at_the_first_address(self, monkeypatch):
        """Every further fetch would cost time on every lead to find nothing."""
        homepage = _page('<a href="/contact">Contact</a><a href="/about">About</a>')
        called = []

        async def fake_fetch(url):
            called.append(url)
            return _page("<p>hi@acme.co.uk</p>")

        monkeypatch.setattr(qualification, "fetch_page_html", fake_fetch)

        await qualification._email_from_contact_pages(homepage, "https://acme.co.uk/")

        assert len(called) == 1

    async def test_an_unreachable_contact_page_is_not_fatal(self, monkeypatch):
        """This only ever improves a lead. Failing here must lose nothing."""
        homepage = _page('<a href="/contact">Contact</a><a href="/about">About</a>')

        async def fake_fetch(url):
            if "contact" in url:
                return None  # dead page
            return _page("<p>team@acme.co.uk</p>")

        monkeypatch.setattr(qualification, "fetch_page_html", fake_fetch)

        found = await qualification._email_from_contact_pages(homepage, "https://acme.co.uk/")

        assert found["email"] == "team@acme.co.uk"


class TestTheCrawlOnlyRunsWhenItIsNeeded:
    async def test_a_homepage_address_costs_no_extra_fetches(self, monkeypatch):
        """A site that publishes its address must not pay for the crawl."""
        homepage = _page('<a href="mailto:hi@acme.co.uk">Email</a><a href="/contact">Contact</a>')

        async def fake_check(url):
            return {
                "has_website": True, "final_url": "https://acme.co.uk/", "state": "live",
                "html": homepage, "elapsed_seconds": 0.2, "content_bytes": len(homepage),
                "status_code": 200, "reason": "", "redirect_hops": 0,
                "input_url": url, "checked_at": "",
            }

        crawled = []

        async def fake_fetch(url):
            crawled.append(url)
            return None

        monkeypatch.setattr(qualification, "check_website", fake_check)
        monkeypatch.setattr(qualification, "fetch_page_html", fake_fetch)
        monkeypatch.setattr(qualification, "is_pagespeed_configured", lambda: False)

        result = await qualification.qualify_website("https://acme.co.uk/", allow_audit=False)

        assert result["contact_email"] == "hi@acme.co.uk"
        assert crawled == []

    async def test_a_homepage_without_an_address_triggers_the_crawl(self, monkeypatch):
        homepage = _page('<a href="/contact">Contact</a>')

        async def fake_check(url):
            return {
                "has_website": True, "final_url": "https://acme.co.uk/", "state": "live",
                "html": homepage, "elapsed_seconds": 0.2, "content_bytes": len(homepage),
                "status_code": 200, "reason": "", "redirect_hops": 0,
                "input_url": url, "checked_at": "",
            }

        async def fake_fetch(url):
            return _page("<p>hello@acme.co.uk</p>")

        monkeypatch.setattr(qualification, "check_website", fake_check)
        monkeypatch.setattr(qualification, "fetch_page_html", fake_fetch)
        monkeypatch.setattr(qualification, "is_pagespeed_configured", lambda: False)

        result = await qualification.qualify_website("https://acme.co.uk/", allow_audit=False)

        assert result["contact_email"] == "hello@acme.co.uk"
        # The page it came from is recorded, so a user can check the claim.
        assert result["evidence"]["contact_page"] == "https://acme.co.uk/contact"
