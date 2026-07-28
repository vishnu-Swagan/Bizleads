import pytest

from services import discovery_provider, google_places


def test_google_places_configuration_reads_environment_at_call_time(monkeypatch):
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    assert google_places.is_google_places_configured() is False

    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    assert google_places.is_google_places_configured() is True


async def test_google_places_is_primary_when_both_providers_are_configured(monkeypatch):
    calls = []

    monkeypatch.setattr(discovery_provider.google_places, "is_google_places_configured", lambda: True)
    monkeypatch.setattr(discovery_provider.mapbox_places, "is_mapbox_configured", lambda: True)

    async def google_search(**kwargs):
        calls.append("google")
        return [{"business_name": "Google result", "data_source": "google_places"}]

    async def mapbox_search(**kwargs):
        calls.append("mapbox")
        return [{"business_name": "MapBox result", "provider": "mapbox"}]

    monkeypatch.setattr(discovery_provider.google_places, "search_places", google_search)
    monkeypatch.setattr(discovery_provider.mapbox_places, "search_places", mapbox_search)

    results = await discovery_provider.search_places(query="cafe", limit=25)

    assert results[0]["business_name"] == "Google result"
    assert calls == ["google"]


@pytest.mark.parametrize("google_outcome", ["empty", "error"])
async def test_mapbox_fallback_handles_empty_results_and_google_failures(monkeypatch, google_outcome):
    calls = []

    monkeypatch.setattr(discovery_provider.google_places, "is_google_places_configured", lambda: True)
    monkeypatch.setattr(discovery_provider.mapbox_places, "is_mapbox_configured", lambda: True)

    async def google_search(**kwargs):
        calls.append("google")
        if google_outcome == "error":
            raise RuntimeError("temporary Google failure")
        return []

    async def mapbox_search(**kwargs):
        calls.append("mapbox")
        assert kwargs["limit"] == discovery_provider.MAX_LIMIT
        return [{"business_name": "MapBox result", "provider": "mapbox"}]

    monkeypatch.setattr(discovery_provider.google_places, "search_places", google_search)
    monkeypatch.setattr(discovery_provider.mapbox_places, "search_places", mapbox_search)

    results = await discovery_provider.search_places(query="cafe", limit=25)

    assert results[0]["business_name"] == "MapBox result"
    assert calls == ["google", "mapbox"]


def test_configured_provider_names_make_fallback_role_explicit(monkeypatch):
    monkeypatch.setattr(discovery_provider.google_places, "is_google_places_configured", lambda: True)
    monkeypatch.setattr(discovery_provider.mapbox_places, "is_mapbox_configured", lambda: True)

    assert discovery_provider.configured_provider_names() == [
        "Google Places",
        "MapBox Places (fallback)",
    ]
