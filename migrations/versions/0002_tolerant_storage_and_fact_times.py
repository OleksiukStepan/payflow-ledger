"""Store payloads as json, unlimited merchant names, time of each authorization fact

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.alter_column("events", "payload", type_=postgresql.JSON(), postgresql_using="payload::json")
    op.alter_column("authorizations", "merchant", type_=sa.Text())
    op.add_column("authorizations", sa.Column("captured_at", TIMESTAMP, nullable=True))
    op.add_column("authorizations", sa.Column("reversed_at", TIMESTAMP, nullable=True))


def downgrade() -> None:
    op.drop_column("authorizations", "reversed_at")
    op.drop_column("authorizations", "captured_at")
    op.alter_column("authorizations", "merchant", type_=sa.String(255))
    op.alter_column("events", "payload", type_=postgresql.JSONB(), postgresql_using="payload::jsonb")
