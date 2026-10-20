from tests.conftest import ROOT


def test_dashboard_page_is_served_with_a_strict_content_security_policy(client):
    response = client.get("/")

    policy = response.headers["content-security-policy"]
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "script-src 'self'" in policy and "unsafe-inline" not in policy
    assert response.headers["x-content-type-options"] == "nosniff"


def test_dashboard_assets_are_served(client):
    assert client.get("/static/dashboard.js").status_code == 200
    assert client.get("/static/dashboard.css").status_code == 200


def test_dashboard_is_not_part_of_the_api_docs(client):
    assert "/" not in client.get("/openapi.json").json()["paths"]


def test_dashboard_script_never_renders_webhook_data_as_html():
    # Merchant names come from webhooks; they must only ever reach the page as text.
    script = (ROOT / "app" / "static" / "dashboard.js").read_text()

    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert sink not in script
