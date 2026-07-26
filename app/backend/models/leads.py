from core.database import Base
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String


class Leads(Base):
    __tablename__ = "leads"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    business_name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    location = Column(String, nullable=False)
    country = Column(String, nullable=False)
    website_url = Column(String, nullable=True, default='', server_default='')
    # No defaults on these three, deliberately.
    #
    # A SQLAlchemy column default fires whenever the value is None at INSERT,
    # so `website_score=None` was silently stored as 0 and `has_website=None`
    # as False. That turned every unmeasured lead into one confirmed to have
    # no website and scoring zero — a fabricated verdict, and the exact defect
    # the scoring model exists to avoid.
    #
    # NULL means not measured. Only the qualification pass may set a value.
    website_score = Column(Integer, nullable=True)
    social_score = Column(Integer, nullable=True)
    has_website = Column(Boolean, nullable=True)
    social_platforms = Column(String, nullable=True, default='[]', server_default='[]')
    contact_email = Column(String, nullable=True, default='', server_default='')
    contact_phone = Column(String, nullable=True, default='', server_default='')
    pipeline_stage = Column(String, nullable=True, default='new_lead', server_default='new_lead')
    priority = Column(String, nullable=True, default='medium', server_default='medium')
    notes_count = Column(Integer, nullable=True, default=0, server_default='0')
    last_contacted = Column(String, nullable=True, default='', server_default='')
    # Provenance. NULL means unknown — deliberately not defaulted, because an
    # unknown origin must stay distinguishable from a verified one.
    data_source = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)