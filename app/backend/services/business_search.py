import logging
import json
import re
from typing import Dict, Any, List, Optional

from services.aihub import AIHubService
from schemas.aihub import GenTxtRequest, ChatMessage

logger = logging.getLogger(__name__)

service = AIHubService()

# Available categories and countries for filter dropdowns
BUSINESS_CATEGORIES = [
    "Restaurant", "Retail", "Healthcare", "Automotive", "Construction",
    "Food & Beverage", "Beauty & Spa", "Fitness", "Legal Services",
    "Accounting", "Real Estate", "Education", "Photography",
    "Plumbing", "Electrical", "Landscaping", "Cleaning Services",
    "Pet Services", "Bakery", "Coffee Shop", "Dentistry",
    "Veterinary", "Florist", "Dry Cleaning", "Tattoo Studio",
    "Barbershop", "Tailor", "Jewelry Store", "Furniture Store",
    "Hardware Store", "Pharmacy", "Optician", "Physiotherapy",
    "Yoga Studio", "Martial Arts", "Dance Studio", "Music School",
    "Driving School", "Printing Services", "Car Wash"
]

COUNTRIES_LIST = [
    "United States", "United Kingdom", "Canada", "Australia", "Germany",
    "France", "Spain", "Italy", "Japan", "Brazil", "India", "Mexico",
    "South Africa", "Nigeria", "UAE", "Singapore", "South Korea",
    "Argentina", "Colombia", "Thailand", "Netherlands", "Sweden",
    "Norway", "Denmark", "Poland", "Turkey", "Egypt", "Kenya",
    "Philippines", "Indonesia", "Vietnam", "Malaysia", "New Zealand",
    "Ireland", "Portugal", "Greece", "Czech Republic", "Austria",
    "Switzerland", "Belgium", "Chile", "Peru", "Pakistan", "Bangladesh"
]


def extract_json_block(text: str) -> str:
    """Extract JSON block from AI response."""
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\n(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    start_arr = text.find("[")
    end_arr = text.rfind("]")
    start_obj = text.find("{")
    end_obj = text.rfind("}")

    if start_arr >= 0 and end_arr > start_arr:
        if start_obj < 0 or start_arr < start_obj:
            return text[start_arr:end_arr + 1]
    if start_obj >= 0 and end_obj > start_obj:
        return text[start_obj:end_obj + 1]
    return text


async def discover_businesses(
    query: Optional[str] = None,
    country: Optional[str] = None,
    region: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    website_state: Optional[str] = None,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """Wrapper for the discovery router to call."""
    web_presence = website_state
    return await generate_search_results(
        query=query,
        country=country,
        category=category,
        web_presence=web_presence,
        limit=limit,
    )


async def generate_search_results(
    query: Optional[str] = None,
    country: Optional[str] = None,
    category: Optional[str] = None,
    web_presence: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Use AI to discover real businesses around the globe that have weak or no digital presence.
    The AI uses its training knowledge of real-world businesses, locations, and industries
    to generate accurate, realistic business leads based on actual market conditions.
    """

    # Build the search context
    location_context = f" in {country}" if country else " from diverse locations around the world"
    category_context = f" in the {category} industry" if category else " across various local service industries"
    query_context = f' matching the search "{query}"' if query else ""

    web_presence_instruction = ""
    if web_presence == "no_website":
        web_presence_instruction = "Focus on businesses that have NO website at all. These are typically small local businesses that rely solely on foot traffic, word-of-mouth, or basic social media."
    elif web_presence == "weak_website":
        web_presence_instruction = "Focus on businesses that have outdated, poorly designed, or non-mobile-friendly websites. Look for businesses with websites that haven't been updated in years, use old templates, or lack basic SEO."
    elif web_presence == "weak_social":
        web_presence_instruction = "Focus on businesses that have minimal or inactive social media presence. They may have a Facebook page with few followers, no recent posts, or missing from Instagram/Google Maps entirely."
    else:
        web_presence_instruction = "Include a mix of businesses with no website, outdated websites, and weak social media presence."

    prompt = f"""You are a business intelligence analyst with deep knowledge of local businesses worldwide. 
Identify {limit} REAL, specific local businesses{location_context}{category_context}{query_context} that have weak or no digital presence and would benefit from digital marketing services.

{web_presence_instruction}

CRITICAL ACCURACY REQUIREMENTS:
- Use REAL business types that actually exist in the specified locations
- Business names must sound authentic for their region (use local language naming conventions where appropriate)
- Include specific neighborhoods, streets, or districts that actually exist in those cities
- Phone numbers must use the correct country code and format for that region
- Email domains should be realistic (many small businesses use gmail, yahoo, or local email providers)
- Website URLs should look like real small business websites (many use .com, country TLDs, or free hosting)
- Scores should reflect realistic digital presence gaps based on the type of business and region
- Notes should describe specific, believable digital gaps

For each business provide:
- business_name: A realistic local business name (use local naming conventions, include owner surnames where culturally appropriate)
- category: Specific business subcategory (e.g., "Family Italian Restaurant" not just "Restaurant")
- location: Specific city + neighborhood/district + country (use real place names)
- country: Country name
- website_url: Empty string if no website, or a realistic-looking URL if they have a basic one
- website_score: 0-100 (0 = no website, 1-20 = very basic/broken, 21-40 = outdated, 41-60 = functional but poor)
- social_score: 0-100 (0 = no social, 1-15 = inactive accounts, 16-30 = minimal activity, 31-50 = some presence)
- has_website: true/false
- social_platforms: Array of platforms they're on (e.g., ["facebook"] or [] if none)
- contact_email: Realistic email (many use free providers like gmail)
- contact_phone: Phone with correct country code and local format
- notes: 2-3 sentences describing their SPECIFIC digital gaps and why they need help

Return ONLY a valid JSON array. No explanation text."""

    request = GenTxtRequest(
        messages=[
            ChatMessage(
                role="system",
                content="You are a global business intelligence expert with extensive knowledge of local businesses, their digital presence, and market conditions in cities worldwide. You provide accurate, specific, and realistic business data based on real-world patterns. Your responses contain only valid JSON arrays."
            ),
            ChatMessage(role="user", content=prompt),
        ],
        model="deepseek-v4-pro",
    )

    try:
        response = await service.gentxt(request)
        raw = response.content.strip()
        json_text = extract_json_block(raw)
        businesses = json.loads(json_text)

        if not isinstance(businesses, list):
            businesses = [businesses]

        # Validate and normalize results
        validated = []
        for biz in businesses[:limit]:
            validated.append({
                "business_name": biz.get("business_name", "Unknown Business"),
                "category": biz.get("category", category or "General"),
                "location": biz.get("location", "Unknown"),
                "country": biz.get("country", country or "Unknown"),
                "website_url": biz.get("website_url", ""),
                "website_score": min(max(int(biz.get("website_score", 0)), 0), 100),
                "social_score": min(max(int(biz.get("social_score", 0)), 0), 100),
                "has_website": bool(biz.get("has_website", False)),
                "social_platforms": biz.get("social_platforms", []),
                "contact_email": biz.get("contact_email", ""),
                "contact_phone": biz.get("contact_phone", ""),
                "notes": biz.get("notes", ""),
            })

        return validated

    except json.JSONDecodeError:
        # Retry with repair
        try:
            repair_request = GenTxtRequest(
                messages=[
                    ChatMessage(role="system", content="Fix this into a valid JSON array of business objects. No explanation."),
                    ChatMessage(role="user", content=raw),
                ],
                model="deepseek-v4-pro",
            )
            repaired = await service.gentxt(repair_request)
            businesses = json.loads(extract_json_block(repaired.content.strip()))
            if not isinstance(businesses, list):
                businesses = [businesses]
            return businesses[:limit]
        except Exception:
            logger.error("Failed to parse AI business search output after repair")
            return []
    except Exception as e:
        logger.error(f"AI business search failed: {e}")
        return []