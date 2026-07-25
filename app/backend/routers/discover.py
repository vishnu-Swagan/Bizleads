"""
BizLeads Discovery Router - Job-based async search with credit metering
"""
import json
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from models.workspaces import Workspaces
from models.search_jobs import Search_jobs
from services.business_search import discover_businesses
from services.scoring import build_score_breakdown
from services.mapbox_places import is_mapbox_configured, search_places
from services.pagespeed import is_pagespeed_configured, audit_website

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/discover", tags=["discover"])


class DiscoverRequest(BaseModel):
    query: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    category: Optional[str] = None
    website_state: Optional[str] = "all"  # no_website, weak, parked, unknown, all
    min_need: Optional[int] = 0
    min_buyability: Optional[int] = 0
    min_priority: Optional[int] = 0
    limit: int = 15
    pass_type: str = "quick"  # quick (Pass 1) or deep (Pass 2)


class EstimateRequest(BaseModel):
    query: Optional[str] = None
    country: Optional[str] = None
    category: Optional[str] = None
    limit: int = 15
    pass_type: str = "quick"


@router.post("/estimate")
async def estimate_search(
    data: EstimateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Estimate credit cost and processing time before running search"""
    # Get workspace credits
    result = await db.execute(
        select(Workspaces).where(Workspaces.owner_id == current_user.id)
    )
    workspace = result.scalar_one_or_none()

    credits_remaining = 0
    if workspace:
        credits_remaining = workspace.monthly_credits - workspace.credits_used

    # Estimate costs
    credit_cost = 1 if data.pass_type == "quick" else 3
    estimated_results = min(data.limit, 15)
    estimated_time_seconds = 15 if data.pass_type == "quick" else 45

    providers_used = ["AI Discovery Engine"]
    if data.pass_type == "deep":
        providers_used.extend(["Website Audit", "Performance Check"])

    return {
        "credit_cost": credit_cost,
        "credits_remaining": credits_remaining,
        "can_afford": credits_remaining >= credit_cost,
        "estimated_results": estimated_results,
        "estimated_time_seconds": estimated_time_seconds,
        "providers": providers_used,
        "data_freshness": "Real-time AI analysis",
        "pass_type": data.pass_type,
    }


@router.post("/run")
async def run_discovery(
    data: DiscoverRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a discovery search job"""
    # Check workspace and credits
    result = await db.execute(
        select(Workspaces).where(Workspaces.owner_id == current_user.id)
    )
    workspace = result.scalar_one_or_none()

    if not workspace:
        # Auto-create trial workspace
        from datetime import timedelta
        workspace = Workspaces(
            name=f"{current_user.email}'s Workspace",
            slug=current_user.id[:8],
            owner_id=current_user.id,
            plan="trial",
            subscription_status="trialing",
            monthly_credits=25,
            credits_used=0,
            max_seats=1,
            trial_ends_at=(datetime.utcnow() + timedelta(days=7)).isoformat(),
            credits_reset_at=(datetime.utcnow() + timedelta(days=30)).isoformat(),
        )
        db.add(workspace)
        await db.commit()
        await db.refresh(workspace)

    credits_remaining = workspace.monthly_credits - workspace.credits_used
    credit_cost = 1 if data.pass_type == "quick" else 3

    if credits_remaining < credit_cost:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "insufficient_credits",
                "message": f"This search requires {credit_cost} credit(s). You have {credits_remaining} remaining.",
                "credits_remaining": credits_remaining,
                "credits_required": credit_cost,
                "upgrade_url": "/app/settings/billing",
            }
        )

    # Create search job record
    job = Search_jobs(
        user_id=current_user.id,
        workspace_id=workspace.id,
        status="running",
        filters_json=json.dumps(data.dict()),
        credits_estimated=credit_cost,
        credits_charged=0,
        results_count=0,
        progress_pct=10,
        started_at=datetime.utcnow().isoformat(),
    )
    db.add(job)
    workspace.credits_used += credit_cost
    await db.commit()
    await db.refresh(job)

    job_id = job.id
    await db.rollback()  # Close transaction before slow external call

    # Run discovery - prefer MapBox API when configured
    try:
        raw_results = []
        data_source = "ai"

        if is_mapbox_configured():
            # Use MapBox API for real business/POI data
            data_source = "mapbox"
            raw_results = await search_places(
                query=data.query or "",
                location=data.city or data.region or "",
                category=data.category,
                country=data.country,
                limit=data.limit,
            )
            logger.info(f"MapBox returned {len(raw_results)} results")

        # Fall back to AI discovery if MapBox returns no results or is not configured
        if not raw_results:
            data_source = "ai"
            raw_results = await discover_businesses(
                query=data.query,
                country=data.country,
                region=data.region,
                city=data.city,
                category=data.category,
                website_state=data.website_state,
                limit=data.limit,
            )

        # Enrich with scoring
        scored_results = []
        for biz in raw_results:
            score_data = build_score_breakdown(biz)
            biz["scores"] = score_data["scores"]
            biz["priority_score"] = score_data["priority_score"]
            biz["score_breakdown"] = score_data["breakdowns"]
            biz["website_state"] = score_data["website_state"]
            biz["score_version"] = score_data["score_version"]
            biz["risk_reasons"] = score_data.get("risk_reasons", [])
            scored_results.append(biz)

        # Sort by priority
        scored_results.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

        # Update job status
        result = await db.execute(select(Search_jobs).where(Search_jobs.id == job_id))
        job = result.scalar_one_or_none()
        if job:
            job.status = "complete"
            job.results_count = len(scored_results)
            job.progress_pct = 100
            job.credits_charged = credit_cost
            job.completed_at = datetime.utcnow().isoformat()
            await db.commit()

        return {
            "job_id": job_id,
            "status": "complete",
            "results": scored_results,
            "total_results": len(scored_results),
            "credits_charged": credit_cost,
            "credits_remaining": workspace.monthly_credits - workspace.credits_used,
            "pass_type": data.pass_type,
            "score_version": "1.0.0",
            "data_source": data_source,
        }

    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        # Mark job as failed, return credit
        result = await db.execute(select(Search_jobs).where(Search_jobs.id == job_id))
        job = result.scalar_one_or_none()
        if job:
            job.status = "failed"
            job.error_message = str(e)[:500]
            job.progress_pct = 0

        # Refund credit
        result2 = await db.execute(
            select(Workspaces).where(Workspaces.owner_id == current_user.id)
        )
        ws = result2.scalar_one_or_none()
        if ws:
            ws.credits_used = max(0, ws.credits_used - credit_cost)

        await db.commit()

        raise HTTPException(
            status_code=500,
            detail={
                "error": "discovery_failed",
                "message": "Discovery search failed. Credits have been refunded.",
                "job_id": job_id,
            }
        )


@router.get("/jobs")
async def list_search_jobs(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    skip: int = 0,
):
    """List recent search jobs"""
    result = await db.execute(
        select(Search_jobs)
        .where(Search_jobs.user_id == current_user.id)
        .order_by(Search_jobs.id.desc())
        .offset(skip)
        .limit(limit)
    )
    jobs = result.scalars().all()

    return {
        "jobs": [
            {
                "id": j.id,
                "status": j.status,
                "filters": json.loads(j.filters_json) if j.filters_json else {},
                "results_count": j.results_count,
                "credits_charged": j.credits_charged,
                "progress_pct": j.progress_pct,
                "error_message": j.error_message,
                "started_at": j.started_at,
                "completed_at": j.completed_at,
                "created_at": str(j.created_at) if j.created_at else None,
            }
            for j in jobs
        ]
    }


@router.get("/filters")
async def get_discovery_filters():
    """Get available filter options for discovery"""
    return {
        "mapbox_connected": is_mapbox_configured(),
        "pagespeed_connected": is_pagespeed_configured(),
        "countries": [
            "United States", "United Kingdom", "Canada", "Australia",
            "Germany", "France", "Spain", "Italy", "Netherlands",
            "Brazil", "Mexico", "India", "Japan", "South Korea",
            "South Africa", "Nigeria", "UAE", "Singapore",
        ],
        "categories": [
            "Restaurant", "Cafe", "Bar & Pub", "Bakery",
            "Hair Salon", "Barber Shop", "Beauty Spa", "Nail Salon",
            "Dentist", "Doctor", "Physiotherapy", "Veterinarian",
            "Plumber", "Electrician", "HVAC", "Landscaping",
            "Auto Repair", "Car Wash", "Tire Shop",
            "Gym & Fitness", "Yoga Studio", "Dance Studio",
            "Real Estate Agent", "Insurance Agent", "Accountant", "Lawyer",
            "Pet Store", "Florist", "Dry Cleaner", "Tailor",
            "Photography Studio", "Tattoo Parlor", "Music School",
            "Daycare", "Tutoring", "Driving School",
        ],
        "website_states": [
            {"value": "all", "label": "All States"},
            {"value": "no_website", "label": "No Website"},
            {"value": "parked", "label": "Parked/Invalid Domain"},
            {"value": "weak", "label": "Weak Website"},
            {"value": "moderate", "label": "Moderate (Improvable)"},
            {"value": "unknown", "label": "Status Unknown"},
        ],
        "pass_types": [
            {"value": "quick", "label": "Quick Discovery (1 credit)", "description": "Fast entity resolution and basic scoring"},
            {"value": "deep", "label": "Deep Analysis (3 credits)", "description": "Full audit, screenshots, competitor benchmark"},
        ],
    }