import logging
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Account, Authorization, Event, Funding, Refund
from app.schemas import (
    AccountFunded,
    AuthorizationClosed,
    AuthorizationCreated,
    Balance,
    EventData,
    RefundCreated,
    Transaction,
    Transactions,
)
from app.schemas import Event as IncomingEvent

logger = logging.getLogger("payflow.ledger")


def process_event(event: IncomingEvent, data: EventData | None) -> str:
    """Stores and applies one event in a single transaction; returns ok, duplicate or ignored."""
    with SessionLocal.begin() as session:
        stored = session.execute(
            insert(Event)
            .values(id=event.id, type=event.type, created_at=event.created_at, payload=event.model_dump(mode="json"))
            .on_conflict_do_nothing(index_elements=[Event.id])
            .returning(Event.id)
        ).first()
        if stored is None:
            logger.info("Event %s already processed, skipping", event.id)
            return "duplicate"
        if data is None:
            logger.info("Event %s has unknown type %s, stored without applying", event.id, event.type)
            return "ignored"
        APPLIERS[event.type](session, event, data)
        _warn_on_foreign_currency(session, event.id, data.account_id, data.currency)
    return "ok"


def _apply_funding(session: Session, event: IncomingEvent, data: AccountFunded) -> None:
    # The first funding to arrive creates the account and fixes its currency.
    session.execute(insert(Account).values(account_id=data.account_id, currency=data.currency).on_conflict_do_nothing())
    session.execute(
        insert(Funding).values(
            event_id=event.id, account_id=data.account_id, amount=data.amount, currency=data.currency
        )
    )


def _apply_authorization_created(session: Session, event: IncomingEvent, data: AuthorizationCreated) -> None:
    _record_authorization_facts(
        session,
        data,
        (Authorization.created_at, Authorization.authorized_amount),
        merchant=data.merchant,
        authorized_amount=data.amount,
        created_at=event.created_at,
        # The authorization's own event decides its currency, not whichever event arrived first.
        currency=data.currency,
    )


def _apply_authorization_captured(session: Session, event: IncomingEvent, data: AuthorizationClosed) -> None:
    _record_authorization_facts(
        session,
        data,
        (Authorization.captured_at, Authorization.captured_amount),
        captured_amount=data.amount,
        captured_at=event.created_at,
    )


def _apply_authorization_reversed(session: Session, event: IncomingEvent, data: AuthorizationClosed) -> None:
    _record_authorization_facts(
        session,
        data,
        (Authorization.reversed_at, Authorization.reversed_amount),
        reversed_amount=data.amount,
        reversed_at=event.created_at,
    )


def _record_authorization_facts(
    session: Session, data: AuthorizationCreated | AuthorizationClosed, version: tuple[Any, Any], **facts: Any
) -> None:
    # Each event type owns its columns, and a fact only replaces an older one (by time, then amount):
    # the result is the same whatever order the events arrive in.
    statement = insert(Authorization).values(
        {"authorization_id": data.authorization_id, "account_id": data.account_id, "currency": data.currency, **facts}
    )
    incoming = tuple_(*(statement.excluded[column.key] for column in version))
    newer = or_(version[0].is_(None), incoming > tuple_(*version))
    row = session.execute(
        statement.on_conflict_do_update(
            index_elements=[Authorization.authorization_id],
            set_=facts,
            where=and_(Authorization.account_id == data.account_id, newer),
        ).returning(Authorization.captured_amount, Authorization.reversed_amount)
    ).first()
    if row is None:
        _log_skipped_fact(session, data)
        return
    closes = "captured_amount" in facts or "reversed_amount" in facts
    if closes and row.captured_amount is not None and row.reversed_amount is not None:
        logger.warning("Authorization %s is both captured and reversed, treating it as captured", data.authorization_id)


def _log_skipped_fact(session: Session, data: AuthorizationCreated | AuthorizationClosed) -> None:
    owner = session.scalar(
        select(Authorization.account_id).where(Authorization.authorization_id == data.authorization_id)
    )
    if owner != data.account_id:
        logger.warning(
            "Authorization %s belongs to account %s, ignored an event for account %s",
            data.authorization_id,
            owner,
            data.account_id,
        )
    else:
        logger.info("Authorization %s already has a newer fact of this kind, kept it", data.authorization_id)


def _apply_refund(session: Session, event: IncomingEvent, data: RefundCreated) -> None:
    # A refund re-sent under a new event id must not count twice.
    session.execute(
        insert(Refund)
        .values(
            refund_id=data.refund_id,
            authorization_id=data.authorization_id,
            account_id=data.account_id,
            amount=data.amount,
            currency=data.currency,
        )
        .on_conflict_do_nothing(index_elements=[Refund.refund_id])
    )


APPLIERS: dict[str, Callable[[Session, IncomingEvent, Any], None]] = {
    "account.funded": _apply_funding,
    "authorization.created": _apply_authorization_created,
    "authorization.captured": _apply_authorization_captured,
    "authorization.reversed": _apply_authorization_reversed,
    "refund.created": _apply_refund,
}


def _warn_on_foreign_currency(session: Session, event_id: str, account_id: str, currency: str) -> None:
    account_currency = session.scalar(select(Account.currency).where(Account.account_id == account_id))
    if account_currency is not None and account_currency != currency:
        logger.warning(
            "Event %s is in %s but account %s is in %s, it is left out of the balance",
            event_id,
            currency,
            account_id,
            account_currency,
        )


def _utc_seconds(value: datetime) -> datetime:
    # The assignment's format: "2026-10-19T10:01:00Z", UTC and whole seconds.
    return value.astimezone(UTC).replace(microsecond=0)


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _total(column: Any, *conditions: Any) -> Any:
    return select(func.coalesce(func.sum(column), 0)).where(*conditions).scalar_subquery()


def get_balance(session: Session, account_id: str) -> Balance | None:
    account = session.get(Account, account_id)
    if account is None:
        return None
    currency = account.currency
    in_account = (Authorization.account_id == account_id, Authorization.currency == currency)
    # One statement, one snapshot: the four sums cannot see different sets of committed events.
    funded, pending, captured, refunded = session.execute(
        select(
            _total(Funding.amount, Funding.account_id == account_id, Funding.currency == currency),
            _total(Authorization.authorized_amount, *in_account, Authorization.status == "pending"),
            _total(Authorization.captured_amount, *in_account),
            _total(Refund.amount, Refund.account_id == account_id, Refund.currency == currency),
        )
    ).one()
    return Balance(
        account_id=account_id,
        currency=currency,
        available=_money(funded - pending - captured + refunded),
        pending=_money(pending),
    )


def get_transactions(session: Session, account_id: str) -> Transactions | None:
    if session.get(Account, account_id) is None:
        return None
    # Same filter as the balance: only refunds of this account in the authorization's currency.
    refunded = (
        select(Refund.authorization_id, Refund.account_id, Refund.currency, func.sum(Refund.amount).label("amount"))
        .group_by(Refund.authorization_id, Refund.account_id, Refund.currency)
        .subquery()
    )
    rows = session.execute(
        select(Authorization, func.coalesce(refunded.c.amount, 0))
        .outerjoin(
            refunded,
            and_(
                refunded.c.authorization_id == Authorization.authorization_id,
                refunded.c.account_id == Authorization.account_id,
                refunded.c.currency == Authorization.currency,
            ),
        )
        .where(Authorization.account_id == account_id)
        .order_by(Authorization.created_at.asc().nulls_last(), Authorization.authorization_id)
    ).all()
    return Transactions(
        items=[
            Transaction(
                authorization_id=authorization.authorization_id,
                merchant=authorization.merchant,
                currency=authorization.currency,
                status=authorization.status,
                authorized_amount=(
                    _money(authorization.authorized_amount) if authorization.authorized_amount is not None else None
                ),
                captured_amount=_money(authorization.captured_amount or Decimal(0)),
                refunded_amount=_money(refunded_amount),
                created_at=_utc_seconds(authorization.created_at) if authorization.created_at else None,
            )
            for authorization, refunded_amount in rows
        ]
    )
