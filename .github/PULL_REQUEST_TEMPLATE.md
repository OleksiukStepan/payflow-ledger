## Why

<!-- the problem or the PayFlow behaviour this addresses -->

## What

<!-- what changes, one bullet per decision -->

## Test

<!-- tests added, scenarios run with PayFlowEventsSender.py -->

## Checklist

- [ ] `docker compose run --rm --build tests` is green
- [ ] `ruff check .`, `ruff format --check .` and `bandit -q -r app` are clean
- [ ] Every new event type is idempotent and order-independent, with a test for both
- [ ] CHANGELOG.md updated; ARCHITECTURE.md updated for a structural change
