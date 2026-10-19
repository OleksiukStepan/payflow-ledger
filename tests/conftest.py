import hashlib
import hmac
import itertools
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

os.environ.setdefault("WEBHOOK_SECRET", "whsec_test_123")

ROOT = Path(__file__).resolve().parents[1]
SECRET = os.environ["WEBHOOK_SECRET"].encode()

HAPPY_BALANCE = {"account_id": "acc_1", "currency": "USD", "available": "585.00", "pending": "15.00"}
HAPPY_ITEMS = [
    {
        "authorization_id": "auth_100",
        "merchant": "AWS",
        "currency": "USD",
        "status": "captured",
        "authorized_amount": "125.50",
        "captured_amount": "125.50",
        "refunded_amount": "25.50",
        "created_at": "2026-10-19T10:01:00Z",
    },
    {
        "authorization_id": "auth_101",
        "merchant": "Uber",
        "currency": "USD",
        "status": "reversed",
        "authorized_amount": "40.00",
        "captured_amount": "0.00",
        "refunded_amount": "0.00",
        "created_at": "2026-10-19T10:02:00Z",
    },
    {
        "authorization_id": "auth_102",
        "merchant": "Hilton",
        "currency": "USD",
        "status": "captured",
        "authorized_amount": "300.00",
        "captured_amount": "300.00",
        "refunded_amount": "0.00",
        "created_at": "2026-10-19T10:10:00Z",
    },
    {
        "authorization_id": "auth_103",
        "merchant": "Slack",
        "currency": "USD",
        "status": "pending",
        "authorized_amount": "15.00",
        "captured_amount": "0.00",
        "refunded_amount": "0.00",
        "created_at": "2026-10-19T12:30:00Z",
    },
]


def serialize(event: dict[str, Any]) -> bytes:
    # Same serialization as PayFlowEventsSender.py
    return json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode()


def sign(body: bytes, secret: bytes = SECRET) -> str:
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    url = make_url(os.environ["DATABASE_URL"])
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")


@pytest.fixture
def reset_db() -> Callable[[], None]:
    from app.db import engine

    def reset() -> None:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE events, accounts, fundings, authorizations, refunds"))

    return reset


@pytest.fixture(autouse=True)
def clean_tables(reset_db: Callable[[], None]) -> None:
    reset_db()


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def send(client: TestClient) -> Callable[..., Response]:
    def send_event(event: dict[str, Any], signature: str | None = None) -> Response:
        body = serialize(event)
        headers = {
            "Content-Type": "application/json",
            "X-PayFlow-Signature": sign(body) if signature is None else signature,
        }
        return client.post("/webhooks", content=body, headers=headers)

    return send_event


@pytest.fixture
def make_event() -> Callable[..., dict[str, Any]]:
    counter = itertools.count(1)

    def build(event_type: str, created_at: str = "2026-10-19T10:00:00Z", **data: Any) -> dict[str, Any]:
        return {"id": f"evt_test_{next(counter)}", "type": event_type, "created_at": created_at, "data": data}

    return build


@pytest.fixture
def happy_path() -> list[dict[str, Any]]:
    return json.loads((ROOT / "tests" / "fixtures" / "happy_path.json").read_text())


@pytest.fixture
def ledger_state(client: TestClient) -> Callable[[str], tuple[Any, Any]]:
    def state(account_id: str = "acc_1") -> tuple[Any, Any]:
        balance = client.get(f"/accounts/{account_id}/balance")
        transactions = client.get(f"/accounts/{account_id}/transactions")
        return balance.json(), transactions.json()

    return state


@pytest.fixture
def assert_happy_state(ledger_state: Callable[[str], tuple[Any, Any]]) -> Callable[[], None]:
    def check() -> None:
        balance, transactions = ledger_state("acc_1")
        assert balance == HAPPY_BALANCE
        assert transactions == {"items": HAPPY_ITEMS}

    return check
