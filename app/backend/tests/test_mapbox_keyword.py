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
