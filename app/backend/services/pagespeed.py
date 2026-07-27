"""
Google PageSpeed Insights API integration for website performance audits.
Provides performance, accessibility, SEO, and best practices scores for lead websites.
"""
import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

def _api_key() -> str:
    """Read the key at call time, never at import.

    As a module constant this was captured once when the process started,
    which put it out of reach of a .env loaded later and of any test that
    sets it. The same pattern has already caused two production bugs in this
    codebase (the MapBox token and the SMTP credentials).
    """
    return os.environ.get("PAGESPEED_API_KEY", "").strip()


# PageSpeed genuinely renders the page, so it is slow — commonly 10-20s, and
# occasionally far worse. 60s was too generous once qualification runs it per
# lead: ten leads could occupy ten minutes while the browser gave up at two.
# A request that has not answered in 30s is not going to rescue the batch.
AUDIT_TIMEOUT_SECONDS = 30.0
PAGESPEED_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def is_pagespeed_configured() -> bool:
    """Check if PageSpeed Insights API key is available."""
    return bool(_api_key())


async def audit_website(url: str, strategy: str = "mobile") -> Optional[dict]:
    """
    Run a PageSpeed Insights audit on a website URL.

    Args:
        url: The website URL to audit
        strategy: 'mobile' or 'desktop'

    Returns:
        Dict with performance metrics or None if audit fails
    """
    if not _api_key():
        logger.warning("PageSpeed API key not configured")
        return None

    if not url or not url.startswith(("http://", "https://")):
        # Try adding https://
        if url and not url.startswith("http"):
            url = f"https://{url}"
        else:
            return None

    params = {
        "url": url,
        "key": _api_key(),
        "strategy": strategy,
        "category": ["performance", "accessibility", "seo", "best-practices"],
    }

    try:
        async with httpx.AsyncClient(timeout=AUDIT_TIMEOUT_SECONDS) as client:
            response = await client.get(PAGESPEED_URL, params=params)

            if response.status_code != 200:
                logger.error(f"PageSpeed API error: {response.status_code} - {response.text[:300]}")
                return None

            data = response.json()
            return _parse_audit_result(data, url, strategy)

    except httpx.TimeoutException:
        logger.error(f"PageSpeed API timeout for URL: {url}")
        return {"url": url, "error": "timeout", "message": "Audit timed out - site may be slow or unreachable"}
    except Exception as e:
        logger.error(f"PageSpeed API error: {e}")
        return None


async def bulk_audit(urls: list[str], strategy: str = "mobile") -> list[dict]:
    """
    Audit multiple websites. Returns results for each URL.
    Processes sequentially to respect API rate limits.
    """
    results = []
    for url in urls[:10]:  # Limit to 10 to avoid rate limiting
        result = await audit_website(url, strategy)
        if result:
            results.append(result)
    return results


def _parse_audit_result(data: dict, url: str, strategy: str) -> dict:
    """Parse the PageSpeed Insights API response into a clean format."""
    lighthouse = data.get("lighthouseResult", {})
    categories = lighthouse.get("categories", {})
    audits = lighthouse.get("audits", {})

    # Extract category scores (0-1 scale, convert to 0-100)
    performance_score = _get_category_score(categories, "performance")
    accessibility_score = _get_category_score(categories, "accessibility")
    seo_score = _get_category_score(categories, "seo")
    best_practices_score = _get_category_score(categories, "best-practices")

    # Extract key metrics
    metrics = {}
    metric_keys = {
        "first-contentful-paint": "fcp",
        "largest-contentful-paint": "lcp",
        "total-blocking-time": "tbt",
        "cumulative-layout-shift": "cls",
        "speed-index": "speed_index",
        "interactive": "tti",
    }

    for audit_key, metric_name in metric_keys.items():
        audit = audits.get(audit_key, {})
        metrics[metric_name] = {
            "value": audit.get("numericValue"),
            "display": audit.get("displayValue", "N/A"),
            "score": int((audit.get("score", 0) or 0) * 100),
        }

    # Extract key opportunities (things to fix)
    opportunities = []
    opportunity_audits = [
        "render-blocking-resources",
        "unused-css-rules",
        "unused-javascript",
        "modern-image-formats",
        "uses-optimized-images",
        "uses-responsive-images",
        "efficient-animated-content",
        "unminified-css",
        "unminified-javascript",
        "uses-text-compression",
        "uses-long-cache-ttl",
        "dom-size",
        "redirects",
        "server-response-time",
    ]

    for key in opportunity_audits:
        audit = audits.get(key, {})
        score = audit.get("score")
        if score is not None and score < 0.9:  # Only include failing/warning audits
            opportunities.append({
                "id": key,
                "title": audit.get("title", key),
                "description": audit.get("description", "")[:200],
                "score": int((score or 0) * 100),
                "savings": audit.get("displayValue", ""),
            })

    # Overall website quality score (weighted average)
    overall_score = int(
        performance_score * 0.4 +
        seo_score * 0.25 +
        accessibility_score * 0.2 +
        best_practices_score * 0.15
    )

    return {
        "url": url,
        "strategy": strategy,
        "overall_score": overall_score,
        "scores": {
            "performance": performance_score,
            "accessibility": accessibility_score,
            "seo": seo_score,
            "best_practices": best_practices_score,
        },
        "metrics": metrics,
        "opportunities": opportunities[:8],  # Top 8 opportunities
        "opportunities_count": len(opportunities),
        "is_mobile_friendly": seo_score >= 70 and performance_score >= 50,
        "needs_redesign": overall_score < 40,
        "quality_tier": _get_quality_tier(overall_score),
    }


def _get_category_score(categories: dict, category_name: str) -> int:
    """Extract a category score as 0-100 integer."""
    cat = categories.get(category_name, {})
    score = cat.get("score")
    if score is not None:
        return int(score * 100)
    return 0


def _get_quality_tier(score: int) -> str:
    """Determine website quality tier from overall score."""
    if score >= 80:
        return "good"
    elif score >= 60:
        return "moderate"
    elif score >= 40:
        return "needs_improvement"
    else:
        return "poor"