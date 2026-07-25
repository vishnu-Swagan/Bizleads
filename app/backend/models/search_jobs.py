from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Search_jobs(Base):
    __tablename__ = "search_jobs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    workspace_id = Column(Integer, index=True, nullable=False)
    status = Column(String, nullable=True, default='queued', server_default='queued')
    filters_json = Column(String, nullable=True, default='{}', server_default='{}')
    credits_estimated = Column(Integer, nullable=True, default=1, server_default='1')
    credits_charged = Column(Integer, nullable=True, default=0, server_default='0')
    results_count = Column(Integer, nullable=True, default=0, server_default='0')
    progress_pct = Column(Integer, nullable=True, default=0, server_default='0')
    error_message = Column(String, nullable=True, default='', server_default='')
    started_at = Column(String, nullable=True, default='', server_default='')
    completed_at = Column(String, nullable=True, default='', server_default='')
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)