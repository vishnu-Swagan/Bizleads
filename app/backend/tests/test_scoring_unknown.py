"""Unknown must never be scored as a known state.

A discovery provider returns a business's name and address, not its website.
The provider adapter previously filled that gap with `has_website=False`, which
scoring read as a confirmed absence and scored Need at 90 — so every real
business came back labelled "No Website" whether or not it had one. A fabricated
verdict on a real business, which is the same defect class as the AI fabrication
that was removed from discovery.

These tests pin the three states apart: unmeasured, confirmed-absent, and
measured.
"""
from services.mapbox_places import _normalize_feature
from services.scoring import build_score_breakdown, calculate_priority_score, get_website_state


class TestWebsiteState:
    def test_unchecked_is_unknown_not_no_website(self):
        assert get_website_state(None, None) == "unknown"

    def test_confirmed_absent_is_no_website(self):
        assert get_website_state(False, None) == "no_website"

    def test_site_found_but_unaudited_is_unknown(self):
        # Having a website tells us nothing about its quality until measured.
        assert get_website_state(True, None) == "unknown"

    def test_measured_scores_map_to_quality_bands(self):
        assert get_website_state(True, 10) == "parked"
        assert get_website_state(True, 30) == "weak"
        assert get_website_state(True, 55) == "moderate"
        assert get_website_state(True, 85) == "healthy"


class TestNeedScore:
    def test_unchecked_website_yields_no_need_score(self):
        result = build_score_breakdown({"has_website": None})

        assert result["scores"]["need"] is None
        assert result["qualification_required"] is True
        assert "not checked" in result["breakdowns"]["need"]["factors"][0]["factor"].lower()

    def test_confirmed_no_website_scores_high_need(self):
        result = build_score_breakdown({"has_website": False, "social_score": 50})

        assert result["scores"]["need"] == 90
        assert result["qualification_required"] is False

    def test_unaudited_website_yields_no_need_score(self):
        result = build_score_breakdown({"has_website": True, "website_score": None})

        assert result["scores"]["need"] is None
        assert result["qualification_required"] is True


class TestPriorityScore:
    def test_priority_is_none_when_need_is_unmeasured(self):
        # Need carries 0.30 weight. Substituting a placeholder would produce a
        # confident-looking ranking derived from a value nobody measured.
        assert calculate_priority_score({"need": None, "buyability": 50}) is None

    def test_priority_is_computed_when_need_is_known(self):
        score = calculate_priority_score(
            {"need": 90, "buyability": 50, "timing": 30, "reachability": 40, "agency_fit": 50, "confidence": 70}
        )
        assert score is not None
        assert 0 <= score <= 100

    def test_unqualified_lead_is_not_ranked_as_hot(self):
        # The whole failure mode: an unmeasured lead must not surface as a
        # high-priority opportunity.
        result = build_score_breakdown({"has_website": None, "contact_phone": "+44 113 000 0000"})
        assert result["priority_score"] is None


class TestConfidenceReflectsEvidence:
    def test_unmeasured_web_presence_lowers_confidence(self):
        unmeasured = build_score_breakdown({"has_website": None})
        measured = build_score_breakdown({"has_website": True, "website_score": 30})

        assert unmeasured["scores"]["confidence"] < measured["scores"]["confidence"]

    def test_confidence_no_longer_claims_ai_inference_for_provider_data(self):
        result = build_score_breakdown({"has_website": None})
        factors = " ".join(f["factor"] for f in result["breakdowns"]["confidence"]["factors"]).lower()
        assert "ai-inferred" not in factors


def _searchbox_poi(name: str, website: str | None = None, phone: str | None = None) -> dict:
    """A Search Box POI feature, shaped as the live API actually returns one."""
    metadata: dict = {}
    if website:
        metadata["website"] = website
    if phone:
        metadata["phone"] = phone
    return {
        "properties": {
            "name": name,
            "mapbox_id": "dXJuOm1ieHBvaTox",
            "feature_type": "poi",
            "full_address": f"1 Test St, Leeds, United Kingdom",
            "place_formatted": "Leeds, United Kingdom",
            "poi_category": ["café", "food"],
            "coordinates": {"longitude": -1.55, "latitude": 53.80},
            "context": {
                "country": {"name": "United Kingdom"},
                "place": {"name": "Leeds"},
                "neighborhood": {"name": "Farnley"},
            },
            "metadata": metadata,
        }
    }


class TestProviderAdapter:
    def test_no_website_on_record_is_unknown_not_absent(self):
        # MapBox not knowing a website is a signal, not proof — the business may
        # have one MapBox has never seen. Only Pass 2 may conclude absence.
        biz = _normalize_feature(_searchbox_poi("Riverside Cafe"), "United Kingdom")

        assert biz["business_name"] == "Riverside Cafe"
        assert biz["has_website"] is None, "must be unknown, never False"
        assert biz["provider_has_no_website"] is True
        assert biz["website_url"] is None
        assert biz["website_score"] is None
        assert biz["website_state"] == "unknown"
        assert biz["qualification_required"] is True

    def test_website_on_record_is_carried_through_for_pass_two(self):
        biz = _normalize_feature(
            _searchbox_poi("Jasmine Cafe", website="https://www.jasminecafe.co.uk/", phone="+441130000000"),
            "United Kingdom",
        )

        assert biz["website_url"] == "https://www.jasminecafe.co.uk/"
        assert biz["has_website"] is True
        assert biz["provider_has_no_website"] is False
        assert biz["contact_phone"] == "+441130000000"
        # Having a site says nothing about its quality until it is audited.
        assert biz["website_score"] is None
        assert biz["website_state"] == "unknown"

    def test_a_mapbox_result_scores_as_unqualified_end_to_end(self):
        scored = build_score_breakdown(
            _normalize_feature(_searchbox_poi("Northgate Plumbing"), "United Kingdom")
        )

        assert scored["priority_score"] is None
        assert scored["website_state"] == "unknown"
        assert scored["qualification_required"] is True

    def test_non_poi_features_are_not_businesses(self):
        # Free-text search returns streets. "plumber Manchester" really does
        # return "Clumber Road" and "Lumber Lane" from the live API.
        street = {"properties": {"name": "Clumber Road", "feature_type": "street"}}
        assert street["properties"]["feature_type"] != "poi"
