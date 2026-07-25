async def test_health_endpoint_serves(anon_client):
    response = await anon_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


async def test_user_a_and_user_b_clients_resolve_independent_identities(user_a_client, user_b_client):
    # Regression test for a bug where both authenticated client fixtures shared a
    # single global app.dependency_overrides entry: whichever client fixture was
    # built second silently clobbered the first's override, so both clients ended
    # up authenticating as the same user. Requesting both fixtures in one test and
    # asserting each resolves to its own identity is what would have caught it.
    response_a = await user_a_client.get("/api/v1/auth/me")
    response_b = await user_b_client.get("/api/v1/auth/me")

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    assert response_a.json()["id"] == "user-a"
    assert response_b.json()["id"] == "user-b"
