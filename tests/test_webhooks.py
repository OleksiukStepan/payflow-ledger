import pytest

from tests.conftest import serialize, sign


def funded(make_event, amount="1000.00", currency="USD", account_id="acc_1"):
    return make_event("account.funded", account_id=account_id, amount=amount, currency=currency)


def test_valid_event_is_accepted(send, make_event, client):
    response = send(funded(make_event))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert client.get("/accounts/acc_1/balance").json()["available"] == "1000.00"


@pytest.mark.parametrize(
    "signature",
    [
        sign(b"another body"),
        "0" * 64,
        "",
        "not-hex",
    ],
)
def test_wrong_signature_is_rejected_and_nothing_is_stored(send, make_event, client, signature):
    response = send(funded(make_event), signature=signature)

    assert response.status_code == 401
    assert client.get("/accounts/acc_1/balance").status_code == 404


def test_signature_from_another_secret_is_rejected(send, make_event, client):
    event = funded(make_event)

    response = send(event, signature=sign(serialize(event), secret=b"whsec_other"))

    assert response.status_code == 401


def test_missing_signature_header_is_rejected(client, make_event):
    body = serialize(funded(make_event))

    response = client.post("/webhooks", content=body, headers={"Content-Type": "application/json"})

    assert response.status_code == 401


def test_signature_is_checked_over_raw_bytes(client, make_event):
    body = serialize(funded(make_event))
    reformatted = body.replace(b",", b", ")

    response = client.post("/webhooks", content=reformatted, headers={"X-PayFlow-Signature": sign(body)})

    assert response.status_code == 401


def test_non_ascii_signature_header_is_rejected_not_crashing(client, make_event):
    body = serialize(funded(make_event))

    response = client.post("/webhooks", content=body, headers={"X-PayFlow-Signature": b"\xe9" * 64})

    assert response.status_code == 401


def test_oversized_body_is_rejected(client):
    body = b'{"padding":"' + b"x" * (70 * 1024) + b'"}'

    response = client.post("/webhooks", content=body, headers={"X-PayFlow-Signature": sign(body)})

    assert response.status_code == 413


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"type":"account.funded","created_at":"2026-10-19T10:00:00Z","data":{}}',
        b'{"id":"evt_1","created_at":"2026-10-19T10:00:00Z","data":{}}',
        b'{"id":"evt_1","type":"account.funded","created_at":"yesterday","data":{}}',
        b'{"id":"evt_1","type":"account.funded","created_at":"2026-10-19T10:00:00","data":{}}',
        b'{"id":"evt_1","type":"account.funded","created_at":"2026-10-19T10:00:00Z"}',
    ],
)
def test_invalid_envelope_is_rejected(client, body):
    response = client.post("/webhooks", content=body, headers={"X-PayFlow-Signature": sign(body)})

    assert response.status_code == 400


@pytest.mark.parametrize(
    "data",
    [
        {"account_id": "acc_1", "amount": "12.5", "currency": "USD"},
        {"account_id": "acc_1", "amount": "-5.00", "currency": "USD"},
        {"account_id": "acc_1", "amount": 1000.0, "currency": "USD"},
        {"account_id": "acc_1", "amount": "1e3", "currency": "USD"},
        {"account_id": "acc_1", "amount": "1000000000000.00", "currency": "USD"},
        {"account_id": "acc_1", "currency": "USD"},
        {"account_id": "acc_1", "amount": "10.00", "currency": "usd"},
        {"account_id": "acc_1", "amount": "10.00", "currency": "USDT"},
        {"account_id": "", "amount": "10.00", "currency": "USD"},
        {"amount": "10.00", "currency": "USD"},
    ],
)
def test_invalid_data_of_a_known_type_is_rejected_and_nothing_is_stored(send, make_event, client, data):
    response = send(make_event("account.funded", **data))

    assert response.status_code == 400
    assert client.get("/accounts/acc_1/balance").status_code == 404


def test_rejected_payload_can_be_delivered_again_once_fixed(send, make_event, client):
    broken = make_event("account.funded", account_id="acc_1", amount="12.5", currency="USD")
    fixed = {**broken, "data": {**broken["data"], "amount": "12.50"}}

    assert send(broken).status_code == 400
    assert send(fixed).status_code == 200
    assert client.get("/accounts/acc_1/balance").json()["available"] == "12.50"


def test_unknown_event_type_is_acknowledged_and_does_not_change_the_ledger(send, make_event, client):
    send(funded(make_event))

    response = send(make_event("card.frozen", account_id="acc_1", amount="500.00", currency="USD"))

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert client.get("/accounts/acc_1/balance").json()["available"] == "1000.00"


def test_unknown_fields_are_tolerated(send, make_event, client):
    event = funded(make_event)
    event["data"]["source"] = "bank_transfer"
    event["livemode"] = False

    assert send(event).status_code == 200


def test_duplicate_delivery_is_applied_once(send, make_event, client):
    event = funded(make_event)

    first = send(event)
    second = send(event)

    assert first.json() == {"status": "ok"}
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}
    assert client.get("/accounts/acc_1/balance").json()["available"] == "1000.00"


def test_previous_secret_keeps_working_during_rotation(send, make_event, client, monkeypatch):
    monkeypatch.setattr("app.signature.WEBHOOK_SECRETS", (b"whsec_new", b"whsec_test_123"))
    event = funded(make_event)
    body = serialize(event)

    assert send(event, signature=sign(body, secret=b"whsec_new")).status_code == 200
    assert send({**event, "id": "evt_rotation_2"}, signature=None).status_code == 200
    assert send({**event, "id": "evt_rotation_3"}, signature=sign(body, secret=b"whsec_other")).status_code == 401
