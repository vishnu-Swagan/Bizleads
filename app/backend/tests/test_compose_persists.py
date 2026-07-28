"""Composing a draft must put it in the approval queue.

Compose returned drafts to the browser and stored nothing, so the queue was
empty no matter how many times "Draft from findings" was pressed, and a page
refresh lost everything. The two halves of the feature each worked in
isolation and looked broken together — the seam, not either side.
"""
import json

from models.leads import Leads

FINDINGS = json.dumps([
    {"id": "no_viewport", "penalty": 30, "evidence": "No viewport meta"},
    {"id": "no_https", "penalty": 20, "evidence": "Plain HTTP"},
])


async def _lead(db, **over):
    values = dict(
        user_id="user-a", business_name="Cafe Rossi", category="Cafe",
        location="Manchester", country="UK", website_url="http://caferossi.co.uk",
        website_score=42, contact_email="hi@caferossi.co.uk",
        findings=FINDINGS, pipeline_stage="new_lead",
    )
    values.update(over)
    lead = Leads(**values)
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


async def test_a_composed_draft_appears_in_the_queue(user_a_client, db_session):
    lead = await _lead(db_session)

    composed = await user_a_client.post("/api/v1/outreach/compose", json={"lead_ids": [lead.id]})
    assert composed.status_code == 200
    assert composed.json()["queued"] == 1

    queue = await user_a_client.get("/api/v1/outreach/queue")
    items = queue.json()["items"]

    assert len(items) == 1, "composing left the queue empty"
    assert items[0]["business_name"] == "Cafe Rossi"
    assert items[0]["to_email"] == "hi@caferossi.co.uk"


async def test_the_response_carries_the_queue_id(user_a_client, db_session):
    """Without it the UI cannot edit or send the row it just created."""
    lead = await _lead(db_session)

    composed = await user_a_client.post("/api/v1/outreach/compose", json={"lead_ids": [lead.id]})

    draft = composed.json()["drafts"][0]
    assert isinstance(draft.get("id"), int)

    sent = await user_a_client.post(f"/api/v1/outreach/queue/{draft['id']}/discard")
    assert sent.status_code in (200, 204), "the returned id does not address a real row"


async def test_recomposing_replaces_rather_than_stacks(user_a_client, db_session):
    """Two pending emails to one prospect is the failure nobody notices
    until both have been sent."""
    lead = await _lead(db_session)

    await user_a_client.post("/api/v1/outreach/compose", json={"lead_ids": [lead.id]})
    await user_a_client.post("/api/v1/outreach/compose", json={"lead_ids": [lead.id]})

    queue = await user_a_client.get("/api/v1/outreach/queue")
    assert len(queue.json()["items"]) == 1


async def test_a_lead_with_nothing_measurable_queues_nothing(user_a_client, db_session):
    """A clean site gives no honest reason to write, so nothing is queued."""
    lead = await _lead(db_session, findings="[]")

    composed = await user_a_client.post("/api/v1/outreach/compose", json={"lead_ids": [lead.id]})

    assert composed.json()["queued"] == 0
    queue = await user_a_client.get("/api/v1/outreach/queue")
    assert queue.json()["items"] == []


async def test_one_users_compose_does_not_reach_another_queue(
    user_a_client, user_b_client, db_session
):
    lead = await _lead(db_session)

    await user_a_client.post("/api/v1/outreach/compose", json={"lead_ids": [lead.id]})

    other = await user_b_client.get("/api/v1/outreach/queue")
    assert other.json()["items"] == []
