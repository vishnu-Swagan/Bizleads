async def test_health_endpoint_serves(anon_client):
    response = await anon_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
