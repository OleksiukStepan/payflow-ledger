# ARCHITECTURE — PayFlow Ledger

Code map, data model and invariants; update with any new table, event type or endpoint.

## Code map

| File | Owns |
|---|---|
| `app/main.py` | routes and the HTTP status of every outcome, body cap, the read-only page and its CSP |
| `app/signature.py` | HMAC-SHA256 over the raw body, constant-time, current and previous secret |
| `app/schemas.py` | strict input per event type (amounts, currencies, `created_at` range), response models |
| `app/ledger.py` | `process_event` (dedupe and apply in one transaction), one applier per event type, the two reads |
| `app/models.py`, `migrations/` | tables, the generated `status` column; Alembic `0001` schema, `0002` json payload and fact times |
| `app/api_docs.py` | Swagger text and examples, kept out of `main.py` |
| `app/static/` | the page: values only through `textContent` |
| `scripts/replay.py`, `scenarios/` | shuffled, duplicated, parallel delivery and `expected.json`; `make verify` |
| `tests/` | pytest on real PostgreSQL, including concurrency and a Hypothesis property test |

## Data model

| Table | Key | Written by |
|---|---|---|
| `events` | PayFlow event `id` | every accepted webhook; the payload as `json` (`jsonb` cannot hold `\u0000`) |
| `accounts` | `account_id` | the first `account.funded` to arrive; fixes the currency |
| `fundings` | `event_id` | `account.funded` |
| `authorizations` | `authorization_id` | created / captured / reversed, one group of columns each |
| `refunds` | `refund_id` | `refund.created` |

| Authorization columns | Written by | Replaced only by |
|---|---|---|
| `merchant`, `authorized_amount`, `created_at`, `currency` | `authorization.created` | a newer created (time, then amount) |
| `captured_amount`, `captured_at` | `authorization.captured` | a newer capture |
| `reversed_amount`, `reversed_at` | `authorization.reversed` | a newer reversal |
| `status` | PostgreSQL | `captured` if captured, else `reversed` if reversed, else `pending` |

Balance, filtered by account and its currency, in one `SELECT`:
`available = SUM(fundings) - SUM(authorized where pending) - SUM(captured) + SUM(refunds)`.

## Invariants

- The signature is checked over the raw bytes before parsing; never re-serialize to verify.
- One webhook, one transaction; the `events` insert comes first and decides duplicate or new.
- Appliers record facts in their own columns and never read state to decide what to write; an upsert replaces a fact only with a newer one and only within the same account.
- No running totals: every number in a response is derived on read.
- Every stored event answers 2xx. Only 400 / 401 / 413 make PayFlow retry, and none of them stores anything; values PostgreSQL rejects (SQLSTATE 22) are 400, never 500.
- Money is `Decimal` / `NUMERIC(14,2)`; amounts on the wire are two-decimal ASCII strings.
- The page never renders API data as HTML.
- A new event type needs a model in `schemas.DATA_MODELS`, an applier in `ledger.APPLIERS`, and a test that it is idempotent and order-independent.
