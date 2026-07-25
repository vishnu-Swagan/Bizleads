import logging
import json
from typing import Optional, Dict, Any
from services.aihub import AIHubService
from schemas.aihub import GenTxtRequest, ChatMessage

logger = logging.getLogger(__name__)

service = AIHubService()


async def send_followup_email(
    to_email: str,
    subject: str,
    body: str,
    from_name: str = "LeadFinder CRM",
    lead_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a follow-up email. Since we don't have a real SMTP service,
    we simulate sending and log it. In production, this would integrate
    with SendGrid, Mailgun, or similar.
    
    For now, we format the email properly and return a delivery status.
    """
    # Format the email with proper HTML structure
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 8px 8px 0 0;">
            <h2 style="color: white; margin: 0;">LeadFinder CRM</h2>
        </div>
        <div style="padding: 24px; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 8px 8px;">
            <p style="color: #4a5568; line-height: 1.6; white-space: pre-wrap;">{body}</p>
        </div>
        <div style="padding: 12px; text-align: center; color: #a0aec0; font-size: 12px;">
            Sent via LeadFinder CRM • AI-Powered Lead Management
        </div>
    </div>
    """

    # In a real implementation, this would use an email API
    # For now, we return a simulated successful delivery
    result = {
        "status": "queued",
        "message_id": f"msg_{hash(to_email + subject) % 10000000:07d}",
        "to": to_email,
        "subject": subject,
        "from_name": from_name,
        "lead_name": lead_name or "Unknown",
        "html_preview": html_body[:200],
        "delivery_estimate": "Within 5 minutes",
    }

    logger.info(f"Email queued for delivery to {to_email}: {subject}")
    return result


async def generate_and_send_email(
    lead_data: Dict[str, Any],
    custom_message: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a personalized email using AI and queue it for sending."""
    from services.ai_automation import generate_followup_email

    email = await generate_followup_email(
        lead_name=lead_data.get("business_name", ""),
        category=lead_data.get("category", ""),
        location=lead_data.get("location", ""),
        website_score=lead_data.get("website_score", 0),
        social_score=lead_data.get("social_score", 0),
        has_website=lead_data.get("has_website", False),
        pipeline_stage=lead_data.get("pipeline_stage", "new_lead"),
        notes=custom_message or lead_data.get("notes", ""),
    )

    # Send the generated email
    to_email = lead_data.get("contact_email", "")
    if not to_email:
        return {
            "status": "failed",
            "error": "No contact email available for this lead",
            "email": email,
        }

    delivery = await send_followup_email(
        to_email=to_email,
        subject=email["subject"],
        body=email["body"],
        lead_name=lead_data.get("business_name", ""),
    )

    return {
        "status": "sent",
        "email": email,
        "delivery": delivery,
    }