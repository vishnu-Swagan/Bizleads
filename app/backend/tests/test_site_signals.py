"""The free website-quality tier: scoring from bytes Pass 2 already fetched.

Two properties matter and are tested separately:

  1. Signals are extracted from real markup, not guessed.
  2. A check that could not run costs the site nothing. An unmeasurable page
     must never score worse than a measured good one — that is the same
     unknown-as-known defect this codebase has been removing throughout.
"""
import json

from services.site_signals import analyse, extract_signals, score_signals

# A genuinely well-built page, not merely an inoffensive one. It gained a lang
# attribute, favicon, canonical, Open Graph tags, analytics and social links
# when the second tier of checks landed: this fixture is the definition of
# "nothing to sell against", so anything a competent build includes belongs
# here. Leaving it minimal would have meant either weakening the >= 90
# assertion or pretending the new checks were wrong, and both would have made
# the test agree with the code by construction.
MODERN_PAGE = """
<html lang="en-GB"><head>
  <title>Riverside Cafe — Leeds</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Independent cafe in Leeds serving breakfast and lunch.">
  <link rel="icon" href="/favicon.ico">
  <link rel="canonical" href="https://example.com/">
  <meta property="og:title" content="Riverside Cafe">
  <meta property="og:image" content="/og.png">
  <script type="application/ld+json">{"@type":"Restaurant"}</script>
  <script async src="https://www.googletagmanager.com/gtag/js"></script>
</head><body>
  <h1>Riverside Cafe</h1>
  <img src="a.jpg" alt="Our terrace">
  <img src="b.jpg" alt="Coffee">
  <img src="c.jpg" alt="Cakes">
  <a href="tel:+441130000000">Call us</a>
  <a href="https://instagram.com/riversidecafe">Instagram</a>
  <form><input name="email"></form>
  <footer>&copy; 2026 Riverside Cafe</footer>
</body></html>
"""

DATED_PAGE = """
<html><head><title>Old Shop</title></head><body>
  <script src="/js/jquery-1.11.min.js"></script>
  <img src="a.jpg"><img src="b.jpg"><img src="c.jpg"><img src="d.jpg">
  <p>Ring us on 0113 000 0000</p>
  <footer>&copy; 2014 Old Shop</footer>
</body></html>
"""


class TestExtraction:
    def test_reads_modern_markup(self):
        s = extract_signals(MODERN_PAGE, final_url="https://example.com", elapsed_seconds=0.4)

        assert s["https"] is True
        assert s["has_viewport_meta"] is True
        assert s["has_title"] is True
        assert s["has_meta_description"] is True
        assert s["has_h1"] is True
        assert s["has_schema_markup"] is True
        assert s["has_tel_link"] is True
        assert s["has_form"] is True
        assert s["image_count"] == 3
        assert s["images_without_alt"] == 0
        assert s["newest_copyright_year"] == 2026

    def test_reads_dated_markup(self):
        s = extract_signals(DATED_PAGE, final_url="http://example.com", elapsed_seconds=4.2)

        assert s["https"] is False
        assert s["has_viewport_meta"] is False
        assert s["has_meta_description"] is False
        assert s["has_h1"] is False
        assert s["images_without_alt"] == 4
        assert s["jquery_major"] == 1
        assert s["newest_copyright_year"] == 2014
        # A phone number in prose is not a tap-to-call link.
        assert s["has_tel_link"] is False

    def test_detects_social_links(self):
        html = '<a href="https://facebook.com/x">fb</a><a href="https://instagram.com/x">ig</a>'
        s = extract_signals(html, final_url="https://example.com")
        assert s["social_links"] == ["facebook", "instagram"]


class TestScoring:
    def test_a_good_site_scores_well(self):
        result = analyse(MODERN_PAGE, final_url="https://example.com", elapsed_seconds=0.4)
        assert result["website_score"] >= 90
        assert result["website_state"] == "healthy"

    def test_a_dated_site_scores_poorly(self):
        result = analyse(DATED_PAGE, final_url="http://example.com", elapsed_seconds=4.2)
        assert result["website_score"] < 40
        assert result["website_state"] in ("weak", "parked")

    def test_missing_viewport_is_the_heaviest_single_penalty(self):
        # Mobile unusability outweighs any individual SEO or stack finding,
        # because it is the one a prospect can see for themselves on their phone.
        result = analyse(DATED_PAGE, final_url="http://example.com")
        top = result["findings"][0]
        assert top["id"] == "no_viewport"
        assert top["penalty"] == 30

    def test_every_finding_carries_checkable_evidence(self):
        # "Why this score?" must show a fact, not just a label.
        result = analyse(DATED_PAGE, final_url="http://example.com", elapsed_seconds=4.2)
        assert result["findings"]
        for finding in result["findings"]:
            assert finding["evidence"].strip(), f"{finding['id']} has no evidence"
            assert finding["penalty"] > 0
            assert finding["category"]

    def test_findings_are_ordered_by_impact(self):
        result = analyse(DATED_PAGE, final_url="http://example.com", elapsed_seconds=4.2)
        penalties = [f["penalty"] for f in result["findings"]]
        assert penalties == sorted(penalties, reverse=True)

    def test_the_tier_is_labelled_so_it_is_not_mistaken_for_lighthouse(self):
        assert analyse(MODERN_PAGE, final_url="https://example.com")["evidence_tier"] == "heuristic"


class TestUnmeasuredChecksCostNothing:
    def test_absent_timing_adds_no_penalty(self):
        with_timing = analyse(MODERN_PAGE, final_url="https://example.com", elapsed_seconds=0.4)
        without_timing = analyse(MODERN_PAGE, final_url="https://example.com", elapsed_seconds=None)

        assert without_timing["website_score"] == with_timing["website_score"]
        assert not any(f["id"] in ("slow", "very_slow") for f in without_timing["findings"])

    def test_absent_page_size_adds_no_penalty(self):
        assert not any(
            f["id"] == "heavy_page"
            for f in analyse(MODERN_PAGE, final_url="https://example.com", content_bytes=None)["findings"]
        )

    def test_a_page_with_no_images_is_not_penalised_for_alt_text(self):
        html = '<html><head><title>T</title><meta name="viewport" content="width=device-width">' \
               '<meta name="description" content="d"></head><body><h1>H</h1>' \
               '<a href="tel:+441130000000">call</a></body></html>'
        assert not any(f["id"] == "images_no_alt" for f in analyse(html, final_url="https://x.com")["findings"])

    def test_score_never_leaves_the_0_100_range(self):
        empty = score_signals({})
        assert 0 <= empty["website_score"] <= 100


class TestTheSecondTierOfChecks:
    """Checks added in site-signals-1.1.0.

    Each exists to give outreach something specific and verifiable to cite, so
    each is tested for the finding it produces rather than only for its effect
    on the score.
    """

    def _ids(self, html, **kwargs):
        kwargs.setdefault("final_url", "https://example.com")
        return {f["id"] for f in analyse(html, **kwargs)["findings"]}

    def test_a_noindex_page_is_flagged(self):
        html = '<html><head><meta name="robots" content="noindex, nofollow"></head><body></body></html>'
        assert "noindex" in self._ids(html)

    def test_an_indexable_page_is_not_flagged(self):
        html = '<html><head><meta name="robots" content="index, follow"></head><body></body></html>'
        assert "noindex" not in self._ids(html)

    def test_missing_social_links_are_flagged(self):
        assert "no_social_links" in self._ids("<html><body>nothing here</body></html>")

    def test_a_linked_platform_clears_the_flag(self):
        html = '<html><body><a href="https://instagram.com/x">ig</a></body></html>'
        assert "no_social_links" not in self._ids(html)

    def test_missing_analytics_is_flagged(self):
        assert "no_analytics" in self._ids("<html><body></body></html>")

    def test_any_mainstream_analytics_clears_the_flag(self):
        html = '<html><head><script src="https://plausible.io/js/script.js"></script></head><body></body></html>'
        assert "no_analytics" not in self._ids(html)

    def test_http_assets_on_an_https_page_are_mixed_content(self):
        html = '<html><body><img src="http://cdn.example.com/a.jpg"></body></html>'
        assert "mixed_content" in self._ids(html)

    def test_http_assets_on_an_http_page_are_not_mixed_content(self):
        """An insecure asset on an insecure page is not "mixed" — no_https
        already reports that, and double-counting it would penalise the same
        defect twice."""
        html = '<html><body><img src="http://cdn.example.com/a.jpg"></body></html>'
        assert "mixed_content" not in self._ids(html, final_url="http://example.com")

    def test_a_schema_org_url_is_not_mistaken_for_mixed_content(self):
        """itemtype="http://schema.org/..." is a namespace identifier the
        browser never fetches. Matching bare "http://" would flag every page
        using microdata."""
        html = '<html><body><div itemscope itemtype="http://schema.org/Restaurant"></div></body></html>'
        assert "mixed_content" not in self._ids(html)

    def test_obsolete_presentational_tags_are_flagged(self):
        assert "legacy_html" in self._ids("<html><body><center><font size=2>hi</font></center></body></html>")

    def test_missing_favicon_canonical_and_lang_are_each_flagged(self):
        ids = self._ids("<html><head></head><body></body></html>")
        assert {"no_favicon", "no_canonical", "no_lang"} <= ids

    def test_a_complete_head_clears_them(self):
        html = ('<html lang="en"><head><link rel="icon" href="/f.ico">'
                '<link rel="canonical" href="https://example.com/">'
                '<meta property="og:title" content="T"></head><body></body></html>')
        ids = self._ids(html)
        assert not ({"no_favicon", "no_canonical", "no_lang", "no_open_graph"} & ids)

    def test_noindex_outweighs_the_cosmetic_checks(self):
        """Severity ordering is the point of the penalties: being invisible to
        search must not rank below a missing favicon."""
        html = '<html><head><meta name="robots" content="noindex"></head><body></body></html>'
        findings = {f["id"]: f["penalty"] for f in analyse(html, final_url="https://example.com")["findings"]}
        assert findings["noindex"] > findings["no_favicon"]

    def test_every_new_finding_carries_evidence(self):
        """A finding with no evidence string cannot be quoted to a prospect,
        which is the only reason these exist."""
        result = analyse("<html><head></head><body></body></html>", final_url="https://example.com")
        assert all(f["evidence"].strip() for f in result["findings"])


class TestPhoneExtraction:
    """A wrong number means cold-calling a stranger about somebody else's
    business, so the extractor is deliberately narrow: a tel: link is a number
    the business published and marked callable."""

    def _phone(self, html):
        return extract_signals(html, final_url="https://example.com")["contact_phone"]

    def test_it_reads_a_tel_link(self):
        assert self._phone('<a href="tel:+441618349644">Call</a>') == "+441618349644"

    def test_readability_separators_are_stripped(self):
        assert self._phone('<a href="tel:+44 161 834-9644">Call</a>') == "+441618349644"

    def test_a_bracketed_trunk_prefix_is_dropped(self):
        """"+44 (0)161..." is written that way to say "omit the 0 when
        dialling internationally". Keeping it produces +4401618349644, which
        does not connect."""
        assert self._phone('<a href="tel:+44 (0)161 834 9644">Call</a>') == "+441618349644"

    def test_a_leading_zero_without_a_plus_is_kept(self):
        """A national-format number has no + to make the trunk prefix
        redundant, so removing it would break the number instead of fixing
        it."""
        assert self._phone('<a href="tel:0161 834 9644">Call</a>') == "01618349644"

    def test_a_number_in_prose_is_not_extracted(self):
        """The whole reason for the tel: restriction: digits in text are
        prices, dates and registration numbers far more often than phones."""
        assert self._phone("<p>Company no. 01234567, est. 1969, from £25.00</p>") is None

    def test_a_shortcode_is_rejected(self):
        assert self._phone('<a href="tel:999">Emergency</a>') is None

    def test_an_over_length_number_is_rejected(self):
        """E.164 tops out at 15 digits; longer is not a phone number."""
        assert self._phone('<a href="tel:+1234567890123456789">x</a>') is None

    def test_pause_and_wait_signalling_is_dropped(self):
        assert self._phone('<a href="tel:+441618349644,,123">Call</a>') == "+441618349644"

    def test_the_first_of_several_wins(self):
        html = '<a href="tel:+441618349644">A</a><a href="tel:+442079460958">B</a>'
        assert self._phone(html) == "+441618349644"

    def test_a_non_uk_number_works_the_same(self):
        """The point of reading the page rather than the listing provider:
        provider phone coverage varies by country, a business's own site does
        not."""
        assert self._phone('<a href="tel:+81352962345">電話</a>') == "+81352962345"


class TestPostalAddressExtraction:
    """Structured data only. A wrong address sends post, or a person, to the
    wrong place — free-text parsing is unreliable in one country and hopeless
    across twenty."""

    def _addr(self, html):
        return extract_signals(html, final_url="https://example.com")["postal_address"]

    def test_it_reads_a_json_ld_postal_address(self):
        html = '''<script type="application/ld+json">
        {"@type":"Restaurant","name":"Riverside Cafe","address":{
          "@type":"PostalAddress","streetAddress":"12 Mill Lane",
          "addressLocality":"Leeds","postalCode":"LS1 4AB",
          "addressCountry":"GB"}}</script>'''
        assert self._addr(html) == "12 Mill Lane, Leeds, LS1 4AB, GB"

    def test_a_nested_country_object_is_flattened(self):
        html = '''<script type="application/ld+json">
        {"@type":"PostalAddress","streetAddress":"1 Rue de Rivoli",
         "addressLocality":"Paris",
         "addressCountry":{"@type":"Country","name":"France"}}</script>'''
        assert self._addr(html) == "1 Rue de Rivoli, Paris, France"

    def test_it_finds_an_address_inside_an_at_graph(self):
        html = '''<script type="application/ld+json">
        {"@context":"https://schema.org","@graph":[
          {"@type":"WebSite","name":"x"},
          {"@type":"LocalBusiness","address":{"@type":"PostalAddress",
            "streetAddress":"5 Hauptstrasse","addressLocality":"Berlin"}}]}</script>'''
        assert self._addr(html) == "5 Hauptstrasse, Berlin"

    def test_an_address_given_as_a_plain_string_is_kept(self):
        html = '''<script type="application/ld+json">
        {"@type":"LocalBusiness","address":"22 Bridge St, Cork"}</script>'''
        assert self._addr(html) == "22 Bridge St, Cork"

    def test_no_structured_data_means_no_address(self):
        assert self._addr("<footer>12 Mill Lane, Leeds LS1 4AB</footer>") is None

    def test_one_malformed_block_does_not_stop_the_others(self):
        """Hand-written JSON-LD is very often slightly invalid."""
        html = '''<script type="application/ld+json">{trailing,,}</script>
        <script type="application/ld+json">
        {"@type":"PostalAddress","streetAddress":"9 Kloof St",
         "addressLocality":"Cape Town"}</script>'''
        assert self._addr(html) == "9 Kloof St, Cape Town"

    def test_deep_nesting_terminates(self):
        """A hostile or broken document must not spend the request budget in
        a recursion."""
        deep = {"a": {}}
        node = deep["a"]
        for _ in range(50):
            node["a"] = {}
            node = node["a"]
        html = f'<script type="application/ld+json">{json.dumps(deep)}</script>'
        assert self._addr(html) is None
