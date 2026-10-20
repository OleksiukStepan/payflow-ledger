<p align="right"><a href="README.md">Українська</a> | <b>English</b></p>

<h1 align="center">PayFlow Ledger</h1>

<p align="center">
  Receives PayFlow corporate card webhooks and keeps the books: what is available, what is on hold, and where every authorization stands.<br>
  Signed, idempotent and order-independent, whatever order and however many times PayFlow delivers.
</p>

<p align="center">
  <a href="https://github.com/OleksiukStepan/payflow-ledger/actions/workflows/ci.yml"><img src="https://github.com/OleksiukStepan/payflow-ledger/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white" alt="Python 3.13">
</p>

## 1. Run and test

```bash
docker compose up --build        # http://localhost:8000, schema migrated on start
```

| Open | What it is |
|---|---|
| http://localhost:8000/ | read-only page: pick a demo scenario (or any account) and see its balance and every authorization; refreshes every 3 s |
| http://localhost:8000/docs | Swagger: how to sign a webhook, example bodies, every possible answer |

<img src="docs/screenshots/dashboard.png" width="720" alt="The account page after the happy path: 585.00 USD available, 15.00 USD on hold, four authorizations">

With the sender from [mekasp/PayFlow](https://github.com/mekasp/PayFlow):

```bash
python3 PayFlowEventsSender.py happy_path.json
curl localhost:8000/accounts/acc_1/balance
# {"account_id":"acc_1","currency":"USD","available":"585.00","pending":"15.00"}
```

**Verify the way PayFlow really delivers.** The sender sends one event at a time, in file order; the PayFlow docs promise duplicates, any order and parallel requests. `make verify` starts the stack and runs `scripts/replay.py` (standard library only) over `scenarios/happy_path.json` and `scenarios/edge_cases.json`: shuffled, with five extra copies, from 16 threads. It then checks every balance and authorization against `scenarios/expected.json` and exits 1 on any mismatch. Run it twice: the second run answers `duplicate` to everything and the numbers do not move. CI does both.

```
Answers: duplicate 6, ignored 1, ok 23
...
40/40 checks match
```

**Tests:** `docker compose run --rm --build tests` (or `make test`). They run against a real PostgreSQL, in a `*_test` database that each run drops and migrates, because what is tested (`ON CONFLICT`, `NUMERIC`, concurrent transactions) is PostgreSQL behaviour:

- signature, body cap and validation; every ledger rule and assumption below;
- concurrency: every happy-path event three times, in random order, from 16 threads;
- a property-based test ([Hypothesis](https://hypothesis.readthedocs.io)): random account histories delivered in random order with random repeats must equal an in-order delivery, and `available` must equal the formula. Checked against deliberately broken code: it shrinks a "created overwrites a reversal" bug to a 0.01 counterexample.

| Endpoint | Answers |
|---|---|
| `POST /webhooks` | `200` with `ok`, `duplicate` or `ignored` (unknown type, stored); `400` signed but invalid; `401` bad or missing signature; `413` body over 64 KB |
| `GET /accounts/{id}/balance` | `200` `available` and `pending` as two-decimal strings; `404` unknown account |
| `GET /accounts/{id}/transactions` | `200` every authorization with its state; `404` unknown account |

Configuration: `WEBHOOK_SECRET` (required, never empty) and `DATABASE_URL`.

## 2. Assumptions

Where the assignment and the PayFlow docs are silent:

- **An account exists from its first `account.funded`.** Earlier events are stored and applied; both GET endpoints answer 404 until the funding arrives, then everything counts.
- **The account currency is that of the first funding to arrive.** Events in another currency are stored and listed but left out of the balance, with a warning. No conversion.
- **An authorization's facts are independent**: created, captured and reversed each fill their own fields. If two events of the same kind arrive for one authorization (two captures, say), the newer by `created_at` wins, and at equal times the larger amount, so the result never depends on arrival order. `authorization.created` decides the authorization's currency.
- **Capture wins over reversal.** With out-of-order delivery both can show up; money that was taken is the stronger fact, and the conflict is logged.
- **A reversal releases the whole hold**, even for a smaller amount (the docs say the hold is released). The amount is kept.
- **Refunds count as they come**, before the capture or above it: `refunded` is defined as the sum of all refunds and order is not guaranteed. A refund re-sent under a new event id counts once (`refund_id` is unique).
- **`available` may go negative.** PayFlow approves operations, the ledger records them.
- **Ids are unique across accounts.** An event for an authorization that belongs to another account is ignored with a warning.
- **Signed but invalid answers 400** (bad amount, missing field, a value PostgreSQL cannot store such as a NUL character, `created_at` outside 1970–9000). It is a contract violation, nothing is stored, and PayFlow's retries are harmless. **Unknown event types answer 200** and are kept; unknown fields are ignored.
- **Amounts are strings with two decimals and ASCII digits** (`[0-9]{1,12}\.[0-9]{2}`), as the docs say; `merchant` is optional and unbounded.
- **Transactions are sorted by `created_at`**, shown in UTC whole seconds. An authorization known only from a capture or reversal shows `merchant`, `authorized_amount` and `created_at` as `null` until `authorization.created` arrives.

## 3. Key decisions

**Exactly-once effect on at-least-once delivery.** Each event is inserted into `events` by its PayFlow `id` (`INSERT ... ON CONFLICT DO NOTHING RETURNING id`) in the same transaction that applies it. No row back means a duplicate: answer 200. If anything fails midway, the event row rolls back with it and PayFlow's retry starts clean. Concurrent copies are serialized by the primary key itself.

**Facts, not transitions.** No event says "move to captured". Each writes its own columns through an atomic upsert that only replaces an older fact, and the status is a PostgreSQL generated column (`captured` if a capture exists, else `reversed`, else `pending`). Any delivery order gives the same state; the property test checks this on random histories.

**No stored balance.** A running total needs read-modify-write on every event and loses updates under parallel delivery unless every event locks the account. The balance is four `SUM`s in one statement instead, which is also one consistent snapshot.

**The raw body is the only truth for the signature.** It is read with a 64 KB cap and the HMAC is computed over exactly those bytes, compared in constant time on bytes (a non-ASCII header cannot crash it). Re-serialized JSON would not match. Money is `Decimal` / `NUMERIC(14,2)` and must arrive as a string: a JSON number has already been through a float.

**FastAPI, SQLAlchemy 2 (sync), Alembic.** Three endpoints do not need Django, and PostgreSQL's upsert is first-class in SQLAlchemy while Django's `update_or_create` is not atomic under concurrency. One millisecond-scale transaction per webhook (0.5 s worst case at 200 parallel senders) fits PayFlow's 10 s budget, so there is no queue to run. The page treats webhook data as untrusted: values reach the DOM through `textContent` only, under a CSP without inline scripts.

## 4. Not done, on purpose

- **No authentication on the read endpoints or the page**; the assignment does not ask for it.
- **No replay protection beyond the event id**: PayFlow signs no timestamp. A replayed event is a harmless duplicate, but a captured request stays valid forever.
- **No queue or worker**, see above.
- **No dead-letter store or replay command** for rejected payloads or unknown types (their errors are logged).
- **No pagination**, as the assignment says.

## 5. Before production

- Ask PayFlow for a timestamped signature and reject old requests, as [Stripe does](https://docs.stripe.com/webhooks) (`t=...,v1=...`, 5-minute tolerance). Load the secret from a secret manager and accept the old and the new secret side by side while rotating it.
- Answer 2xx to signed but invalid payloads and keep them in a dead-letter table: providers like Stripe [disable endpoints](https://support.stripe.com/questions/why-is-stripe-trying-to-reach-my-webhook-endpoints) that keep failing for days.
- Reconcile against a PayFlow events API on a schedule: webhooks are lost after 72 h of failed retries ([Stripe's approach](https://docs.stripe.com/events/manage-webhook-endpoints)).
- Authenticate the read endpoints and the page; rate-limit `/webhooks`; allowlist PayFlow's IPs if published.
- Run migrations as a separate deploy step, not on container start, so replicas do not race.
- Structured logs with the event id, alerts on 4xx rates and on the anomaly warnings.
- For large accounts: per-account totals maintained in the same transaction under a row lock, instead of summing on every read.

Code map, data model and invariants: [ARCHITECTURE.md](ARCHITECTURE.md).
