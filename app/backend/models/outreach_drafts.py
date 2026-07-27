from core.database import Base
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer, String, Text


class Outreach_drafts(Base):
    """An email written from a lead's findings, waiting for a human.

    Kept as its own table rather than a column on the lead because a lead can
    be written to more than once - an initial approach and later follow-ups -
    and each of those needs its own status and history.

    Nothing here has been sent. `status` is the only thing that says otherwise.
    """

    __tablename__ = "outreach_drafts"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    lead_id = Column(Integer, index=True, nullable=False)
    # NULL when a human drafted it by hand rather than an automation.
    automation_id = Column(Integer, index=True, nullable=True)

    to_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body_text = Column(Text, nullable=False)

    # Which measured findings produced this draft, as a JSON array of ids.
    # Kept so the UI can show the evidence behind every claim, and so a draft
    # written before a re-qualification can be told apart from a fresh one.
    based_on = Column(Text, nullable=True)

    # "pending" | "sent" | "discarded" | "failed"
    status = Column(String, nullable=False, default="pending", server_default="pending")
    # Which touch this is: 1 = first approach, 2+ = follow-up.
    sequence_step = Column(Integer, nullable=False, default=1, server_default="1")

    send_error = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
