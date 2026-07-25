import logging
import json
import re
import random
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from services.aihub import AIHubService
from schemas.aihub import GenTxtRequest, ChatMessage

logger = logging.getLogger(__name__)

service = AIHubService()


def extract_json_block(text: str) -> str:
    """Extract JSON block from AI response."""
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\n(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    # Try to find array
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


async def generate_new_leads(
    country: Optional[str] = None,
    category: Optional[str] = None,
    count: int = 5,
    min_website_score: int = 0,
    max_website_score: int = 30,
    min_social_score: int = 0,
    max_social_score: int = 25,
    business_size: Optional[str] = None,
    years_in_business: Optional[str] = None,
    target_revenue: Optional[str] = None,
    intent_signals: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Use AI to generate realistic new business leads with advanced targeting."""

    location_hint = f" in {country}" if country else " globally"
    category_hint = f" in the {category} industry" if category else ""

    # Build advanced targeting context
    targeting_context = []
    if business_size:
        size_map = {
            "small": "1-10 employees, likely owner-operated",
            "medium": "11-50 employees, has some staff",
            "large": "50+ employees, established operations",
        }
        targeting_context.append(f"Business size: {size_map.get(business_size, business_size)}")

    if years_in_business:
        years_map = {
            "new": "0-2 years old, recently started",
            "established": "3-10 years old, proven track record",
            "veteran": "10+ years old, long-standing local presence",
        }
        targeting_context.append(f"Age: {years_map.get(years_in_business, years_in_business)}")

    if target_revenue:
        rev_map = {
            "under_100k": "estimated annual revenue under $100K",
            "100k_500k": "estimated annual revenue $100K-$500K",
            "500k_1m": "estimated annual revenue $500K-$1M",
            "over_1m": "estimated annual revenue over $1M",
        }
        targeting_context.append(f"Revenue: {rev_map.get(target_revenue, target_revenue)}")

    if intent_signals:
        signal_descriptions = {
            "hiring": "currently hiring new staff (growth signal)",
            "expanding": "expanding to new locations or services",
            "rebranding": "undergoing rebranding or renovation",
            "new_location": "recently opened a new location",
        }
        signals_text = ", ".join(signal_descriptions.get(s, s) for s in intent_signals)
        targeting_context.append(f"Intent signals: {signals_text}")

    targeting_block = ""
    if targeting_context:
        targeting_block = "\n\nAdvanced targeting criteria:\n" + "\n".join(f"- {t}" for t in targeting_context)

    prompt = f"""You are a business intelligence analyst with deep knowledge of real local businesses worldwide.
Identify {count} REAL, specific local businesses{location_hint}{category_hint} that have weak or no web presence and would benefit from digital marketing services.{targeting_block}

CRITICAL - REAL DATA REQUIREMENTS:
- These must represent REAL types of businesses that actually exist in these locations
- Business names must follow local naming conventions (use local language, owner surnames, cultural patterns)
- Locations must reference REAL neighborhoods, streets, districts, and postal areas that exist
- Phone numbers must use the CORRECT country code and local format (e.g., +44 for UK, +91 for India, +1 for US)
- Email addresses should reflect how real small businesses operate (many use gmail, yahoo, or local providers)
- Website URLs should look like actual small business websites (country TLDs, free hosting, or no website)
- Digital presence scores must reflect REAL market conditions for that region and industry
- Notes should describe SPECIFIC, verifiable digital gaps (e.g., "No Google My Business listing, only a dormant Facebook page with 23 followers created in 2019, no website, competitors in the area all have active Instagram accounts")

For each business, provide:
- business_name: A highly realistic local business name (include owner surname if appropriate)
- category: Specific business category (e.g., "Italian Restaurant", "Auto Body Shop", "Family Dentistry")
- location: Specific city, neighborhood/district, and country
- country: Country name
- contact_email: A realistic business email (based on business name)
- contact_phone: Phone with correct country code format
- website_url: Either empty string (no website) or a basic/outdated looking URL
- website_score: {min_website_score}-{max_website_score} (weak presence)
- social_score: {min_social_score}-{max_social_score} (weak social)
- has_website: true/false
- notes: 2-3 sentences explaining SPECIFIC digital gaps and why they need help
- estimated_employees: Number estimate
- years_operating: Estimated years in business
- opportunity_score: 1-10 rating of how good this opportunity is for a digital agency

Return ONLY a valid JSON array of objects. No explanation text."""

    request = GenTxtRequest(
        messages=[
            ChatMessage(role="system", content="You are a business intelligence expert specializing in identifying local businesses that need digital transformation. Generate highly realistic, specific leads with accurate details. Return ONLY valid JSON arrays."),
            ChatMessage(role="user", content=prompt),
        ],
        model="deepseek-v4-pro",
    )

    try:
        response = await service.gentxt(request)
        raw = response.content.strip()
        json_text = extract_json_block(raw)
        leads = json.loads(json_text)

        if not isinstance(leads, list):
            leads = [leads]

        # Validate and normalize each lead
        validated = []
        for lead in leads[:count]:
            ws = min(max(int(lead.get("website_score", 0)), min_website_score), max_website_score)
            ss = min(max(int(lead.get("social_score", 0)), min_social_score), max_social_score)
            validated.append({
                "business_name": lead.get("business_name", "Unknown Business"),
                "category": lead.get("category", "General"),
                "location": lead.get("location", "Unknown"),
                "country": lead.get("country", "Unknown"),
                "contact_email": lead.get("contact_email", ""),
                "contact_phone": lead.get("contact_phone", ""),
                "website_url": lead.get("website_url", ""),
                "website_score": ws,
                "social_score": ss,
                "has_website": bool(lead.get("has_website", False)),
                "notes": lead.get("notes", "Needs digital presence improvement"),
                "pipeline_stage": "new_lead",
                "priority": "high" if lead.get("opportunity_score", 5) >= 7 else ("medium" if lead.get("opportunity_score", 5) >= 4 else "low"),
                "estimated_employees": lead.get("estimated_employees"),
                "years_operating": lead.get("years_operating"),
                "opportunity_score": lead.get("opportunity_score", 5),
            })

        return validated
    except json.JSONDecodeError:
        # Retry with repair
        repair_request = GenTxtRequest(
            messages=[
                ChatMessage(role="system", content="Fix this into a valid JSON array only. No explanation."),
                ChatMessage(role="user", content=raw),
            ],
            model="deepseek-v4-pro",
        )
        repaired = await service.gentxt(repair_request)
        try:
            leads = json.loads(extract_json_block(repaired.content.strip()))
            if not isinstance(leads, list):
                leads = [leads]
            return leads[:count]
        except Exception:
            logger.error("Failed to parse AI lead generation output after repair")
            return []
    except Exception as e:
        logger.error(f"AI lead generation failed: {e}")
        return []


async def generate_followup_email(
    lead_name: str,
    category: str,
    location: str,
    website_score: int,
    social_score: int,
    has_website: bool,
    pipeline_stage: str,
    notes: Optional[str] = None,
    tone: Optional[str] = None,
) -> Dict[str, str]:
    """Use AI to generate a personalized follow-up email for a lead."""

    web_status = "no website" if not has_website else f"a basic website (score: {website_score}/100)"
    social_status = f"social media presence score of {social_score}/100"

    stage_context = {
        "new_lead": "This is a first outreach email. Be friendly and introduce our services.",
        "contacted": "We've reached out before. Follow up on our initial contact.",
        "in_progress": "We're in active discussions. Push toward closing the deal.",
        "won": "They're a client now. Send a welcome/onboarding email.",
        "lost": "They declined before. Try a gentle re-engagement approach.",
    }

    tone_instructions = {
        "professional": "Use a formal, corporate tone. Be polished and authoritative.",
        "friendly": "Use a warm, approachable tone. Be conversational and personable.",
        "urgent": "Create urgency. Mention limited-time offers or competitive pressure.",
        "casual": "Be relaxed and informal. Use short sentences and a natural voice.",
    }

    context = stage_context.get(pipeline_stage, "Send a professional outreach email.")
    tone_hint = tone_instructions.get(tone, "") if tone else ""
    notes_context = f"\nAdditional context: {notes}" if notes else ""

    prompt = f"""Write a professional follow-up email for this business lead:

Business: {lead_name}
Industry: {category}
Location: {location}
Digital Presence: {web_status}, {social_status}
Stage: {pipeline_stage}
Context: {context}
{f"Tone: {tone_hint}" if tone_hint else ""}{notes_context}

The email should:
1. Be personalized to their specific business and industry
2. Reference specific digital gaps (no website, low social engagement, missing Google listing, etc.)
3. Include concrete benefits with numbers where possible (e.g., "businesses with optimized Google profiles get 70% more visits")
4. Include a clear, low-commitment call-to-action
5. Be concise (under 200 words)
6. Sound human and genuine, not like a template

Return a JSON object with:
- subject: Compelling email subject line (under 60 chars)
- body: Email body text with proper greeting and sign-off
- suggested_action: What to do next after sending (1 sentence)"""

    request = GenTxtRequest(
        messages=[
            ChatMessage(role="system", content="You are an expert sales copywriter who writes high-converting cold emails for digital agencies. Return ONLY valid JSON."),
            ChatMessage(role="user", content=prompt),
        ],
        model="deepseek-v4-pro",
    )

    try:
        response = await service.gentxt(request)
        raw = response.content.strip()
        json_text = extract_json_block(raw)
        result = json.loads(json_text)
        return {
            "subject": result.get("subject", f"Helping {lead_name} grow online"),
            "body": result.get("body", ""),
            "suggested_action": result.get("suggested_action", "Follow up in 3 days"),
        }
    except Exception as e:
        logger.error(f"AI email generation failed: {e}")
        return {
            "subject": f"Helping {lead_name} grow their digital presence",
            "body": f"Hi,\n\nI noticed that {lead_name} could benefit from improved online visibility. As a {category} business in {location}, having a strong digital presence is crucial for attracting new customers.\n\nI'd love to discuss how we can help. Would you be available for a quick call this week?\n\nBest regards",
            "suggested_action": "Follow up in 3 days if no response",
        }


async def generate_daily_report(
    leads: List[Dict[str, Any]],
    user_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Use AI to generate a daily activity report summarizing lead progress."""

    # Calculate stats
    total = len(leads)
    by_stage = {}
    by_priority = {}
    by_category = {}
    recent_activity = []

    for lead in leads:
        stage = lead.get("pipeline_stage", "unknown")
        priority = lead.get("priority", "unknown")
        category = lead.get("category", "unknown")
        by_stage[stage] = by_stage.get(stage, 0) + 1
        by_priority[priority] = by_priority.get(priority, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1

        # Check for recent updates
        updated = lead.get("updated_at", "")
        if updated:
            recent_activity.append({
                "name": lead.get("business_name", "Unknown"),
                "stage": stage,
                "priority": priority,
                "updated": updated,
            })

    # Sort by most recent
    recent_activity.sort(key=lambda x: x.get("updated", ""), reverse=True)
    recent_activity = recent_activity[:10]

    # Calculate conversion rate
    won = by_stage.get("won", 0)
    conversion_rate = round((won / total * 100), 1) if total > 0 else 0

    stats_summary = f"""Total leads: {total}
By stage: {json.dumps(by_stage)}
By priority: {json.dumps(by_priority)}
Top categories: {json.dumps(dict(sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:5]))}
Conversion rate: {conversion_rate}%
Recent activity (last 10 updated): {json.dumps(recent_activity[:5])}"""

    greeting = f"for {user_name}" if user_name else ""

    prompt = f"""Generate a comprehensive daily CRM activity report {greeting} based on these stats:

{stats_summary}

The report should include:
1. Executive summary (2-3 sentences with key insights)
2. Key metrics highlights with context (not just numbers, explain what they mean)
3. Action items for today (5 specific, actionable tasks prioritized by impact)
4. Leads requiring immediate attention (based on stage, priority, and staleness)
5. Strategic recommendations for improving conversion rate and pipeline health
6. Industry insights based on the lead categories present

Return a JSON object with:
- summary: Executive summary text
- metrics: Object with key metric names and values (include conversion_rate, pipeline_velocity, top_category)
- action_items: Array of action item strings (specific and actionable)
- urgent_leads: Array of lead names needing attention
- recommendations: Array of strategic recommendation strings
- generated_at: Current timestamp"""

    request = GenTxtRequest(
        messages=[
            ChatMessage(role="system", content="You are a senior CRM analytics consultant. Provide actionable, data-driven insights. Return ONLY valid JSON."),
            ChatMessage(role="user", content=prompt),
        ],
        model="deepseek-v4-pro",
    )

    try:
        response = await service.gentxt(request)
        raw = response.content.strip()
        json_text = extract_json_block(raw)
        result = json.loads(json_text)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        result["raw_stats"] = {
            "total_leads": total,
            "by_stage": by_stage,
            "by_priority": by_priority,
            "conversion_rate": conversion_rate,
        }
        return result
    except Exception as e:
        logger.error(f"AI report generation failed: {e}")
        return {
            "summary": f"You have {total} leads in your pipeline. {by_stage.get('new_lead', 0)} are new, {by_stage.get('in_progress', 0)} are in progress. Conversion rate: {conversion_rate}%.",
            "metrics": {"total": total, "new": by_stage.get("new_lead", 0), "won": won, "conversion_rate": conversion_rate},
            "action_items": ["Follow up with high-priority leads", "Review new leads from today", "Update pipeline stages", "Send follow-up emails to contacted leads", "Analyze lost leads for patterns"],
            "urgent_leads": [a["name"] for a in recent_activity[:3]],
            "recommendations": ["Focus on converting in-progress leads", "Reach out to new leads within 24 hours", "Improve follow-up cadence"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "raw_stats": {"total_leads": total, "by_stage": by_stage, "by_priority": by_priority, "conversion_rate": conversion_rate},
        }