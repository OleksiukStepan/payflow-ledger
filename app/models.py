from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Computed, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Money = Numeric(14, 2)

# Captured wins over reversed: once money is taken, a stray reversal cannot undo it.
AUTHORIZATION_STATUS = (
    "CASE WHEN captured_amount IS NOT NULL THEN 'captured' "
    "WHEN reversed_amount IS NOT NULL THEN 'reversed' "
    "ELSE 'pending' END"
)


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # json, not jsonb: jsonb cannot hold \u0000, and the payload is kept as delivered.
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    currency: Mapped[str] = mapped_column(String(3))


class Funding(Base):
    __tablename__ = "fundings"

    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(255), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))


class Authorization(Base):
    __tablename__ = "authorizations"

    authorization_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(255), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    merchant: Mapped[str | None] = mapped_column(Text)
    authorized_amount: Mapped[Decimal | None] = mapped_column(Money)
    captured_amount: Mapped[Decimal | None] = mapped_column(Money)
    reversed_amount: Mapped[Decimal | None] = mapped_column(Money)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(8), Computed(AUTHORIZATION_STATUS, persisted=True))


class Refund(Base):
    __tablename__ = "refunds"

    refund_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    authorization_id: Mapped[str] = mapped_column(String(255), index=True)
    account_id: Mapped[str] = mapped_column(String(255), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
