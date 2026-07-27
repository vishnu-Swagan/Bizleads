"""persist qualification findings on leads

Website qualification (services/qualification.py, POST /api/v1/discover/qualify)
computed a `findings` list and an `evidence_tier` for every measured lead, sent
them to the browser in the response body, and then threw them away — nothing
in the update dict passed to LeadsService.update() stored them. A user who
refreshed the page or came back later lost the specific, sellable "here is
what's wrong with this site" evidence and had to re-spend a credit to see it
again.

Two columns, added with the same no-default discipline as website_score /
has_website / data_source before them (see e9f3a7c2d4b8 and
c7d1e2f3a4b5):

    findings      TEXT, nullable, no default. JSON-encoded list of finding
                  dicts. NULL means "never qualified". "[]" means "qualified,
                  and the analysis found nothing wrong" — a real, asserted
                  result, and must stay distinguishable from "nobody looked".
                  A server_default of '[]' would make every pre-existing,
                  never-qualified lead look like a clean bill of health.

    qualified_at  VARCHAR, nullable, no default. ISO timestamp of the last
                  qualification pass, set together with `findings`. NULL
                  means never qualified, for the same reason.

Existing rows are left untouched (both columns NULL) rather than backfilled:
there is no way to reconstruct whether or when a lead already scored via the
old code path was actually qualified.

Revision ID: a3c6d9f21e07
Revises: f1a4c8e5b2d7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3c6d9f21e07"
down_revision: Union[str, Sequence[str], None] = "f1a4c8e5b2d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("findings", sa.Text(), nullable=True))
    op.add_column("leads", sa.Column("qualified_at", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "qualified_at")
    op.drop_column("leads", "findings")
