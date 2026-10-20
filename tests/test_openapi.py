def test_api_docs_promise_exactly_the_answers_the_service_gives(client):
    paths = client.get("/openapi.json").json()["paths"]
    webhook = paths["/webhooks"]["post"]

    assert [param["name"] for param in webhook["parameters"]] == ["X-PayFlow-Signature"]
    assert set(webhook["responses"]) == {"200", "400", "401", "413"}
    for path in ("/accounts/{account_id}/balance", "/accounts/{account_id}/transactions"):
        assert "404" in paths[path]["get"]["responses"]
