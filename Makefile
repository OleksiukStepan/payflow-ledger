EVENTS = scenarios/happy_path.json scenarios/edge_cases.json

.PHONY: up down test verify

up:
	docker compose up --build -d --wait

down:
	docker compose down

test:
	docker compose run --rm --build tests

# Idempotent by design: running it again on the same database gives the same numbers.
verify: up
	python3 scripts/replay.py $(EVENTS) --shuffle --duplicates 5 --parallel 16 --expect scenarios/expected.json
