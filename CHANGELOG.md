# Changelog

## Unreleased

- `make verify` / `scripts/replay.py`: delivers event files the way the PayFlow docs describe
  (shuffled, duplicated, in parallel) and checks every balance and authorization against
  `scenarios/expected.json`; CI runs it twice to prove the second run changes nothing.
- Property-based tests (Hypothesis): random account histories in random order with random
  repeats always equal an in-order delivery and always satisfy the balance formula.
- Swagger at `/docs` explains webhook signing, shows an example per event type and documents
  exactly the answers the service gives.
- Read-only account page at `/`: balance, the formula written out, every authorization,
  auto-refresh; webhook data is rendered as text only, under a strict Content-Security-Policy.
- `WEBHOOK_SECRET_PREVIOUS` keeps the old secret valid during a rotation.
- README compares the service with Stripe's current webhook and Issuing guidance.
- PayFlow webhook intake at `POST /webhooks`: the HMAC-SHA256 signature is checked over the raw
  body in constant time, the body is capped at 64 KB, events are validated strictly (amounts as
  two-decimal strings, ISO 4217 currency codes). A bad signature answers 401, an invalid payload
  400; duplicates and unknown event types answer 200 so PayFlow stops retrying.
- Idempotent, order-independent processing: each event is stored by its PayFlow id in the same
  transaction that applies it, and authorizations keep facts (authorized, captured, reversed
  amounts) with the status derived by PostgreSQL. Capture wins over reversal; a reversal releases
  the whole hold; refunds are deduped by `refund_id`.
- `GET /accounts/{id}/balance` (`available`, `pending`) and `GET /accounts/{id}/transactions`,
  both 404 until the account's first funding arrives. Events in a currency other than the
  account's are listed but left out of the balance.
- `docker compose up` starts PostgreSQL and the service on port 8000 and migrates the schema;
  `docker compose run --rm --build tests` runs the suite against a real PostgreSQL.
- Tests for signature and validation, ledger rules, 50 shuffled deliveries with duplicates,
  parallel delivery from 16 threads, and two scenario files for `PayFlowEventsSender.py`.
- CI: ruff, bandit, pip-audit, pytest on PostgreSQL and a compose smoke run.
- Safety guards: the service refuses to start with an empty `WEBHOOK_SECRET`, and the test
  suite refuses a `DATABASE_URL` whose database name does not end in `_test` (it drops it).
