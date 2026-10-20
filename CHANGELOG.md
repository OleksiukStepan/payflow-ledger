# Changelog

## Unreleased

### Added
- `POST /webhooks`: HMAC-SHA256 over the raw body in constant time, 64 KB cap, strict
  validation; 401 bad signature, 400 signed but invalid, 413 too large, 200 for applied,
  duplicate and unknown-type events.
- Idempotent, order-independent ledger: events stored by PayFlow id in the transaction that
  applies them; authorization facts in their own columns, newest fact wins, status derived by
  PostgreSQL; refunds deduped by `refund_id`.
- `GET /accounts/{id}/balance` and `/transactions`, 404 until the first funding; foreign-currency
  events listed but left out of the balance.
- `docker compose up`, tests on real PostgreSQL (concurrency, Hypothesis property test),
  `make verify` (shuffled, duplicated, parallel replay checked against `scenarios/expected.json`),
  Swagger at `/docs`, a read-only account page at `/`, CI.

### Fixed
- Found by an adversarial run against the live stack: a NUL character, an out-of-range
  `created_at` or an account id with `/` no longer cause a 500 or an unreadable account;
  repeated captures, reversals and creations no longer depend on arrival order; an event for
  another account's authorization no longer changes it; `refunded_amount` matches the balance;
  non-ASCII digits are rejected.
