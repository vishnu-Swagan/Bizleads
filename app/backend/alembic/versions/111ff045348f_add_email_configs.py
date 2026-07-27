"""add email_configs table

Per-customer email sending identity. Until now every workspace's outreach
left from the ONE address configured in process environment variables — fine
for a single operator, wrong the moment this is sold on subscription: one
customer's spam complaint would blacklist the shared domain for everyone,
replies would land in the operator's inbox instead of the customer's, and the
Terms (clause 5) name the customer as the sender.

This table lets each workspace bring its own SMTP or Resend credentials.
Secrets (`smtp_password_encrypted`, `resend_api_key_encrypted`) are stored
encrypted via services/credential_crypto.py and are never returned by the API
— only ever reported as present or absent. See models/email_configs.py for
the full reasoning; this migration mirrors that model exactly.

Revision ID: 111ff045348f
Revises: b7a2f9c4e1d3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "111ff045348f"
down_revision: Union[str, Sequence[str], None] = "b7a2f9c4e1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default="smtp"),
        sa.Column("from_email", sa.String(), nullable=True),
        sa.Column("from_name", sa.String(), nullable=True),
        sa.Column("smtp_host", sa.String(), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True, server_default="587"),
        sa.Column("smtp_username", sa.String(), nullable=True),
        sa.Column("smtp_use_tls", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("smtp_password_encrypted", sa.Text(), nullable=True),
        sa.Column("resend_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_email_configs_user_id"),
    )
    op.create_index("ix_email_configs_user_id", "email_configs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_email_configs_user_id", table_name="email_configs")
    op.drop_table("email_configs")
