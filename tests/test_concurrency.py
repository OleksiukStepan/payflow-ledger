import random
from concurrent.futures import ThreadPoolExecutor

from app import ledger
from app.schemas import parse_event
from tests.conftest import serialize


def test_parallel_delivery_with_duplicates_applies_each_event_once(happy_path, assert_happy_state, reset_db):
    rng = random.Random(7)
    for _ in range(5):
        reset_db()
        events = happy_path * 3
        rng.shuffle(events)
        parsed = [parse_event(serialize(event)) for event in events]

        # Same entry point the HTTP handler uses, so every call runs in its own transaction.
        with ThreadPoolExecutor(max_workers=16) as pool:
            statuses = list(pool.map(lambda item: ledger.process_event(*item), parsed))

        assert statuses.count("ok") == len(happy_path)
        assert statuses.count("duplicate") == 2 * len(happy_path)
        assert_happy_state()
