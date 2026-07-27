"""Pass 2 of discovery: measure a lead's web presence.

Pass 1 (a geo provider) returns identity but no web presence, so a fresh lead
is unqualified and has no priority score. This module measures what Pass 1
could not, and is the only place permitted to set `has_website` to a definite
value.

Degrades honestly. With no PageSpeed key we can still establish whether a site
exists and whether it is a parking page — enough to separate "no website" from
"has one". Quality banding ("weak" vs "healthy") requires the audit, and
without it the state stays `unknown` rather than guessing a number.
"""
import logging
from typing import Any, Dict, Optional

from services.pagespeed import audit_website, is_pagespeed_configured
from services.site_signals import analyse
from services.website_check import check_website

logger = logging.getLogger(__name__)

# How the four Lighthouse categories combine into one 0-100 website score.
# Performance and SEO dominate because they are what a prospect loses customers
# to; accessibility and best-practices still count because they are part of the
# pitch. Versioned so a score can be traced to the weights that produced it.
AUDIT_WEIGHTS = {
    "performance_score": 0.40,
    "seo_score": 0.30,
    "accessibility_score": 0.15,
    "best_practices_score": 0.15,
}
SCORE_VERSION = "website-quality-1.0.0"


def band_for_score(score: int) -> str:
    """Map a 0-100 website score onto the quality bands used across the app."""
    if score < 15:
        return "parked"
    if score < 40:
        return "weak"
    if score < 70:
        return "moderate"
    return "healthy"


def _blend_audit_scores(audit: Dict[str, Any]) -> Optional[int]:
    """Combine Lighthouse categories into a single 0-100 score.

    Returns None if no category came back, rather than defaulting to zero — an
    audit that measured nothing must not read as a site that scored nothing.
    """
    total = 0.0
    weight_used = 0.0

    for key, weight in AUDIT_WEIGHTS.items():
        value = audit.get(key)
        if isinstance(value, (int, float)):
            total += float(value) * weight
            weight_used += weight

    if weight_used == 0:
        return None

    return round(total / weight_used)


async def qualify_website(raw_url: Optional[str]) -> Dict[str, Any]:
    """Measure one candidate website. Never guesses.

    Returns the fields a lead needs to become rankable, plus the evidence that
    produced them so a user can disagree with it.
    """
    check = await check_website(raw_url)

    result: Dict[str, Any] = {
        "has_website": check["has_website"],
        "website_url": check["final_url"],
        "website_score": None,
        "website_state": "unknown",
        "audit": None,
        "findings": [],
        # An address published on the site itself. The listing provider never
        # supplies one, so without this a qualified lead still has no
        # recipient and outreach cannot be drafted for it at all.
        "contact_email": None,
        "evidence_tier": None,
        "audit_available": is_pagespeed_configured(),
        "evidence": {
            "website_check": check,
            "score_version": SCORE_VERSION,
        },
    }

    state = check["state"]

    if state == "invalid":
        # No candidate URL at all. That is not evidence either way: the business
        # may have a site we simply do not know about.
        result["website_state"] = "unknown"
        return result

    if state == "blocked":
        result["website_state"] = "unknown"
        return result

    if state == "parked":
        result["website_state"] = "parked"
        return result

    if state == "unreachable":
        # Distinguished from "no website" on purpose — the spec lists
        # "temporarily unavailable" as its own state.
        result["website_state"] = "no_website" if check["has_website"] is False else "unreachable"
        return result

    # state == "live": the site exists, so quality is measurable.
    #
    # Three tiers, best available wins, and the result always records which one
    # produced the score so nobody mistakes a heuristic for a Lighthouse run:
    #
    #   heuristic  — free, instant, from bytes already fetched. Always runs.
    #   lighthouse — local Chrome, no API key, slower. Optional.
    #   pagespeed  — Google's hosted Lighthouse, needs a free key. Optional.
    #
    # The heuristic tier runs first and unconditionally: even when a deeper tier
    # is available, its findings are the human-readable "here is what is wrong
    # with your site" list that a deeper score alone does not give you.
    heuristic = None
    if check.get("html"):
        heuristic = analyse(
            check["html"],
            final_url=check["final_url"] or raw_url or "",
            elapsed_seconds=check.get("elapsed_seconds"),
            content_bytes=check.get("content_bytes"),
        )
        result["website_score"] = heuristic["website_score"]
        result["website_state"] = heuristic["website_state"]
        result["findings"] = heuristic["findings"]
        result["contact_email"] = heuristic["signals"].get("contact_email")
        result["evidence"]["heuristic"] = {
            "signals": heuristic["signals"],
            "score_version": heuristic["score_version"],
        }
        result["evidence_tier"] = heuristic["evidence_tier"]
    else:
        result["evidence"]["quality_note"] = "Site responded but returned no readable HTML"

    audit = None
    if is_pagespeed_configured():
        audit = await audit_website(check["final_url"] or raw_url or "")

    if audit and not audit.get("error"):
        score = _blend_audit_scores(audit)
        if score is not None:
            # A real Lighthouse run supersedes the heuristic score, but the
            # heuristic findings stay — they are the sales evidence.
            result["audit"] = audit
            result["website_score"] = score
            result["website_state"] = band_for_score(score)
            result["evidence_tier"] = "pagespeed"
            result["evidence"]["audit_score_version"] = SCORE_VERSION
        else:
            result["evidence"]["quality_note"] = "Audit returned no category scores"
    elif audit and audit.get("error"):
        result["evidence"]["quality_note"] = f"Audit unavailable: {audit.get('message')}"
    elif heuristic is None:
        result["website_state"] = "unknown"

    return result
