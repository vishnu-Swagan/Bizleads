import logging
import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from core.database import get_db
from core.config import settings
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from models.workspaces import Workspaces
from models.credit_ledger import Credit_ledger
from dependencies.tenancy import ensure_workspace_for_user

import stripe

# Configure Stripe API key from environment
_stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
if _stripe_key:
    stripe.api_key = _stripe_key
else:
    logging.getLogger(__name__).warning("STRIPE_SECRET_KEY not set - billing endpoints will fail")

# Handle both old (stripe.error.*) and new (stripe.*) exception styles
StripeAuthenticationError = getattr(stripe, 'AuthenticationError', None) or getattr(getattr(stripe, 'error', None), 'AuthenticationError', Exception)
StripeInvalidRequestError = getattr(stripe, 'InvalidRequestError', None) or getattr(getattr(stripe, 'error', None), 'InvalidRequestError', Exception)
StripeAPIError = getattr(stripe, 'APIError', None) or getattr(getattr(stripe, 'error', None), 'APIError', Exception)

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

logger = logging.getLogger(__name__)

PLANS = {
    "trial": {"name": "Trial", "price": 0, "credits": 25, "seats": 1},
    "solo": {"name": "Solo", "price": 2900, "credits": 300, "seats": 1},
    "pro": {"name": "Pro", "price": 7900, "credits": 1500, "seats": 3},
    "agency": {"name": "Agency", "price": 19900, "credits": 5000, "seats": 10},
}


class CreateCheckoutRequest(BaseModel):
    plan: str
    annual: bool = False
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    session_id: str
    url: str


class VerifyPaymentRequest(BaseModel):
    session_id: str


class CreditTopUpRequest(BaseModel):
    credits: int
    success_url: str
    cancel_url: str


@router.get("/plans")
async def get_plans():
    """Get available subscription plans"""
    return {
        "plans": [
            {
                "id": "solo",
                "name": "Solo",
                "price_monthly": 29,
                "price_annual": 290,
                "credits": 300,
                "seats": 1,
                "features": [
                    "300 monthly discovery credits",
                    "1 team seat",
                    "Full scoring system",
                    "Lead pipeline management",
                    "Basic analytics",
                    "CSV export",
                ]
            },
            {
                "id": "pro",
                "name": "Pro",
                "price_monthly": 79,
                "price_annual": 790,
                "credits": 1500,
                "seats": 3,
                "features": [
                    "1,500 monthly discovery credits",
                    "3 team seats",
                    "Saved search monitoring",
                    "Advanced analytics & funnel",
                    "White-label Proof Rooms",
                    "Integrations & API access",
                    "Priority job processing",
                ]
            },
            {
                "id": "agency",
                "name": "Agency",
                "price_monthly": 199,
                "price_annual": 1990,
                "credits": 5000,
                "seats": 10,
                "features": [
                    "5,000 monthly discovery credits",
                    "10 team seats",
                    "Lead reservations",
                    "Advanced analytics & calibration",
                    "CRM/API access",
                    "Priority processing",
                    "Dedicated support",
                    "Custom integrations",
                ]
            },
        ],
        "trial": {
            "duration_days": 7,
            "credits": 25,
            "limitations": ["Watermarked Proof Rooms", "No bulk export", "Limited saves"]
        }
    }


@router.get("/usage")
async def get_usage(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current workspace usage and entitlements"""
    workspace = await ensure_workspace_for_user(current_user, db)

    plan_info = PLANS.get(workspace.plan, PLANS["trial"])
    credits_remaining = workspace.monthly_credits - workspace.credits_used

    return {
        "workspace_id": workspace.id,
        "plan": workspace.plan,
        "plan_name": plan_info["name"],
        "subscription_status": workspace.subscription_status,
        "credits_total": workspace.monthly_credits,
        "credits_used": workspace.credits_used,
        "credits_remaining": max(0, credits_remaining),
        "max_seats": workspace.max_seats,
        "trial_ends_at": workspace.trial_ends_at,
        "credits_reset_at": workspace.credits_reset_at,
    }


@router.post("/create-checkout", response_model=CheckoutResponse)
async def create_checkout(
    data: CreateCheckoutRequest,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe checkout session for subscription"""
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Payment service is not configured. Please contact support.")

    if data.plan not in ["solo", "pro", "agency"]:
        raise HTTPException(status_code=400, detail="Invalid plan selected")

    plan = PLANS[data.plan]

    # Resolve frontend host for redirect URLs
    frontend_host = request.headers.get("App-Host")
    if frontend_host and not frontend_host.startswith(("http://", "https://")):
        frontend_host = f"https://{frontend_host}"

    # Use client-provided URLs as primary, fall back to App-Host derived URLs
    success_url = data.success_url or (f"{frontend_host}/app/settings/billing" if frontend_host else None)
    cancel_url = data.cancel_url or (f"{frontend_host}/pricing" if frontend_host else None)

    if not success_url or not cancel_url:
        raise HTTPException(status_code=400, detail="Unable to determine redirect URLs. Please provide success_url and cancel_url.")

    # Ensure success_url has session_id parameter for verification
    if "session_id" not in success_url:
        separator = "&" if "?" in success_url else "?"
        success_url = f"{success_url}{separator}session_id={{CHECKOUT_SESSION_ID}}"

    # Calculate price - server-side authoritative pricing
    unit_amount = plan["price"]
    interval = "month"
    if data.annual:
        unit_amount = int(plan["price"] * 10)  # 2 months free
        interval = "year"

    try:
        # Build session kwargs - omit customer_email if empty/None
        session_kwargs = {
            "payment_method_types": ["card"],
            "line_items": [{
                "price_data": {
                    # All plans are billed in USD; non-US customers are charged in USD
                    # at their card network's exchange rate (disclosed on the Pricing
                    # page). Stripe Tax (automatic_tax={"enabled": True}) is NOT enabled
                    # here: it requires Stripe Tax to be configured in the Dashboard
                    # (origin address, tax registrations, product tax codes) first.
                    # Enabling it without that configuration would error out or silently
                    # miscalculate tax on every checkout. To turn this on: configure
                    # Stripe Tax in the Dashboard for Torque Trends LLC (Kentucky, US),
                    # then set automatic_tax={"enabled": True} on the session and add
                    # customer_update={"address": "auto"} / collect billing address so
                    # Stripe can determine the customer's tax jurisdiction.
                    "currency": "usd",
                    "product_data": {
                        "name": f"BizLeads {plan['name']} Plan",
                        "description": f"{plan['credits']} monthly credits, {plan['seats']} seat(s)",
                    },
                    "unit_amount": unit_amount,
                    "recurring": {"interval": interval},
                },
                "quantity": 1,
            }],
            "mode": "subscription",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {
                "user_id": current_user.id,
                "plan": data.plan,
                "annual": str(data.annual),
            },
        }

        # Only include customer_email if it's a non-empty valid string
        email = getattr(current_user, 'email', None)
        if email and isinstance(email, str) and email.strip():
            session_kwargs["customer_email"] = email.strip()

        session = stripe.checkout.Session.create(**session_kwargs)

        if not session.url:
            logger.error(f"Stripe session created but no URL returned. Session ID: {session.id}, status: {session.status}")
            raise HTTPException(status_code=500, detail="Checkout session created but no redirect URL was provided by Stripe.")

        return CheckoutResponse(session_id=session.id, url=session.url)
    except HTTPException:
        raise
    except StripeAuthenticationError as e:
        logger.error(f"Stripe authentication error: {e}")
        raise HTTPException(status_code=500, detail="Payment service configuration error. Please contact support.")
    except StripeInvalidRequestError as e:
        logger.error(f"Stripe invalid request: {e}")
        raise HTTPException(status_code=400, detail=f"Payment request error: {str(e)}")
    except Exception as e:
        logger.error(f"Checkout creation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create checkout: {str(e)}")


@router.post("/verify-payment")
async def verify_payment(
    data: VerifyPaymentRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify a completed checkout and activate the subscription.

    Guards, in order: the session must belong to the caller, must be paid, and
    must not have been applied before. Without the last guard a single purchase
    could be replayed to reset credit usage indefinitely.
    """
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Payment service is not configured. Please contact support.")

    if not data.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    try:
        session = stripe.checkout.Session.retrieve(data.session_id)
    except StripeInvalidRequestError as e:
        logger.error(f"Invalid session_id: {e}")
        raise HTTPException(status_code=400, detail="Invalid checkout session")
    except Exception as e:
        logger.error(f"Stripe retrieval error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve payment session")

    metadata = session.metadata or {}
    if metadata.get("user_id") != current_user.id:
        logger.warning("Checkout session %s does not belong to the calling user", data.session_id)
        raise HTTPException(status_code=403, detail="This checkout session does not belong to your account")

    plan = metadata.get("plan", "solo")
    plan_info = PLANS.get(plan, PLANS["solo"])

    if session.status != "complete" or getattr(session, "payment_status", None) != "paid":
        return {"status": session.status or "pending", "plan": plan}

    workspace = await ensure_workspace_for_user(current_user, db)

    existing = await db.execute(
        select(Credit_ledger).where(Credit_ledger.reference_id == session.id)
    )
    if existing.scalars().first():
        # Already applied. Report current state; mutate nothing.
        return {
            "status": "active",
            "plan": workspace.plan,
            "plan_name": PLANS.get(workspace.plan, plan_info)["name"],
            "credits": workspace.monthly_credits,
            "already_applied": True,
        }

    workspace.plan = plan
    workspace.subscription_status = "active"
    workspace.monthly_credits = plan_info["credits"]
    workspace.max_seats = plan_info["seats"]
    workspace.stripe_customer_id = session.customer or ""
    workspace.stripe_subscription_id = session.subscription or ""
    workspace.credits_used = 0
    workspace.credits_reset_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    db.add(Credit_ledger(
        workspace_id=workspace.id,
        amount=plan_info["credits"],
        balance_after=plan_info["credits"],
        action="subscription_activated",
        description=f"{plan_info['name']} plan activated",
        reference_id=session.id,
        idempotency_key=session.id,
    ))

    await db.commit()

    return {
        "status": "active",
        "plan": plan,
        "plan_name": plan_info["name"],
        "credits": plan_info["credits"],
    }


@router.post("/deduct-credit")
async def deduct_credit(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deduct one credit for a search/action"""
    result = await db.execute(
        select(Workspaces).where(Workspaces.owner_id == current_user.id).order_by(Workspaces.id.asc()).limit(1)
    )
    workspace = result.scalars().first()

    if not workspace:
        raise HTTPException(status_code=404, detail="No workspace found")

    remaining = workspace.monthly_credits - workspace.credits_used
    if remaining <= 0:
        raise HTTPException(
            status_code=403,
            detail="No credits remaining. Please upgrade your plan or purchase a credit top-up."
        )

    workspace.credits_used += 1
    await db.commit()

    return {
        "credits_remaining": workspace.monthly_credits - workspace.credits_used,
        "credits_used": workspace.credits_used,
    }