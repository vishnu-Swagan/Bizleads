"""add data_source to leads

Revision ID: c7d1e2f3a4b5
Revises: b1f0ca7c0c08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7d1e2f3a4b5"
down_revision: Union[str, Sequence[str], None] = "b1f0ca7c0c08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The eight records seeded from backend/mock_data/leads.json. They share a
# numeric user_id, whereas real users carry a UUID platform sub, so the match
# is unambiguous. Matching on both columns guards against a real business
# happening to share a name.
MOCK_USER_ID = "1466317"
MOCK_BUSINESS_NAMES = (
    "Mario's Pizzeria",
    "Chen's Auto Repair",
    "Bloom & Petal Florist",
    "Café del Sol",
    "Tanaka Dental Clinic",
    "Silva Construction",
    "Nordic Bakery",
    "Patel Electronics",
)


def upgrade() -> None:
    op.add_column("leads", sa.Column("data_source", sa.String(), nullable=True))

    leads = sa.table("leads", sa.column("data_source", sa.String), sa.column("user_id", sa.String), sa.column("business_name", sa.String))
    op.execute(
        leads.update()
        .where(sa.and_(
            leads.c.user_id == MOCK_USER_ID,
            leads.c.business_name.in_(MOCK_BUSINESS_NAMES),
        ))
        .values(data_source="mock")
    )
    # Every other pre-existing row stays NULL. Their provenance genuinely
    # cannot be reconstructed, and guessing would defeat the point.


def downgrade() -> None:
    op.drop_column("leads", "data_source")
