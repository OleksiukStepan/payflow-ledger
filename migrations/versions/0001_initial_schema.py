"""Initial ledger schema

Revision ID: 0001
Revises:
Create Date: 2026-10-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

MONEY = sa.Numeric(14, 2)
TIMESTAMP = sa.DateTime(timezone=True)
AUTHORIZATION_STATUS = (
    "CASE WHEN captured_amount IS NOT NULL THEN 'captured' "
    "WHEN reversed_amount IS NOT NULL THEN 'reversed' "
    "ELSE 'pending' END"
)


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("type", sa.String(255), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("received_at", TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )
    op.create_table(
        "accounts",
        sa.Column("account_id", sa.String(255), primary_key=True),
        sa.Column("currency", sa.String(3), nullable=False),
    )
    op.create_table(
        "fundings",
        sa.Column("event_id", sa.String(255), sa.ForeignKey("events.id"), primary_key=True),
        sa.Column("account_id", sa.String(255), nullable=False, index=True),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
    )
    op.create_table(
        "authorizations",
        sa.Column("authorization_id", sa.String(255), primary_key=True),
        sa.Column("account_id", sa.String(255), nullable=False, index=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("merchant", sa.String(255), nullable=True),
        sa.Column("authorized_amount", MONEY, nullable=True),
        sa.Column("captured_amount", MONEY, nullable=True),
        sa.Column("reversed_amount", MONEY, nullable=True),
        sa.Column("created_at", TIMESTAMP, nullable=True),
        sa.Column("status", sa.String(8), sa.Computed(AUTHORIZATION_STATUS, persisted=True), nullable=False),
    )
    op.create_table(
        "refunds",
        sa.Column("refund_id", sa.String(255), primary_key=True),
        sa.Column("authorization_id", sa.String(255), nullable=False, index=True),
        sa.Column("account_id", sa.String(255), nullable=False, index=True),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
    )


def downgrade() -> None:
    for table in ("refunds", "authorizations", "fundings", "accounts", "events"):
        op.drop_table(table)
