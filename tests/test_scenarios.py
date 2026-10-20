import json
import random

from scripts.replay import build_delivery, check_expectations
from tests.conftest import ROOT

EVENT_FILES = [ROOT / "scenarios" / "happy_path.json", ROOT / "scenarios" / "edge_cases.json"]
EXPECTED = json.loads((ROOT / "scenarios" / "expected.json").read_text())


def fetch_with(client):
    def fetch(path):
        response = client.get(path)
        return response.json() if response.status_code == 200 else None

    return fetch


def test_event_files_shuffled_with_duplicates_match_expected_json(send, client):
    events = [event for path in EVENT_FILES for event in json.loads(path.read_text())]
    for event in build_delivery(events, shuffle=True, duplicates=10, rng=random.Random(42)):
        assert send(event).status_code == 200

    rows = check_expectations(EXPECTED, fetch_with(client))

    assert [row for row in rows if row[2] != row[3]] == []
    assert ("acc_1", "available", "585.00", "585.00") in rows


def test_a_wrong_expectation_is_reported(client):
    rows = check_expectations({"acc_1": {**EXPECTED["acc_1"], "available": "999.99"}}, fetch_with(client))

    assert ("acc_1", "available", "999.99", "missing") in rows
