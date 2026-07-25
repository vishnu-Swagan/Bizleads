import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from services.business_search import generate_search_results, BUSINESS_CATEGORIES, COUNTRIES_LIST

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/search", tags=["search"])


class SearchRequest(BaseModel):
    query: Optional[str] = None
    country: Optional[str] = None
    category: Optional[str] = None
    web_presence: Optional[str] = None  # no_website, weak_website, weak_social, all
    limit: int = 20


class BusinessResult(BaseModel):
    business_name: str
    category: str
    location: str
    country: str
    website_url: str
    website_score: int
    social_score: int
    has_website: bool
    social_platforms: List[str]
    contact_email: str
    contact_phone: str
    notes: Optional[str] = ""


class SearchResponse(BaseModel):
    results: List[BusinessResult]
    total: int
    filters_applied: Dict[str, Any]


class FiltersResponse(BaseModel):
    categories: List[str]
    countries: List[str]
    web_presence_options: List[Dict[str, str]]


@router.post("/businesses", response_model=SearchResponse)
async def search_businesses(
    data: SearchRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Search for real businesses with weak web presence globally using AI-powered discovery."""
    try:
        results = await generate_search_results(
            query=data.query,
            country=data.country,
            category=data.category,
            web_presence=data.web_presence,
            limit=data.limit,
        )

        return SearchResponse(
            results=results,
            total=len(results),
            filters_applied={
                "query": data.query,
                "country": data.country,
                "category": data.category,
                "web_presence": data.web_presence,
            }
        )
    except Exception as e:
        logger.error(f"Search error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/filters", response_model=FiltersResponse)
async def get_search_filters(
    current_user: UserResponse = Depends(get_current_user),
):
    """Get available search filter options."""
    return FiltersResponse(
        categories=sorted(BUSINESS_CATEGORIES),
        countries=sorted(COUNTRIES_LIST),
        web_presence_options=[
            {"value": "all", "label": "All Weak Presence"},
            {"value": "no_website", "label": "No Website"},
            {"value": "weak_website", "label": "Weak Website (Score < 40)"},
            {"value": "weak_social", "label": "Weak Social Media"},
        ]
    )