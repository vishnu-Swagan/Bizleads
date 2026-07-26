"""drop server defaults on lead measurement columns

leads.website_score and leads.social_score defaulted to 0, and
leads.has_website defaulted to false. A SQLAlchemy column default fires
whenever the value is None at INSERT, so writing None — the value meaning "not
measured" — was silently stored as 0 / false.

Every unmeasured lead was therefore recorded as one confirmed to have no
website and scoring zero: a fabricated verdict about a real business, and the
same defect class as the AI fabrication removed from discovery. The scoring
model treats has_website=False as evidence and scores Need at 90, so these
leads would also have surfaced as high-need opportunities.

NULL now means "not measured" and survives. Only the qualification pass may
set a value.

Existing rows are NOT rewritten: a stored 0 might be a genuine measurement of a
terrible site, and there is no way to tell it apart from a coerced None after
the fact. Guessing would replace one fabricated value with another.

Revision ID: e9f3a7c2d4b8
Revises: d8e2f4a6b1c3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e9f3a7c2d4b8"
down_revision: Union[str, Sequence[str], None] = "d8e2f4a6b1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("leads", "website_score", existing_type=sa.Integer(), server_default=None)
    op.alter_column("leads", "social_score", existing_type=sa.Integer(), server_default=None)
    op.alter_column("leads", "has_website", existing_type=sa.Boolean(), server_default=None)


def downgrade() -> None:
    op.alter_column("leads", "website_score", existing_type=sa.Integer(), server_default="0")
    op.alter_column("leads", "social_score", existing_type=sa.Integer(), server_default="0")
    op.alter_column("leads", "has_website", existing_type=sa.Boolean(), server_default="false")
