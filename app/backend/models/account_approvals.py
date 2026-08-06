from core.database import Base
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Index, Integer, String, Text


class Account_approvals(Base):
    """Whether an account has been cleared to receive its free credits.

    A separate table rather than columns on `workspaces`, and that is not a
    stylistic choice: this service has no `alembic upgrade` in its build or
    start command, so schema arrives via `Base.metadata.create_all`, which
    creates tables that do not exist and never alters ones that do. Adding
    `approval_status` to `workspaces` would therefore compile locally, pass
    every test against a freshly-created SQLite schema, and then fail in
    production on a column that was never added.

    The absence of a row is meaningful: it means the account predates
    approval and is grandfathered. New workspaces get a `pending` row at
    creation, so nothing that already works stops working — locking out
    paying customers to introduce a signup gate would be a far worse
    outcome than a few unreviewed legacy accounts.
    """

    __tablename__ = "account_approvals"
    __table_args__ = (
        Index("ix_account_approvals_status_created", "status", "created_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)

    # One row per account. Not a database-level unique constraint, because
    # adding one later to a table that already has duplicates fails the
    # migration; the service treats the lowest id as authoritative, the same
    # tolerance ensure_workspace_for_user applies to duplicate workspaces.
    user_id = Column(String, index=True, nullable=False)
    email = Column(String, index=True, nullable=True)
    workspace_id = Column(Integer, index=True, nullable=True)

    # pending | approved | rejected | blocked
    #
    # rejected and blocked are kept apart on purpose. Rejected is a decision
    # about a signup that never started; blocked is a decision about an
    # account that did. Collapsing them would lose the difference between
    # "we never let them in" and "we threw them out", which is exactly what
    # somebody reviewing the decision later needs to know.
    status = Column(String, index=True, nullable=False, default="pending", server_default="pending")

    credits_granted = Column(Integer, nullable=True, default=0, server_default="0")

    # Who decided, and why. An approval nobody can be asked about is not an
    # audit trail, it is a rumour.
    decided_by = Column(String, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(Text, nullable=True, default="", server_default="")

    # Risk flags at signup, JSON-encoded, frozen at the moment of the
    # decision. Recomputing them when the console renders would show the
    # reviewer different evidence from the reviewer before them.
    risk_json = Column(Text, nullable=True, default="{}", server_default="{}")

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
