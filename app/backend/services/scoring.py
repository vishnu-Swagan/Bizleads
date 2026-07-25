"""
BizLeads Multi-Score System

Implements the 6-score model:
1. Need Score (0-100): How deficient the current website/digital presence
2. Buyability Score (0-100): Evidence business is active, viable, growing
3. Timing Score (0-100): Evidence this is a good moment to approach
4. Reachability Score (0-100): Availability of lawful contact routes
5. Agency Fit Score (0-100): Match to subscriber's services/stack/portfolio
6. Evidence Confidence (0-100): Source agreement, freshness, completeness

Priority = 0.30*Need + 0.25*Buyability + 0.20*Timing + 0.15*Reachability + 0.10*AgencyFit
         * confidenceMultiplier - RiskPenalty
"""
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def calculate_priority_score(scores: Dict[str, Any], risk_penalty: int = 0) -> Optional[int]:
    """Calculate weighted priority score from sub-scores.

    Returns None when Need is unmeasured. Need carries the heaviest weight
    (0.30), so substituting a placeholder for it would produce a confident-
    looking ranking derived from a value nobody measured. An unqualified lead
    has no priority until the enrichment pass gives it one.
    """
    need = scores.get("need")
    if need is None:
        return None
    buyability = scores.get("buyability", 0)
    timing = scores.get("timing", 0)
    reachability = scores.get("reachability", 0)
    agency_fit = scores.get("agency_fit", 50)  # default 50 if not personalized
    confidence = scores.get("confidence", 50)

    base = (
        0.30 * need
        + 0.25 * buyability
        + 0.20 * timing
        + 0.15 * reachability
        + 0.10 * agency_fit
    )

    confidence_multiplier = 0.65 + 0.35 * (confidence / 100)
    priority = round(base * confidence_multiplier - risk_penalty)
    return max(0, min(100, priority))


def get_website_state(has_website: Optional[bool], website_score: Optional[int]) -> str:
    """
    Distinguish website states:
    - unknown: not checked yet — NOT the same as "no website"
    - no_website: confirmed to have none
    - parked: domain resolves but is a placeholder
    - weak: exists but poor quality
    - moderate: acceptable but improvable
    - healthy: good website

    `has_website` is Optional on purpose. Discovery providers do not return
    website data, so a freshly-discovered business is `None` (unchecked) until
    the enrichment pass measures it. Treating None as False is how every real
    business ended up labelled "No Website".
    """
    if has_website is None:
        return "unknown"
    if has_website is False:
        return "no_website"
    if website_score is None:
        return "unknown"
    if website_score < 15:
        return "parked"
    if website_score < 40:
        return "weak"
    if website_score < 70:
        return "moderate"
    return "healthy"


def build_score_breakdown(business_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build detailed score breakdown with explanations"""
    # No defaults here. A missing key means "not measured", and defaulting it to
    # 0 or False is what made unqualified leads look like confirmed opportunities.
    website_score = business_data.get("website_score")
    social_score = business_data.get("social_score")
    has_website = business_data.get("has_website")

    # Need Score
    need: Optional[int] = None
    need_factors = []
    if has_website is None:
        need = None
        need_factors.append({
            "factor": "Website status not checked — run deep qualification to measure",
            "impact": 0,
            "source": "system",
        })
    elif has_website is False:
        need = 90
        need_factors.append({"factor": "No website detected", "impact": +40, "source": "audit"})
    elif website_score is None:
        need = None
        need_factors.append({
            "factor": "Website found but not yet audited",
            "impact": 0,
            "source": "system",
        })
    elif website_score < 20:
        need = 80
        need_factors.append({"factor": "Very weak website presence", "impact": +35, "source": "audit"})
    elif website_score < 40:
        need = 60
        need_factors.append({"factor": "Below-average website quality", "impact": +25, "source": "audit"})
    else:
        need = max(0, 100 - website_score)
        need_factors.append({"factor": f"Website score: {website_score}/100", "impact": 0, "source": "audit"})

    if social_score is None:
        need_factors.append({
            "factor": "Social presence not checked",
            "impact": 0,
            "source": "system",
        })
    elif social_score < 20 and need is not None:
        need = min(100, need + 15)
        need_factors.append({"factor": "Minimal social media presence", "impact": +15, "source": "audit"})

    # Buyability Score (based on available signals)
    buyability = business_data.get("buyability_score", 50)
    buyability_factors = business_data.get("buyability_factors", [
        {"factor": "Business appears active (listed/operational)", "impact": +30, "source": "discovery"},
        {"factor": "Baseline estimate - limited commercial data", "impact": 0, "source": "inference"},
    ])

    # Timing Score
    timing = business_data.get("timing_score", 30)
    timing_factors = business_data.get("timing_factors", [
        {"factor": "No specific timing signal detected", "impact": 0, "source": "inference"},
    ])

    # Reachability Score
    reachability = 0
    reachability_factors = []
    contact_email = business_data.get("contact_email", "")
    contact_phone = business_data.get("contact_phone", "")
    if contact_email:
        reachability += 40
        reachability_factors.append({"factor": "Email contact available", "impact": +40, "source": "discovery"})
    if contact_phone:
        reachability += 30
        reachability_factors.append({"factor": "Phone contact available", "impact": +30, "source": "discovery"})
    if not contact_email and not contact_phone:
        reachability = 10
        reachability_factors.append({"factor": "No direct contact found", "impact": -40, "source": "discovery"})

    # Evidence Confidence — must reflect what was actually measured.
    confidence = business_data.get("confidence_score")
    confidence_factors = business_data.get("confidence_factors")
    if confidence is None:
        if has_website is None:
            # Identity came from a provider, but the thing we rank on is unmeasured.
            confidence = 40
            confidence_factors = [
                {"factor": "Identity confirmed by discovery provider", "impact": +25, "source": "provider"},
                {"factor": "Web presence not yet measured", "impact": -35, "source": "system"},
            ]
        else:
            confidence = 70
            confidence_factors = [
                {"factor": "Identity confirmed by discovery provider", "impact": +25, "source": "provider"},
                {"factor": "Website status measured directly", "impact": +25, "source": "audit"},
            ]
    if confidence_factors is None:
        confidence_factors = []

    scores = {
        "need": need,
        "buyability": buyability,
        "timing": timing,
        "reachability": reachability,
        "agency_fit": 50,  # Default until personalized
        "confidence": confidence,
    }

    risk_penalty = business_data.get("risk_penalty", 0)
    priority = calculate_priority_score(scores, risk_penalty)

    return {
        "priority_score": priority,
        # True when the lead cannot be ranked until the enrichment pass measures
        # its web presence. The UI must show this rather than a number.
        "qualification_required": need is None,
        "scores": scores,
        "breakdowns": {
            "need": {"score": need, "factors": need_factors},
            "buyability": {"score": buyability, "factors": buyability_factors},
            "timing": {"score": timing, "factors": timing_factors},
            "reachability": {"score": reachability, "factors": reachability_factors},
            "agency_fit": {"score": 50, "factors": [{"factor": "Default - configure offer profile for personalization", "impact": 0, "source": "system"}]},
            "confidence": {"score": confidence, "factors": confidence_factors},
        },
        "risk_penalty": risk_penalty,
        "risk_reasons": business_data.get("risk_reasons", []),
        "website_state": get_website_state(has_website, website_score),
        "score_version": "1.0.0",
        "weights": {"need": 0.30, "buyability": 0.25, "timing": 0.20, "reachability": 0.15, "agency_fit": 0.10},
    }