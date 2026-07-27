from core.database import Base
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text


class Automations(Base):
    """A saved search that runs on a schedule and drafts outreach.

    This is the unit the user configures once and then leaves alone: what to
    look for, how often, and how far to take each lead it finds. It never
    sends. Drafts land in Outreach_drafts for a human to approve, because the
    customer is the legal sender of every message under the Terms and an
    unattended cold-email sender is how a domain gets blacklisted.
    """

    __tablename__ = "automations"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)

    # --- What to search for. Mirrors the Discover form. ---
    city = Column(String, nullable=True)
    country = Column(String, nullable=True)
    category = Column(String, nullable=True)
    query = Column(String, nullable=True)
    website_state = Column(String, nullable=True, default="all", server_default="all")

    # --- How far to take each lead found ---
    # Qualification spends a credit per lead, so it is opt-in and capped.
    auto_qualify = Column(Boolean, nullable=False, default=True, server_default="true")
    auto_draft = Column(Boolean, nullable=False, default=True, server_default="true")
    # A runaway schedule must not be able to drain a month of credits
    # overnight. This is the per-run ceiling on leads qualified.
    max_leads_per_run = Column(Integer, nullable=False, default=10, server_default="10")

    # --- Schedule ---
    # "manual" | "daily" | "weekly". Manual still runs on demand; it simply
    # never becomes due on its own.
    schedule = Column(String, nullable=False, default="manual", server_default="manual")
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")

    # NULL means never run. Distinct from "ran and found nothing", which is
    # recorded in last_run_summary.
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_summary = Column(Text, nullable=True)
    last_run_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
