"""add address to leads

Revision ID: a2b7c9d4e6f1
Revises: 111ff045348f

MapBox has returned `full_address` on every POI all along — see
services/mapbox_places.py::_normalize_feature — and the save path dropped it
because there was no column to put it in. A lead therefore carried a
neighbourhood and a country but not a street address, which is the one thing
somebody needs to turn up in person or address a letter.

Nullable with no backfill: every existing row genuinely has no address stored,
and rows saved before this migration cannot have one reconstructed. Writing a
placeholder would assert an address nobody established, which is the same
mistake as the fabricated leads this codebase deleted. Re-running Discover on
a search populates it for newly saved leads.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2b7c9d4e6f1"
down_revision: Union[str, Sequence[str], None] = "111ff045348f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("address", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "address")
