"""Measuring every business a search returns.

Shared by the interactive search and the scheduled automations, which is the
point: leads found by an automation were arriving unmeasured — no email, no
score — while leads from a manual search arrived complete. Same product, two
different qualities of lead depending on how it was found.

Lives in services rather than in the router because a service importing a
router is backwards, and automations are a service.
"""
import asyncio
import logging
from datetime import datetime, timezone
from time import monotonic

from services.qualification import qualify_website

logger = logging.getLogger(__name__)


# Discovery measures every result it returns, rather than handing back listing
# rows that a separate Qualify step had to complete.
#
# Email is the reason. No listing provider supplies one — google_places.py
# returns "" and mapbox_places.py returns None — so a business's email exists
# only on its own page. An unmeasured lead therefore has nobody to write to,
# which made Qualify not an optional refinement but the step that produced the
# thing the user searched for.
#
# The measurements run concurrently because they are almost entirely network
# wait. In series a twenty-result search would take twenty times the per-site
# timeout and the browser would give up long before it returned.
DISCOVERY_MEASURE_CONCURRENCY = 8

# PageSpeed renders the page and costs 10-20s per lead, so it cannot run for
# every result inside one request. Leads are audited while this budget lasts
# and measured at the free heuristic tier afterwards. evidence_tier on each
# result records which tier produced its score, so a shallower result is
# visibly shallower rather than quietly weaker.
DISCOVERY_AUDIT_BUDGET_SECONDS = 45.0


async def measure_results(results: list) -> None:
    """Measure each discovered business against its own website, in place.

    Merges what the site itself publishes into the listing row: contact email,
    phone and postal address, the social platforms it links to, a website
    score, and the findings that justify that score.

    Never raises. A site that is slow, blocked, parked or simply broken is an
    ordinary outcome of searching a city, not a failure of the search, so that
    business keeps the listing data it arrived with and reports an unmeasured
    site. One unreachable host must not cost the user the whole result set they
    have already paid a credit for.
    """
    if not results:
        return

    started = monotonic()
    semaphore = asyncio.Semaphore(DISCOVERY_MEASURE_CONCURRENCY)

    async def measure_one(biz: dict) -> None:
        async with semaphore:
            # Read inside the semaphore rather than when the task was created,
            # so the budget reflects when this measurement actually begins
            # instead of when it was queued behind seven others.
            within_budget = (monotonic() - started) < DISCOVERY_AUDIT_BUDGET_SECONDS
            try:
                measurement = await qualify_website(
                    biz.get("website_url"), allow_audit=within_budget
                )
            except Exception:
                logger.exception(
                    "Could not measure %r during discovery; keeping its listing data",
                    biz.get("business_name"),
                )
                return

        biz["has_website"] = measurement["has_website"]
        biz["website_state"] = measurement["website_state"]
        biz["website_score"] = measurement["website_score"]
        biz["evidence_tier"] = measurement["evidence_tier"]
        biz["findings"] = measurement["findings"]

        # findings and qualified_at are only claimed when a score was actually
        # established, matching /qualify. A None score means the measurement
        # could not run at all, and recording "[]" plus a timestamp there would
        # assert "checked, found nothing wrong" about a site nobody could read.
        if measurement["website_score"] is not None:
            biz["qualified_at"] = datetime.now(timezone.utc).isoformat()
        else:
            biz["findings"] = None

        if measurement["website_url"]:
            biz["website_url"] = measurement["website_url"]

        # The page is the better source for all of these, but only where it
        # actually yielded something. An unreachable site must not blank a
        # phone number the listing provider did supply — that would make
        # measuring a lead strictly worse than not measuring it.
        for field in ("contact_email", "contact_phone"):
            if measurement.get(field):
                biz[field] = measurement[field]
        if measurement.get("postal_address"):
            biz["full_address"] = measurement["postal_address"]
        if measurement.get("social_links") is not None:
            biz["social_platforms"] = measurement["social_links"]

    await asyncio.gather(*(measure_one(biz) for biz in results))
