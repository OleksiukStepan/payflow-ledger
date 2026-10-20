# ARCHITECTURE — PayFlow Ledger

Code map, data model and invariants. Keep it under 150 lines; update it in the same PR as any
structural change (new table, event type, endpoint). State as of 2026-10-19.

## Shape

```
PayFlow ──POST /webhooks (HMAC-signed JSON, at-least-once, any order, parallel)──▶ FastAPI ──▶ PostgreSQL
Clients ──GET /accounts/{id}/balance | /transactions──────────────────────────────▶ FastAPI ──▶ PostgreSQL
```

One process, one database. No queue: each webhook is one short transaction.

## Code map

| File | Owns |
|---|---|
| `app/main.py` | routes, body size cap, the HTTP status of every outcome |
| `app/signature.py` | HMAC-SHA256 over the raw body, constant-time comparison |
| `app/schemas.py` | strict input models per event type, money and currency formats, response models |
| `app/ledger.py` | `process_event` (dedupe + apply in one transaction), one applier per event type, balance and transactions queries |
| `app/models.py` | tables and the generated `status` column |
| `app/db.py`, `app/config.py` | engine and session, settings from the environment (fail fast if missing) |
| `migrations/` | Alembic; `0001` is the whole schema |
| `tests/` | pytest against real PostgreSQL: signature and validation, ledger rules, ordering, concurrency, scenario files |
| `scenarios/` | extra event files for `PayFlowEventsSender.py` |

## Webhook flow

1. Read the body, at most 64 KB (413 above).
2. Verify `X-PayFlow-Signature` over those bytes (401 if wrong or missing).
3. Parse the envelope, then the `data` of a known type (400 if invalid). Unknown types skip this step.
4. In one transaction: insert into `events` with `ON CONFLICT DO NOTHING`; no row means a duplicate, answer 200.
5. Known type: run its applier. Unknown type: leave it in `events` only.
6. Commit and answer 200. Any failure rolls back the event row too, so PayFlow's retry starts clean.

## Data model

| Table | Key | Written by | Notes |
|---|---|---|---|
| `events` | `id` (PayFlow event id) | every accepted webhook | raw payload as `jsonb`, `created_at` from PayFlow, `received_at` ours |
| `accounts` | `account_id` | first `account.funded` to arrive | fixes the account currency |
| `fundings` | `event_id` | `account.funded` | one row per funding |
| `authorizations` | `authorization_id` | `authorization.created / captured / reversed` | one column per fact; `status` is generated |
| `refunds` | `refund_id` | `refund.created` | deduped by `refund_id` as well |

Authorization facts and who writes them:

| Column | Written by |
|---|---|
| `merchant`, `authorized_amount`, `created_at` | `authorization.created` |
| `captured_amount` | `authorization.captured` |
| `reversed_amount` | `authorization.reversed` |
| `account_id`, `currency` | whichever of the three arrives first (insert only) |
| `status` | PostgreSQL: `captured` if `captured_amount`, else `reversed` if `reversed_amount`, else `pending` |

Balance, all filtered by the account and its currency:

```
funded    = SUM(fundings.amount)
pending   = SUM(authorizations.authorized_amount) WHERE status = 'pending'
captured  = SUM(authorizations.captured_amount)
refunded  = SUM(refunds.amount)
available = funded - pending - captured + refunded
```

The four sums are scalar subqueries of one `SELECT`, so they read one snapshot.

## Invariants

- The signature is checked over the raw bytes before parsing; never re-serialize to verify.
- One webhook, one transaction; the `events` insert comes first and decides duplicate vs new.
- Appliers record facts and touch only their own columns; no applier reads state to decide what to write.
- No running totals: every number in a response is derived on read.
- Any stored event answers 2xx. Only 400 / 401 / 413 make PayFlow retry, and none of them stores anything.
- Money is `Decimal` / `NUMERIC(14,2)`; amounts on the wire are strings with two decimals.
- Adding an event type: a model in `schemas.DATA_MODELS`, an applier in `ledger.APPLIERS`, a test that it is idempotent and order-independent, and a row in the tables above.

## Boundaries

- No authentication on read endpoints (see README, "Before production").
- Migrations run on container start (`alembic upgrade head`), fine for one replica.
- Tests never use SQLite: the guarantees above are PostgreSQL behaviour.
