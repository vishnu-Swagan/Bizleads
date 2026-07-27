"""Outreach must be provable, or it must not be sent.

The product's claim is that it finds businesses whose sites are costing them
customers AND can prove it. The proof is the findings. So the composer's
contract is narrow and absolute: every claim about a prospect's site traces
to a measurement, and where there is no measurement there is no email.

That second half is the part worth testing hardest. A composer that emits a
cheerful generic email for an unqualified lead would be indistinguishable
from every spam tool on the market, and would burn the sender's domain.
"""
import json

import pytest

from services.outreach_composer import compose, compose_many, parse_findings

MOBILE = {"id": "no_viewport", "penalty": 30, "evidence": "No <meta name='viewport'>"}
INSECURE = {"id": "no_https", "penalty": 20, "evidence": "Served over plain HTTP"}
SLOW = {"id": "very_slow", "penalty": 15, "evidence": "Took 4.2s to respond"}
NO_TEL = {"id": "no_tel_link", "penalty": 5, "evidence": "No tel: link"}


def lead(**over):
    base = {
        "id": 1,
        "business_name": "Cafe Rossi",
        "website_url": "http://caferossi.co.uk",
        "website_score": 42,
        "contact_email": "hi@caferossi.co.uk",
        "findings": json.dumps([MOBILE, INSECURE]),
    }
    base.update(over)
    return base


class TestNothingIsInvented:
    def test_an_unqualified_lead_produces_no_email(self):
        """NULL findings means nobody has looked. There is nothing to say."""
        assert compose(lead(findings=None)) is None

    def test_a_clean_site_produces_no_email(self):
        """Measured and found nothing wrong — no honest pitch exists."""
        assert compose(lead(findings="[]")) is None

    def test_an_unrecognised_finding_is_dropped_not_guessed(self):
        """Inventing prose for an id we do not know is fabrication."""
        assert compose(lead(findings=json.dumps([{"id": "brand_new", "penalty": 99}]))) is None

    def test_only_measured_defects_appear_in_the_body(self):
        draft = compose(lead(findings=json.dumps([MOBILE])))

        assert "mobile-friendly" in draft["body_text"]
        # Never mentioned, because it was never measured.
        assert "Not secure" not in draft["body_text"]
        assert "slow" not in draft["body_text"].lower()

    def test_the_score_is_omitted_when_unmeasured(self):
        draft = compose(lead(website_score=None))

        assert "out of 100" not in draft["body_text"]

    def test_the_stated_issue_count_matches_what_is_listed(self):
        """Saying '4 issues above' under a list of 3 is a trust-killer."""
        draft = compose(lead(findings=json.dumps([MOBILE, INSECURE, SLOW, NO_TEL])))
        body = draft["body_text"]

        listed = body.count("\n- ")
        assert f"including the {listed} issue" in body


class TestTheEmailIsUsable:
    def test_the_subject_names_the_worst_defect(self):
        draft = compose(lead(findings=json.dumps([NO_TEL, MOBILE])))

        assert "phone" in draft["subject"].lower()
        assert "Cafe Rossi" in draft["subject"]

    def test_findings_are_ordered_by_severity(self):
        draft = compose(lead(findings=json.dumps([NO_TEL, MOBILE, INSECURE])))
        body = draft["body_text"]

        assert body.index("mobile-friendly") < body.index("Not secure") < body.index("tappable")

    def test_no_more_than_three_points_are_made(self):
        draft = compose(lead(findings=json.dumps([MOBILE, INSECURE, SLOW, NO_TEL])))

        assert draft["body_text"].count("\n- ") == 3
        assert "1 other issue" in draft["body_text"]

    def test_the_greeting_does_not_read_as_a_mail_merge(self):
        draft = compose(lead())

        assert "Hi Cafe Rossi," not in draft["body_text"]

    def test_the_sender_signs_the_email(self):
        draft = compose(lead(), sender_name="Vishnu", sender_business="Torque Trends")

        assert "Vishnu" in draft["body_text"]
        assert "Torque Trends" in draft["body_text"]

    def test_the_html_carries_no_tracker_or_image(self):
        """A tracking pixel is what turns cold email into filtered email."""
        html = compose(lead())["body_html"]

        assert "<img" not in html
        assert "http://" not in html.replace("http://caferossi", "")

    def test_the_body_never_renders_raw_html(self):
        """Findings copy is ours, but the escaper must still hold."""
        html = compose(lead())["body_html"]

        assert "<script" not in html.lower()

    def test_a_business_name_cannot_inject_an_email_header(self):
        """Names come from a third-party listing provider, so they are untrusted.

        CR/LF in a subject is how an attacker appends "Bcc:" and turns one
        customer's outreach into a relay.
        """
        draft = compose(lead(business_name="Cafe\r\nBcc: victim@example.com"))

        assert "\r" not in draft["subject"] and "\n" not in draft["subject"]
        assert "Bcc:" not in draft["subject"].replace("Bcc: victim", "")

    def test_the_draft_reports_which_findings_it_used(self):
        draft = compose(lead(findings=json.dumps([MOBILE, INSECURE])))

        assert json.loads(draft["based_on"]) == ["no_viewport", "no_https"]


class TestBatch:
    def test_skips_are_explained_not_silent(self):
        result = compose_many([
            lead(id=1),
            lead(id=2, contact_email=""),
            lead(id=3, findings=None),
            lead(id=4, findings="[]"),
        ])

        assert result["composed"] == 1
        assert result["total"] == 4
        reasons = {s["lead_id"]: s["reason"] for s in result["skipped"]}
        assert reasons == {2: "no_email", 3: "not_qualified", 4: "nothing_to_report"}

    def test_one_corrupt_row_does_not_fail_the_batch(self):
        result = compose_many([lead(id=1), lead(id=2, findings="{not json")])

        assert result["composed"] == 1
        assert result["skipped"][0]["lead_id"] == 2


@pytest.mark.parametrize("raw,expected", [
    (None, 0), ("", 0), ("[]", 0), ("not json", 0), ({"id": "x"}, 0),
    (json.dumps([MOBILE]), 1), ([MOBILE, INSECURE], 2),
    (json.dumps([{"no_id": True}]), 0),
])
def test_parse_findings_never_raises(raw, expected):
    assert len(parse_findings(raw)) == expected
