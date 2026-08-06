"""Working out where a request actually came from.

Behind a proxy, `request.client.host` is the proxy. The real client address is
in `X-Forwarded-For`, which is a client-controlled header: anyone can send
`X-Forwarded-For: 1.2.3.4` and be believed. That matters here specifically,
because this address is used to decide whether somebody is opening several
accounts, and the person doing that is exactly the person who would forge it.

The mitigation is to take the LAST entry rather than the first. A forwarding
proxy appends the address it saw, so the rightmost entries are the ones added
by infrastructure we control and the leftmost is whatever the client claimed.
Render puts one proxy in front of the app, so the last entry is the address
its edge observed.

This is a signal for a human to review, never an automatic ban, and it is
treated that way throughout: a forged header can make two accounts look
related, and it must not be able to delete anybody by itself.
"""
import logging
from typing import Optional, Tuple

from fastapi import Request

logger = logging.getLogger(__name__)

# Headers that carry a country when a CDN sets one. Render alone does not, so
# nothing may depend on a country being present.
_COUNTRY_HEADERS = ("cf-ipcountry", "x-vercel-ip-country", "x-country-code")

MAX_USER_AGENT_CHARS = 400


def client_ip(request: Optional[Request]) -> Optional[str]:
    """The caller's address, or None when it cannot be established."""
    if request is None:
        return None

    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        # Rightmost is what our own edge saw; leftmost is client-supplied.
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1][:64]

    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip[:64]

    if request.client and request.client.host:
        return request.client.host[:64]

    return None


def client_country(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    for header in _COUNTRY_HEADERS:
        value = (request.headers.get(header) or "").strip()
        # Cloudflare sends XX when it does not know, which is not a country.
        if value and value.upper() not in {"XX", "T1"}:
            return value.upper()[:8]
    return None


def client_user_agent(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    return (request.headers.get("user-agent") or "")[:MAX_USER_AGENT_CHARS] or None


def describe(request: Optional[Request]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """(ip, country, user_agent) for one request."""
    return client_ip(request), client_country(request), client_user_agent(request)
