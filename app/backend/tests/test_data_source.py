from tests.conftest import USER_A_ID


async def test_lead_can_be_created_with_data_source(user_a_client):
    response = await user_a_client.post("/api/v1/entities/leads", json={
        "business_name": "Real Cafe", "category": "Cafe",
        "location": "Leeds", "country": "United Kingdom",
        "data_source": "provider",
    })
    assert response.status_code == 201
    assert response.json()["data_source"] == "provider"


async def test_data_source_defaults_to_null_when_absent(user_a_client):
    response = await user_a_client.post("/api/v1/entities/leads", json={
        "business_name": "Unknown Origin", "category": "Cafe",
        "location": "Leeds", "country": "United Kingdom",
    })
    assert response.status_code == 201
    assert response.json()["data_source"] is None
