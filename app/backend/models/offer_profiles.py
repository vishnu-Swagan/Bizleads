from core.database import Base
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String


class Offer_profiles(Base):
    __tablename__ = "offer_profiles"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    workspace_id = Column(Integer, index=True, nullable=False)
    services = Column(String, nullable=True, default='[]', server_default='[]')
    platforms = Column(String, nullable=True, default='[]', server_default='[]')
    price_range_min = Column(Integer, nullable=True, default=0, server_default='0')
    price_range_max = Column(Integer, nullable=True, default=0, server_default='0')
    target_categories = Column(String, nullable=True, default='[]', server_default='[]')
    target_geographies = Column(String, nullable=True, default='[]', server_default='[]')
    languages = Column(String, nullable=True, default='[]', server_default='[]')
    min_client_size = Column(String, nullable=True, default='', server_default='')
    max_client_size = Column(String, nullable=True, default='', server_default='')
    monthly_capacity = Column(Integer, nullable=True, default=5, server_default='5')
    preferred_channels = Column(String, nullable=True, default='[]', server_default='[]')
    portfolio_tags = Column(String, nullable=True, default='[]', server_default='[]')
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)