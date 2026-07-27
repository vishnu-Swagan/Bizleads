from core.database import Base
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer, String


class Workspaces(Base):
    __tablename__ = "workspaces"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    owner_id = Column(String, index=True, nullable=False)
    plan = Column(String, nullable=True, default='trial', server_default='trial')
    trial_ends_at = Column(String, nullable=True, default='', server_default='')
    stripe_customer_id = Column(String, index=True, nullable=True, default='', server_default='')
    stripe_subscription_id = Column(String, index=True, nullable=True, default='', server_default='')
    subscription_status = Column(String, nullable=True, default='trialing', server_default='trialing')
    monthly_credits = Column(Integer, nullable=True, default=25, server_default='25')
    credits_used = Column(Integer, nullable=True, default=0, server_default='0')
    credits_reset_at = Column(String, nullable=True, default='', server_default='')
    max_seats = Column(Integer, nullable=True, default=1, server_default='1')
    settings_json = Column(String, nullable=True, default='{}', server_default='{}')
    # Python-side default using tz-aware UTC (not server_default=func.now()) because
    # these DB columns were never given a DB-level default via migration; switching
    # to server_default without a matching Alembic migration would risk NULL/NOT NULL
    # failures on insert. datetime.now (naive/local) into a tz-aware column silently
    # recorded the wrong instant, so this is fixed to timezone-aware UTC instead.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))