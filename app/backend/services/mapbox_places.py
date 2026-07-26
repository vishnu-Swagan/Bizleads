"""MapBox Search Box adapter — Pass 1 of discovery.

Finds real businesses in a place. Returns identity, contact and a candidate
website URL where MapBox has one on record. It does NOT decide whether a
website is weak; that is Pass 2 (services/qualification.py).

Why Search Box and not geocoding:

  * The v5 geocoding endpoint this module used to call returns HTTP 200 with
    an empty feature list for POI queries. Discovery found nothing, always.
  * Free-text search matches street names. Querying "plumber Manchester"
    returns "Clumber Road", "Plummer Avenue" and "Lumber Lane" alongside real
    plumbers, because it is fuzzy text matching over places.
  * The category endpoint returns only POIs, and their `metadata` carries
    `website` and `phone` — the fields this product is built on.

On "no website": MapBox having no website on record is a useful signal, not
proof. The business may have a site MapBox does not know about. So a missing
website yields has_website=None (unknown) plus an explicit
`provider_has_no_website` flag, never has_website=False. Only Pass 2, which
actually tries to fetch a site, may conclude that one is absent.
"""
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

SEARCHBOX_URL = "https://api.mapbox.com/search/searchbox/v1"
GEOCODE_V6_URL = "https://api.mapbox.com/search/geocode/v6"
REQUEST_TIMEOUT = 25.0
MAX_LIMIT = 25

# The app's category labels mapped to MapBox canonical category IDs, verified
# against /search/searchbox/v1/list/category. Anything unmapped falls back to
# a text search filtered to POIs.
CATEGORY_MAP: Dict[str, str] = {
    "Restaurant": "restaurant",
    "Cafe": "cafe",
    "Coffee Shop": "cafe",
    "Bar & Pub": "bar",
    "Bakery": "bakery",
    "Hair Salon": "hairdresser",
    "Barbershop": "hairdresser",
    "Barber Shop": "hairdresser",
    "Beauty Spa": "spa",
    "Nail Salon": "nail_salon",
    "Dentist": "dentist",
    "Dentistry": "dentist",
    "Doctor": "doctors_office",
    "Veterinarian": "veterinarian",
    "Veterinary": "veterinarian",
    "Landscaping": "landscaping",
    "Car Wash": "car_wash",
    "Yoga Studio": "yoga_studio",
    "Dance Studio": "dance_studio",
    "Real Estate Agent": "real_estate_agent",
    "Insurance Agent": "insurance_broker",
    "Lawyer": "lawyer",
    "Legal Services": "lawyer",
    "Pet Store": "pet_store",
    "Pet Services": "pet_store",
    "Florist": "florist",
    "Dry Cleaner": "dry_cleaners",
    "Dry Cleaning": "dry_cleaners",
    "Tailor": "tailor",
    "Photography Studio": "photographer",
    "Photography": "photographer",
    "Tattoo Parlor": "tattoo_parlour",
    "Tattoo Studio": "tattoo_parlour",
    "Music School": "music_school",
    "Driving School": "driving_school",

    # Trades. MapBox has no canonical category for plumber, electrician, HVAC
    # or tyre fitter — these are rarely storefront POIs, so its taxonomy groups
    # them under home_repair. Verified to return real businesses: a Manchester
    # home_repair search returned 15, only 8 with a website on record, the
    # highest gap rate of any category tested.
    #
    # Without these, the dropdown offered ten categories that fell through to
    # fuzzy text search, matched street names, filtered them out as non-POIs,
    # and reported "no businesses found" every time.
    "Plumber": "home_repair",
    "Electrician": "home_repair",
    "HVAC": "home_repair",
    "Landscaping": "landscaping",
    "Auto Repair": "auto_repair",
    "Tire Shop": "auto_repair",
    "Gym & Fitness": "fitness_center",
    "Physiotherapy": "physiotherapist",
    "Accountant": "tax_advisor",
    "Accounting": "tax_advisor",
    "Daycare": "childcare",
    "Tutoring": "school",
    "Education": "school",
}

COUNTRY_CODES: Dict[str, str] = {
    "United States": "US", "United Kingdom": "GB", "Canada": "CA",
    "Australia": "AU", "Germany": "DE", "France": "FR", "Spain": "ES",
    "Italy": "IT", "Netherlands": "NL", "Brazil": "BR", "Mexico": "MX",
    "India": "IN", "Japan": "JP", "South Korea": "KR", "South Africa": "ZA",
    "Nigeria": "NG", "UAE": "AE", "Singapore": "SG", "Ireland": "IE",
    "New Zealand": "NZ", "Portugal": "PT", "Poland": "PL", "Sweden": "SE",
}


def _token() -> Optional[str]:
    """Read the token at call time, not import time, so .env loading and tests work."""
    return os.environ.get("MAPBOX_ACCESS_TOKEN")


def is_mapbox_configured() -> bool:
    return bool(_token())


def canonical_category(label: Optional[str]) -> Optional[str]:
    if not label:
        return None
    return CATEGORY_MAP.get(label.strip())


async def _geocode(query: str, types: str, country_code: Optional[str]) -> Optional[Dict[str, Any]]:
    """One geocoding attempt. Returns coordinates and, when present, a bbox."""
    token = _token()
    if not token or not query:
        return None

    params: Dict[str, Any] = {"q": query, "access_token": token, "limit": 1, "types": types}
    if country_code:
        params["country"] = country_code

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(f"{GEOCODE_V6_URL}/forward", params=params)
            if response.status_code != 200:
                logger.warning("MapBox geocode failed: %s", response.status_code)
                return None
            features = response.json().get("features", [])
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("MapBox geocode error: %s", type(exc).__name__)
        return None

    if not features:
        return None

    props = features[0].get("properties", {})
    coords = props.get("coordinates") or {}
    if "longitude" not in coords or "latitude" not in coords:
        return None

    result: Dict[str, Any] = {"longitude": coords["longitude"], "latitude": coords["latitude"]}
    bbox = props.get("bbox")
    # A bbox of four numbers lets a search cover a whole country rather than a
    # point. Only countries and large regions carry one.
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        result["bbox"] = list(bbox)
    return result


async def geocode_location(
    location_text: str, country: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Resolve a search area to coordinates, and a bbox when it is a country.

    Two attempts, because they fail in different ways:

      1. As a place/locality/postcode, filtered to the selected country. This
         is the normal case — "Leeds", "SW1A 1AA".
      2. As a country, unfiltered. Required when the user picks a country and
         no city: querying "United Kingdom" with types=place AND country=GB
         asks for a *town* called United Kingdom inside the UK, finds nothing,
         and returns no proximity at all. MapBox's category endpoint returns
         zero results without proximity or bbox, so every country-only search
         reported "no businesses found".

         The United States appeared to work only by accident — there is a
         place called United States in Louisiana, so attempt 1 matched it and
         searches were silently centred there.
    """
    if not location_text:
        return None

    country_code = COUNTRY_CODES.get(country) if country else None

    # When the area to search IS the country, resolve it as a country. Looking
    # it up as a place first matches whatever happens to share the name:
    # "United States" matches a region in the US Virgin Islands, whose bbox is
    # a few islands in the Caribbean, so a nationwide search returned nothing.
    if country and location_text.strip().lower() == country.strip().lower():
        return await _geocode(location_text, "country", None)

    found = await _geocode(location_text, "place,locality,postcode,district,region", country_code)
    if found:
        return found

    # Fall back to treating the text as a country name.
    return await _geocode(location_text, "country", None)


async def search_places(
    query: str = "",
    location: Optional[str] = None,
    category: Optional[str] = None,
    country: Optional[str] = None,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """Find businesses. Category search when the category is known, else text."""
    token = _token()
    if not token:
        logger.warning("MapBox token not configured")
        return []

    limit = max(1, min(limit, MAX_LIMIT))
    proximity = await geocode_location(location or country or "", country) if (location or country) else None
    canonical = canonical_category(category)

    params: Dict[str, Any] = {"access_token": token, "limit": limit}
    if country and (code := COUNTRY_CODES.get(country)):
        params["country"] = code

    if proximity:
        params["proximity"] = f"{proximity['longitude']},{proximity['latitude']}"
        # When the area resolved to a country rather than a town, search its
        # whole bounding box. A single centroid would return only businesses
        # near the geographic middle of the country — for the UK, a field in
        # Cumbria.
        if not location and proximity.get("bbox"):
            params["bbox"] = ",".join(str(v) for v in proximity["bbox"])

    keyword = (query or "").strip()

    async def _fetch(url: str, extra: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """One search request. None means the call failed; [] means no matches."""
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.get(url, params={**params, **extra})
                if response.status_code != 200:
                    logger.error(
                        "MapBox search failed: %s %s", response.status_code, response.text[:300]
                    )
                    return None
                return response.json().get("features", [])
        except httpx.HTTPError as exc:
            logger.error("MapBox search error: %s", type(exc).__name__)
            return None
        except ValueError:
            logger.error("MapBox returned malformed JSON")
            return None

    if canonical and keyword:
        # Both a category and a keyword. The category endpoint takes no query
        # parameter, so routing here would have discarded the keyword entirely:
        # "vegan" + Restaurant returned every restaurant in the city, and the
        # word the user typed changed nothing about the results.
        #
        # Forward search accepts poi_category, which applies the keyword as a
        # relevance query *within* the category — the behaviour the search box
        # has always implied.
        features = await _fetch(
            f"{SEARCHBOX_URL}/forward", {"q": keyword, "poi_category": canonical}
        )
        # A narrow keyword can legitimately match nothing. Falling back to the
        # category alone returns the broader set rather than an empty page,
        # which is more useful than "no businesses found".
        if not features:
            logger.info("Keyword %r matched nothing in %s; widening to category", keyword, canonical)
            features = await _fetch(f"{SEARCHBOX_URL}/category/{quote(canonical)}", {})
    elif canonical:
        features = await _fetch(f"{SEARCHBOX_URL}/category/{quote(canonical)}", {})
    else:
        text = " ".join(p for p in [keyword, category, location] if p) or "business"
        features = await _fetch(f"{SEARCHBOX_URL}/forward", {"q": text})

    if not features:
        return []

    results = []
    for feature in features:
        # Free-text search returns streets and addresses alongside businesses.
        if feature.get("properties", {}).get("feature_type") != "poi":
            continue
        normalised = _normalize_feature(feature, country or "")
        if normalised:
            results.append(normalised)

    logger.info("MapBox returned %d POIs (%d raw features)", len(results), len(features))
    return results[:limit]


def _normalize_feature(feature: Dict[str, Any], country: str) -> Optional[Dict[str, Any]]:
    """Map a Search Box POI into the shape scoring expects."""
    try:
        props = feature.get("properties", {})
        if not props:
            return None

        name = props.get("name") or "Unknown Business"
        metadata = props.get("metadata") or {}
        context = props.get("context") or {}

        place = (context.get("place") or {}).get("name", "")
        neighborhood = (context.get("neighborhood") or {}).get("name", "")
        resolved_country = (context.get("country") or {}).get("name", "") or country

        location = ", ".join(p for p in [neighborhood, place] if p) or props.get("place_formatted", "")

        categories = props.get("poi_category") or []
        category = categories[0].title() if categories else "Local Business"

        website = (metadata.get("website") or "").strip() or None
        phone = (metadata.get("phone") or "").strip() or None

        return {
            "business_name": name,
            "category": category,
            "location": location,
            "country": resolved_country,
            "full_address": props.get("full_address", ""),
            # A website on record means one exists. No website on record is a
            # signal, not proof — hence None, plus the explicit flag below.
            "website_url": website,
            "has_website": True if website else None,
            "provider_has_no_website": website is None,
            "website_score": None,
            "social_score": None,
            "website_state": "unknown",
            "contact_phone": phone,
            "contact_email": None,
            "mapbox_id": props.get("mapbox_id", ""),
            "coordinates": [
                (props.get("coordinates") or {}).get("longitude"),
                (props.get("coordinates") or {}).get("latitude"),
            ],
            "open_hours": bool(metadata.get("open_hours")),
            "data_source": "provider",
            "provider": "mapbox",
            "timing_signal": "",
            "qualification_required": True,
        }
    except (AttributeError, TypeError, IndexError) as exc:
        logger.error("Error normalising MapBox feature: %s", type(exc).__name__)
        return None
