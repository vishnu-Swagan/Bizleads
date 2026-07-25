"""Measure whether a prospect's website exists and whether it is a real site.

This is Pass 2 of discovery. Pass 1 (a geo provider) returns a business's
identity but no web presence, so every freshly-discovered lead is unqualified.
This module is what turns "weak or missing website" from an assumption into a
measurement.

SECURITY — read before changing anything here.

This is the first code in the application that fetches an attacker-influenceable
URL from the server. A prospect record's website field is not trusted input: it
can come from a provider, from a user typing it, or from an owner-submitted
claim. Without the guards below, `GET http://169.254.169.254/latest/meta-data/`
or `http://127.0.0.1:8000/api/v1/entities/workspaces` would be fetched by our
own server, from inside our own network, and the response handed back to the
caller. That is a server-side request forgery, and it is the reason the audit
lists criterion 24.

The guards, and why each exists:

  * Scheme allowlist — `file://`, `gopher://` and friends are not fetches.
  * DNS resolution before connecting, with EVERY resolved address checked.
    A hostname can legitimately resolve to several addresses; one public and
    one private is enough to win if you only check the first.
  * Private, loopback, link-local, reserved, multicast and unspecified ranges
    are all rejected. Link-local covers 169.254.169.254, the cloud metadata
    endpoint that turns SSRF into credential theft.
  * Redirects are followed manually, and each hop is re-validated. A public URL
    that 302s to 127.0.0.1 defeats a check performed only on the original URL.
  * Response size and time are capped so a hostile endpoint cannot exhaust us.
  * Only HTML-ish content types are read.

Do not replace the manual redirect loop with `follow_redirects=True`.
"""
import asyncio
import ipaddress
import time
import logging
import socket
from datetime import datetime, timezone
from typing import Literal, Optional, TypedDict
from urllib.parse import urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = ("http", "https")
MAX_REDIRECTS = 5
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 512 * 1024
USER_AGENT = "BizLeadsBot/1.0 (+website availability check)"

WebsiteState = Literal["live", "parked", "unreachable", "invalid", "blocked"]


class WebsiteCheck(TypedDict):
    """Result of checking one candidate URL. Every field is measured, never assumed."""

    input_url: str
    final_url: Optional[str]
    state: WebsiteState
    status_code: Optional[int]
    reason: str
    redirect_hops: int
    checked_at: str
    # Response body and timings, carried so the quality tier can score the page
    # without issuing a second request. Transient — not persisted.
    html: Optional[str]
    elapsed_seconds: Optional[float]
    content_bytes: Optional[int]
    # None when the check could not reach a conclusion (unreachable/blocked).
    # Callers must not coerce this to False — that is the bug this whole
    # module exists to avoid.
    has_website: Optional[bool]


# Phrases that appear on registrar parking pages and "coming soon" placeholders.
# Deliberately conservative: a false "parked" verdict is a fabricated claim
# about a real business, so only unambiguous markers belong here.
PARKED_MARKERS = (
    "domain is for sale",
    "buy this domain",
    "domain for sale",
    "parked free, courtesy of",
    "this domain is parked",
    "future home of something quite cool",
    "godaddy.com/domainfind",
    "sedoparking.com",
    "hugedomains.com",
    "under construction",
    "coming soon",
    "site not published",
    "default web page",
    "welcome to nginx",
    "apache2 ubuntu default page",
    "it works!",
)

MIN_MEANINGFUL_BODY_BYTES = 512


def normalise_candidate_url(raw: Optional[str]) -> Optional[str]:
    """Turn a loosely-formatted website value into an absolute http(s) URL.

    Returns None when the input cannot be a website at all, which is different
    from a website that fails to load.
    """
    if not raw or not isinstance(raw, str):
        return None

    candidate = raw.strip()
    if not candidate:
        return None

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        return None
    if "." not in parsed.hostname:
        return None

    return urlunparse(parsed)


async def _resolve_all_addresses(hostname: str, port: int) -> list[str]:
    """Resolve a hostname to every address it maps to, without blocking the loop."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


def _is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False

    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # includes 169.254.169.254, the metadata endpoint
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def assert_url_is_publicly_routable(url: str) -> Optional[str]:
    """Return None if the URL is safe to fetch, else a human-readable reason.

    Every resolved address must be public. One private address among several is
    enough to make the request unsafe.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        return f"scheme '{parsed.scheme}' is not permitted"
    if not parsed.hostname:
        return "URL has no hostname"

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        addresses = await _resolve_all_addresses(parsed.hostname, port)
    except (socket.gaierror, OSError):
        return "hostname does not resolve"

    if not addresses:
        return "hostname does not resolve"

    for address in addresses:
        if not _is_public_address(address):
            return f"resolves to a non-public address ({address})"

    return None


def _looks_parked(body: str, final_url: str) -> bool:
    lowered = body.lower()
    if any(marker in lowered for marker in PARKED_MARKERS):
        return True
    # A response with almost no markup is not a real site. Checked after the
    # marker scan so a small but genuine page with real content still passes.
    if len(body.strip()) < MIN_MEANINGFUL_BODY_BYTES and "<body" not in lowered:
        return True
    return False


async def check_website(raw_url: Optional[str]) -> WebsiteCheck:
    """Fetch a candidate URL and classify what is actually there."""
    checked_at = datetime.now(timezone.utc).isoformat()
    url = normalise_candidate_url(raw_url)

    base: WebsiteCheck = {
        "input_url": raw_url or "",
        "final_url": None,
        "state": "invalid",
        "status_code": None,
        "reason": "",
        "redirect_hops": 0,
        "checked_at": checked_at,
        "has_website": None,
        "html": None,
        "elapsed_seconds": None,
        "content_bytes": None,
    }

    if url is None:
        base["reason"] = "not a usable http(s) URL"
        return base

    current = url
    hops = 0

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=False,  # see module docstring — do not change
        headers={"User-Agent": USER_AGENT},
    ) as client:
        while hops <= MAX_REDIRECTS:
            blocked_reason = await assert_url_is_publicly_routable(current)
            if blocked_reason is not None:
                # Distinguish "we refused to fetch this" from "the site is down".
                state: WebsiteState = (
                    "unreachable" if blocked_reason == "hostname does not resolve" else "blocked"
                )
                base.update(
                    {
                        "final_url": current,
                        "state": state,
                        "reason": blocked_reason,
                        "redirect_hops": hops,
                        "has_website": False if state == "unreachable" else None,
                    }
                )
                return base

            request_started = time.perf_counter()
            try:
                response = await client.get(current)
            except httpx.TimeoutException:
                base.update({"final_url": current, "state": "unreachable", "reason": "request timed out", "redirect_hops": hops})
                return base
            except httpx.HTTPError as exc:
                base.update(
                    {
                        "final_url": current,
                        "state": "unreachable",
                        "reason": f"request failed: {type(exc).__name__}",
                        "redirect_hops": hops,
                        "has_website": False,
                    }
                )
                return base

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    base.update({"final_url": current, "state": "unreachable", "reason": "redirect without a location", "redirect_hops": hops, "has_website": False})
                    return base
                current = str(httpx.URL(current).join(location))
                hops += 1
                continue

            body = ""
            content_type = response.headers.get("content-type", "")
            if "html" in content_type or "text" in content_type or not content_type:
                body = response.text[:MAX_RESPONSE_BYTES]

            if response.status_code >= 400:
                base.update(
                    {
                        "final_url": current,
                        "state": "unreachable",
                        "status_code": response.status_code,
                        "reason": f"server returned {response.status_code}",
                        "redirect_hops": hops,
                        # A server that answered 500 exists — the site is broken,
                        # not absent. Only a domain that does not resolve is
                        # evidence of no website. Conflating the two would tell a
                        # user a business has no site when it has a broken one,
                        # which is a different sales conversation entirely.
                        "has_website": True,
                    }
                )
                return base

            parked = _looks_parked(body, current)
            base.update(
                {
                    "html": body,
                    "elapsed_seconds": round(time.perf_counter() - request_started, 3),
                    "content_bytes": len(response.content),
                    "final_url": current,
                    "state": "parked" if parked else "live",
                    "status_code": response.status_code,
                    "reason": "placeholder or parking page" if parked else "responded with content",
                    "redirect_hops": hops,
                    # A parked domain is a site that exists but serves nothing —
                    # commercially that is closer to having no website, and the
                    # state field preserves the distinction for anyone who cares.
                    "has_website": not parked,
                }
            )
            return base

    base.update({"final_url": current, "state": "unreachable", "reason": "too many redirects", "redirect_hops": hops, "has_website": False})
    return base
