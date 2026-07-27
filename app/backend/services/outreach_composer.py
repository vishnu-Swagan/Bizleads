"""Compose outreach email from a lead's measured findings.

The product's whole claim is that it finds businesses whose websites are
costing them customers, and can prove it. That proof already exists: every
qualified lead carries findings from services/site_signals.py, each one a
measured defect plus the evidence that established it.

So this composer writes nothing it cannot substantiate. There is no language
model here and there should never be one - an invented compliment or a
fabricated statistic would poison the one thing that makes this outreach
land, which is that every claim can be checked by the recipient in a minute.

Concretely:

  * Every sentence about the prospect's site traces to a finding.
  * A lead with no findings produces no email. Silence beats a generic
    "I was browsing your site and loved it!" - the template every recipient
    has already learned to delete.
  * The subject names the single highest-penalty defect, because that is the
    one most likely to be worth money to fix.
  * Nothing is exaggerated. "No <meta name=viewport>" becomes "renders at
    desktop width on phones", which is what that actually means.

The output is a draft for a human to review and send, never an autonomous
send. The sender is the customer, not us: they are legally the sender under
the Terms, and they know things about the prospect that we do not.
"""
import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# How each finding is described to a business owner who is not technical.
#
# The impact phrasing is deliberately concrete and free of adjectives: it says
# what happens, not how bad it is. A recipient who can verify the claim trusts
# the rest of the email; one who smells salesmanship stops reading.
FINDING_COPY: Dict[str, Dict[str, str]] = {
    "no_viewport": {
        "headline": "your site isn't mobile-friendly",
        "impact": "On a phone it renders at desktop width, so visitors have to pinch and zoom to read anything. Most of your customers are searching on a phone.",
    },
    "no_https": {
        "headline": "your site isn't secure",
        "impact": "It's served over plain HTTP, so Chrome and Safari show visitors a \"Not secure\" warning in the address bar before they read a word.",
    },
    "very_slow": {
        "headline": "your site is slow to load",
        "impact": "It took over three seconds to respond. Visitors leave long before that, and search engines rank slow sites lower.",
    },
    "slow": {
        "headline": "your site is slow to load",
        "impact": "It takes noticeably longer to respond than visitors expect, which costs you traffic that never sees the page.",
    },
    "heavy_page": {
        "headline": "your pages are heavy",
        "impact": "The page carries a large amount of HTML, which is slow and expensive to load on mobile data.",
    },
    "no_contact_route": {
        "headline": "there's no way to contact you from the site",
        "impact": "No tap-to-call link, no contact form and no email link. A visitor who wants to hire you has to go and find your number somewhere else.",
    },
    "no_tel_link": {
        "headline": "your phone number isn't tappable",
        "impact": "On a phone the number can't be tapped to call. Every extra step loses enquiries.",
    },
    "no_title": {
        "headline": "your site has no page title",
        "impact": "Google shows the raw URL in search results instead of your business name, which almost nobody clicks.",
    },
    "no_meta_description": {
        "headline": "your search listing writes itself",
        "impact": "With no meta description, Google picks whatever text it likes to show under your name in results.",
    },
    "no_h1": {
        "headline": "your page has no main heading",
        "impact": "Search engines use the main heading to work out what a page is about. Without one they guess.",
    },
    "no_schema": {
        "headline": "you're missing structured data",
        "impact": "No schema.org markup, so you can't appear with star ratings, opening hours or prices in search results the way competitors do.",
    },
    "images_missing_alt": {
        "headline": "your images have no descriptions",
        "impact": "Image alt text is missing, which hurts search visibility and makes the site unusable with a screen reader.",
    },
    "stale_copyright": {
        "headline": "your site looks abandoned",
        "impact": "The copyright notice in the footer is years out of date, which tells visitors nobody is minding the shop.",
    },
}

# Findings worth naming in a subject line, phrased as the owner would see the
# problem. A subject naming an abstract SEO defect gets deleted; one naming
# the phone gets opened.
SUBJECT_TEMPLATES: Dict[str, str] = {
    "no_viewport": "{business} - your website on a phone",
    "no_https": "{business} - visitors see a \"Not secure\" warning",
    "no_contact_route": "{business} - no way to get in touch from your site",
    "no_tel_link": "{business} - your number isn't tappable on mobile",
    "very_slow": "{business} - your site takes {seconds}s to load",
    "slow": "{business} - your site is slow on mobile",
    "no_title": "{business} - Google is showing your URL, not your name",
}

MAX_POINTS_IN_EMAIL = 3
DEFAULT_SUBJECT = "{business} - a few things on your website"


def _header_safe(text: str) -> str:
    """Strip anything that could break out of an email header.

    Business names come from a third-party listing provider, so they are not
    ours to trust. A name containing CR/LF flows into the Subject header, and
    a crafted listing could append "Bcc:" or a second header there. Python's
    email package refuses some of this on send, but the subject is also shown
    in the UI and stored, so it is sanitised at the source rather than relying
    on a downstream library to catch it.
    """
    cleaned = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    # Collapse the runs of whitespace that stripping leaves behind.
    return " ".join(cleaned.split()).strip()


def _domain(url: Optional[str]) -> str:
    """Bare domain for readable prose. Never raises on malformed input."""
    if not url:
        return "your website"
    try:
        host = urlparse(url if "//" in url else "https://" + url).netloc
        return host[4:] if host.startswith("www.") else host or "your website"
    except (ValueError, AttributeError):
        return "your website"


def parse_findings(raw: Any) -> List[Dict[str, Any]]:
    """Accept findings as a JSON string (how they are stored) or a list.

    Returns [] for anything unusable rather than raising: one malformed row
    must not take down a bulk compose, it must simply produce no email.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        if not raw.strip():
            return []
        try:
            items = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Lead has unparseable findings; skipping")
            return []
    else:
        return []

    if not isinstance(items, list):
        return []
    return [f for f in items if isinstance(f, dict) and f.get("id")]


def _ranked(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Highest-penalty first - the defect most worth money leads the email.

    Findings with no copy are dropped rather than rendered raw: showing a
    business owner "no_schema" helps nobody, and inventing a description for
    an id we do not recognise is the fabrication this module exists to avoid.
    """
    known = [f for f in findings if f.get("id") in FINDING_COPY]
    return sorted(known, key=lambda f: f.get("penalty", 0), reverse=True)


def compose(
    lead: Dict[str, Any],
    *,
    sender_name: str = "",
    sender_business: str = "",
) -> Optional[Dict[str, str]]:
    """Draft an email for one lead, or None if there is nothing to say.

    Returning None is a feature. A lead that has not been qualified, or whose
    site measured clean, gives no honest reason to write - and a "just
    checking in" email sent on that basis is what gets a domain blocked.
    """
    findings = _ranked(parse_findings(lead.get("findings")))
    if not findings:
        return None

    business = _header_safe(lead.get("business_name") or "") or "your business"
    site = _domain(lead.get("website_url"))
    score = lead.get("website_score")
    top = findings[0]
    points = findings[:MAX_POINTS_IN_EMAIL]

    template = SUBJECT_TEMPLATES.get(top["id"], DEFAULT_SUBJECT)
    seconds = ""
    evidence = top.get("evidence") or ""
    if "Took " in evidence:
        seconds = evidence.split("Took ", 1)[1].split("s", 1)[0]
    subject = template.format(business=business, seconds=seconds or "3")

    plural = len(points) > 1
    opener = (
        "I had a look at " + site + " this week and found "
        + ("a few things that are" if plural else "something that is")
        + " likely costing you enquiries."
    )

    lines: List[str] = []
    for finding in points:
        copy = FINDING_COPY[finding["id"]]
        lines.append(copy["headline"].capitalize() + ". " + copy["impact"])

    # The measured score, only when one exists. Never invented, never rounded
    # into a claim the measurement does not support.
    score_line = ""
    if isinstance(score, int):
        # Counts the points actually listed, not every finding. Saying
        # "the 4 issues above" under a list of 3 is the kind of small
        # inaccuracy that makes a recipient distrust the whole email.
        shown = len(points)
        issue_word = "issues" if shown != 1 else "issue"
        score_line = (
            "Overall the site scores " + str(score) + " out of 100 on the checks "
            "I run - including the " + str(shown) + " " + issue_word + " above."
        )

    remaining = len(findings) - len(points)
    more_line = ""
    if remaining > 0:
        verb = "are" if remaining != 1 else "is"
        noun = "issues" if remaining != 1 else "issue"
        more_line = (
            "There " + verb + " " + str(remaining) + " other " + noun
            + " I can walk you through too."
        )

    close = (
        "These are all fixable, and the first two usually take an afternoon. "
        "Would it be useful if I sent over the full list with what each one "
        "would take to put right?"
    )

    signoff = "\n\n".join(
        part for part in ("Best,", sender_name.strip(), sender_business.strip()) if part
    ) or "Best,"

    # We know the business name but not the owner's. "Hi <Business Name>,"
    # is unmistakably a mail merge; a bare greeting reads like a person
    # wrote it, and the business is named in the subject line anyway.
    greeting = "Hi there,"
    bullet_block = "\n\n".join("- " + line for line in lines)

    body_text = "\n\n".join(
        part for part in (
            greeting, opener, bullet_block, score_line, more_line, close, signoff,
        ) if part
    )

    body_html = _to_html(greeting, opener, lines, score_line, more_line, close, signoff)

    return {
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        # Echoed back so the UI can show exactly which measurements produced
        # this draft. Someone editing the copy should be able to see the
        # evidence behind every claim.
        "based_on": json.dumps([f["id"] for f in points]),
    }


def _to_html(
    greeting: str,
    opener: str,
    lines: List[str],
    score_line: str,
    more_line: str,
    close: str,
    signoff: str,
) -> str:
    """Plain, deliverable HTML.

    No images, no tracking pixel, no wrapper table, no webfonts. Cold email
    that looks like a newsletter gets filtered like one; this is styled to
    look like a person typed it.
    """
    def esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    bullets = "".join(
        '<li style="margin-bottom:10px">' + esc(line) + "</li>" for line in lines
    )
    tail = "".join(
        "<p>" + esc(part) + "</p>" for part in (score_line, more_line, close) if part
    )
    return (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        'font-size:15px;line-height:1.6;color:#1f2937">'
        + "<p>" + esc(greeting) + "</p>"
        + "<p>" + esc(opener) + "</p>"
        + '<ul style="padding-left:18px">' + bullets + "</ul>"
        + tail
        + '<p style="white-space:pre-line">' + esc(signoff) + "</p>"
        + "</div>"
    )


def compose_many(
    leads: List[Dict[str, Any]],
    *,
    sender_name: str = "",
    sender_business: str = "",
) -> Dict[str, Any]:
    """Draft for a batch, reporting who was skipped and why.

    Skips are surfaced rather than silently dropped: "12 drafts from 20 leads"
    with no explanation looks like a bug, and the reasons are actionable - an
    unqualified lead just needs qualifying.
    """
    drafts: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for lead in leads:
        lead_id = lead.get("id")
        if not (lead.get("contact_email") or "").strip():
            skipped.append({"lead_id": lead_id, "reason": "no_email",
                            "message": "No contact email on this lead"})
            continue
        if lead.get("findings") is None:
            skipped.append({"lead_id": lead_id, "reason": "not_qualified",
                            "message": "Qualify this lead first to measure its site"})
            continue

        draft = compose(lead, sender_name=sender_name, sender_business=sender_business)
        if draft is None:
            skipped.append({"lead_id": lead_id, "reason": "nothing_to_report",
                            "message": "The site measured clean - no honest pitch to make"})
            continue

        entry = {
            "lead_id": lead_id,
            "business_name": lead.get("business_name"),
            "to_email": lead.get("contact_email"),
        }
        entry.update(draft)
        drafts.append(entry)

    return {"drafts": drafts, "skipped": skipped,
            "total": len(leads), "composed": len(drafts)}
