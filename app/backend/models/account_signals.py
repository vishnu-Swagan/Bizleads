from core.database import Base
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Index, Integer, String


class Account_signals(Base):
    """Where an account has been seen from.

    One row per (user, IP) pair rather than per request. A row per request
    would be an unbounded write on the hot path that answers no question the
    pair does not already answer: "which accounts share an address" needs the
    edge, not every time it was traversed. `hits` and `last_seen` carry the
    frequency information that would otherwise justify the extra rows.

    This exists to answer one question — is one person opening several
    accounts to collect the free credits more than once — and it should not
    grow past that. It holds no page history, no behavioural profile and no
    identifiers beyond what every HTTP request already carries.
    """

    __tablename__ = "account_signals"
    __table_args__ = (
        Index("ix_account_signals_ip_user", "ip", "user_id"),
        Index("ix_account_signals_ip_created", "ip", "created_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)

    user_id = Column(String, index=True, nullable=False)
    email = Column(String, index=True, nullable=True)

    # The client address as the proxy reported it. Nullable because a
    # deployment behind an unexpected proxy chain may not yield one, and a
    # missing address must read as "unknown" rather than as a shared empty
    # string that would make every such account look related.
    ip = Column(String, index=True, nullable=True)

    # Best-effort, from a CDN header where the platform sets one. Absent on
    # Render without a CDN in front, so nothing may depend on it being here.
    country = Column(String, index=True, nullable=True)

    user_agent = Column(String, nullable=True)

    hits = Column(Integer, nullable=True, default=1, server_default="1")

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_seen = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
