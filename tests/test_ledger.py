import random

import pytest


def deliver_all(send, events):
    for event in events:
        assert send(event).status_code == 200, event["id"]


def balance_of(client, account_id="acc_1"):
    return client.get(f"/accounts/{account_id}/balance").json()


def items_of(client, account_id="acc_1"):
    return client.get(f"/accounts/{account_id}/transactions").json()["items"]


@pytest.fixture
def fund(send, make_event):
    def funding(amount="1000.00", currency="USD", account_id="acc_1"):
        assert (
            send(make_event("account.funded", account_id=account_id, amount=amount, currency=currency)).status_code
            == 200
        )

    return funding


@pytest.fixture
def auth_event(make_event):
    def build(event_type, amount, authorization_id="auth_1", currency="USD", account_id="acc_1", **extra):
        return make_event(
            event_type,
            account_id=account_id,
            authorization_id=authorization_id,
            amount=amount,
            currency=currency,
            **extra,
        )

    return build


def test_happy_path_in_order(send, happy_path, assert_happy_state):
    deliver_all(send, happy_path)

    assert_happy_state()


def test_happy_path_in_reverse_order(send, happy_path, assert_happy_state):
    deliver_all(send, reversed(happy_path))

    assert_happy_state()


def test_happy_path_delivered_twice(send, happy_path, assert_happy_state):
    deliver_all(send, happy_path + happy_path)

    assert_happy_state()


def test_happy_path_shuffled_with_duplicates(send, happy_path, assert_happy_state, reset_db):
    rng = random.Random(20261019)
    for _ in range(50):
        reset_db()
        events = happy_path + rng.sample(happy_path, 3)
        rng.shuffle(events)

        deliver_all(send, events)

        assert_happy_state()


def test_capture_above_the_authorized_amount(send, fund, auth_event, client):
    fund()
    deliver_all(
        send,
        [
            auth_event("authorization.created", "100.00", merchant="Hilton"),
            auth_event("authorization.captured", "130.00"),
        ],
    )

    assert balance_of(client) == {"account_id": "acc_1", "currency": "USD", "available": "870.00", "pending": "0.00"}
    [item] = items_of(client)
    assert (item["status"], item["authorized_amount"], item["captured_amount"]) == ("captured", "100.00", "130.00")


def test_capture_below_the_authorized_amount(send, fund, auth_event, client):
    fund()
    deliver_all(send, [auth_event("authorization.created", "100.00"), auth_event("authorization.captured", "80.00")])

    assert balance_of(client)["available"] == "920.00"
    assert balance_of(client)["pending"] == "0.00"


def test_several_refunds_add_up_and_a_resent_refund_counts_once(send, fund, auth_event, make_event, client):
    fund()
    deliver_all(send, [auth_event("authorization.created", "100.00"), auth_event("authorization.captured", "100.00")])
    refund = {"account_id": "acc_1", "authorization_id": "auth_1", "currency": "USD"}
    deliver_all(
        send,
        [
            make_event("refund.created", refund_id="re_1", amount="10.00", **refund),
            make_event("refund.created", refund_id="re_2", amount="15.00", **refund),
            make_event("refund.created", refund_id="re_1", amount="10.00", **refund),
        ],
    )

    assert balance_of(client)["available"] == "925.00"
    assert items_of(client)[0]["refunded_amount"] == "25.00"


@pytest.mark.parametrize(
    "order",
    [
        ("authorization.created", "authorization.reversed", "authorization.captured"),
        ("authorization.captured", "authorization.reversed", "authorization.created"),
        ("authorization.reversed", "authorization.captured", "authorization.created"),
    ],
)
def test_capture_wins_over_reversal_in_any_order(send, fund, auth_event, client, order):
    fund()
    deliver_all(send, [auth_event(event_type, "100.00", merchant="AWS") for event_type in order])

    assert balance_of(client) == {"account_id": "acc_1", "currency": "USD", "available": "900.00", "pending": "0.00"}
    assert items_of(client)[0]["status"] == "captured"


def test_partial_reversal_releases_the_whole_hold(send, fund, auth_event, client):
    fund()
    deliver_all(send, [auth_event("authorization.created", "100.00"), auth_event("authorization.reversed", "60.00")])

    assert balance_of(client) == {"account_id": "acc_1", "currency": "USD", "available": "1000.00", "pending": "0.00"}
    assert items_of(client)[0]["status"] == "reversed"


def test_events_before_the_first_funding_count_once_the_account_exists(send, fund, auth_event, client):
    response = send(auth_event("authorization.created", "50.00", account_id="acc_9"))

    assert response.status_code == 200
    assert client.get("/accounts/acc_9/balance").status_code == 404
    assert client.get("/accounts/acc_9/transactions").status_code == 404

    fund(amount="500.00", account_id="acc_9")

    assert balance_of(client, "acc_9") == {
        "account_id": "acc_9",
        "currency": "USD",
        "available": "450.00",
        "pending": "50.00",
    }


def test_authorization_in_a_foreign_currency_is_listed_but_not_counted(send, fund, auth_event, client):
    fund()

    response = send(auth_event("authorization.created", "100.00", currency="EUR"))

    assert response.status_code == 200
    assert balance_of(client) == {"account_id": "acc_1", "currency": "USD", "available": "1000.00", "pending": "0.00"}
    assert items_of(client)[0]["currency"] == "EUR"


def test_second_funding_in_another_currency_keeps_the_account_currency(fund, client):
    fund()
    fund(amount="500.00", currency="EUR")

    assert balance_of(client) == {"account_id": "acc_1", "currency": "USD", "available": "1000.00", "pending": "0.00"}


def test_unknown_account_is_not_found(client):
    assert client.get("/accounts/acc_missing/balance").status_code == 404
    assert client.get("/accounts/acc_missing/transactions").status_code == 404


def test_capture_without_a_known_authorization_is_listed_with_unknown_details(send, fund, auth_event, client):
    fund()
    deliver_all(send, [auth_event("authorization.captured", "40.00")])

    assert balance_of(client)["available"] == "960.00"
    assert items_of(client) == [
        {
            "authorization_id": "auth_1",
            "merchant": None,
            "currency": "USD",
            "status": "captured",
            "authorized_amount": None,
            "captured_amount": "40.00",
            "refunded_amount": "0.00",
            "created_at": None,
        }
    ]


def test_transactions_are_sorted_by_creation_time(send, fund, auth_event, client):
    fund()
    deliver_all(
        send,
        [
            auth_event(
                "authorization.created", "1.00", authorization_id="auth_late", created_at="2026-10-19T12:00:00Z"
            ),
            auth_event("authorization.captured", "2.00", authorization_id="auth_unknown"),
            auth_event(
                "authorization.created", "3.00", authorization_id="auth_early", created_at="2026-10-19T08:00:00Z"
            ),
        ],
    )

    assert [item["authorization_id"] for item in items_of(client)] == ["auth_early", "auth_late", "auth_unknown"]


def test_available_can_go_negative(send, fund, auth_event, client):
    fund(amount="100.00")
    deliver_all(send, [auth_event("authorization.created", "150.00")])

    assert balance_of(client)["available"] == "-50.00"


def test_account_ids_with_a_slash_can_be_read(fund, client):
    fund(account_id="team/acc")

    assert client.get("/accounts/team%2Facc/balance").json()["available"] == "1000.00"
    assert client.get("/accounts/team%2Facc/transactions").json() == {"items": []}


def test_refunded_amount_only_counts_refunds_the_balance_counts(send, fund, auth_event, make_event, client):
    fund()
    deliver_all(send, [auth_event("authorization.created", "100.00"), auth_event("authorization.captured", "100.00")])
    refund = {"authorization_id": "auth_1", "refund_id": "re_eur", "amount": "5.00"}
    deliver_all(send, [make_event("refund.created", account_id="acc_1", currency="EUR", **refund)])

    assert balance_of(client)["available"] == "900.00"
    assert items_of(client)[0]["refunded_amount"] == "0.00"


def test_an_authorization_id_reused_by_another_account_does_not_touch_the_first(send, fund, auth_event, client):
    fund()
    fund(account_id="acc_other")
    deliver_all(send, [auth_event("authorization.created", "100.00")])

    deliver_all(send, [auth_event("authorization.captured", "100.00", account_id="acc_other")])

    assert balance_of(client) == {"account_id": "acc_1", "currency": "USD", "available": "900.00", "pending": "100.00"}
    assert balance_of(client, "acc_other")["available"] == "1000.00"


@pytest.mark.parametrize("arrival", ["older_first", "newer_first"])
def test_a_repeated_capture_keeps_the_newest_one_in_any_order(send, fund, auth_event, client, arrival):
    fund()
    older = auth_event("authorization.captured", "100.00", created_at="2026-10-19T10:05:00Z")
    newer = auth_event("authorization.captured", "60.00", created_at="2026-10-19T11:00:00Z")
    deliver_all(send, [auth_event("authorization.created", "100.00")])

    deliver_all(send, [older, newer] if arrival == "older_first" else [newer, older])

    assert items_of(client)[0]["captured_amount"] == "60.00"
    assert balance_of(client)["available"] == "940.00"


@pytest.mark.parametrize("arrival", ["small_first", "large_first"])
def test_repeated_facts_at_the_same_time_resolve_the_same_way_in_any_order(send, fund, auth_event, client, arrival):
    fund()
    small = auth_event("authorization.created", "40.00", created_at="2026-10-19T10:00:00Z")
    large = auth_event("authorization.created", "70.00", created_at="2026-10-19T10:00:00Z")

    deliver_all(send, [small, large] if arrival == "small_first" else [large, small])

    assert balance_of(client)["pending"] == "70.00"


def test_long_merchant_names_are_kept(send, fund, auth_event, client):
    fund()
    deliver_all(send, [auth_event("authorization.created", "10.00", merchant="M" * 300)])

    assert items_of(client)[0]["merchant"] == "M" * 300


def test_created_at_is_shown_in_utc_without_fractions(send, fund, auth_event, client):
    fund()
    deliver_all(send, [auth_event("authorization.created", "10.00", created_at="2026-10-19T13:01:00.5+03:00")])

    assert items_of(client)[0]["created_at"] == "2026-10-19T10:01:00Z"


@pytest.mark.parametrize("arrival", ["created_first", "captured_first"])
def test_the_authorization_event_decides_its_currency_in_any_order(send, fund, auth_event, client, arrival):
    fund()
    created = auth_event("authorization.created", "10.00", currency="EUR")
    captured = auth_event("authorization.captured", "10.00", currency="USD")

    deliver_all(send, [created, captured] if arrival == "created_first" else [captured, created])

    assert items_of(client)[0]["currency"] == "EUR"
    assert balance_of(client)["available"] == "1000.00"
