"""drop LeadScope tables from the shared database

The Supabase project was previously used by LeadScope, a different application,
which left two tables behind in the public schema:

    saved_leads_v2  (id, name, phone, address, website, status, score,
                     lead_tier, call_status, notes, created_at)
    search_history  (id, query, results_count, no_website_filter, created_at)

Both were empty (0 rows, verified immediately before this migration was
written). They are unrelated to this application: nothing in models/ declares
them and no code references them.

Removed so the schema reflects one application. IF EXISTS keeps this idempotent
and lets it run against a fresh database where these never existed.

Deliberately NOT touched, because they are ours despite the confusing names:
`users` and `oidc_states` come from models/auth.py and belong to the legacy
Atoms authentication that is still live during the Supabase migration.

The downgrade recreates the structure but not the data. That is honest rather
than lossy-by-surprise: the tables were empty, so there is nothing to restore.

Revision ID: f1a4c8e5b2d7
Revises: e9f3a7c2d4b8
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a4c8e5b2d7"
down_revision: Union[str, Sequence[str], None] = "e9f3a7c2d4b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.saved_leads_v2")
    op.execute("DROP TABLE IF EXISTS public.search_history")


def downgrade() -> None:
    # Structure only — both tables were empty when dropped.
    op.create_table(
        "saved_leads_v2",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("website", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("lead_tier", sa.Text(), nullable=False),
        sa.Column("call_status", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "search_history",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("results_count", sa.Integer(), nullable=False),
        sa.Column("no_website_filter", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
