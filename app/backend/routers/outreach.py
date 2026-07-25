"""
BizLeads Outreach Router - PageSpeed audits and email delivery
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from services.pagespeed import is_pagespeed_configured, audit_website, bulk_audit
from services.email_sender import is_email_configured, send_email, send_bulk_emails, get_email_config_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/outreach", tags=["outreach"])


# --- PageSpeed Audit Endpoints ---

class AuditRequest(BaseModel):
    url: str
    strategy: str = "mobile"  # mobile or desktop


class BulkAuditRequest(BaseModel):
    urls: list[str]
    strategy: str = "mobile"


@router.post("/audit")
async def run_pagespeed_audit(
    data: AuditRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Run a PageSpeed Insights audit on a single website."""
    if not is_pagespeed_configured():
        raise HTTPException(
            status_code=503,
            detail="PageSpeed Insights is not configured. Please add your PAGESPEED_API_KEY in Settings > Integrations."
        )

    result = await audit_website(data.url, data.strategy)
    if result is None:
        raise HTTPException(status_code=400, detail="Failed to audit website. Please check the URL is valid and accessible.")

    return result


@router.post("/audit/bulk")
async def run_bulk_audit(
    data: BulkAuditRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Run PageSpeed audits on multiple websites (max 10)."""
    if not is_pagespeed_configured():
        raise HTTPException(
            status_code=503,
            detail="PageSpeed Insights is not configured. Please add your PAGESPEED_API_KEY in Settings > Integrations."
        )

    if not data.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    results = await bulk_audit(data.urls[:10], data.strategy)
    return {
        "results": results,
        "total_audited": len(results),
        "total_requested": len(data.urls),
    }


# --- Email Outreach Endpoints ---

class SendEmailRequest(BaseModel):
    to_email: str
    subject: str
    body_html: str
    body_text: Optional[str] = None
    reply_to: Optional[str] = None


class BulkEmailRequest(BaseModel):
    recipients: list[dict]  # Each has 'email', optional 'name', 'business_name'
    subject_template: str
    body_html_template: str
    body_text_template: Optional[str] = None


@router.post("/send-email")
async def send_outreach_email(
    data: SendEmailRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Send a single outreach email to a lead."""
    if not is_email_configured():
        raise HTTPException(
            status_code=503,
            detail="Email sending is not configured. Please set up SMTP credentials in Settings > Integrations."
        )

    result = await send_email(
        to_email=data.to_email,
        subject=data.subject,
        body_html=data.body_html,
        body_text=data.body_text,
        reply_to=data.reply_to,
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("message", "Failed to send email"))

    return result


@router.post("/send-bulk")
async def send_bulk_outreach(
    data: BulkEmailRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Send outreach emails to multiple leads using templates."""
    if not is_email_configured():
        raise HTTPException(
            status_code=503,
            detail="Email sending is not configured. Please set up SMTP credentials in Settings > Integrations."
        )

    if not data.recipients:
        raise HTTPException(status_code=400, detail="No recipients provided")

    result = await send_bulk_emails(
        recipients=data.recipients,
        subject_template=data.subject_template,
        body_html_template=data.body_html_template,
        body_text_template=data.body_text_template,
    )

    return result


@router.get("/email-status")
async def get_email_status(
    current_user: UserResponse = Depends(get_current_user),
):
    """Get the current email configuration status."""
    return get_email_config_status()


@router.get("/status")
async def get_outreach_status(
    current_user: UserResponse = Depends(get_current_user),
):
    """Get overall outreach capabilities status."""
    return {
        "pagespeed": {
            "configured": is_pagespeed_configured(),
            "description": "Website performance audits via Google PageSpeed Insights",
        },
        "email": {
            "configured": is_email_configured(),
            "description": "SMTP/Gmail email sending for lead outreach",
            **get_email_config_status(),
        },
    }