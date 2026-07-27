"""A follow-up sent to the wrong lead is worse than no follow-up at all.

There is no inbox reading in this product, so `pipeline_stage` is the only
honest signal that a human has taken a conversation over from the tool. This
module's contract is almost entirely made of "do not send" rules; the tests
below lean hardest on those, because a false positive here (following up on
someone who already replied) is what gets a customer's domain blocked.

`compose_followup` and `select_due_followups` are both pure - no DB, no
network - so every test constructs plain dicts by hand.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from services.outreach_followup import (
    FOLLOWUP_STEPS,
    MAX_FOLLOWUP_STEP,
    SAFE_TO_FOLLOW_UP,
    compose_followup,
    select_due_followups,
)

MOBILE = {"id": "no_viewport", "penalty": 30, "evidence": "No <meta name='viewport'>"}
INSECURE = {"id": "no_https", "penalty": 20, "evidence": "Served over plain HTTP"}
SLOW = {"id": "very_slow", "penalty": 15, "evidence": "Took 4.2s to respond"}


def lead(**over):
    base = {
        "id": 1,
        "business_name": "Cafe Rossi",
        "website_url": "http://caferossi.co.uk",
        "contact_email": "hi@caferossi.co.uk",
        "pipeline_stage": "contacted",
        "findings": json.dumps([MOBILE, INSECURE]),
    }
    base.update(over)
    return base


def previous_draft(**over):
    base = {
        "subject": "Cafe Rossi - your website on a phone",
        "body_text": "Hi there,\n\nI had a look...",
        "based_on": json.dumps(["no_viewport"]),
        "status": "sent",
        "sequence_step": 1,
        "sent_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    base.update(over)
    return base


class TestComposeFollowup:
    def test_step_2_references_the_worst_finding_again(self):
        draft = compose_followup(lead(), previous_draft(), 2)

        assert draft is not None
        assert "mobile-friendly" in draft["body_text"]

    def test_step_2_does_not_restate_the_whole_original(self):
        """A follow-up that repeats the first email is spam, not persistence."""
        draft = compose_followup(lead(), previous_draft(), 2)

        # The second finding from the original is not re-pitched.
        assert "Not secure" not in draft["body_text"]
        assert len(draft["body_text"]) < 600

    def test_step_2_offers_something_concrete(self):
        draft = compose_followup(lead(), previous_draft(), 2)

        assert "full list" in draft["body_text"]

    def test_step_3_is_the_shortest(self):
        step2 = compose_followup(lead(), previous_draft(), 2)
        step3 = compose_followup(lead(), previous_draft(sequence_step=2), 3)

        assert len(step3["body_text"]) < len(step2["body_text"])

    def test_step_3_says_it_is_the_last_message(self):
        draft = compose_followup(lead(), previous_draft(sequence_step=2), 3)

        assert "won't follow up again" in draft["body_text"]

    def test_step_3_is_easy_to_decline(self):
        draft = compose_followup(lead(), previous_draft(sequence_step=2), 3)

        assert "ignore" in draft["body_text"].lower()
        assert "!" not in draft["body_text"]

    def test_subject_threads_with_the_original(self):
        draft = compose_followup(lead(), previous_draft(subject="Cafe Rossi - a note"), 2)

        assert draft["subject"] == "Re: Cafe Rossi - a note"

    def test_missing_original_subject_falls_back_gracefully(self):
        draft = compose_followup(lead(), previous_draft(subject=""), 2)

        assert draft["subject"]
        assert not draft["subject"].startswith("Re: ")

    def test_no_findings_means_no_followup(self):
        """Fail safe: nothing measured, nothing to reference, no email."""
        assert compose_followup(lead(findings=None), previous_draft(), 2) is None
        assert compose_followup(lead(findings="[]"), previous_draft(), 2) is None

    def test_unrecognised_finding_is_not_invented_a_description(self):
        draft_lead = lead(findings=json.dumps([{"id": "brand_new", "penalty": 99}]))
        assert compose_followup(draft_lead, previous_draft(), 2) is None

    def test_step_1_and_step_4_are_refused(self):
        """Step 1 is the original email's job; step 4 does not exist."""
        assert compose_followup(lead(), previous_draft(), 1) is None
        assert compose_followup(lead(), previous_draft(), 4) is None

    def test_every_claim_traces_to_a_measurement(self):
        """No invented urgency, no generic bump-to-the-top filler."""
        draft = compose_followup(lead(), previous_draft(), 2)
        forbidden = ["top of your inbox", "limited time", "act now", "just checking in"]

        lowered = draft["body_text"].lower()
        for phrase in forbidden:
            assert phrase not in lowered

    def test_based_on_reports_the_finding_used(self):
        draft = compose_followup(lead(), previous_draft(), 2)

        assert json.loads(draft["based_on"]) == ["no_viewport"]

    def test_handles_a_missing_previous_gracefully(self):
        """previous is documented as a dict, but a caller passing {} must not crash."""
        draft = compose_followup(lead(), {}, 2)

        assert draft is not None
        assert not draft["subject"].startswith("Re: ")

    def test_body_html_has_no_raw_findings_markup(self):
        draft = compose_followup(lead(), previous_draft(), 2)

        assert "<script" not in draft["body_html"].lower()


class TestFollowupSteps:
    def test_step_2_is_four_days_after_previous_send(self):
        assert FOLLOWUP_STEPS[2] == 4

    def test_step_3_is_nine_days_after_previous_send(self):
        assert FOLLOWUP_STEPS[3] == 9

    def test_there_is_no_step_beyond_three(self):
        assert MAX_FOLLOWUP_STEP == 3
        assert 4 not in FOLLOWUP_STEPS


NOW = datetime(2026, 1, 20, tzinfo=timezone.utc)


def item(drafts, stage="contacted", **lead_over):
    return {"lead": lead(pipeline_stage=stage, **lead_over), "drafts": drafts}


class TestSelectDueFollowups:
    def test_a_lead_with_no_drafts_is_never_due(self):
        due = select_due_followups([{"lead": lead(), "drafts": []}], now=NOW)
        assert due == []

    def test_first_followup_is_due_after_four_days(self):
        sent_4_days_ago = NOW - timedelta(days=4)
        due = select_due_followups(
            [item([previous_draft(sequence_step=1, sent_at=sent_4_days_ago)])], now=NOW,
        )

        assert len(due) == 1
        assert due[0]["step"] == 2

    def test_first_followup_is_not_due_before_four_days(self):
        sent_3_days_ago = NOW - timedelta(days=3, hours=23)
        due = select_due_followups(
            [item([previous_draft(sequence_step=1, sent_at=sent_3_days_ago)])], now=NOW,
        )

        assert due == []

    def test_second_followup_is_due_after_nine_days(self):
        sent_9_days_ago = NOW - timedelta(days=9)
        due = select_due_followups(
            [item([
                previous_draft(sequence_step=1, sent_at=NOW - timedelta(days=20)),
                previous_draft(sequence_step=2, sent_at=sent_9_days_ago),
            ])],
            now=NOW,
        )

        assert len(due) == 1
        assert due[0]["step"] == 3

    def test_second_followup_is_not_due_before_nine_days(self):
        sent_8_days_ago = NOW - timedelta(days=8)
        due = select_due_followups(
            [item([
                previous_draft(sequence_step=1, sent_at=NOW - timedelta(days=20)),
                previous_draft(sequence_step=2, sent_at=sent_8_days_ago),
            ])],
            now=NOW,
        )

        assert due == []

    def test_never_goes_past_step_three(self):
        """A fourth touch is harassment, not persistence - hard stop."""
        sent_long_ago = NOW - timedelta(days=100)
        due = select_due_followups(
            [item([
                previous_draft(sequence_step=1, sent_at=NOW - timedelta(days=200)),
                previous_draft(sequence_step=2, sent_at=NOW - timedelta(days=100)),
                previous_draft(sequence_step=3, sent_at=sent_long_ago),
            ])],
            now=NOW,
        )

        assert due == []

    @pytest.mark.parametrize("stage", ["replied", "qualified", "won", "lost"])
    def test_a_human_touched_stage_is_never_followed_up(self, stage):
        """The core fail-safe rule: pipeline_stage past the early stages means stop."""
        due = select_due_followups(
            [item([previous_draft(sequence_step=1, sent_at=NOW - timedelta(days=30))], stage=stage)],
            now=NOW,
        )

        assert due == []

    def test_an_unknown_pipeline_stage_is_treated_as_unsafe(self):
        """Fail safe on values this module has never seen, not fail open."""
        due = select_due_followups(
            [item(
                [previous_draft(sequence_step=1, sent_at=NOW - timedelta(days=30))],
                stage="some_future_stage_nobody_told_us_about",
            )],
            now=NOW,
        )

        assert due == []

    def test_a_missing_pipeline_stage_is_treated_as_unsafe(self):
        due = select_due_followups(
            [item([previous_draft(sequence_step=1, sent_at=NOW - timedelta(days=30))], stage=None)],
            now=NOW,
        )

        assert due == []

    def test_new_lead_stage_is_safe(self):
        due = select_due_followups(
            [item([previous_draft(sequence_step=1, sent_at=NOW - timedelta(days=30))], stage="new_lead")],
            now=NOW,
        )

        assert len(due) == 1

    def test_safe_stages_are_exactly_new_lead_and_contacted(self):
        assert SAFE_TO_FOLLOW_UP == {"new_lead", "contacted"}

    def test_a_pending_latest_draft_is_never_due(self):
        """The most recent draft must be sent - a drafted-but-unsent email is not a signal to escalate."""
        due = select_due_followups(
            [item([previous_draft(sequence_step=1, status="pending", sent_at=None)])],
            now=NOW,
        )

        assert due == []

    def test_a_failed_latest_draft_is_never_due(self):
        due = select_due_followups(
            [item([previous_draft(sequence_step=1, status="failed", sent_at=None)])],
            now=NOW,
        )

        assert due == []

    def test_a_discarded_latest_draft_is_never_due(self):
        due = select_due_followups(
            [item([previous_draft(sequence_step=1, status="discarded")])],
            now=NOW,
        )

        assert due == []

    def test_a_sent_draft_with_no_sent_at_is_never_due(self):
        """Defensive: status says sent but the timestamp is missing - cannot tell, so don't act."""
        due = select_due_followups(
            [item([previous_draft(sequence_step=1, status="sent", sent_at=None)])],
            now=NOW,
        )

        assert due == []

    def test_never_stacks_a_new_draft_on_an_unsent_one(self):
        """Rule: skip if ANY prior draft for the lead is still pending, even if the latest is sent."""
        due = select_due_followups(
            [item([
                previous_draft(sequence_step=1, status="pending", sent_at=None),
                previous_draft(sequence_step=1, status="sent", sent_at=NOW - timedelta(days=30)),
            ])],
            now=NOW,
        )

        assert due == []

    def test_naive_sent_at_is_treated_as_utc_and_does_not_crash(self):
        naive_9_days_ago = (NOW - timedelta(days=9)).replace(tzinfo=None)
        due = select_due_followups(
            [item([previous_draft(sequence_step=1, sent_at=naive_9_days_ago)])], now=NOW,
        )

        assert len(due) == 1
        assert due[0]["step"] == 2

    def test_naive_now_does_not_crash(self):
        naive_now = NOW.replace(tzinfo=None)
        due = select_due_followups(
            [item([previous_draft(sequence_step=1, sent_at=NOW - timedelta(days=5))])],
            now=naive_now,
        )

        assert len(due) == 1

    def test_iso_string_sent_at_is_accepted(self):
        sent_at = (NOW - timedelta(days=5)).isoformat()
        due = select_due_followups(
            [item([previous_draft(sequence_step=1, sent_at=sent_at)])], now=NOW,
        )

        assert len(due) == 1

    def test_unparseable_sent_at_does_not_crash_and_is_skipped(self):
        due = select_due_followups(
            [item([previous_draft(sequence_step=1, sent_at="not-a-date")])], now=NOW,
        )

        assert due == []

    def test_previous_returned_is_the_actual_prior_draft(self):
        prior = previous_draft(sequence_step=1, sent_at=NOW - timedelta(days=5))
        due = select_due_followups([item([prior])], now=NOW)

        assert due[0]["previous"] is prior

    def test_multiple_leads_are_evaluated_independently(self):
        due_item = item([previous_draft(sequence_step=1, sent_at=NOW - timedelta(days=5))],
                         stage="new_lead", id=1)
        not_due_item = item([previous_draft(sequence_step=1, sent_at=NOW - timedelta(days=1))],
                             stage="new_lead", id=2)
        blocked_item = item([previous_draft(sequence_step=1, sent_at=NOW - timedelta(days=30))],
                             stage="replied", id=3)

        due = select_due_followups([due_item, not_due_item, blocked_item], now=NOW)

        assert len(due) == 1
        assert due[0]["lead"]["id"] == 1

    def test_empty_input_returns_empty_list(self):
        assert select_due_followups([], now=NOW) == []
