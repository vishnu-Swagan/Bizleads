"""Measure website quality from the response Pass 2 already fetched.

This is the zero-cost tier of website scoring. `website_check` downloads the
page to decide whether a site is live; this module reads the same bytes to
decide whether it is any good. No second request, no API key, no quota, no
rate limit.

It is deliberately weaker than Lighthouse on raw performance, and it does not
pretend otherwise — `evidence_tier` on the result says which tier produced the
score so a user can see how much to trust it.

What it measures is chosen for what actually sells a rebuild, not for what is
easy to count. A missing mobile viewport is worth more than a missing meta
description because the first makes the site unusable on a phone and the
second costs some search traffic.

Every finding carries the evidence that produced it, so "Why this score?" can
show a fact rather than a number.
"""
import re
from typing import Any, Dict, List, Optional, TypedDict

SCORE_VERSION = "site-signals-1.0.0"
EVIDENCE_TIER = "heuristic"

# Slower than this and a visitor notices; slower than SLOW and many leave.
TTFB_OK_SECONDS = 1.5
TTFB_SLOW_SECONDS = 3.0
HEAVY_PAGE_BYTES = 3 * 1024 * 1024
CURRENT_YEAR = 2026


class Finding(TypedDict):
    id: str
    label: str
    penalty: int
    evidence: str
    category: str


def _re(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def extract_signals(
    html: str,
    *,
    final_url: str,
    elapsed_seconds: Optional[float] = None,
    content_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    """Pull raw, checkable facts out of a fetched page. No judgement here."""
    low = html.lower()
    img_tags = re.findall(r"<img\b[^>]*>", low)
    jquery = re.search(r"jquery[.\-]?(\d+)\.(\d+)", low)
    copyright_years = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)\s*(20\d{2})", low)]

    return {
        "https": final_url.lower().startswith("https://"),
        "elapsed_seconds": elapsed_seconds,
        "content_bytes": content_bytes,
        "has_viewport_meta": _re(r'<meta[^>]+name=["\']viewport["\']', low),
        "has_title": _re(r"<title[^>]*>\s*\S", low),
        "has_meta_description": _re(r'<meta[^>]+name=["\']description["\']', low),
        "has_h1": "<h1" in low,
        "image_count": len(img_tags),
        "images_without_alt": sum(1 for tag in img_tags if "alt=" not in tag),
        "has_form": "<form" in low,
        "has_tel_link": 'href="tel:' in low or "href='tel:" in low,
        "has_mailto_link": 'href="mailto:' in low or "href='mailto:" in low,
        "has_schema_markup": "application/ld+json" in low or "itemtype=" in low,
        "is_wordpress": "wp-content" in low or "wp-includes" in low,
        "jquery_major": int(jquery.group(1)) if jquery else None,
        "newest_copyright_year": max(copyright_years) if copyright_years else None,
        "social_links": sorted(
            {
                platform
                for platform in ("facebook", "instagram", "twitter", "linkedin", "tiktok", "youtube")
                if f"{platform}.com" in low
            }
        ),
    }


def score_signals(signals: Dict[str, Any]) -> Dict[str, Any]:
    """Turn facts into a 0-100 score plus the findings that justify it.

    Starts at 100 and deducts for measured defects. A check that could not run
    contributes nothing rather than a default penalty — an unmeasurable site
    must not score worse than a measured good one.
    """
    findings: List[Finding] = []

    def deduct(fid: str, label: str, penalty: int, evidence: str, category: str) -> None:
        findings.append({"id": fid, "label": label, "penalty": penalty, "evidence": evidence, "category": category})

    # Mobile usability — the strongest single pitch. A site with no viewport
    # meta renders desktop-width on a phone and is effectively unusable.
    if not signals.get("has_viewport_meta"):
        deduct("no_viewport", "Not mobile-friendly", 30,
               "No <meta name='viewport'> — the page renders at desktop width on phones", "mobile")

    if not signals.get("https"):
        deduct("no_https", "No HTTPS", 20,
               "Served over plain HTTP; browsers mark it 'Not secure'", "security")

    elapsed = signals.get("elapsed_seconds")
    if isinstance(elapsed, (int, float)):
        if elapsed > TTFB_SLOW_SECONDS:
            deduct("very_slow", "Very slow to load", 15,
                   f"Took {elapsed:.1f}s to respond", "performance")
        elif elapsed > TTFB_OK_SECONDS:
            deduct("slow", "Slow to load", 8, f"Took {elapsed:.1f}s to respond", "performance")

    size = signals.get("content_bytes")
    if isinstance(size, int) and size > HEAVY_PAGE_BYTES:
        deduct("heavy_page", "Heavy page", 8, f"{round(size / 1024 / 1024, 1)}MB of HTML", "performance")

    # Conversion — a site with no way to contact the business cannot convert.
    if not any((signals.get("has_tel_link"), signals.get("has_form"), signals.get("has_mailto_link"))):
        deduct("no_contact_route", "No way to make contact", 12,
               "No tap-to-call link, contact form or email link found", "conversion")
    elif not signals.get("has_tel_link"):
        deduct("no_tel_link", "No tap-to-call link", 5,
               "Mobile visitors cannot tap to phone the business", "conversion")

    if not signals.get("has_title"):
        deduct("no_title", "No page title", 12, "Missing <title> — search results show the URL", "seo")
    if not signals.get("has_meta_description"):
        deduct("no_meta_description", "No meta description", 8,
               "Search engines write their own snippet", "seo")
    if not signals.get("has_h1"):
        deduct("no_h1", "No main heading", 5, "No <h1> on the page", "seo")
    if not signals.get("has_schema_markup"):
        deduct("no_schema", "No structured data", 4,
               "No schema.org markup — no rich results in search", "seo")

    images = signals.get("image_count") or 0
    missing_alt = signals.get("images_without_alt") or 0
    if images >= 3 and missing_alt / images > 0.5:
        deduct("images_no_alt", "Images missing alt text", 8,
               f"{missing_alt} of {images} images have no alt attribute", "accessibility")

    jquery_major = signals.get("jquery_major")
    if isinstance(jquery_major, int) and jquery_major < 3:
        deduct("old_jquery", "Outdated JavaScript library", 5,
               f"Runs jQuery {jquery_major}.x, superseded in 2016", "stack")

    newest_year = signals.get("newest_copyright_year")
    if isinstance(newest_year, int) and newest_year < CURRENT_YEAR - 1:
        deduct("stale_copyright", "Site looks unmaintained", 5,
               f"Copyright notice still says {newest_year}", "stack")

    score = max(0, min(100, 100 - sum(f["penalty"] for f in findings)))

    if score < 15:
        band = "parked"
    elif score < 40:
        band = "weak"
    elif score < 70:
        band = "moderate"
    else:
        band = "healthy"

    return {
        "website_score": score,
        "website_state": band,
        "findings": sorted(findings, key=lambda f: f["penalty"], reverse=True),
        "evidence_tier": EVIDENCE_TIER,
        "score_version": SCORE_VERSION,
        "signals": signals,
    }


def analyse(html: str, *, final_url: str, elapsed_seconds: Optional[float] = None,
            content_bytes: Optional[int] = None) -> Dict[str, Any]:
    """Convenience: extract then score in one call."""
    return score_signals(
        extract_signals(html, final_url=final_url, elapsed_seconds=elapsed_seconds, content_bytes=content_bytes)
    )
