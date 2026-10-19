import logging
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import ledger
from app.config import MAX_BODY_BYTES
from app.db import get_session
from app.schemas import Balance, Transactions, parse_event
from app.signature import is_valid_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("payflow.api")

app = FastAPI(title="PayFlow Ledger")

SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def _read_body(request: Request) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="request body is too large")
    return bytes(body)


@app.post("/webhooks")
async def receive_webhook(request: Request) -> dict[str, str]:
    body = await _read_body(request)
    if not is_valid_signature(body, request.headers.get("X-PayFlow-Signature")):
        logger.warning("Rejected a webhook with an invalid signature")
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        event, data = parse_event(body)
    except ValidationError as error:
        errors = error.errors(include_url=False, include_context=False, include_input=False)
        logger.warning("Rejected a webhook with an invalid payload: %s", errors)
        raise HTTPException(status_code=400, detail=errors) from None
    # The DB layer is synchronous; running it in a thread keeps the event loop free.
    status = await run_in_threadpool(ledger.process_event, event, data)
    return {"status": status}


@app.get("/accounts/{account_id}/balance")
def get_balance(account_id: str, session: SessionDep) -> Balance:
    balance = ledger.get_balance(session, account_id)
    if balance is None:
        raise HTTPException(status_code=404, detail="account not found")
    return balance


@app.get("/accounts/{account_id}/transactions")
def get_transactions(account_id: str, session: SessionDep) -> Transactions:
    transactions = ledger.get_transactions(session, account_id)
    if transactions is None:
        raise HTTPException(status_code=404, detail="account not found")
    return transactions
