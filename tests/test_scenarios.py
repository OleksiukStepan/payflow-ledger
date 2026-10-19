import json
import random

from scripts.replay import build_delivery, check_expectations
from tests.conftest import ROOT

EVENT_FILES = [
    ROOT / "tests" / "fixtures" / "happy_path.json",
    ROOT / "scenarios" / "shuffled_duplicates.json",
    ROOT / "scenarios" / "edge_cases.json",
]
EXPECTED = json.loads((ROOT / "scenarios" / "expected.json").read_text())


def mismatches(client):
    def fetch(path):
        response = client.get(path)
        return response.json() if response.status_code == 200 else None

    return [row for row in check_expectations(EXPECTED, fetch) if row[2] != row[3]]


def all_events():
    return [event for path in EVENT_FILES for event in json.loads(path.read_text())]


def test_every_scenario_file_matches_expected_json(send, client):
    for event in all_events():
        assert send(event).status_code == 200

    assert mismatches(client) == []


def test_replay_shuffled_with_duplicates_matches_expected_json(send, client):
    for event in build_delivery(all_events(), shuffle=True, duplicates=10, rng=random.Random(42)):
        assert send(event).status_code == 200

    assert mismatches(client) == []


def test_a_wrong_expectation_is_reported(send, client):
    for event in all_events():
        send(event)
    wrong = {"acc_1": {**EXPECTED["acc_1"], "available": "999.99"}}

    rows = check_expectations(wrong, lambda path: client.get(path).json())

    assert ("acc_1", "available", "999.99", "585.00") in rows
