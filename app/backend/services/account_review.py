"""Approving new accounts, and noticing when one person opens several.

Two things live here.

**The gate.** A new workspace is created with no credits and a pending
approval row. An operator grants the free credits deliberately. The absence of
a row means the account predates this feature and is left alone — a signup
gate that retroactively locked out paying customers would be a much worse
failure than a handful of unreviewed legacy accounts.

**The signals.** Whether this signup looks like the same person coming back
for another free allowance. Everything here produces evidence for a human to
read, never an automatic refusal, and the wording throughout is deliberate:
these are reasons to look, not findings of guilt. Two colleagues in one office
share an IP. So do a family, a university, a coffee shop, and every customer
behind one corporate NAT. Treating a shared address as proof would ban them.

On VPNs specifically: this module cannot detect one on its own, and does not
pretend to. Identifying a VPN or datacenter exit node requires a maintained
database of address ranges, which is what IP-reputation providers sell. The
hook for one is here and stays inert until a key is configured — `vpn_check`
reports "not configured" rather than "clean", because a check that quietly
returns a pass when it never ran is worse than no check at all. What does work
without a provider is the behaviour that actually matters: several accounts
from one address, which catches credit farming whether or not a VPN was
involved.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.account_approvals import Account_approvals
from models.account_signals import Account_signals
from models.workspaces import Workspaces

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_BLOCKED = "blocked"

# What an approved account receives. Matches the trial allowance the product
# advertises, so approving somebody gives them exactly what the pricing page
# promised rather than a number invented here.
FREE_CREDITS = 25

# Mailbox providers whose addresses are disposable by design. Deliberately
# short and conservative: a false positive here puts a real customer in front
# of a reviewer who then has to guess, and a long scraped list of "temporary"
# domains reliably contains somebody's real provider.
_DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "temp-mail.org", "throwawaymail.com", "yopmail.com", "trashmail.com",
    "sharklasers.com", "getnada.com", "dispostable.com", "maildrop.cc",
    "fakeinbox.com", "mailnesia.com", "spamgourmet.com", "mintemail.com",
})

# More accounts than this from one address stops being a coincidence worth
# ignoring. Three tolerates a couple sharing a home connection and a pair of
# colleagues; it does not tolerate a farm.
SAME_IP_ACCOUNT_THRESHOLD = 3

# Signups from one address inside a day. Distinct from the total above: five
# accounts over a year from an office is ordinary, five in an afternoon is not.
RAPID_SIGNUP_THRESHOLD = 3

_VPN_PROVIDER_KEY = "IP_REPUTATION_API_KEY"


async def record_signal(
    db: AsyncSession,
    *,
    user_id: str,
    email: Optional[str],
    ip: Optional[str],
    country: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Note that this account was seen from this address. Never raises.

    Upserts on (user_id, ip) so the table holds the edge rather than one row
    per request. Like the activity recorder, this observes a request somebody
    is already making and must never be able to break it.
    """
    if not user_id:
        return

    try:
        existing = (
            await db.execute(
                select(Account_signals).where(
                    Account_signals.user_id == user_id,
                    Account_signals.ip == ip,
                ).limit(1)
            )
        ).scalars().first()

        if existing:
            existing.hits = (existing.hits or 0) + 1
            existing.last_seen = datetime.now(timezone.utc)
            if country and not existing.country:
                existing.country = country
        else:
            db.add(Account_signals(
                user_id=user_id, email=(email or "").lower() or None, ip=ip,
                country=country, user_agent=user_agent, hits=1,
            ))
        await db.flush()
    except Exception:
        logger.exception("Could not record account signal for %s", user_id)
        try:
            await db.rollback()
        except Exception:
            logger.exception("Could not roll back after a failed signal write")


def vpn_check(ip: Optional[str]) -> Dict[str, Any]:
    """Whether this address belongs to a VPN, proxy or datacenter.

    Returns `{"configured": False}` when no provider key is set. That is not
    the same as "clean", and the console renders it differently: a check that
    silently passes when it never ran would tell an operator the address had
    been cleared by something that does not exist.

    Implementing this properly means calling a reputation provider. The shape
    is settled here so that adding one is a single function body rather than a
    change that ripples through the review UI.
    """
    if not os.environ.get(_VPN_PROVIDER_KEY, "").strip():
        return {"configured": False, "is_vpn": None, "note": "No IP reputation provider configured"}

    # A provider call belongs here. Left unimplemented rather than faked: a
    # stub returning False would read on the dashboard as "checked, not a
    # VPN", which is a claim nothing has established.
    return {"configured": False, "is_vpn": None, "note": "Provider key set but no provider implemented"}


async def assess(
    db: AsyncSession,
    *,
    user_id: str,
    email: Optional[str],
    ip: Optional[str],
) -> Dict[str, Any]:
    """Reasons a human might want to look at this signup.

    Never decides anything. The return value is evidence rendered to a
    reviewer, and every flag is phrased as an observation because the innocent
    explanation is usually the right one.
    """
    flags: List[Dict[str, str]] = []
    address = (email or "").lower().strip()
    domain = address.rsplit("@", 1)[-1] if "@" in address else ""

    same_ip_emails: List[str] = []
    recent_from_ip = 0

    if ip:
        rows = (
            await db.execute(
                select(Account_signals.email, Account_signals.user_id)
                .where(Account_signals.ip == ip)
                .distinct()
            )
        ).all()
        same_ip_emails = sorted({(e or uid) for e, uid in rows if (e or uid)})

        # Count distinct accounts, not rows: one person revisiting is one
        # account however many times they came back.
        others = [e for e in same_ip_emails if e != address]
        if len(same_ip_emails) >= SAME_IP_ACCOUNT_THRESHOLD:
            flags.append({
                "code": "shared_ip",
                "severity": "high",
                "label": f"{len(same_ip_emails)} accounts share this IP address",
                "detail": (
                    "Several accounts have been seen from this address: "
                    + ", ".join(same_ip_emails[:10])
                    + ". Offices, families and shared networks do this legitimately."
                ),
            })
        elif others:
            flags.append({
                "code": "shared_ip_minor",
                "severity": "low",
                "label": f"{len(others)} other account(s) from this IP",
                "detail": "Common on a shared connection; worth a glance, rarely a problem.",
            })

        day_ago = datetime.now(timezone.utc).replace(microsecond=0)
        recent_from_ip = int(
            (
                await db.execute(
                    select(func.count(func.distinct(Account_signals.user_id))).where(
                        Account_signals.ip == ip,
                        Account_signals.created_at >= day_ago.replace(hour=0, minute=0, second=0),
                    )
                )
            ).scalar()
            or 0
        )
        if recent_from_ip >= RAPID_SIGNUP_THRESHOLD:
            flags.append({
                "code": "rapid_signups",
                "severity": "high",
                "label": f"{recent_from_ip} accounts from this IP today",
                "detail": "Several accounts created from one address in a single day.",
            })
    else:
        flags.append({
            "code": "no_ip",
            "severity": "low",
            "label": "No client address recorded",
            "detail": "The proxy chain did not yield one, so IP checks could not run.",
        })

    if domain in _DISPOSABLE_DOMAINS:
        flags.append({
            "code": "disposable_email",
            "severity": "high",
            "label": "Disposable email provider",
            "detail": f"{domain} issues throwaway addresses.",
        })

    reputation = vpn_check(ip)
    if reputation.get("is_vpn"):
        flags.append({
            "code": "vpn",
            "severity": "high",
            "label": "VPN, proxy or datacenter address",
            "detail": str(reputation.get("note") or ""),
        })

    severity = "high" if any(f["severity"] == "high" for f in flags) else (
        "low" if flags else "clean"
    )

    return {
        "severity": severity,
        "flags": flags,
        "ip": ip,
        "accounts_from_ip": same_ip_emails,
        "signups_from_ip_today": recent_from_ip,
        "ip_reputation": reputation,
        "assessed_at": datetime.now(timezone.utc).isoformat(),
    }


ACCOUNT_FLAGGED = "account.flagged"
ACCOUNT_PENDING = "account.pending_review"


async def flag_if_suspicious(
    db: AsyncSession,
    *,
    user_id: str,
    email: Optional[str],
    ip: Optional[str],
) -> Dict[str, Any]:
    """Assess a signup and, when it looks off, put it in front of an operator.

    The notification is an entry in the activity trail rather than an email.
    That is deliberate: the trail is already where operators look, it is
    filterable and exportable, and it cannot be missed in an inbox or fill
    one during a burst — a farm creating forty accounts would send forty
    emails and get itself muted, which is precisely when the alerts matter.
    The console surfaces these as failures do, and the pending queue shows
    the same evidence beside the decision.

    Only high-severity assessments are recorded. A flag raised for every
    shared office connection would train whoever reads it to ignore all of
    them, and an alert nobody reads is worse than none because it looks like
    coverage.
    """
    risk = await assess(db, user_id=user_id, email=email, ip=ip)

    if risk["severity"] == "high":
        # Imported here rather than at module scope: services.activity does
        # not import this module, and keeping it that way avoids a cycle if
        # it ever needs to.
        from services import activity

        labels = ", ".join(f["label"] for f in risk["flags"] if f["severity"] == "high")
        await activity.record(
            db,
            ACCOUNT_FLAGGED,
            user_id=user_id,
            user_email=email,
            entity_type="account",
            entity_id=user_id,
            status="failed",
            summary=f"Signup flagged for review: {labels}",
            metadata=risk,
        )

    return risk


async def get_approval(db: AsyncSession, user_id: str) -> Optional[Account_approvals]:
    """This account's approval row, or None when it predates the gate."""
    return (
        await db.execute(
            select(Account_approvals)
            .where(Account_approvals.user_id == user_id)
            .order_by(Account_approvals.id.asc())
            .limit(1)
        )
    ).scalars().first()


async def open_pending(
    db: AsyncSession,
    *,
    user_id: str,
    email: Optional[str],
    workspace_id: Optional[int],
    risk: Optional[Dict[str, Any]] = None,
) -> Optional[Account_approvals]:
    """Create the pending row for a brand-new account. Never raises.

    Idempotent: a second call for the same account returns the existing row
    rather than opening a second review of one signup.
    """
    try:
        existing = await get_approval(db, user_id)
        if existing:
            return existing

        row = Account_approvals(
            user_id=user_id,
            email=(email or "").lower() or None,
            workspace_id=workspace_id,
            status=STATUS_PENDING,
            credits_granted=0,
            risk_json=json.dumps(risk or {}, default=str)[:8000],
        )
        db.add(row)
        await db.flush()
        return row
    except Exception:
        logger.exception("Could not open an approval for %s", user_id)
        return None


_AUTO_APPROVE_VAR = "HOLD_ALL_SIGNUPS_FOR_REVIEW"


def hold_everything() -> bool:
    """Whether every signup waits for a human, however ordinary it looks.

    Off by default, so a signup that raises no flag is approved immediately
    and a suspicious one is held. Holding everything makes the queue the
    bottleneck on growth: an ordinary customer who signs up at midnight
    cannot use the product they just signed up for until somebody wakes up,
    and most of them will not come back to find out whether you did.

    The setting exists because that trade is a business decision rather than
    a technical one, and it can be reversed without a deploy.
    """
    return os.environ.get(_AUTO_APPROVE_VAR, "").strip().lower() in {"1", "true", "yes"}


async def auto_approve_if_clean(
    db: AsyncSession,
    approval: Account_approvals,
    risk: Dict[str, Any],
) -> bool:
    """Grant the free credits when nothing about this signup looks wrong.

    Returns whether it was approved.

    "Clean" means no high-severity flag. A low-severity note — one other
    account on a shared office connection, say — is not a reason to make a
    real customer wait, and holding on it would mean holding most of them:
    colleagues, families and anyone behind one corporate connection all trip
    it legitimately.

    High-severity signups still wait for a person. That is the whole point of
    the queue, and it stays small enough to actually be worked.
    """
    if hold_everything():
        return False
    if risk.get("severity") == "high":
        return False

    workspace = (
        await db.execute(
            select(Workspaces).where(Workspaces.owner_id == approval.user_id)
            .order_by(Workspaces.id.asc()).limit(1)
        )
    ).scalars().first()

    approval.status = STATUS_APPROVED
    approval.decided_by = "system (no flags raised)"
    approval.decided_at = datetime.now(timezone.utc)
    approval.reason = "Approved automatically: nothing unusual found at signup."

    if workspace:
        workspace.monthly_credits = FREE_CREDITS
        approval.credits_granted = FREE_CREDITS

    return True


async def ensure_assessed(
    db: AsyncSession,
    *,
    user_id: str,
    email: Optional[str],
    ip: Optional[str],
) -> None:
    """Assess a pending account once, the first time we have an address.

    The assessment cannot happen where the approval row is opened, because
    that is `ensure_workspace_for_user`, which has no request and therefore no
    client address. It happens here instead, on the account's first real
    action, and writes the result onto the pending row so it runs exactly once
    rather than on every request the account makes while it waits.

    Never raises. A failure to assess must leave the signup pending for a
    human rather than break the request or, worse, wave it through.
    """
    try:
        approval = await get_approval(db, user_id)
        if approval is None or approval.status != STATUS_PENDING:
            return
        # Already assessed. Re-running would overwrite the evidence a
        # reviewer may already be looking at.
        if approval.risk_json and approval.risk_json not in ("{}", ""):
            return

        risk = await flag_if_suspicious(db, user_id=user_id, email=email, ip=ip)
        approval.risk_json = json.dumps(risk, default=str)[:8000]

        # Decided in the same request that assessed it, so an ordinary
        # customer never sees a waiting screen at all — the queue holds only
        # the signups somebody actually needs to look at.
        await auto_approve_if_clean(db, approval, risk)

        await db.flush()
    except Exception:
        logger.exception("Could not assess pending account %s", user_id)


def access_state(approval: Optional[Account_approvals]) -> str:
    """What this approval permits: "allowed", "pending" or "blocked".

    No row means allowed. Those accounts existed before the gate, and the
    alternative — treating unknown as pending — would suspend every customer
    the moment this shipped.
    """
    if approval is None:
        return "allowed"
    if approval.status == STATUS_APPROVED:
        return "allowed"
    if approval.status in (STATUS_BLOCKED, STATUS_REJECTED):
        return "blocked"
    return "pending"


def parse_risk(approval: Optional[Account_approvals]) -> Dict[str, Any]:
    if approval is None or not approval.risk_json:
        return {}
    try:
        return json.loads(approval.risk_json)
    except (TypeError, ValueError):
        return {}
