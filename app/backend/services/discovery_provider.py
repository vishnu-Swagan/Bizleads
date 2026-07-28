"""Select the live business-discovery provider.

Google Places is the primary source when configured. MapBox stays available
as a fallback so a missing result or temporary Google failure does not make
discovery unusable.
"""
import logging
from typing import Optional

from services import google_places, mapbox_places

logger = logging.getLogger(__name__)

# Places Text Search (New) returns at most 20 results per request.
MAX_LIMIT = 20


def is_google_places_configured() -> bool:
    return google_places.is_google_places_configured()


def is_mapbox_configured() -> bool:
    return mapbox_places.is_mapbox_configured()


def is_discovery_configured() -> bool:
    return is_google_places_configured() or is_mapbox_configured()


def active_provider_slug() -> Optional[str]:
    if is_google_places_configured():
        return "google_places"
    if is_mapbox_configured():
        return "mapbox"
    return None


def configured_provider_names() -> list[str]:
    providers = []
    if is_google_places_configured():
        providers.append("Google Places")
    if is_mapbox_configured():
        providers.append("MapBox Places (fallback)" if providers else "MapBox Places")
    return providers


def provider_for_results(results: list[dict]) -> Optional[str]:
    """Return the provider that produced a result set."""
    if results:
        source = results[0].get("provider") or results[0].get("data_source")
        if source in {"google_places", "mapbox"}:
            return source
    return active_provider_slug()


async def search_places(
    query: str = "",
    location: Optional[str] = None,
    category: Optional[str] = None,
    country: Optional[str] = None,
    limit: int = MAX_LIMIT,
) -> list[dict]:
    """Search Google first, then MapBox when Google has no usable results."""
    limit = max(1, min(limit, MAX_LIMIT))

    if is_google_places_configured():
        try:
            results = await google_places.search_places(
                query=query,
                location=location,
                category=category,
                country=country,
                limit=limit,
            )
        except Exception:  # noqa: BLE001 - a provider outage must reach the fallback
            logger.exception("Google Places search failed; trying MapBox fallback")
        else:
            if results:
                return results
            logger.info("Google Places returned no usable results; trying MapBox fallback")

    if is_mapbox_configured():
        return await mapbox_places.search_places(
            query=query,
            location=location,
            category=category,
            country=country,
            limit=limit,
        )

    return []
