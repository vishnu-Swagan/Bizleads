from core.database import Base
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text


class Email_configs(Base):
    """One customer's own sending identity.

    Delivery settings used to live in process environment variables, which
    meant every customer's outreach left from the operator's single address.
    That is fine for one operator and wrong the moment the product is sold:
    one customer's spam complaint would blacklist the shared domain and stop
    delivery for everyone, replies would land in the operator's inbox instead
    of the customer's, and the Terms — which make the customer the sender and
    give them the CAN-SPAM and GDPR obligations — would not match reality.

    So each workspace brings its own credentials and owns its own reputation.

    Secrets are stored encrypted (see services/credential_crypto.py) and are
    never returned by the API, only ever reported as present or absent.
    """

    __tablename__ = "email_configs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    # Unique: one sending identity per customer. A second row would make
    # "which credentials send this email" ambiguous.
    user_id = Column(String, index=True, unique=True, nullable=False)

    # "smtp" | "resend"
    provider = Column(String, nullable=False, default="smtp", server_default="smtp")

    from_email = Column(String, nullable=True)
    from_name = Column(String, nullable=True)

    smtp_host = Column(String, nullable=True)
    smtp_port = Column(Integer, nullable=True, default=587, server_default="587")
    smtp_username = Column(String, nullable=True)
    smtp_use_tls = Column(Boolean, nullable=False, default=True, server_default="true")

    # --- Encrypted at rest. Never returned by any endpoint. ---
    smtp_password_encrypted = Column(Text, nullable=True)
    resend_api_key_encrypted = Column(Text, nullable=True)

    # Set only after a real send succeeded with these settings. NULL means
    # untested — distinct from tested-and-failed, which records the reason.
    # Without this a customer discovers their credentials are wrong only when
    # an automation has already drafted a queue full of unsendable email.
    verified_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
