"""The follow-up queue must actually fill, and must fail safe.

The composer and the due-selector were built and tested as pure functions.
This covers the wiring between them and the database — the part that no unit
test touches and that silently does nothing if a field name is wrong.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from models.leads import Leads
from models.outreach_drafts import Outreach_drafts
from routers.automation_cron import _queue_due_followups

FINDINGS = json.dumps([
    {"id": "no_viewport", "label": "Not mobile-friendly", "penalty": 30,
     "evidence": "No viewport meta", "category": "mobile"},
    {"id": "no_https", "label": "No HTTPS", "penalty": 20,
     "evidence": "Plain HTTP", "category": "security"},
])

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


async def _seed(db, *, stage="new_lead", sent_days_ago=6, status="sent", step=1):
    lead = Leads(
        user_id="user-a", business_name="Cafe Rossi", category="Cafe",
        location="Manchester", country="United Kingdom",
        website_url="http://caferossi.co.uk", website_score=42,
        contact_email="hi@caferossi.co.uk", findings=FINDINGS,
        pipeline_stage=stage,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    db.add(Outreach_drafts(
        user_id="user-a", lead_id=lead.id, to_email="hi@caferossi.co.uk",
        subject="Cafe Rossi - your website on a phone",
        body_text="original body", based_on=json.dumps(["no_viewport"]),
        status=status, sequence_step=step,
        sent_at=NOW - timedelta(days=sent_days_ago) if status == "sent" else None,
    ))
    await db.commit()
    return lead


async def _pending(db, lead_id):
    from sqlalchemy import select
    res = await db.execute(
        select(Outreach_drafts).where(
            Outreach_drafts.lead_id == lead_id,
            Outreach_drafts.status == "pending",
        )
    )
    return list(res.scalars().all())


async def test_a_due_followup_is_queued(db_session):
    lead = await _seed(db_session, sent_days_ago=6)

    queued = await _queue_due_followups(db_session, NOW)
    await db_session.commit()

    assert queued == 1
    drafts = await _pending(db_session, lead.id)
    assert len(drafts) == 1
    assert drafts[0].sequence_step == 2
    assert drafts[0].to_email == "hi@caferossi.co.uk"
    assert drafts[0].body_text, "a follow-up with no body is worse than none"


async def test_nothing_is_queued_before_it_is_due(db_session):
    lead = await _seed(db_session, sent_days_ago=1)

    assert await _queue_due_followups(db_session, NOW) == 0
    assert await _pending(db_session, lead.id) == []


@pytest.mark.parametrize("stage", ["replied", "won", "lost", "qualified", "something_new"])
async def test_a_lead_that_moved_on_is_never_chased(db_session, stage):
    """Following up someone who already replied is the fastest way to
    look like a spammer. Unknown stages must also be excluded."""
    lead = await _seed(db_session, stage=stage, sent_days_ago=30)

    assert await _queue_due_followups(db_session, NOW) == 0
    assert await _pending(db_session, lead.id) == []


async def test_an_unsent_draft_blocks_a_new_one(db_session):
    """Never stack a second unsent draft on top of a pending one."""
    lead = await _seed(db_session, status="pending", sent_days_ago=30)

    assert await _queue_due_followups(db_session, NOW) == 0
    assert len(await _pending(db_session, lead.id)) == 1


async def test_running_twice_does_not_duplicate(db_session):
    """The hourly tick must be idempotent between sends."""
    lead = await _seed(db_session, sent_days_ago=6)

    first = await _queue_due_followups(db_session, NOW)
    await db_session.commit()
    second = await _queue_due_followups(db_session, NOW)
    await db_session.commit()

    assert (first, second) == (1, 0), "the second tick queued a duplicate"
    assert len(await _pending(db_session, lead.id)) == 1


async def test_an_empty_database_is_handled(db_session):
    assert await _queue_due_followups(db_session, NOW) == 0
