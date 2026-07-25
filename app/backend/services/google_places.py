"""
Google Places API integration for real business discovery.
Uses the Places API (New) for text search and place details.
Falls back to AI-powered discovery when API key is not configured.
"""
import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")
PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAILS_URL = "https://places.googleapis.com/v1/places"


def is_google_places_configured() -> bool:
    """Check if Google Places API key is available."""
    return bool(GOOGLE_PLACES_API_KEY)


async def search_places(
    query: str,
    location: Optional[str] = None,
    category: Optional[str] = None,
    country: Optional[str] = None,
    limit: int = 15,
) -> list[dict]:
    """
    Search for businesses using Google Places API (New).
    Returns a list of business dicts with normalized fields.
    """
    if not GOOGLE_PLACES_API_KEY:
        logger.warning("Google Places API key not configured, returning empty results")
        return []

    # Build the text query
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

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.types,places.websiteUri,places.nationalPhoneNumber,"
            "places.internationalPhoneNumber,places.rating,places.userRatingCount,"
            "places.businessStatus,places.primaryType,places.primaryTypeDisplayName,"
            "places.shortFormattedAddress,places.googleMapsUri"
        ),
    }

    body = {
        "textQuery": text_query,
        "pageSize": min(limit, 20),
        "languageCode": "en",
    }

    # Add location bias if country is specified
    if country:
        # Map common country names to region codes for better results
        country_codes = {
            "United States": "US", "United Kingdom": "GB", "Canada": "CA",
            "Australia": "AU", "Germany": "DE", "France": "FR",
            "Spain": "ES", "Italy": "IT", "Netherlands": "NL",
            "Brazil": "BR", "Mexico": "MX", "India": "IN",
            "Japan": "JP", "South Korea": "KR", "South Africa": "ZA",
            "Nigeria": "NG", "UAE": "AE", "Singapore": "SG",
        }
        region_code = country_codes.get(country)
        if region_code:
            body["regionCode"] = region_code

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=body)

            if response.status_code != 200:
                logger.error(f"Google Places API error: {response.status_code} - {response.text[:500]}")
                return []

            data = response.json()
            places = data.get("places", [])

            results = []
            for place in places:
                biz = _normalize_place(place, country or "")
                if biz:
                    results.append(biz)

            logger.info(f"Google Places returned {len(results)} results for query: {text_query}")
            return results

    except httpx.TimeoutException:
        logger.error("Google Places API timeout")
        return []
    except Exception as e:
        logger.error(f"Google Places API error: {e}")
        return []


async def get_place_details(place_id: str) -> Optional[dict]:
    """Get detailed information about a specific place."""
    if not GOOGLE_PLACES_API_KEY:
        return None

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": (
            "id,displayName,formattedAddress,websiteUri,"
            "nationalPhoneNumber,internationalPhoneNumber,"
            "rating,userRatingCount,businessStatus,"
            "types,primaryType,primaryTypeDisplayName,"
            "regularOpeningHours,googleMapsUri,"
            "shortFormattedAddress"
        ),
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{PLACES_DETAILS_URL}/{place_id}",
                headers=headers,
            )

            if response.status_code != 200:
                logger.error(f"Place details error: {response.status_code}")
                return None

            return response.json()

    except Exception as e:
        logger.error(f"Place details error: {e}")
        return None


def _normalize_place(place: dict, country: str) -> Optional[dict]:
    """Normalize a Google Places result into BizLeads business format."""
    try:
        display_name = place.get("displayName", {})
        name = display_name.get("text", "Unknown Business")

        # Extract address
        address = place.get("formattedAddress", "")
        short_address = place.get("shortFormattedAddress", address)

        # Determine category from types
        primary_type_display = place.get("primaryTypeDisplayName", {}).get("text", "")
        primary_type = place.get("primaryType", "")
        types = place.get("types", [])

        category = primary_type_display or _map_type_to_category(primary_type, types)

        # Website analysis
        website_url = place.get("websiteUri", "")
        has_website = bool(website_url)

        # Determine website state
        if not has_website:
            website_state = "no_website"
            website_score = 0
        else:
            # Basic heuristic - will be refined by deep analysis
            website_state = "unknown"
            website_score = 50  # Default until audited

        # Phone
        phone = place.get("nationalPhoneNumber", "") or place.get("internationalPhoneNumber", "")

        # Rating-based social score proxy
        rating = place.get("rating", 0)
        rating_count = place.get("userRatingCount", 0)
        social_score = min(100, int((rating / 5.0) * 40 + min(rating_count / 50, 1) * 60)) if rating > 0 else 20

        # Business status
        biz_status = place.get("businessStatus", "OPERATIONAL")
        if biz_status != "OPERATIONAL":
            return None  # Skip closed businesses

        return {
            "business_name": name,
            "category": category,
            "location": short_address,
            "country": country,
            "website_url": website_url,
            "website_score": website_score,
            "social_score": social_score,
            "has_website": has_website,
            "contact_email": "",  # Not available from Places API
            "contact_phone": phone,
            "google_place_id": place.get("id", ""),
            "google_maps_url": place.get("googleMapsUri", ""),
            "google_rating": rating,
            "google_review_count": rating_count,
            "website_state": website_state,
            "data_source": "google_places",
            # Timing signals from review count
            "timing_signal": _detect_timing_signal(rating, rating_count, has_website),
            "top_opportunity": _detect_opportunity(has_website, website_score, rating, rating_count),
        }
    except Exception as e:
        logger.error(f"Error normalizing place: {e}")
        return None


def _map_type_to_category(primary_type: str, types: list) -> str:
    """Map Google Places types to BizLeads categories."""
    type_map = {
        "restaurant": "Restaurant",
        "cafe": "Cafe",
        "bar": "Bar & Pub",
        "bakery": "Bakery",
        "hair_salon": "Hair Salon",
        "beauty_salon": "Beauty Spa",
        "spa": "Beauty Spa",
        "dentist": "Dentist",
        "doctor": "Doctor",
        "physiotherapist": "Physiotherapy",
        "veterinary_care": "Veterinarian",
        "plumber": "Plumber",
        "electrician": "Electrician",
        "gym": "Gym & Fitness",
        "real_estate_agency": "Real Estate Agent",
        "insurance_agency": "Insurance Agent",
        "accounting": "Accountant",
        "lawyer": "Lawyer",
        "pet_store": "Pet Store",
        "florist": "Florist",
        "laundry": "Dry Cleaner",
        "car_repair": "Auto Repair",
        "car_wash": "Car Wash",
    }

    if primary_type in type_map:
        return type_map[primary_type]

    for t in types:
        if t in type_map:
            return type_map[t]

    return primary_type.replace("_", " ").title() if primary_type else "Local Business"


def _detect_timing_signal(rating: float, review_count: int, has_website: bool) -> str:
    """Detect timing signals from available data."""
    if not has_website and review_count > 20:
        return "Active business without website"
    if rating >= 4.5 and review_count > 50:
        return "High-rated, growing reviews"
    if review_count > 100 and not has_website:
        return "Popular business, no web presence"
    if rating < 3.5 and review_count > 10:
        return "Low ratings may trigger rebrand"
    return ""


def _detect_opportunity(has_website: bool, website_score: int, rating: float, review_count: int) -> str:
    """Detect the top opportunity for this business."""
    if not has_website and review_count > 20:
        return "No website despite active customer base - high conversion potential"
    if not has_website:
        return "No online presence - full website build opportunity"
    if website_score < 40:
        return "Weak website needs complete redesign"
    if rating >= 4.0 and review_count > 30:
        return "Strong reputation not reflected in digital presence"
    return "Digital presence improvement opportunity"