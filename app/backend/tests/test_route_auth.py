import pytest

ALL_ROUTES = [
    "/api/v1/entities/leads/all",
    "/api/v1/entities/lead_notes/all",
    "/api/v1/entities/ai_interaction_logs/all",
    "/api/v1/entities/workspaces/all",
    "/api/v1/entities/workspace_members/all",
    "/api/v1/entities/credit_ledger/all",
    "/api/v1/entities/provider_connections/all",
    "/api/v1/entities/offer_profiles/all",
    "/api/v1/entities/search_jobs/all",
]


@pytest.mark.parametrize("path", ALL_ROUTES)
async def test_all_routes_are_deleted(anon_client, path):
    # The deleted "/all" handler used to be the exact match for this path. With
    # it gone, the request falls through to the "/{id}" route registered right
    # after it in the same router - "all" has the same path *shape* as an id,
    # so FastAPI still routes it there rather than 404ing. What that route does
    # with it next depends on that route's own auth:
    #   - leads / lead_notes / ai_interaction_logs: "/{id}" requires auth, so
    #     the auth dependency rejects first -> 401.
    #   - the other six: "/{id}" is unauthenticated (a separate defect, out of
    #     scope for this task) -> path validation rejects "all" as a bad int
    #     id -> 422.
    # Neither status code returns another tenant's rows, which is the property
    # this task is responsible for, so we assert that instead of a literal 404.
    response = await anon_client.get(path)
    assert response.status_code != 200, f"{path} still returns data unauthenticated"
    assert response.status_code in (401, 422), (
        f"{path} returned unexpected status {response.status_code}"
    )


AIHUB_ROUTES = [
    "/api/v1/aihub/gentxt",
    "/api/v1/aihub/genimg",
    "/api/v1/aihub/genvideo",
    "/api/v1/aihub/genaudio",
    "/api/v1/aihub/transcribe",
    "/api/v1/aihub/analyzepdf",
]


@pytest.mark.parametrize("path", AIHUB_ROUTES)
async def test_aihub_requires_authentication(anon_client, path):
    response = await anon_client.post(path, json={})
    assert response.status_code == 401, f"{path} is callable anonymously"


FABRICATION_ROUTES = [
    "/api/v1/search/businesses",
    "/api/v1/automation/generate-leads",
]


@pytest.mark.parametrize("path", FABRICATION_ROUTES)
async def test_fabrication_routes_are_deleted(user_a_client, path):
    # Unlike the ALL_ROUTES case above, this really is a plain 404: both
    # "/businesses" and "/generate-leads" are literal path segments, not
    # "/{id}"-shaped, so there is no sibling route left in search.py or
    # automation.py for FastAPI to fall through to. Verified empirically
    # (not assumed) before writing this assertion.
    response = await user_a_client.post(path, json={})
    assert response.status_code == 404, f"{path} still generates fabricated businesses"
