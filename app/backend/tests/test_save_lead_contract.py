"""Saving a lead from Discovery must accept an explicitly unknown state.

The generated entity schemas declared nullable fields as `website_score: int
= None`. In Pydantic v2 a None *default* does not make a field nullable: the
field validates as `int`, so omitting the key works but sending `null`
explicitly is rejected with 422.

Discovery sends null on purpose — an unmeasured lead has no score, and
sending 0 would fabricate a verdict. So every save from the Discover page
failed with 422 while the code looked correct from either side. Two accounts
ran twenty real searches and saved nothing.

These tests post the exact payload the frontend builds, so the schema cannot
drift away from the client again.
"""
import pytest

# Mirrors leadPayload() in app/frontend/src/pages/app/Discover.tsx. Keep in
# step with it: this is the contract between the two halves of the product.
DISCOVER_PAYLOAD = {
    "business_name": "The Allotment Vegan Eatery",
    "category": "Restaurant",
    "location": "Northern Quarter, Manchester",
    "country": "United Kingdom",
    "website_url": "",
    "website_score": None,
    "social_score": None,
    "has_website": None,
    "social_platforms": "[]",
    "contact_email": "",
    "contact_phone": "",
    "pipeline_stage": "new_lead",
    "priority": "high",
    "notes_count": 0,
    "last_contacted": "",
    "data_source": "provider",
}


async def test_a_lead_with_unknown_measurements_saves(user_a_client):
    response = await user_a_client.post("/api/v1/entities/leads", json=DISCOVER_PAYLOAD)

    assert response.status_code == 201, (
        f"Discovery's own payload was rejected: {response.text[:400]}"
    )


async def test_unknown_stays_unknown_through_the_round_trip(user_a_client):
    """Null must survive the save. Storing 0/false would invent a verdict."""
    created = await user_a_client.post("/api/v1/entities/leads", json=DISCOVER_PAYLOAD)
    assert created.status_code == 201
    body = created.json()

    assert body["website_score"] is None, "an unmeasured score came back as a number"
    assert body["social_score"] is None
    assert body["has_website"] is None, "unmeasured was recorded as 'has no website'"


async def test_a_measured_lead_still_saves_its_values(user_a_client):
    """Widening to Optional must not stop real measurements being stored."""
    measured = {**DISCOVER_PAYLOAD, "website_score": 42, "social_score": 15, "has_website": True}

    response = await user_a_client.post("/api/v1/entities/leads", json=measured)

    assert response.status_code == 201
    body = response.json()
    assert (body["website_score"], body["social_score"], body["has_website"]) == (42, 15, True)


@pytest.mark.parametrize("field", ["website_score", "social_score", "has_website"])
async def test_each_nullable_field_accepts_null_individually(user_a_client, field):
    """Pinpoints which field regressed, rather than just failing the batch."""
    payload = {**DISCOVER_PAYLOAD, "website_score": 10, "social_score": 10, "has_website": True}
    payload[field] = None

    response = await user_a_client.post("/api/v1/entities/leads", json=payload)

    assert response.status_code == 201, f"{field} rejects null: {response.text[:300]}"
    assert response.json()[field] is None


async def test_saved_leads_are_listed_back(user_a_client):
    """A save nobody can read back is not a save."""
    await user_a_client.post("/api/v1/entities/leads", json=DISCOVER_PAYLOAD)

    listed = await user_a_client.get("/api/v1/entities/leads")

    assert listed.status_code == 200
    names = [item["business_name"] for item in listed.json()["items"]]
    assert "The Allotment Vegan Eatery" in names
