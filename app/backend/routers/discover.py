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
from dependencies.tenancy import ensure_workspace_for_user
from schemas.auth import UserResponse
from models.workspaces import Workspaces
from models.search_jobs import Search_jobs
from services.scoring import build_score_breakdown
from services.mapbox_places import is_mapbox_configured, search_places
from services.pagespeed import is_pagespeed_configured

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/discover", tags=["discover"])

# Both passes currently perform identical work: audit_website is imported but
# never invoked. Charging 3 for the deep pass was billing users for an audit
# that does not run. Restore the differential when the deep pass does more.
CREDIT_COST_PER_PASS = {"quick": 1, "deep": 1}


def credit_cost_for(pass_type: str) -> int:
    return CREDIT_COST_PER_PASS.get(pass_type, 1)


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
    credit_cost = credit_cost_for(data.pass_type)
    estimated_results = min(data.limit, 15)
    estimated_time_seconds = 15 if data.pass_type == "quick" else 45

    providers_used = ["MapBox Places"] if is_mapbox_configured() else []

    return {
        "credit_cost": credit_cost,
        "credits_remaining": credits_remaining,
        "can_afford": credits_remaining >= credit_cost,
        "estimated_results": estimated_results,
        "estimated_time_seconds": estimated_time_seconds,
        "providers": providers_used,
        "provider_configured": is_mapbox_configured(),
        "data_freshness": "Real-time AI analysis",
        "pass_type": data.pass_type,
    }


@router.post("/run")
async def run_discovery(
    data: DiscoverRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a discovery search.

    The provider check happens before any job row or credit deduction, so an
    unconfigured provider costs the user nothing. There is deliberately no AI
    fallback: fabricated businesses must never be returned as live results.
    """
    workspace = await ensure_workspace_for_user(current_user, db)

    if not is_mapbox_configured():
        return {
            "status": "provider_unconfigured",
            "error": "provider_unconfigured",
            "message": "No discovery provider is connected. Add a MapBox access token in Settings to run searches.",
            "provider": "mapbox",
            "results": [],
            "total_results": 0,
            "credits_charged": 0,
            "credits_remaining": workspace.monthly_credits - workspace.credits_used,
        }

    credit_cost = credit_cost_for(data.pass_type)
    credits_remaining = workspace.monthly_credits - workspace.credits_used

    if credits_remaining < credit_cost:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "insufficient_credits",
                "message": f"This search requires {credit_cost} credit(s). You have {credits_remaining} remaining.",
                "credits_remaining": credits_remaining,
                "credits_required": credit_cost,
                "upgrade_url": "/app/settings/billing",
            },
        )

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
    await db.refresh(workspace)
    job_id = job.id
    credits_left = workspace.monthly_credits - workspace.credits_used

    try:
        raw_results = await search_places(
            query=data.query or "",
            location=data.city or data.region or "",
            category=data.category,
            country=data.country,
            limit=data.limit,
        )

        scored_results = []
        for biz in raw_results:
            score_data = build_score_breakdown(biz)
            biz["scores"] = score_data["scores"]
            biz["priority_score"] = score_data["priority_score"]
            biz["score_breakdown"] = score_data["breakdowns"]
            biz["website_state"] = score_data["website_state"]
            biz["score_version"] = score_data["score_version"]
            biz["risk_reasons"] = score_data.get("risk_reasons", [])
            biz["data_source"] = "provider"
            scored_results.append(biz)

        scored_results.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

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
            "status": "complete" if scored_results else "no_matches",
            "results": scored_results,
            "total_results": len(scored_results),
            "credits_charged": credit_cost,
            "credits_remaining": credits_left,
            "pass_type": data.pass_type,
            "score_version": "1.0.0",
            "data_source": "mapbox",
        }

    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        result = await db.execute(select(Search_jobs).where(Search_jobs.id == job_id))
        job = result.scalar_one_or_none()
        if job:
            job.status = "failed"
            job.error_message = str(e)[:500]
            job.progress_pct = 0

        ws_result = await db.execute(select(Workspaces).where(Workspaces.id == workspace.id))
        ws = ws_result.scalar_one_or_none()
        if ws:
            ws.credits_used = max(0, ws.credits_used - credit_cost)

        await db.commit()

        raise HTTPException(
            status_code=500,
            detail={
                "error": "discovery_failed",
                "message": "Discovery search failed. Credits have been refunded.",
                "job_id": job_id,
            },
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
            {"value": "quick", "label": "Quick Discovery (1 credit)", "description": "Entity resolution and basic scoring"},
            {"value": "deep", "label": "Deep Analysis (1 credit)", "description": "Currently identical to Quick; website audits are not yet wired up"},
        ],
    }