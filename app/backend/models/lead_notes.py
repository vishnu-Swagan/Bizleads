from core.database import Base
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer, String


class Lead_notes(Base):
    __tablename__ = "lead_notes"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    lead_id = Column(Integer, index=True, nullable=False)
    content = Column(String, nullable=False)
    note_type = Column(String, nullable=True, default='note', server_default='note')
    # Python-side default using tz-aware UTC (not server_default=func.now()) because
    # this DB column has no DB-level default from a migration; adding server_default
    # without a matching Alembic migration would risk NULL/NOT NULL failures on insert.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))