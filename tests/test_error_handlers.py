from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_not_found_uses_error_envelope() -> None:
    response = client.get("/missing")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == 404
    assert body["router"] == "/missing"
    assert body["message"] == "Not Found"
    assert body["details"] is None
