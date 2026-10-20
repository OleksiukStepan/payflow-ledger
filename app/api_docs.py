from typing import Any

DESCRIPTION = """
Keeps the books for PayFlow corporate cards: what is available, what is on hold and where every authorization stands.

**Webhooks are signed.** `POST /webhooks` needs `X-PayFlow-Signature: hex(HMAC_SHA256(secret, raw_body))` over the
exact bytes sent, so "Try it out" answers 401 unless you paste a signature computed for that body. To send signed
events, use `scripts/replay.py` or PayFlow's `PayFlowEventsSender.py`.
"""

_EXAMPLES = {
    "account.funded": {
        "id": "evt_0001",
        "type": "account.funded",
        "created_at": "2026-10-19T10:00:00Z",
        "data": {"account_id": "acc_1", "amount": "1000.00", "currency": "USD"},
    },
    "authorization.created": {
        "id": "evt_0002",
        "type": "authorization.created",
        "created_at": "2026-10-19T10:01:00Z",
        "data": {
            "account_id": "acc_1",
            "authorization_id": "auth_100",
            "amount": "125.50",
            "currency": "USD",
            "merchant": "AWS",
        },
    },
}

# Declared here, not as a FastAPI parameter, so the docs do not advertise a 422 the endpoint never returns.
WEBHOOK_OPENAPI: dict[str, Any] = {
    "parameters": [
        {
            "name": "X-PayFlow-Signature",
            "in": "header",
            "required": True,
            "description": "hex(HMAC_SHA256(secret, raw_body))",
            "schema": {"type": "string"},
        }
    ],
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"type": "object", "required": ["id", "type", "created_at", "data"]},
                "examples": {name: {"value": event} for name, event in _EXAMPLES.items()},
            }
        },
    },
}

WEBHOOK_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {"description": "Stored: ok, duplicate or ignored (unknown type). PayFlow stops retrying."},
    400: {"description": "Signed correctly but invalid. Nothing is stored; PayFlow will retry."},
    401: {"description": "Missing or wrong X-PayFlow-Signature."},
    413: {"description": "Body larger than 64 KB."},
}

ACCOUNT_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "No account.funded has arrived yet."}}
