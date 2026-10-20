from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

amounts = st.integers(min_value=1, max_value=10_000_000).map(lambda cents: f"{Decimal(cents) / 100:.2f}")
outcomes = st.sampled_from(["pending", "captured", "reversed", "captured_and_reversed"])


@st.composite
def account_histories(draw):
    """One account's events in creation order, plus the totals the ledger must arrive at."""
    facts = []
    totals = {"funded": Decimal(0), "pending": Decimal(0), "captured": Decimal(0), "refunded": Decimal(0)}

    for amount in draw(st.lists(amounts, min_size=1, max_size=3)):
        facts.append(("account.funded", {"amount": amount}))
        totals["funded"] += Decimal(amount)

    for index in range(draw(st.integers(min_value=0, max_value=5))):
        auth = {"authorization_id": f"auth_{index}"}
        authorized = draw(amounts)
        facts.append(("authorization.created", {**auth, "amount": authorized, "merchant": f"Merchant {index}"}))
        outcome = draw(outcomes)
        if outcome == "pending":
            totals["pending"] += Decimal(authorized)
        if outcome in ("reversed", "captured_and_reversed"):
            facts.append(("authorization.reversed", {**auth, "amount": draw(amounts)}))
        if outcome in ("captured", "captured_and_reversed"):
            captured = draw(amounts)
            facts.append(("authorization.captured", {**auth, "amount": captured}))
            totals["captured"] += Decimal(captured)
            for refund_index, refund in enumerate(draw(st.lists(amounts, max_size=2))):
                facts.append(("refund.created", {**auth, "refund_id": f"re_{index}_{refund_index}", "amount": refund}))
                totals["refunded"] += Decimal(refund)

    events = [
        {
            "id": f"evt_{position}",
            "type": event_type,
            "created_at": f"2026-10-19T10:{position:02d}:00Z",
            "data": {"account_id": "acc_p", "currency": "USD", **data},
        }
        for position, (event_type, data) in enumerate(facts)
    ]
    return events, totals


@st.composite
def deliveries(draw):
    """The same history delivered the way PayFlow may deliver it: any order, some events more than once."""
    events, totals = draw(account_histories())
    repeats = draw(st.lists(st.sampled_from(events), max_size=len(events)))
    return events, draw(st.permutations(events + repeats)), totals


def deliver_and_read(send, client, events):
    for event in events:
        assert send(event).status_code == 200
    return client.get("/accounts/acc_p/balance").json(), client.get("/accounts/acc_p/transactions").json()


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(case=deliveries())
def test_order_and_duplicates_never_change_the_result_and_the_balance_follows_the_formula(send, client, reset_db, case):
    in_order, shuffled_with_repeats, totals = case

    reset_db()
    expected = deliver_and_read(send, client, in_order)
    reset_db()
    balance, transactions = deliver_and_read(send, client, shuffled_with_repeats)

    assert (balance, transactions) == expected
    available = totals["funded"] - totals["pending"] - totals["captured"] + totals["refunded"]
    assert balance["available"] == f"{available:.2f}"
    assert balance["pending"] == f"{totals['pending']:.2f}"
