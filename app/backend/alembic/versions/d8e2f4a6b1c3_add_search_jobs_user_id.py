"""add user_id to search_jobs

Closes schema drift: models/search_jobs.py declares `user_id` and
routers/discover.py writes it on every search, but no migration ever added the
column. The application therefore worked on any database built from the models
via `Base.metadata.create_all` — which is what the test suite does — and failed
with `UndefinedColumnError` on any database built from migrations, which is
what production does.

That is the failure mode the audit named: a model/migration mismatch passes
tests and breaks in production. It surfaced the first time discovery ran
against real Postgres.

The column is added nullable, backfilled, then made NOT NULL to match the
model. Adding it NOT NULL in one step would fail on any deployment that
already has rows.

Revision ID: d8e2f4a6b1c3
Revises: c7d1e2f3a4b5
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8e2f4a6b1c3"
down_revision: Union[str, Sequence[str], None] = "c7d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Rows predating this column have no recoverable owner. They are stamped so the
# value is explicit and searchable rather than silently empty.
ORPHAN_OWNER = "unknown-pre-migration"


def upgrade() -> None:
    op.add_column("search_jobs", sa.Column("user_id", sa.String(), nullable=True))

    search_jobs = sa.table("search_jobs", sa.column("user_id", sa.String))
    op.execute(
        search_jobs.update().where(search_jobs.c.user_id.is_(None)).values(user_id=ORPHAN_OWNER)
    )

    op.alter_column("search_jobs", "user_id", existing_type=sa.String(), nullable=False)
    op.create_index(op.f("ix_search_jobs_user_id"), "search_jobs", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_search_jobs_user_id"), table_name="search_jobs")
    op.drop_column("search_jobs", "user_id")
