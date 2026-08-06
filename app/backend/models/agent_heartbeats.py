from core.database import Base
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer, String


class Agent_heartbeats(Base):
    """When each triage agent was last alive.

    Two agents work the same support queue: one on the operator's laptop every
    fifteen minutes, one in the cloud every hour. Without coordination both
    pick up the same request and both reply to it — duplicated work, and two
    diagnoses on one thread that may not agree, which is worse than one.

    This is the coordination. The laptop records that it is running; the cloud
    run reads that and stands down while it is fresh. Deliberately the
    smallest thing that works: one row per agent, overwritten. A queue,
    a lock table or a lease would all be more correct in the abstract and all
    solve a contention problem that does not exist between two cooperating
    agents on a several-minute cycle.

    Not in activity_events, though it would have fitted: a heartbeat every
    fifteen minutes is ninety-six rows a day of pure noise in the feed the
    operators actually read.
    """

    __tablename__ = "agent_heartbeats"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)

    # "local" or "cloud". Indexed and treated as unique by the service, which
    # takes the lowest id if a duplicate ever appears rather than raising —
    # the same tolerance applied elsewhere for rows without a DB constraint.
    agent = Column(String, index=True, nullable=False)

    # Free text the agent supplies about itself, e.g. a hostname. Useful when
    # somebody wonders which machine has been answering.
    detail = Column(String, nullable=True, default="", server_default="")

    last_seen = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
