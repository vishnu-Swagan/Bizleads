from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Credit_ledger(Base):
    __tablename__ = "credit_ledger"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    workspace_id = Column(Integer, index=True, nullable=False)
    amount = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    action = Column(String, nullable=False)
    description = Column(String, nullable=True, default='', server_default='')
    reference_id = Column(String, index=True, nullable=True, default='', server_default='')
    idempotency_key = Column(String, nullable=True, default='', server_default='')
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)