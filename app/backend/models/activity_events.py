from core.database import Base
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Index, Integer, String, Text


class Activity_events(Base):
    """One thing that happened, recorded so the operators can see it later.

    This is an append-only log. Nothing updates or deletes a row: an activity
    trail that can be edited answers "what do we think happened" rather than
    "what happened", which is the only question worth asking it.

    Deliberately denormalised. user_email and workspace_name are copied in at
    write time rather than joined at read time, so the trail still reads
    correctly after an account is renamed or removed — an audit line that
    silently changes its meaning when a row elsewhere changes is worse than no
    audit line. It also keeps the admin queries free of joins across tables
    that are already the hot path for customers.
    """

    __tablename__ = "activity_events"
    __table_args__ = (
        # The console's default view is "recent activity, newest first", and
        # every other view filters that by actor, workspace or kind. These
        # cover all four without scanning a table that only ever grows.
        Index("ix_activity_events_created_at_desc", "created_at"),
        Index("ix_activity_events_action_created", "action", "created_at"),
        Index("ix_activity_events_user_created", "user_id", "created_at"),
        Index("ix_activity_events_workspace_created", "workspace_id", "created_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)

    # What happened, as a stable machine value like "search.run" or
    # "outreach.sent". Read by the console for grouping and counting, so it
    # must not be a sentence — the human wording belongs in `summary`, where
    # rewording it breaks no aggregate.
    action = Column(String, index=True, nullable=False)

    # Who did it. Nullable because some events have no actor: a scheduled
    # automation firing at 3am was nobody's click, and attributing it to the
    # workspace owner would put an action in their trail they did not take.
    user_id = Column(String, index=True, nullable=True)
    user_email = Column(String, index=True, nullable=True)

    workspace_id = Column(Integer, index=True, nullable=True)

    # What it happened to, e.g. ("lead", "412"). Kept as strings so an event
    # can point at anything without this table growing a column per entity.
    entity_type = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)

    # One line a human can read without decoding the payload.
    summary = Column(String, nullable=True, default='', server_default='')

    # JSON. Whatever is worth keeping about this specific event — result
    # counts, credit cost, error text. Text rather than String because some
    # payloads (a failure with a provider message) are long.
    metadata_json = Column(Text, nullable=True, default='{}', server_default='{}')

    # "ok" or "failed". Failures are recorded, not dropped: a console that
    # only shows successes reports a healthy platform right up until someone
    # complains, which is precisely when the trail needed to be honest.
    status = Column(String, index=True, nullable=True, default='ok', server_default='ok')

    # Python-side tz-aware UTC default, matching every other model here. A
    # naive datetime.now() into a tz-aware column silently records the wrong
    # instant, and for an audit trail that is a defect rather than a nuisance.
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
