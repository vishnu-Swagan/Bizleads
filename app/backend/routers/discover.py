"""
BizLeads Discovery Router - Job-based async search with credit metering
"""
import json
import logging
from time import monotonic
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from dependencies.tenancy import ensure_workspace_for_user, trial_ended_at
from schemas.auth import UserResponse
from models.workspaces import Workspaces
from models.search_jobs import Search_jobs
from services.scoring import build_score_breakdown
from services.discovery_provider import (
    MAX_LIMIT,
    active_provider_slug,
    configured_provider_names,
    is_discovery_configured,
    is_google_places_configured,
    is_mapbox_configured,
    provider_for_results,
    search_places,
)
from services.pagespeed import is_pagespeed_configured
from services.qualification import qualify_website
from services.entitlements import has_unlimited_credits
from services.lead_angle import write_angle_note
from services.leads import LeadsService
from services import ai_writer

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
    limit: int = Field(default=MAX_LIMIT, ge=1, le=MAX_LIMIT)
    pass_type: str = "quick"  # quick (Pass 1) or deep (Pass 2)


class EstimateRequest(BaseModel):
    query: Optional[str] = None
    country: Optional[str] = None
    category: Optional[str] = None
    limit: int = Field(default=MAX_LIMIT, ge=1, le=MAX_LIMIT)
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
        select(Workspaces).where(Workspaces.owner_id == current_user.id).order_by(Workspaces.id.asc()).limit(1)
    )
    workspace = result.scalars().first()

    credits_remaining = 0
    if workspace:
        credits_remaining = workspace.monthly_credits - workspace.credits_used

    # Estimate costs
    credit_cost = credit_cost_for(data.pass_type)
    estimated_results = min(data.limit, MAX_LIMIT)
    estimated_time_seconds = 15 if data.pass_type == "quick" else 45

    providers_used = configured_provider_names()

    return {
        "credit_cost": credit_cost,
        "credits_remaining": credits_remaining,
        "can_afford": credits_remaining >= credit_cost,
        "estimated_results": estimated_results,
        "estimated_time_seconds": estimated_time_seconds,
        "providers": providers_used,
        "provider_configured": is_discovery_configured(),
        # Was "Real-time AI analysis" — discovery has used a licensed
        # provider since the AI fabrication path was removed.
        "data_freshness": "Live provider data",
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

    # Entitlement before capability. An expired trial is refused whether or
    # not a provider happens to be connected: "no provider is connected" is
    # operator information, and showing it to somebody whose trial has run out
    # answers a question they did not ask while hiding the one thing they need
    # to do. Both checks still precede any job row or credit deduction.
    _refuse_if_trial_expired(workspace, current_user.email)

    if not is_discovery_configured():
        return {
            "status": "provider_unconfigured",
            "error": "provider_unconfigured",
            "message": "No discovery provider is connected. Add a Google Places API key or MapBox access token in Settings to run searches.",
            "provider": None,
            "results": [],
            "total_results": 0,
            "credits_charged": 0,
            "credits_remaining": workspace.monthly_credits - workspace.credits_used,
        }

    # An unmetered account pays nothing and is never refused for balance.
    # The search itself is identical — same provider, same results, same
    # persistence — so nothing downstream needs to know.
    unmetered = has_unlimited_credits(current_user.email)
    credit_cost = 0 if unmetered else credit_cost_for(data.pass_type)
    credits_remaining = workspace.monthly_credits - workspace.credits_used

    if not unmetered and credits_remaining < credit_cost:
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
            biz["qualification_required"] = score_data.get("qualification_required", False)
            biz["data_source"] = biz.get("data_source") or "provider"
            scored_results.append(biz)

        # priority_score is None for leads whose web presence has not been
        # measured yet. Sort those last rather than treating them as zero —
        # unranked is not the same as ranked-lowest.
        scored_results.sort(
            key=lambda x: (x.get("priority_score") is not None, x.get("priority_score") or 0),
            reverse=True,
        )

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
            "data_source": provider_for_results(scored_results),
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
        "google_places_connected": is_google_places_configured(),
        "mapbox_connected": is_mapbox_configured(),
        "pagespeed_connected": is_pagespeed_configured(),
        "discovery_provider": active_provider_slug(),
        "max_results": MAX_LIMIT,
        # Only countries where the provider actually returns business POIs.
        # Japan, South Africa and Nigeria were removed after testing: MapBox
        # returns zero POIs for every category there, including from major
        # cities, so offering them meant a guaranteed "no businesses found"
        # that still cost the user a credit.
        "countries": [
            "United States", "United Kingdom", "Canada", "Australia",
            "Germany", "France", "Spain", "Italy", "Netherlands",
            "Ireland", "Portugal", "Poland", "Sweden", "New Zealand",
            "Brazil", "Mexico", "India", "South Korea", "UAE", "Singapore",
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

# ─────────────────────────────────────────────────────────────────────────────
# Pass 2 — qualification
#
# Discovery (Pass 1) returns identity but not web presence, so every fresh lead
# is unranked: priority_score is None until something is actually measured.
# This is what does the measuring, and it is the only path by which a lead can
# acquire a definite has_website value.
#
# It costs a credit per lead because it does real work — a DNS lookup, an HTTP
# fetch with SSRF guards, and optionally a PageSpeed audit.
# ─────────────────────────────────────────────────────────────────────────────

# Each lead qualified makes at least one outbound request. A generous batch
# would let one call fan out into hundreds of fetches against third parties.
MAX_QUALIFY_BATCH = 10

# How long a single Qualify request may spend on deep PageSpeed audits before
# the rest of the batch falls back to the free heuristic tier. Chosen well
# under the client's 120s timeout so a large batch returns a complete, honest
# result instead of failing after the credits were already charged.
AUDIT_BUDGET_SECONDS = 70.0

# Separate, tighter budget for the AI angle notes, measured against the same
# clock. Deliberately lower than the audit budget: audits are the paid-for
# measurement and must get the lion's share of the request, whereas a note is
# a convenience that the Notes tab can produce later on demand. Set so that a
# full batch of ten still returns inside the client's 120s timeout even when
# every audit ran long first.
ANGLE_BUDGET_SECONDS = 90.0
CREDITS_PER_QUALIFICATION = 1


def _refuse_if_trial_expired(workspace, email: str = "") -> None:
    """Block the credit-spending passes once a trial has run out.

    Applied to Discover and Qualify only — the two operations that spend
    credits and call third-party providers. Reading, editing and exporting
    existing leads stay available: that is the customer's own data, and
    holding it hostage would be a worse product than an honest paywall on new
    work. Outreach drafting is likewise untouched, since it costs no credits
    and only re-reads measurements already paid for.

    Until this existed, trial_ends_at was written at signup and read by
    nothing, so every trial was effectively unlimited — which competes
    directly with the paid plans.
    """
    # An unmetered account is not on a trial in any meaningful sense —
    # gating it would lock the operator out of their own product on day eight.
    if has_unlimited_credits(email):
        return

    ended = trial_ended_at(workspace)
    if ended is None:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "error": "trial_expired",
            "message": (
                f"Your free trial ended on {ended.date().isoformat()}. "
                "Upgrade to keep discovering and qualifying leads — the leads "
                "you have already saved stay available."
            ),
            "trial_ended_at": ended.isoformat(),
            "upgrade_url": "/app/settings/billing",
        },
    )


class QualifyRequest(BaseModel):
    lead_ids: list[int]


@router.post("/qualify")
async def qualify_leads(
    data: QualifyRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Measure the web presence of saved leads and rank them.

    Only leads belonging to the caller are touched; unknown ids are reported
    back rather than silently ignored, so a caller can tell the difference
    between "not yours" and "measured".
    """
    if not data.lead_ids:
        raise HTTPException(status_code=400, detail="No lead_ids provided")

    if len(data.lead_ids) > MAX_QUALIFY_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Qualify at most {MAX_QUALIFY_BATCH} leads per request "
                   f"({len(data.lead_ids)} requested)",
        )

    workspace = await ensure_workspace_for_user(current_user, db)
    credits_remaining = workspace.monthly_credits - workspace.credits_used
    unmetered = has_unlimited_credits(current_user.email)
    cost = 0 if unmetered else CREDITS_PER_QUALIFICATION * len(data.lead_ids)

    _refuse_if_trial_expired(workspace, current_user.email)

    if not unmetered and credits_remaining < cost:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "insufficient_credits",
                "message": f"Qualifying {len(data.lead_ids)} lead(s) requires {cost} credit(s). "
                           f"You have {credits_remaining} remaining.",
                "credits_remaining": credits_remaining,
                "credits_required": cost,
                "upgrade_url": "/app/settings/billing",
            },
        )

    service = LeadsService(db)
    results = []
    not_found = []
    charged = 0
    started_at = monotonic()
    audits_skipped = 0
    angles_written = 0
    angles_skipped = 0

    for lead_id in data.lead_ids:
        lead = await service.get_by_id(lead_id, user_id=str(current_user.id))
        if lead is None:
            # 404-equivalent per lead: do not confirm whether the row exists
            # for someone else.
            not_found.append(lead_id)
            continue

        # PageSpeed renders the page, so it costs 10-20s per lead. Ten leads
        # would run for minutes while the browser gives up after two, and the
        # user would see a timeout having already been charged. The batch
        # therefore audits only while the budget lasts and drops to the free
        # heuristic tier afterwards — evidence_tier records which produced
        # each score, so the result stays honest rather than silently weaker.
        within_budget = (monotonic() - started_at) < AUDIT_BUDGET_SECONDS
        measurement = await qualify_website(lead.website_url, allow_audit=within_budget)
        if not within_budget:
            audits_skipped += 1
        if not unmetered:
            charged += CREDITS_PER_QUALIFICATION

        scored = build_score_breakdown(
            {
                "has_website": measurement["has_website"],
                "website_score": measurement["website_score"],
                "social_score": lead.social_score,
                "contact_email": lead.contact_email or None,
                "contact_phone": lead.contact_phone or None,
                "data_source": lead.data_source,
            }
        )

        # Persist only what was measured. None means unmeasured and is stored
        # as NULL — writing 0 or false here would assert a verdict nobody
        # established, which is the defect this whole pass exists to avoid.
        update: dict = {
            "has_website": measurement["has_website"],
            "website_score": measurement["website_score"],
        }
        if measurement["website_url"]:
            # The URL after redirects — what was actually measured.
            update["website_url"] = measurement["website_url"]

        # Fill in contact details found on the site, but never overwrite one
        # that is already there: a value the provider supplied, or one the
        # user entered or corrected, outranks anything scraped from a page.
        #
        # This is what makes phone and address work outside the provider's
        # strong markets. MapBox carries a phone for some countries and an
        # address for some, so a provider-only pipeline left most non-UK/US
        # leads unreachable; the business's own page does not vary that way.
        if measurement.get("contact_email") and not (lead.contact_email or "").strip():
            update["contact_email"] = measurement["contact_email"]

        if measurement.get("contact_phone") and not (lead.contact_phone or "").strip():
            update["contact_phone"] = measurement["contact_phone"]

        if measurement.get("postal_address") and not (lead.address or "").strip():
            update["address"] = measurement["postal_address"]

        # Social presence, measured from the same page fetch. Only written
        # when a page was actually read.
        #
        # social_platforms cannot itself express "never looked": the column
        # defaults to '[]' and the save path writes '[]' on create, so an
        # untouched lead is indistinguishable from one measured as having no
        # links. `qualified_at` is what carries that distinction — it is NULL
        # until a measurement runs — so the UI must gate on it before
        # reporting "no social links found". Writing '[]' here regardless
        # would make that gate meaningless.
        if measurement.get("social_links") is not None:
            update["social_platforms"] = json.dumps(measurement["social_links"])

        # findings/qualified_at follow the same rule: only persist them when
        # a website_score was actually established. A None score means the
        # measurement could not run (invalid/blocked/parked/unreachable), and
        # writing "[]" there would assert "checked, found nothing wrong" for
        # a lead nobody actually analysed.
        if measurement["website_score"] is not None:
            update["findings"] = json.dumps(measurement["findings"])
            update["qualified_at"] = datetime.now(timezone.utc).isoformat()

        priority = scored["priority_score"]
        if priority is not None:
            update["priority"] = (
                "high" if priority >= 60 else "medium" if priority >= 35 else "low"
            )

        await service.update(lead_id, update, user_id=str(current_user.id))

        # An angle note per measured lead, on the same budget discipline as
        # the PageSpeed audit above and for the same reason: this adds a model
        # round-trip per lead, and ten of them in series would run past the
        # browser's patience on a bulk qualify. Once the budget is gone the
        # remaining leads are measured and stored exactly as before, just
        # without a note — the Notes tab can generate one on demand later.
        #
        # write_angle_note never raises and returns None when there is nothing
        # honest to say, so nothing here can fail a qualification the user has
        # already been charged for.
        if (
            measurement["website_score"] is not None
            and ai_writer.is_ai_configured()
            and (monotonic() - started_at) < ANGLE_BUDGET_SECONDS
        ):
            refreshed = await service.get_by_id(lead_id, user_id=str(current_user.id))
            if refreshed is not None:
                if await write_angle_note(db, refreshed, str(current_user.id)):
                    angles_written += 1
                else:
                    angles_skipped += 1
        elif measurement["website_score"] is not None:
            angles_skipped += 1

        results.append(
            {
                "lead_id": lead_id,
                "business_name": lead.business_name,
                "has_website": measurement["has_website"],
                "website_url": measurement["website_url"],
                "website_score": measurement["website_score"],
                "website_state": measurement["website_state"],
                "priority_score": priority,
                "qualification_required": scored["qualification_required"],
                "evidence_tier": measurement["evidence_tier"],
                # The sellable part: specific, checkable problems with the site.
                "findings": measurement["findings"],
            }
        )

    workspace.credits_used += charged
    await db.commit()

    return {
        "qualified": results,
        "not_found": not_found,
        "credits_charged": charged,
        "credits_remaining": workspace.monthly_credits - workspace.credits_used,
        "audit_available": is_pagespeed_configured(),
        # Reported rather than silent: a batch that ran out of budget wrote
        # fewer notes than leads, and the UI should be able to say so instead
        # of leaving the user to wonder why some leads have an angle and
        # others do not.
        "angles_written": angles_written,
        "angles_skipped": angles_skipped,
    }
