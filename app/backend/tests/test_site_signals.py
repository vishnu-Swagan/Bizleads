"""The free website-quality tier: scoring from bytes Pass 2 already fetched.

Two properties matter and are tested separately:

  1. Signals are extracted from real markup, not guessed.
  2. A check that could not run costs the site nothing. An unmeasurable page
     must never score worse than a measured good one — that is the same
     unknown-as-known defect this codebase has been removing throughout.
"""
from services.site_signals import analyse, extract_signals, score_signals

MODERN_PAGE = """
<html><head>
  <title>Riverside Cafe — Leeds</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Independent cafe in Leeds serving breakfast and lunch.">
  <script type="application/ld+json">{"@type":"Restaurant"}</script>
</head><body>
  <h1>Riverside Cafe</h1>
  <img src="a.jpg" alt="Our terrace">
  <img src="b.jpg" alt="Coffee">
  <img src="c.jpg" alt="Cakes">
  <a href="tel:+441130000000">Call us</a>
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
