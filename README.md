<h1 align="center">PayFlow Ledger</h1>

<p align="center">
  Receives PayFlow corporate card webhooks and keeps the books: what is available, what is on hold, and where every authorization stands.<br>
  Signed, idempotent and order-independent, whatever order and however many times PayFlow delivers.
</p>

<p align="center">
  <a href="https://github.com/OleksiukStepan/payflow-ledger/actions/workflows/ci.yml"><img src="https://github.com/OleksiukStepan/payflow-ledger/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white" alt="Python 3.13">
  <img src="https://img.shields.io/badge/FastAPI-0.142-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL 17">
</p>

## Quick start

```bash
docker compose up --build
```

The service listens on http://localhost:8000. The schema is migrated on start.

Send the provider's events with the sender from [mekasp/PayFlow](https://github.com/mekasp/PayFlow):

```bash
python3 PayFlowEventsSender.py happy_path.json
curl localhost:8000/accounts/acc_1/balance
# {"account_id":"acc_1","currency":"USD","available":"585.00","pending":"15.00"}
curl localhost:8000/accounts/acc_1/transactions
```

### Tests

```bash
docker compose run --rm --build tests
```

The suite runs against a real PostgreSQL (a separate `payflow_test` database that every run drops, recreates and migrates), because the guarantees under test (`ON CONFLICT`, `NUMERIC`, concurrent transactions) are PostgreSQL behaviour. Outside Docker: `pip install -e ".[dev]"`, point `DATABASE_URL` at a database whose name ends in `_test` (the suite drops and recreates it, and refuses any other name) and run `pytest`.

### Extra scenarios

`scenarios/` holds event files in the sender's format, on their own accounts, so they can be replayed on top of the happy path:

| File | What it delivers | Expected |
|---|---|---|
| `shuffled_duplicates.json` | the happy path on `acc_2`, shuffled, four events twice | `acc_2`: 585.00 available, 15.00 pending |
| `edge_cases.json` | `acc_3`: events before the first funding, capture above and below the hold, partial reversal, capture racing a reversal, two refunds and a re-sent one, an unknown event type, a EUR authorization | `acc_3`: 555.00 available, 0.00 pending |

```bash
python3 PayFlowEventsSender.py scenarios/edge_cases.json
```

## API

| Endpoint | Answers |
|---|---|
| `POST /webhooks` | `200 {"status": "ok"}` applied, `200 {"status": "duplicate"}` already applied, `200 {"status": "ignored"}` unknown type (stored), `400` invalid payload, `401` bad or missing signature, `413` body over 64 KB |
| `GET /accounts/{id}/balance` | `200` with `available` and `pending` as two-decimal strings, `404` for an unknown account |
| `GET /accounts/{id}/transactions` | `200` with every authorization of the account and its current state, `404` for an unknown account |
| `GET /health` | `200`, used by the compose healthcheck |

`available = funded − pending − captured + refunded`, all in the account currency.

## Assumptions

Where the assignment and the PayFlow docs are silent, the service does the following.

- **An account exists from its first `account.funded`.** Events that arrive earlier are stored and applied; both GET endpoints answer 404 until the funding arrives, then everything counts.
- **The account currency is the currency of the first funding that arrives.** Events in another currency are stored and listed in transactions, but left out of the balance and logged as a warning. No conversion.
- **Capture wins over reversal.** The lifecycle says an authorization is either captured or reversed; with out-of-order delivery both facts can still show up. Money that was taken is the stronger fact, and the conflict is logged.
- **A reversal releases the whole hold**, even when its amount is smaller than the authorization (the docs say the hold is released and nothing is charged). The amount is kept for audit.
- **Refunds count as they come**: before the capture arrives, or above the captured amount. The task defines `refunded` as the sum of all refunds; the order is not guaranteed, so they are not validated against the capture. A refund re-sent under a new event id counts once (`refund_id` is unique).
- **`available` may go negative.** PayFlow approves operations, not us; the ledger records what happened.
- **A valid signature with an invalid payload answers 400.** It is a contract violation, not an attack; PayFlow keeps retrying, which is visible on both sides and harmless because processing is idempotent. Nothing is stored for it.
- **Unknown event types answer 200** and are stored, so they can be replayed once supported. Unknown fields are ignored (forward compatible).
- **`authorization_id` and `refund_id` are unique across accounts**; a redelivery with the same event `id` is the same event, its content is not compared.
- **Amounts are strings with exactly two decimals** (`^\d{1,12}\.\d{2}$`), as the docs specify; a JSON number or `"12.5"` is rejected. `merchant` is optional.
- **Transactions are sorted by the authorization's `created_at`**; an authorization known only from a capture or reversal has `merchant`, `authorized_amount` and `created_at` set to `null` until `authorization.created` arrives, and is listed last.

## Key decisions

**Exactly-once effect on top of at-least-once delivery.** Every event is inserted into `events` with its PayFlow `id` as the primary key (`INSERT ... ON CONFLICT DO NOTHING RETURNING id`) in the same transaction that applies it. No row returned means a duplicate: answer 200 and stop. If anything fails midway, the transaction rolls back together with the event row, PayFlow retries and processing starts clean. Concurrent duplicates are serialized by the primary key itself: the second insert waits for the first transaction and then does nothing.

**Facts, not transitions.** An event never says "move to captured"; it records a fact in the authorization's own column: `authorized_amount` (created), `captured_amount`, `reversed_amount`. Each event type writes only its columns through an atomic upsert, so reordered or parallel events cannot overwrite each other. The status is a PostgreSQL generated column (`captured` if a capture exists, else `reversed`, else `pending`), so the result is the same for every delivery order. The tests replay the happy path reversed, twice, in 50 seeded shuffles with duplicates and from 16 threads at once.

**No stored balance.** A running balance column needs a read-modify-write on every event and loses updates under parallel delivery unless every event locks the account. Instead the balance is four `SUM`s in one statement, which also makes it one consistent snapshot. Reads cost one indexed scan of the account's rows; see production notes for when to change that.

**Signature over the raw bytes, before anything else.** The body is read with a 64 KB cap, the HMAC-SHA256 is computed over exactly those bytes and compared in constant time (`hmac.compare_digest`, on bytes so a non-ASCII header cannot crash it). Re-serializing parsed JSON would change spacing or key order and break the signature.

**Money is `Decimal` and `NUMERIC(14,2)`, never float.** Amounts must arrive as strings: a JSON number has already been through a float by the time it is parsed.

**FastAPI + SQLAlchemy 2 (sync) + Alembic.** Three endpoints do not need Django's machinery, and the PostgreSQL-specific upsert (`insert().on_conflict_do_update()`) is first-class in SQLAlchemy, while Django's `update_or_create` is not atomic under concurrency. The DB layer is synchronous and runs in FastAPI's thread pool: simpler to read and test, and the database is the bottleneck anyway.

**Fast, synchronous processing.** One short transaction per webhook takes milliseconds (0.2 s worst case with 24 parallel senders locally), well inside PayFlow's 10 s budget, so there is no queue to operate.

## Not done, on purpose

- **No authentication on the GET endpoints.** The assignment does not ask for it; anyone who can reach the service can read any balance.
- **No replay protection beyond the event id.** The signature carries no timestamp, so a captured request can be re-sent. Re-sending the same event is harmless (duplicate), but a request is valid forever.
- **No queue or worker**, see above.
- **No tooling to replay stored unknown events** or to inspect rejected payloads (their validation errors are logged, the bodies are not stored).
- **No pagination**, as the assignment says.

## Before production

- Load the webhook secret from a secret manager and accept two secrets during rotation.
- Ask PayFlow for a timestamped signature (Stripe-style `t=...,v1=...`) and reject requests older than a few minutes.
- Authenticate the read endpoints and check that the caller may see the account; rate-limit `/webhooks`.
- Run migrations as a separate deploy step instead of on container start, so several replicas do not race.
- Structured JSON logs with the event id, metrics and alerts on 4xx rates and on the anomaly warnings (capture plus reversal, foreign currency).
- Store rejected payloads in a dead-letter table and add a replay command for them and for unknown event types.
- Reconcile against PayFlow's API on a schedule: webhooks can be lost after 72 hours of failed retries.
- If accounts grow large: keep per-account totals updated in the same transaction (with a row lock on the account) or periodic snapshots, instead of summing on every read.
- Lock dependencies with hashes; run the app under a process manager with a sized connection pool.

## Project layout

See [ARCHITECTURE.md](ARCHITECTURE.md) for the code map, the data model and the invariants, and [CHANGELOG.md](CHANGELOG.md) for what changed.
