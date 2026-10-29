from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_liveness_without_database() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "procureops-ai"}


def test_openapi_is_available() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "ProcureOps AI"
