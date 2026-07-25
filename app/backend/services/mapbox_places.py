"""
MapBox Geocoding & Search API integration for business discovery.
Uses the Mapbox Search API (v1) for POI (point of interest) search.
Falls back to AI-powered discovery when access token is not configured.
"""
import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

MAPBOX_ACCESS_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN")
MAPBOX_GEOCODING_URL = "https://api.mapbox.com/geocoding/v5/mapbox.places"
MAPBOX_SEARCH_URL = "https://api.mapbox.com/search/searchbox/v1"


def is_mapbox_configured() -> bool:
    """Check if MapBox access token is available."""
    return bool(MAPBOX_ACCESS_TOKEN)


async def search_places(
    query: str,
    location: Optional[str] = None,
    category: Optional[str] = None,
    country: Optional[str] = None,
    limit: int = 15,
) -> list[dict]:
    """
    Search for businesses using MapBox Search/Geocoding API.
    Returns a list of business dicts with normalized fields.
    """
    if not MAPBOX_ACCESS_TOKEN:
        logger.warning("MapBox access token not configured, returning empty results")
        return []

    # Build the search query
    search_parts = []
    if query:
        search_parts.append(query)
    if category:
        search_parts.append(category)
    if location:
        search_parts.append(location)
    if country:
        search_parts.append(country)

    text_query = " ".join(search_parts) if search_parts else "local business"

    # Map country names to ISO 3166-1 alpha-2 codes for Mapbox
    country_codes = {
        "United States": "us", "United Kingdom": "gb", "Canada": "ca",
        "Australia": "au", "Germany": "de", "France": "fr",
        "Spain": "es", "Italy": "it", "Netherlands": "nl",
        "Brazil": "br", "Mexico": "mx", "India": "in",
        "Japan": "jp", "South Korea": "kr", "South Africa": "za",
        "Nigeria": "ng", "UAE": "ae", "Singapore": "sg",
    }

    # Use Mapbox Geocoding API with POI type filter
    params = {
        "access_token": MAPBOX_ACCESS_TOKEN,
        "types": "poi",
        "limit": min(limit, 10),  # Mapbox limit is 10 per request
        "language": "en",
    }

    # Add country filter if available
    if country:
        code = country_codes.get(country)
        if code:
            params["country"] = code

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # URL-encode the query into the path
            encoded_query = text_query.replace(" ", "%20")
            url = f"{MAPBOX_GEOCODING_URL}/{encoded_query}.json"

            response = await client.get(url, params=params)

            if response.status_code != 200:
                logger.error(f"MapBox API error: {response.status_code} - {response.text[:500]}")
                return []

            data = response.json()
            features = data.get("features", [])

            results = []
            for feature in features:
                biz = _normalize_feature(feature, country or "")
                if biz:
                    results.append(biz)

            logger.info(f"MapBox returned {len(results)} results for query: {text_query}")

            # If we need more results, do a second request with different phrasing
            if len(results) < limit and category and location:
                alt_query = f"{category} near {location}"
                encoded_alt = alt_query.replace(" ", "%20")
                alt_url = f"{MAPBOX_GEOCODING_URL}/{encoded_alt}.json"
                alt_response = await client.get(alt_url, params=params)
                if alt_response.status_code == 200:
                    alt_data = alt_response.json()
                    alt_features = alt_data.get("features", [])
                    existing_ids = {r.get("mapbox_id") for r in results}
                    for feature in alt_features:
                        biz = _normalize_feature(feature, country or "")
                        if biz and biz.get("mapbox_id") not in existing_ids:
                            results.append(biz)
                            existing_ids.add(biz.get("mapbox_id"))

            return results[:limit]

    except httpx.TimeoutException:
        logger.error("MapBox API timeout")
        return []
    except Exception as e:
        logger.error(f"MapBox API error: {e}")
        return []


async def geocode_location(location_text: str) -> Optional[dict]:
    """Geocode a location string to coordinates using MapBox."""
    if not MAPBOX_ACCESS_TOKEN:
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            encoded = location_text.replace(" ", "%20")
            url = f"{MAPBOX_GEOCODING_URL}/{encoded}.json"
            params = {
                "access_token": MAPBOX_ACCESS_TOKEN,
                "types": "place,locality,neighborhood",
                "limit": 1,
            }
            response = await client.get(url, params=params)

            if response.status_code != 200:
                return None

            data = response.json()
            features = data.get("features", [])
            if features:
                coords = features[0].get("center", [])
                return {
                    "longitude": coords[0] if len(coords) > 0 else None,
                    "latitude": coords[1] if len(coords) > 1 else None,
                    "place_name": features[0].get("place_name", ""),
                }
            return None

    except Exception as e:
        logger.error(f"MapBox geocoding error: {e}")
        return None


def _normalize_feature(feature: dict, country: str) -> Optional[dict]:
    """Normalize a MapBox feature into BizLeads business format."""
    try:
        properties = feature.get("properties", {})
        # For geocoding API v5, data is in the feature directly
        name = feature.get("text", "") or properties.get("name", "Unknown Business")
        place_name = feature.get("place_name", "")

        # Extract category from the feature
        categories = feature.get("properties", {}).get("category", "")
        if isinstance(categories, list):
            category = categories[0] if categories else "Local Business"
        elif isinstance(categories, str):
            category = categories.split(",")[0].strip() if categories else "Local Business"
        else:
            category = "Local Business"

        # Format category nicely
        category = category.replace("_", " ").title() if category else "Local Business"

        # Extract address components
        address = place_name or ""
        context = feature.get("context", [])
        city = ""
        region = ""
        for ctx in context:
            ctx_id = ctx.get("id", "")
            if ctx_id.startswith("place"):
                city = ctx.get("text", "")
            elif ctx_id.startswith("region"):
                region = ctx.get("text", "")

        short_address = f"{city}, {region}" if city else address

        # MapBox doesn't provide website/phone directly in geocoding results
        # These will be enriched by scoring or deep analysis
        return {
            "business_name": name,
            "category": category,
            "location": short_address or address,
            "country": country,
            "website_url": "",
            "website_score": 0,
            "social_score": 20,  # Default - unknown
            "has_website": False,  # Unknown from MapBox, assume no for discovery
            "contact_email": "",
            "contact_phone": "",
            "mapbox_id": feature.get("id", ""),
            "coordinates": feature.get("center", []),
            "website_state": "unknown",
            "data_source": "mapbox",
            "timing_signal": "",
            "top_opportunity": "Digital presence unknown - potential website build opportunity",
        }
    except Exception as e:
        logger.error(f"Error normalizing MapBox feature: {e}")
        return None