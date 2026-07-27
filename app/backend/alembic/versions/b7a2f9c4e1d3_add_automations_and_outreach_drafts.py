"""add automations and outreach_drafts tables

Two new, additive tables behind scheduled lead automation:

  automations      A saved search that runs on a schedule and drafts
                    outreach. See models/automations.py for the full
                    reasoning; the short version is it never sends on its
                    own, it only searches, saves, qualifies and drafts.

  outreach_drafts   An email written from a lead's measured findings,
                    waiting for a human to review and send. See
                    models/outreach_drafts.py.

Both tables mirror their models exactly, including the deliberate absence of
a default on findings-shaped nullable columns (`last_run_summary`,
`last_run_error`, `based_on`, ...) — NULL there means "hasn't happened yet",
same discipline as `leads.findings` from a3c6d9f21e07. Nothing here touches
`leads`.

Revision ID: b7a2f9c4e1d3
Revises: a3c6d9f21e07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7a2f9c4e1d3"
down_revision: Union[str, Sequence[str], None] = "a3c6d9f21e07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "automations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("query", sa.String(), nullable=True),
        sa.Column("website_state", sa.String(), nullable=True, server_default="all"),
        sa.Column("auto_qualify", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("auto_draft", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_leads_per_run", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("schedule", sa.String(), nullable=False, server_default="manual"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_summary", sa.Text(), nullable=True),
        sa.Column("last_run_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_automations_user_id", "automations", ["user_id"])

    op.create_table(
        "outreach_drafts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("automation_id", sa.Integer(), nullable=True),
        sa.Column("to_email", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("based_on", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("sequence_step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("send_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outreach_drafts_user_id", "outreach_drafts", ["user_id"])
    op.create_index("ix_outreach_drafts_lead_id", "outreach_drafts", ["lead_id"])
    op.create_index("ix_outreach_drafts_automation_id", "outreach_drafts", ["automation_id"])


def downgrade() -> None:
    op.drop_index("ix_outreach_drafts_automation_id", table_name="outreach_drafts")
    op.drop_index("ix_outreach_drafts_lead_id", table_name="outreach_drafts")
    op.drop_index("ix_outreach_drafts_user_id", table_name="outreach_drafts")
    op.drop_table("outreach_drafts")

    op.drop_index("ix_automations_user_id", table_name="automations")
    op.drop_table("automations")
