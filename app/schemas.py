import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, BeforeValidator, StringConstraints

# [0-9], not \d: \d also matches Arabic-Indic and other Unicode digits.
AMOUNT_PATTERN = re.compile(r"[0-9]{1,12}\.[0-9]{2}")


def _parse_amount(value: Any) -> Decimal:
    # Strings only: a JSON number like 12.5 would already have gone through a float.
    if not isinstance(value, str) or not AMOUNT_PATTERN.fullmatch(value):
        raise ValueError("amount must be a string with two decimals, like '125.50'")
    return Decimal(value)


def _to_utc(value: datetime) -> datetime:
    # Years outside this range would be stored but could not be read back (or converted) later.
    try:
        utc = value.astimezone(UTC)
    except OverflowError:
        raise ValueError("created_at is out of range") from None
    if not 1970 <= utc.year < 9000:
        raise ValueError("created_at is out of range")
    return utc


Amount = Annotated[Decimal, BeforeValidator(_parse_amount)]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=255)]
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]


class Event(BaseModel):
    id: Identifier
    type: Identifier
    created_at: UtcDatetime
    # Any: unknown event types are acknowledged whatever their data looks like.
    data: Any


class AccountFunded(BaseModel):
    account_id: Identifier
    amount: Amount
    currency: Currency


class AuthorizationClosed(BaseModel):
    account_id: Identifier
    authorization_id: Identifier
    amount: Amount
    currency: Currency


class AuthorizationCreated(AuthorizationClosed):
    merchant: str | None = None


class RefundCreated(AuthorizationClosed):
    refund_id: Identifier


EventData = AccountFunded | AuthorizationCreated | AuthorizationClosed | RefundCreated

DATA_MODELS: dict[str, type[EventData]] = {
    "account.funded": AccountFunded,
    "authorization.created": AuthorizationCreated,
    "authorization.captured": AuthorizationClosed,
    "authorization.reversed": AuthorizationClosed,
    "refund.created": RefundCreated,
}


def parse_event(body: bytes) -> tuple[Event, EventData | None]:
    """Raises pydantic.ValidationError; data is None for event types we do not know yet."""
    event = Event.model_validate_json(body)
    model = DATA_MODELS.get(event.type)
    return event, model.model_validate(event.data) if model else None


class WebhookAck(BaseModel):
    status: Literal["ok", "duplicate", "ignored"]


class Balance(BaseModel):
    account_id: str
    currency: str
    available: str
    pending: str


class Transaction(BaseModel):
    authorization_id: str
    merchant: str | None
    currency: str
    status: Literal["pending", "captured", "reversed"]
    authorized_amount: str | None
    captured_amount: str
    refunded_amount: str
    created_at: datetime | None


class Transactions(BaseModel):
    items: list[Transaction]
