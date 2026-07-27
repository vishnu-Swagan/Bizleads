"""A qualified lead must end up with a recipient, or outreach cannot happen.

The listing provider always returns contact_email = None. Nothing else in the
pipeline supplied one, so every lead reached the composer with no recipient
and was skipped: the automation would search, qualify, spend credits, and
draft nothing at all. The page is already fetched and parsed for the quality
checks, so the address is taken from there.
"""
import pytest

from services.site_signals import _first_email, extract_signals


def test_a_published_address_is_found():
    html = '<a href="mailto:hello@caferossi.co.uk">Email us</a>'
    assert _first_email(html) == "hello@caferossi.co.uk"


def test_a_page_with_no_mailto_yields_nothing():
    assert _first_email("<p>Call us on 0161 555 0100</p>") is None


@pytest.mark.parametrize("address", [
    "noreply@wixpress.com", "no-reply@squarespace.com",
    "you@example.com", "support@godaddy.com", "donotreply@wordpress.org",
])
def test_platform_and_placeholder_addresses_are_skipped(address):
    """Writing to these reaches a hosting provider, not the business."""
    assert _first_email(f'<a href="mailto:{address}">x</a>') is None


def test_a_real_address_is_preferred_over_noise_earlier_in_the_page():
    html = (
        '<a href="mailto:noreply@wixpress.com">a</a>'
        '<a href="mailto:hello@caferossi.co.uk">b</a>'
    )
    assert _first_email(html) == "hello@caferossi.co.uk"


def test_only_mailto_links_count():
    """A loose scan of raw HTML picks up asset names and analytics ids, and
    one wrong address emails a stranger about a business that is not theirs."""
    html = '<img src="logo@2x.png"><script>track("id@segment.io")</script>'
    assert _first_email(html) is None


def test_the_address_is_normalised():
    html = '<a href="mailto:  Hello@CafeRossi.co.uk  ">x</a>'
    assert _first_email(html) == "hello@caferossi.co.uk"


def test_it_survives_malformed_input():
    for bad in ("", None, "<a href='mailto:'>x</a>", "<a href='mailto:@'>x</a>"):
        assert _first_email(bad) is None


def test_extract_signals_exposes_it():
    signals = extract_signals(
        '<a href="mailto:hi@shop.com">x</a>', final_url="http://shop.com"
    )
    assert signals["contact_email"] == "hi@shop.com"
    assert signals["has_mailto_link"] is True
