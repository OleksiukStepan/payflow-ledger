import json

from tests.conftest import HAPPY_BALANCE, ROOT


def load(name):
    return json.loads((ROOT / "scenarios" / name).read_text())


def test_shuffled_duplicates_scenario(send, client):
    for event in load("shuffled_duplicates.json"):
        assert send(event).status_code == 200

    assert client.get("/accounts/acc_2/balance").json() == {**HAPPY_BALANCE, "account_id": "acc_2"}


def test_edge_cases_scenario(send, client):
    for event in load("edge_cases.json"):
        assert send(event).status_code == 200

    balance = client.get("/accounts/acc_3/balance").json()
    items = client.get("/accounts/acc_3/transactions").json()["items"]

    assert balance == {"account_id": "acc_3", "currency": "USD", "available": "555.00", "pending": "0.00"}
    assert [
        (item["authorization_id"], item["status"], item["currency"], item["captured_amount"], item["refunded_amount"])
        for item in items
    ] == [
        ("auth_301", "captured", "USD", "320.00", "0.00"),
        ("auth_302", "captured", "USD", "80.00", "15.00"),
        ("auth_303", "reversed", "USD", "0.00", "0.00"),
        ("auth_305", "captured", "USD", "60.00", "0.00"),
        ("auth_306", "pending", "EUR", "0.00", "0.00"),
    ]
