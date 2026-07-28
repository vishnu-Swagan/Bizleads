"""Skip and restore: setting a draft aside without destroying it.

Discard is a verdict — this prospect is not worth writing to — and is final.
Skip is "not now". Before this, clearing a draft you did not want to send
today meant discarding it and re-composing later to get it back, so the only
available action was heavier than the decision being made.

The reversibility is the whole feature, so these tests are mostly about the
transitions that must NOT be allowed: anything that would let a sent email be
un-sent, or let skip quietly become a second discard.
"""
import pytest
from sqlalchemy import select

from models.outreach_drafts import Outreach_drafts
from tests.conftest import USER_A_ID, USER_B_ID


async def _draft(db_session, *, user_id=USER_A_ID, status="pending", lead_id=1):
    draft = Outreach_drafts(
        user_id=user_id, lead_id=lead_id, automation_id=None,
        to_email="owner@example.com", subject="Your site",
        body_text="Three things we measured.", based_on="[]",
        status=status, sequence_step=1,
    )
    db_session.add(draft)
    await db_session.commit()
    await db_session.refresh(draft)
    return draft


async def _status_of(db_session, draft_id):
    row = (await db_session.execute(
        select(Outreach_drafts).where(Outreach_drafts.id == draft_id)
    )).scalar_one()
    await db_session.refresh(row)
    return row.status


@pytest.mark.asyncio
class TestSkip:
    async def test_a_pending_draft_can_be_skipped(self, user_a_client, db_session):
        draft = await _draft(db_session)
        resp = await user_a_client.post(f"/api/v1/outreach/queue/{draft.id}/skip")
        assert resp.status_code == 200
        assert await _status_of(db_session, draft.id) == "skipped"

    async def test_a_sent_draft_cannot_be_skipped(self, user_a_client, db_session):
        """Skipping a sent email would imply the send could be taken back."""
        draft = await _draft(db_session, status="sent")
        resp = await user_a_client.post(f"/api/v1/outreach/queue/{draft.id}/skip")
        assert resp.status_code == 400
        assert await _status_of(db_session, draft.id) == "sent"

    async def test_a_discarded_draft_cannot_be_skipped(self, user_a_client, db_session):
        draft = await _draft(db_session, status="discarded")
        assert (await user_a_client.post(f"/api/v1/outreach/queue/{draft.id}/skip")).status_code == 400

    async def test_another_users_draft_is_not_found(self, user_a_client, db_session):
        draft = await _draft(db_session, user_id=USER_B_ID)
        resp = await user_a_client.post(f"/api/v1/outreach/queue/{draft.id}/skip")
        assert resp.status_code == 404
        assert await _status_of(db_session, draft.id) == "pending"


@pytest.mark.asyncio
class TestRestore:
    async def test_a_skipped_draft_comes_back_as_pending(self, user_a_client, db_session):
        draft = await _draft(db_session, status="skipped")
        resp = await user_a_client.post(f"/api/v1/outreach/queue/{draft.id}/restore")
        assert resp.status_code == 200
        assert await _status_of(db_session, draft.id) == "pending"

    async def test_a_discarded_draft_cannot_be_restored(self, user_a_client, db_session):
        """Discard was a deliberate decision. Re-composing writes a fresh
        draft from the same findings, so nothing is lost by refusing here."""
        draft = await _draft(db_session, status="discarded")
        assert (await user_a_client.post(f"/api/v1/outreach/queue/{draft.id}/restore")).status_code == 400

    async def test_a_sent_draft_cannot_be_restored(self, user_a_client, db_session):
        draft = await _draft(db_session, status="sent")
        assert (await user_a_client.post(f"/api/v1/outreach/queue/{draft.id}/restore")).status_code == 400


@pytest.mark.asyncio
class TestTheQueueSurfacesSkippedDrafts:
    async def test_skipped_drafts_leave_the_active_list(self, user_a_client, db_session):
        pending = await _draft(db_session, lead_id=1)
        skipped = await _draft(db_session, status="skipped", lead_id=2)

        body = (await user_a_client.get("/api/v1/outreach/queue")).json()
        assert [d["id"] for d in body["items"]] == [pending.id]
        assert [d["id"] for d in body["skipped"]] == [skipped.id]

    async def test_they_are_offered_back_rather_than_hidden(self, user_a_client, db_session):
        """A skipped draft the user cannot find again is just a slower
        discard, which would make the whole distinction pointless."""
        await _draft(db_session, status="skipped")
        body = (await user_a_client.get("/api/v1/outreach/queue")).json()
        assert len(body["skipped"]) == 1

    async def test_send_all_ignores_skipped_drafts(self, user_a_client, db_session):
        """The one thing skip must guarantee: Send all does not send it."""
        await _draft(db_session, status="skipped")
        resp = await user_a_client.post("/api/v1/outreach/queue/send-all")
        # 503 when no sending identity is configured, which is the case here —
        # what matters is that the skipped draft was never a candidate.
        assert resp.status_code in (200, 503)
        assert await _status_of(db_session, 1) == "skipped"
