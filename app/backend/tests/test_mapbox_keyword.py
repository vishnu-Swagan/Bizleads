"""The search box's keyword must reach MapBox.

The category endpoint accepts no query parameter. When a category mapped to a
canonical id, search_places routed there and dropped the user's keyword on the
floor: "vegan" + Restaurant returned every restaurant in the city, and the word
the user typed changed nothing. The box looked functional and did nothing.

These tests stub at the HTTP boundary so they assert the request actually sent
to MapBox, not just the shape of a return value.
"""
import httpx
import pytest

from services import mapbox_places


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "pk.test-token")


def _poi(name: str) -> dict:
    return {
        "properties": {
            "name": name,
            "feature_type": "poi",
            "metadata": {},
            "context": {},
            "coordinates": {"longitude": -2.24, "latitude": 53.48},
        }
    }


class _Recorder:
    """Captures every outbound request and replies with a scripted response."""

    def __init__(self, *responses):
        self.calls: list[httpx.URL] = []
        self._responses = list(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url)
        body = self._responses.pop(0) if self._responses else {"features": []}
        return httpx.Response(200, json=body)

    def install(self, monkeypatch):
        transport = httpx.MockTransport(self.handler)
        original = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        monkeypatch.setattr(mapbox_places.httpx, "AsyncClient", factory)
        return self


@pytest.mark.asyncio
async def test_keyword_and_category_filters_within_the_category(monkeypatch):
    """A keyword alongside a category must be sent, scoped by poi_category."""
    rec = _Recorder({"features": [_poi("The Allotment Vegan Eatery")]}).install(monkeypatch)

    results = await mapbox_places.search_places(query="vegan", category="Restaurant")

    search = rec.calls[-1]
    assert "/forward" in search.path, "must use forward search, which accepts a query"
    assert search.params["q"] == "vegan", "the user's keyword must reach MapBox"
    assert search.params["poi_category"] == "restaurant", "and stay scoped to the category"
    assert [r["business_name"] for r in results] == ["The Allotment Vegan Eatery"]


@pytest.mark.asyncio
async def test_category_alone_still_uses_the_category_endpoint(monkeypatch):
    """No keyword means no query — the category endpoint remains the right call."""
    rec = _Recorder({"features": [_poi("Moose")]}).install(monkeypatch)

    await mapbox_places.search_places(category="Restaurant")

    search = rec.calls[-1]
    assert "/category/restaurant" in search.path
    assert "q" not in search.params


@pytest.mark.asyncio
async def test_keyword_matching_nothing_widens_to_the_category(monkeypatch):
    """An over-narrow keyword returns the category rather than an empty page."""
    rec = _Recorder(
        {"features": []},                      # keyword matches nothing
        {"features": [_poi("Moose")]},         # widened category search
    ).install(monkeypatch)

    results = await mapbox_places.search_places(query="zzzznotathing", category="Restaurant")

    assert len(rec.calls) == 2, "must retry without the keyword"
    assert "/category/restaurant" in rec.calls[-1].path
    assert [r["business_name"] for r in results] == ["Moose"], "user sees results, not nothing"


@pytest.mark.asyncio
async def test_unmapped_category_still_falls_back_to_text_search(monkeypatch):
    """Categories with no canonical id keep using plain text search."""
    rec = _Recorder({"features": [_poi("Bob's Widgets")]}).install(monkeypatch)

    await mapbox_places.search_places(query="widgets", category="Not A Real Category")

    search = rec.calls[-1]
    assert "/forward" in search.path
    assert "widgets" in search.params["q"]
    assert "poi_category" not in search.params


@pytest.mark.asyncio
async def test_a_city_outside_the_country_list_still_searches(monkeypatch):
    """A city anywhere must work, with or without a supported country.

    The country dropdown lists only the 20 countries where the provider is
    verified to return business POIs. That is honest, but until the Discover
    page gained a city field it was also the ONLY geography control, so a user
    in Nairobi or Manila could not say where they were: their search ran with
    no proximity at all and returned businesses from anywhere on earth, which
    is useless for a local-outreach tool.

    Free-text geocoding covers far more of the world than any list we
    maintain, so the city alone must be enough.
    """
    rec = _Recorder(
        {"features": [{"properties": {"coordinates": {"longitude": 36.82, "latitude": -1.29}}}]},
        {"features": [_poi("Java House Nairobi")]},
    ).install(monkeypatch)

    results = await mapbox_places.search_places(category="Cafe", location="Nairobi")

    geocode, search = rec.calls[0], rec.calls[-1]
    assert "geocode" in str(geocode), "the city must be geocoded"
    assert "country" not in geocode.params, "no country filter — the city stands alone"
    assert search.params["proximity"] == "36.82,-1.29", "results must centre on the city"
    assert [r["business_name"] for r in results] == ["Java House Nairobi"]


@pytest.mark.asyncio
async def test_a_city_search_is_not_widened_to_the_whole_country(monkeypatch):
    """A city search must stay local.

    bbox is only correct for a country-wide search. Applying a country's bbox
    to a city search would scatter results across the nation and defeat the
    point of naming a city.
    """
    rec = _Recorder(
        {
            "features": [
                {
                    "properties": {
                        "coordinates": {"longitude": 4.83, "latitude": 45.76},
                        "bbox": [-5.2, 41.3, 9.6, 51.1],
                    }
                }
            ]
        },
        {"features": [_poi("Boulangerie Lyonnaise")]},
    ).install(monkeypatch)

    await mapbox_places.search_places(category="Bakery", location="Lyon", country="France")

    search = rec.calls[-1]
    assert "bbox" not in search.params, "a named city must not be widened to its country"
    assert search.params["proximity"] == "4.83,45.76"
