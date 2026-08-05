"""add activity_events

The append-only trail behind the operators' console.

Written for parity with the rest of the repository, but note that it is not
what creates the table in production: this service has no `alembic upgrade`
in its build or start command (see render.yaml), and tables are created by
`Base.metadata.create_all` during application startup. create_all adds tables
that do not exist and never alters ones that do, so a brand-new table like
this one arrives correctly on deploy — which is why this change was safe to
ship without a migration step, and why a future change that ALTERS a column
will not be.

Revision ID: b4d8e1f7c2a9
Revises: a2b7c9d4e6f1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4d8e1f7c2a9"
down_revision: Union[str, Sequence[str], None] = "a2b7c9d4e6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("user_email", sa.String(), nullable=True),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("entity_type", sa.String(), nullable=True),
        sa.Column("entity_id", sa.String(), nullable=True),
        sa.Column("summary", sa.String(), server_default="", nullable=True),
        sa.Column("metadata_json", sa.Text(), server_default="{}", nullable=True),
        sa.Column("status", sa.String(), server_default="ok", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activity_events_id", "activity_events", ["id"])
    op.create_index("ix_activity_events_action", "activity_events", ["action"])
    op.create_index("ix_activity_events_user_id", "activity_events", ["user_id"])
    op.create_index("ix_activity_events_user_email", "activity_events", ["user_email"])
    op.create_index("ix_activity_events_workspace_id", "activity_events", ["workspace_id"])
    op.create_index("ix_activity_events_status", "activity_events", ["status"])
    # Composite indexes for the console's four views: recent, by kind, by
    # actor, by workspace — each ordered by time.
    op.create_index("ix_activity_events_created_at_desc", "activity_events", ["created_at"])
    op.create_index("ix_activity_events_action_created", "activity_events", ["action", "created_at"])
    op.create_index("ix_activity_events_user_created", "activity_events", ["user_id", "created_at"])
    op.create_index(
        "ix_activity_events_workspace_created", "activity_events", ["workspace_id", "created_at"]
    )


def downgrade() -> None:
    for name in (
        "ix_activity_events_workspace_created",
        "ix_activity_events_user_created",
        "ix_activity_events_action_created",
        "ix_activity_events_created_at_desc",
        "ix_activity_events_status",
        "ix_activity_events_workspace_id",
        "ix_activity_events_user_email",
        "ix_activity_events_user_id",
        "ix_activity_events_action",
        "ix_activity_events_id",
    ):
        op.drop_index(name, table_name="activity_events")
    op.drop_table("activity_events")
