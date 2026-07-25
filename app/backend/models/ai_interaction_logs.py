from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Ai_interaction_logs(Base):
    __tablename__ = "ai_interaction_logs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    action_type = Column(String, nullable=False)
    input_summary = Column(String, nullable=True)
    output_summary = Column(String, nullable=True)
    status = Column(String, nullable=False)
    lead_id = Column(Integer, index=True, nullable=True)
    metadata_json = Column(String, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)