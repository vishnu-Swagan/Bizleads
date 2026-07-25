import logging
import json
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from core.database import get_db
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from models.leads import Leads
from models.ai_interaction_logs import Ai_interaction_logs
from services.ai_automation import generate_followup_email, generate_daily_report
from services.ai_interaction_logger import AIInteractionLogger
from services.email_service import send_followup_email, generate_and_send_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])


# ─── Request/Response Models ───────────────────────────────────────────────────

class FollowUpRequest(BaseModel):
    lead_id: int
    custom_message: Optional[str] = None
    tone: Optional[str] = None  # professional, friendly, urgent, casual


class FollowUpResponse(BaseModel):
    subject: str
    body: str
    suggested_action: str
    lead_name: str


class SendEmailRequest(BaseModel):
    lead_id: int
    subject: Optional[str] = None
    body: Optional[str] = None
    custom_message: Optional[str] = None


class SendEmailResponse(BaseModel):
    status: str
    message_id: Optional[str] = None
    to: Optional[str] = None
    subject: Optional[str] = None
    delivery_estimate: Optional[str] = None
    error: Optional[str] = None


class DailyReportResponse(BaseModel):
    summary: str
    metrics: Dict[str, Any]
    action_items: List[str]
    urgent_leads: List[str]
    recommendations: List[str]
    generated_at: str
    raw_stats: Dict[str, Any]


class InteractionLogEntry(BaseModel):
    id: int
    action_type: str
    input_summary: str
    output_summary: str
    status: str
    lead_id: Optional[int] = None
    duration_ms: int
    created_at: str


class InteractionLogsResponse(BaseModel):
    logs: List[InteractionLogEntry]
    total: int
    page: int
    per_page: int


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/follow-up-email", response_model=FollowUpResponse)
async def generate_follow_up(
    data: FollowUpRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI-powered follow-up email for a specific lead."""
    ai_logger = AIInteractionLogger(db, current_user.id)
    ai_logger.start()

    try:
        # Fetch the lead
        result = await db.execute(
            select(Leads).where(Leads.id == data.lead_id, Leads.user_id == current_user.id)
        )
        lead = result.scalar_one_or_none()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        lead_name = lead.business_name
        lead_category = lead.category or ""
        lead_location = lead.location or ""
        lead_ws = lead.website_score or 0
        lead_ss = lead.social_score or 0
        lead_hw = lead.has_website or False
        lead_ps = lead.pipeline_stage or "new_lead"

        # Close DB transaction before AI call
        await db.rollback()

        # Generate email using AI
        email = await generate_followup_email(
            lead_name=lead_name,
            category=lead_category,
            location=lead_location,
            website_score=lead_ws,
            social_score=lead_ss,
            has_website=lead_hw,
            pipeline_stage=lead_ps,
            notes=data.custom_message,
            tone=data.tone,
        )

        # Log the interaction
        await ai_logger.log(
            action_type="follow_up_email",
            input_summary=f"Email for {lead_name} (stage: {lead_ps})",
            output_summary=f"Subject: {email['subject']}",
            status="success",
            lead_id=data.lead_id,
        )

        return FollowUpResponse(
            subject=email["subject"],
            body=email["body"],
            suggested_action=email["suggested_action"],
            lead_name=lead_name,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Follow-up email generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate email: {str(e)}")


@router.post("/send-email", response_model=SendEmailResponse)
async def send_email_to_lead(
    data: SendEmailRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate and send a follow-up email directly to a lead's email address."""
    ai_logger = AIInteractionLogger(db, current_user.id)
    ai_logger.start()

    try:
        # Fetch the lead
        result = await db.execute(
            select(Leads).where(Leads.id == data.lead_id, Leads.user_id == current_user.id)
        )
        lead = result.scalar_one_or_none()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        lead_email = lead.contact_email
        lead_name = lead.business_name

        if not lead_email:
            raise HTTPException(status_code=400, detail="This lead has no contact email address")

        # Close DB before slow work
        await db.rollback()

        # If subject and body provided, send directly
        if data.subject and data.body:
            delivery = await send_followup_email(
                to_email=lead_email,
                subject=data.subject,
                body=data.body,
                lead_name=lead_name,
            )
        else:
            # Generate and send
            lead_data = {
                "business_name": lead_name,
                "category": lead.category or "",
                "location": lead.location or "",
                "website_score": lead.website_score or 0,
                "social_score": lead.social_score or 0,
                "has_website": lead.has_website or False,
                "pipeline_stage": lead.pipeline_stage or "new_lead",
                "contact_email": lead_email,
                "notes": data.custom_message or "",
            }
            result_data = await generate_and_send_email(lead_data, data.custom_message)

            if result_data["status"] == "failed":
                raise HTTPException(status_code=400, detail=result_data.get("error", "Failed to send"))

            delivery = result_data["delivery"]

        # Log the interaction
        await ai_logger.log(
            action_type="send_email",
            input_summary=f"Send email to {lead_name} ({lead_email})",
            output_summary=f"Status: {delivery['status']}, ID: {delivery.get('message_id', '')}",
            status="success",
            lead_id=data.lead_id,
            metadata={"to": lead_email, "message_id": delivery.get("message_id")},
        )

        # Update lead's last_contacted
        result2 = await db.execute(
            select(Leads).where(Leads.id == data.lead_id)
        )
        lead_obj = result2.scalar_one_or_none()
        if lead_obj:
            from datetime import datetime, timezone
            lead_obj.last_contacted = datetime.now(timezone.utc).isoformat()
            if lead_obj.pipeline_stage == "new_lead":
                lead_obj.pipeline_stage = "contacted"
            await db.commit()

        return SendEmailResponse(
            status=delivery["status"],
            message_id=delivery.get("message_id"),
            to=delivery.get("to"),
            subject=delivery.get("subject"),
            delivery_estimate=delivery.get("delivery_estimate"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Send email error: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


@router.get("/daily-report", response_model=DailyReportResponse)
async def get_daily_report(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI-powered daily activity report for all leads."""
    ai_logger = AIInteractionLogger(db, current_user.id)
    ai_logger.start()

    try:
        # Fetch all user leads
        result = await db.execute(
            select(Leads).where(Leads.user_id == current_user.id)
        )
        leads = result.scalars().all()

        # Convert to dicts
        leads_data = []
        for lead in leads:
            leads_data.append({
                "business_name": lead.business_name,
                "category": lead.category,
                "location": lead.location,
                "country": lead.country,
                "pipeline_stage": lead.pipeline_stage,
                "priority": lead.priority,
                "website_score": lead.website_score,
                "social_score": lead.social_score,
                "updated_at": str(lead.updated_at) if lead.updated_at else "",
            })

        # Close DB transaction before AI call
        await db.rollback()

        # Generate report using AI
        report = await generate_daily_report(
            leads=leads_data,
            user_name=getattr(current_user, 'name', None) or current_user.email,
        )

        # Log the interaction
        await ai_logger.log(
            action_type="daily_report",
            input_summary=f"Daily report for {len(leads_data)} leads",
            output_summary=report.get("summary", "")[:200],
            status="success",
            metadata={"total_leads": len(leads_data)},
        )

        return DailyReportResponse(
            summary=report.get("summary", "No data available"),
            metrics=report.get("metrics", {}),
            action_items=report.get("action_items", []),
            urgent_leads=report.get("urgent_leads", []),
            recommendations=report.get("recommendations", []),
            generated_at=report.get("generated_at", ""),
            raw_stats=report.get("raw_stats", {}),
        )
    except Exception as e:
        logger.error(f"Daily report generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("/interaction-logs", response_model=InteractionLogsResponse)
async def get_interaction_logs(
    page: int = 1,
    per_page: int = 20,
    action_type: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the user's AI interaction history log."""
    try:
        query = select(Ai_interaction_logs).where(Ai_interaction_logs.user_id == current_user.id)
        count_query = select(func.count(Ai_interaction_logs.id)).where(Ai_interaction_logs.user_id == current_user.id)

        if action_type:
            query = query.where(Ai_interaction_logs.action_type == action_type)
            count_query = count_query.where(Ai_interaction_logs.action_type == action_type)

        # Get total count
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Get paginated results
        query = query.order_by(desc(Ai_interaction_logs.created_at))
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await db.execute(query)
        logs = result.scalars().all()

        log_entries = []
        for log in logs:
            log_entries.append(InteractionLogEntry(
                id=log.id,
                action_type=log.action_type,
                input_summary=log.input_summary or "",
                output_summary=log.output_summary or "",
                status=log.status or "unknown",
                lead_id=log.lead_id,
                duration_ms=log.duration_ms or 0,
                created_at=str(log.created_at) if log.created_at else "",
            ))

        return InteractionLogsResponse(
            logs=log_entries,
            total=total,
            page=page,
            per_page=per_page,
        )
    except Exception as e:
        logger.error(f"Interaction logs fetch error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {str(e)}")