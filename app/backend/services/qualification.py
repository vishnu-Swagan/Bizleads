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
from services.site_signals import analyse, extract_signals
from services.website_check import check_website, fetch_page_html, find_contact_urls

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


async def _email_from_contact_pages(
    homepage_html: str, homepage_url: str
) -> Optional[Dict[str, Any]]:
    """Look for a published address on the site's contact-style pages.

    Returns the first address found, with the page it came from, or None.
    Pages are tried in the order find_contact_urls ranks them and the search
    stops at the first hit — the remaining fetches would cost time on every
    lead in a search to improve nothing.

    Sequential rather than concurrent on purpose: most sites answer on the
    first page tried, so firing all of them would double the requests this
    makes against a prospect's server to save a fraction of a second.
    """
    urls = find_contact_urls(homepage_html, homepage_url)
    if not urls:
        return None

    for url in urls:
        html = await fetch_page_html(url)
        if not html:
            continue

        signals = extract_signals(html, final_url=url)
        email = signals.get("contact_email")
        if email:
            return {"email": email, "source_url": url, "signals": signals}

    return None


async def qualify_website(raw_url: Optional[str], *, allow_audit: bool = True) -> Dict[str, Any]:
    """Measure one candidate website. Never guesses.

    Returns the fields a lead needs to become rankable, plus the evidence that
    produced them so a user can disagree with it.

    `allow_audit=False` skips the PageSpeed call and settles for the free
    heuristic tier. Callers use it to stay inside a time budget: PageSpeed
    renders the page and commonly takes 10-20 seconds, so a batch of ten runs
    for minutes while the browser gives up after two. Degrading to the
    heuristic is honest rather than lossy — `evidence_tier` on the result
    records which tier produced the score, so nobody is misled about how much
    to trust it.
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
        # Phone and postal address published on the site itself. The listing
        # provider supplies a phone for some countries and an address for
        # some, inconsistently; these come from the business's own page and
        # so behave the same in every market.
        "contact_phone": None,
        "postal_address": None,
        # Which social platforms the site links to. Measured the same way as
        # everything else here — from the page already fetched — and kept as
        # None rather than [] until a page has actually been read, so "no
        # links found" stays distinguishable from "never looked".
        "social_links": None,
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
        result["contact_phone"] = heuristic["signals"].get("contact_phone")
        result["postal_address"] = heuristic["signals"].get("postal_address")
        result["social_links"] = heuristic["signals"].get("social_links") or []
        result["evidence"]["heuristic"] = {
            "signals": heuristic["signals"],
            "score_version": heuristic["score_version"],
        }
        result["evidence_tier"] = heuristic["evidence_tier"]

        # A homepage very often carries no address; the page called "Contact"
        # is where it lives. Reading only the homepage was the largest single
        # reason a lead arrived with nothing to write to, which made the lead
        # unusable for the one thing this product is for.
        #
        # Only runs when the homepage yielded nothing, so a site that
        # published its address costs no extra requests.
        if not result["contact_email"]:
            found = await _email_from_contact_pages(
                check["html"], check["final_url"] or raw_url or ""
            )
            if found:
                result["contact_email"] = found["email"]
                result["evidence"]["contact_page"] = found["source_url"]
                # Phone and address are worth taking from the same page, but
                # never over something the homepage already established.
                for field in ("contact_phone", "postal_address"):
                    if not result[field] and found["signals"].get(field):
                        result[field] = found["signals"][field]
    else:
        result["evidence"]["quality_note"] = "Site responded but returned no readable HTML"

    audit = None
    if is_pagespeed_configured() and allow_audit:
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
