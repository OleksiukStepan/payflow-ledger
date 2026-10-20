from typing import Any

DESCRIPTION = """
Keeps the books for PayFlow corporate cards: what is available, what is on hold and where every authorization stands.

**Webhooks are signed.** Every `POST /webhooks` needs the header `X-PayFlow-Signature` set to
`hex(HMAC_SHA256(secret, raw_body))`, computed over the exact bytes sent. "Try it out" here will answer 401
unless you paste a signature computed for the exact body, for example:

```python
import hashlib, hmac
hmac.new(b"whsec_test_123", body_bytes, hashlib.sha256).hexdigest()
```

To send events with signatures, use `scripts/replay.py` or PayFlow's own `PayFlowEventsSender.py`.

Delivery may be duplicated, out of order and parallel: every outcome is idempotent and order-independent.
"""

_EVENT_EXAMPLES = {
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
    "authorization.captured": {
        "id": "evt_0004",
        "type": "authorization.captured",
        "created_at": "2026-10-19T10:05:00Z",
        "data": {"account_id": "acc_1", "authorization_id": "auth_100", "amount": "125.50", "currency": "USD"},
    },
    "refund.created": {
        "id": "evt_0008",
        "type": "refund.created",
        "created_at": "2026-10-19T12:00:00Z",
        "data": {
            "account_id": "acc_1",
            "refund_id": "re_500",
            "authorization_id": "auth_100",
            "amount": "25.50",
            "currency": "USD",
        },
    },
}

# Declared here, not as a FastAPI parameter, so the docs do not advertise a 422 the endpoint never returns.
WEBHOOK_REQUEST_BODY: dict[str, Any] = {
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
                "examples": {name: {"value": event} for name, event in _EVENT_EXAMPLES.items()},
            }
        },
    },
}


def _json_examples(**examples: Any) -> dict[str, Any]:
    return {"application/json": {"examples": {name: {"value": value} for name, value in examples.items()}}}


WEBHOOK_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Stored. PayFlow stops retrying.",
        "content": _json_examples(
            ok={"status": "ok"}, duplicate={"status": "duplicate"}, ignored={"status": "ignored"}
        ),
    },
    400: {
        "description": "Signed correctly but the payload is invalid. Nothing is stored; PayFlow will retry.",
        "content": _json_examples(
            invalid_amount={
                "detail": [
                    {
                        "type": "value_error",
                        "loc": ["amount"],
                        "msg": "Value error, amount must be a string with two decimals, like '125.50'",
                    }
                ]
            }
        ),
    },
    401: {
        "description": "Missing or wrong X-PayFlow-Signature.",
        "content": _json_examples(invalid_signature={"detail": "invalid signature"}),
    },
    413: {
        "description": "Body larger than 64 KB.",
        "content": _json_examples(too_large={"detail": "request body is too large"}),
    },
}

ACCOUNT_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {
        "description": "No account.funded has arrived for this account yet.",
        "content": _json_examples(not_found={"detail": "account not found"}),
    }
}
