"""Stripe webhook — the only trustworthy source of billing truth.

Activation previously happened only in /verify-payment, which the browser
calls after checkout. That leaves three ways for money and access to diverge:

  * The customer pays and closes the tab before the redirect. Stripe has
    their money; the workspace is still on a trial.
  * Renewals never activate anything. Month two charges the card, but nothing
    resets credits_used, so a paying customer runs out and stays out.
  * Cancellations, refunds and failed payments are never reflected at all, so
    access continues indefinitely after someone stops paying.

Stripe delivers those events here regardless of what any browser does.

Security: the signature is verified against STRIPE_WEBHOOK_SECRET on the RAW
request body. Without that check this endpoint is an open door to free
subscriptions — anyone could POST a fabricated "payment succeeded" event. An
unset secret disables the endpoint rather than accepting anything.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.workspaces import Workspaces

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])

# Kept in step with PLANS in routers/payments.py. Duplicated deliberately
# rather than imported: that module fails to import when STRIPE_SECRET_KEY is
# absent, and a webhook that cannot load is a webhook that silently drops
# every event Stripe sends.
PLAN_ENTITLEMENTS = {
    "trial": {"credits": 25, "seats": 1},
    "solo": {"credits": 300, "seats": 1},
    "pro": {"credits": 1500, "seats": 3},
    "agency": {"credits": 5000, "seats": 10},
}

HANDLED_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
}


def _verify(payload: bytes, signature: str | None):
    """Verify the Stripe signature, or refuse the request."""
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        # Fails closed. An endpoint that accepts unsigned billing events is a
        # free-subscription vending machine.
        raise HTTPException(
            status_code=503,
            detail="Billing webhook is not configured (STRIPE_WEBHOOK_SECRET unset).",
        )
    if not signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
    try:
        return stripe.Webhook.construct_event(payload, signature, secret)
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed payload")
    except stripe.error.SignatureVerificationError:
        logger.warning("Rejected a webhook with an invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")


async def _workspace_for(db: AsyncSession, *, customer_id: str | None,
                         subscription_id: str | None, owner_id: str | None):
    """Find the workspace an event belongs to.

    Tried in order of reliability: subscription id, then customer id, then the
    owner recorded in checkout metadata. The last is what links the very first
    payment, before either Stripe id has been stored.
    """
    for column, value in (
        (Workspaces.stripe_subscription_id, subscription_id),
        (Workspaces.stripe_customer_id, customer_id),
        (Workspaces.owner_id, owner_id),
    ):
        if not value:
            continue
        result = await db.execute(select(Workspaces).where(column == value).limit(1))
        workspace = result.scalar_one_or_none()
        if workspace:
            return workspace
    return None


def _apply_plan(workspace: Workspaces, plan: str) -> None:
    """Grant a plan's entitlements and start a fresh credit period."""
    entitlements = PLAN_ENTITLEMENTS.get(plan)
    if not entitlements:
        logger.warning("Unknown plan %r on workspace %s; entitlements unchanged",
                       plan, workspace.id)
        return
    workspace.plan = plan
    workspace.monthly_credits = entitlements["credits"]
    workspace.max_seats = entitlements["seats"]
    # A new billing period starts unused. Not doing this is why renewals
    # silently left paying customers with no credits.
    workspace.credits_used = 0
    workspace.credits_reset_at = (
        datetime.now(timezone.utc) + timedelta(days=30)
    ).isoformat()


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Receive billing events from Stripe."""
    # The RAW body is required: any re-serialisation changes the bytes the
    # signature was computed over and every event would be rejected.
    payload = await request.body()
    event = _verify(payload, stripe_signature)

    event_type = event.get("type", "")
    if event_type not in HANDLED_EVENTS:
        # 200 on purpose. A non-2xx makes Stripe retry an event we will never
        # act on, and eventually disables the endpoint.
        return {"received": True, "handled": False, "type": event_type}

    obj = (event.get("data") or {}).get("object") or {}
    metadata = obj.get("metadata") or {}

    customer_id = obj.get("customer")
    subscription_id = (
        obj.get("subscription") if event_type.startswith(("checkout", "invoice"))
        else obj.get("id")
    )

    workspace = await _workspace_for(
        db,
        customer_id=customer_id,
        subscription_id=subscription_id,
        owner_id=metadata.get("user_id") or metadata.get("owner_id"),
    )
    if workspace is None:
        # 200, not 404: retrying will not conjure a workspace, and a failing
        # endpoint eventually gets disabled by Stripe.
        logger.error("No workspace matched %s (customer=%s subscription=%s)",
                     event_type, customer_id, subscription_id)
        return {"received": True, "handled": False, "reason": "workspace_not_found"}

    if event_type in ("checkout.session.completed", "customer.subscription.created"):
        if event_type == "checkout.session.completed" and obj.get("payment_status") != "paid":
            return {"received": True, "handled": False, "reason": "not_paid"}
        plan = metadata.get("plan") or workspace.plan or "solo"
        _apply_plan(workspace, plan)
        workspace.subscription_status = "active"
        if customer_id:
            workspace.stripe_customer_id = customer_id
        if subscription_id:
            workspace.stripe_subscription_id = subscription_id

    elif event_type == "customer.subscription.updated":
        status = obj.get("status", "")
        workspace.subscription_status = status
        plan = metadata.get("plan")
        if plan and plan != workspace.plan:
            _apply_plan(workspace, plan)
        # cancel_at_period_end leaves status "active" until the period ends,
        # so access correctly continues for what has already been paid for.

    elif event_type == "customer.subscription.deleted":
        workspace.subscription_status = "canceled"
        # Entitlements are deliberately NOT stripped here. The customer keeps
        # read access to leads they created and paid for; only new spending is
        # gated, by subscription_status.

    elif event_type == "invoice.paid":
        # The renewal path. Without this, month two charges the card and the
        # customer stays at zero credits.
        billing_reason = obj.get("billing_reason", "")
        if billing_reason in ("subscription_cycle", "subscription_update", "subscription_create"):
            _apply_plan(workspace, workspace.plan or "solo")
        workspace.subscription_status = "active"

    elif event_type == "invoice.payment_failed":
        workspace.subscription_status = "past_due"

    await db.commit()
    logger.info("Applied %s to workspace %s", event_type, workspace.id)
    return {"received": True, "handled": True, "type": event_type,
            "workspace_id": workspace.id}
