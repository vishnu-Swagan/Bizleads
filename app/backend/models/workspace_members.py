from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Workspace_members(Base):
    __tablename__ = "workspace_members"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    workspace_id = Column(Integer, index=True, nullable=False)
    role = Column(String, nullable=True, default='member', server_default='member')
    invited_email = Column(String, nullable=True, default='', server_default='')
    status = Column(String, nullable=True, default='active', server_default='active')
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)