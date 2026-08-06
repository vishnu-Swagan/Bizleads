from core.database import Base
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Index, Integer, String, Text


class Support_tickets(Base):
    """One request from the operators to whoever is working on the product.

    A queue rather than a chat, and the distinction is the whole design. The
    person reading these is not sitting in the application waiting; they read
    the open ones when they next sit down to work. Modelling it as a chat
    would promise a reply that is not coming and leave somebody watching a
    box, which is worse than no feature at all — so the UI says when requests
    are picked up, and nothing anywhere claims anyone is listening now.

    Kept deliberately small: a title, a body, a status and a thread. Anything
    resembling assignment, SLAs or escalation would be furniture for a support
    organisation that does not exist.
    """

    __tablename__ = "support_tickets"
    __table_args__ = (
        Index("ix_support_tickets_status_created", "status", "created_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)

    title = Column(String, nullable=False)
    body = Column(Text, nullable=True, default="", server_default="")

    # open | in_progress | resolved | closed
    #
    # resolved and closed are separate: resolved is a claim by whoever did the
    # work, closed is the operator agreeing. Collapsing them would let one
    # side declare something finished that the other never confirmed, which is
    # exactly the argument a ticket exists to prevent.
    status = Column(String, index=True, nullable=False, default="open", server_default="open")

    # low | normal | high. Whoever raises it decides; nothing here reorders
    # work automatically, because a priority field that silently reorders is
    # how everything becomes high.
    priority = Column(String, index=True, nullable=True, default="normal", server_default="normal")

    # Free text: "bug", "change", "question". Not an enum, because guessing
    # the categories now would mean fighting them later.
    kind = Column(String, nullable=True, default="", server_default="")

    created_by = Column(String, index=True, nullable=True)
    created_by_email = Column(String, nullable=True)

    # Which part of the product it concerns, when the operator names one.
    area = Column(String, nullable=True, default="", server_default="")

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    # Set when somebody claims the work is done, so "how long did this take"
    # is answerable without reading the thread.
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class Support_messages(Base):
    """One message on a ticket, from either side."""

    __tablename__ = "support_messages"
    __table_args__ = (
        Index("ix_support_messages_ticket_created", "ticket_id", "created_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    ticket_id = Column(Integer, index=True, nullable=False)

    # "operator" or "engineer". Stored rather than derived from the author,
    # because the engineer side authenticates with a shared secret and has no
    # user row to infer a side from.
    author_type = Column(String, nullable=False, default="operator", server_default="operator")
    author = Column(String, nullable=True)

    body = Column(Text, nullable=False)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
