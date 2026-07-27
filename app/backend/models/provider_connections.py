from core.database import Base
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer, String


class Provider_connections(Base):
    __tablename__ = "provider_connections"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    workspace_id = Column(Integer, index=True, nullable=False)
    provider_type = Column(String, nullable=False)
    provider_name = Column(String, nullable=False)
    status = Column(String, nullable=True, default='disconnected', server_default='disconnected')
    config_json = Column(String, nullable=True, default='{}', server_default='{}')
    last_health_check = Column(String, nullable=True, default='', server_default='')
    error_count = Column(Integer, nullable=True, default=0, server_default='0')
    # Python-side default using tz-aware UTC (not server_default=func.now()) because
    # this DB column has no DB-level default from a migration; adding server_default
    # without a matching Alembic migration would risk NULL/NOT NULL failures on insert.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))