from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_service_status():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_unknown_venue_returns_not_found():
    with TestClient(app) as client:
        response = client.get("/api/venues/not-a-real-venue")
    assert response.status_code == 404
    assert response.json()["detail"] == "venue_not_found"


def test_unknown_emergency_node_returns_not_found():
    with TestClient(app) as client:
        response = client.post(
            "/api/simulation/emergency",
            json={"kind": "fire", "node_id": "not-a-real-node"},
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "venue_node_not_found"


def test_history_limit_is_bounded():
    with TestClient(app) as client:
        too_large = client.get("/api/simulation/history?limit=501")
        zero = client.get("/api/simulation/history?limit=0")
    assert too_large.status_code == 422
    assert zero.status_code == 422
