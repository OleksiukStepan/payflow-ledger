def test_webhook_is_documented_with_signature_example_and_every_answer(client):
    spec = client.get("/openapi.json").json()
    webhook = spec["paths"]["/webhooks"]["post"]

    headers = {param["name"].lower() for param in webhook["parameters"] if param["in"] == "header"}
    examples = webhook["requestBody"]["content"]["application/json"]["examples"]
    answers = webhook["responses"]["200"]["content"]["application/json"]["examples"]

    assert "x-payflow-signature" in headers
    assert {"authorization.created", "account.funded"} <= set(examples)
    assert {"ok", "duplicate", "ignored"} <= set(answers)
    assert set(webhook["responses"]) == {"200", "400", "401", "413"}


def test_read_endpoints_document_unknown_accounts(client):
    paths = client.get("/openapi.json").json()["paths"]

    for path in ("/accounts/{account_id}/balance", "/accounts/{account_id}/transactions"):
        assert "404" in paths[path]["get"]["responses"]


def test_service_description_explains_how_to_sign(client):
    description = client.get("/openapi.json").json()["info"]["description"]

    assert "HMAC" in description and "X-PayFlow-Signature" in description
