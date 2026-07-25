from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Lead_notes(Base):
    __tablename__ = "lead_notes"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    lead_id = Column(Integer, index=True, nullable=False)
    content = Column(String, nullable=False)
    note_type = Column(String, nullable=True, default='note', server_default='note')
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)