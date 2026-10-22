import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core import security
from app.core.config import settings
from app.main import app, engine


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    engine.reset()
    for lim in (security.operator_limiter, security.geo_limiter, security.parse_limiter):
        lim.reset()
    yield
    engine.reset()
    for lim in (security.operator_limiter, security.geo_limiter, security.parse_limiter):
        lim.reset()


def test_auth_disabled_when_no_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "operator_api_key", "")
    with TestClient(app) as c:
        assert c.post("/api/simulation/start").status_code == 200


def test_operator_routes_require_key(monkeypatch):
    monkeypatch.setattr(settings, "operator_api_key", "s3cret")
    with TestClient(app) as c:
        for path in ["start", "pause", "reset", "emergency/clear"]:
            assert c.post(f"/api/simulation/{path}").status_code == 401
        assert c.post("/api/simulation/emergency", json={"kind": "fire", "node_id": "gate-e"}).status_code == 401
        assert c.post("/api/simulation/scenario", json={}).status_code == 401
        assert c.post("/api/simulation/start", headers={"X-API-Key": "wrong"}).status_code == 401
        ok = c.post("/api/simulation/start", headers={"X-API-Key": "s3cret"})
        assert ok.status_code == 200
        assert engine.state.status == "running"


def test_read_routes_stay_public(monkeypatch):
    monkeypatch.setattr(settings, "operator_api_key", "s3cret")
    with TestClient(app) as c:
        for path in ["/health", "/api/simulation", "/api/simulation/history", "/api/venues", "/api/cctv/sources"]:
            assert c.get(path).status_code == 200, path


def test_rejected_request_does_not_change_state(monkeypatch):
    monkeypatch.setattr(settings, "operator_api_key", "s3cret")
    before = engine.state.status
    with TestClient(app) as c:
        c.post("/api/simulation/start")
    assert engine.state.status == before


def test_operator_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "operator_api_key", "")
    monkeypatch.setattr(settings, "rate_limit_operator", 3)
    with TestClient(app) as c:
        codes = [c.post("/api/simulation/pause").status_code for _ in range(5)]
        assert codes == [200, 200, 200, 429, 429]
        r = c.post("/api/simulation/pause")
        assert int(r.headers["retry-after"]) >= 1


def test_unauthenticated_requests_still_count_toward_limit(monkeypatch):
    monkeypatch.setattr(settings, "operator_api_key", "k")
    monkeypatch.setattr(settings, "rate_limit_operator", 2)
    with TestClient(app) as c:
        codes = [c.post("/api/simulation/start").status_code for _ in range(3)]
    assert codes[0] == 401  # key check runs first


def test_parse_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_parse", 2)
    with TestClient(app) as c:
        codes = [c.post("/api/scenarios/parse", json={"text": "5000 people"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_geo_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_geo", 1)
    with TestClient(app) as c:
        assert c.get("/api/geo/search?q=x").status_code == 422  # validation, but limiter ran first
        assert c.get("/api/geo/search?q=x").status_code == 429


def test_forwarded_for_ignored_unless_trusted(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_parse", 1)
    monkeypatch.setattr(settings, "trust_proxy", False)
    with TestClient(app) as c:
        a = c.post("/api/scenarios/parse", json={"text": "x"}, headers={"X-Forwarded-For": "1.1.1.1"})
        b = c.post("/api/scenarios/parse", json={"text": "x"}, headers={"X-Forwarded-For": "2.2.2.2"})
    assert (a.status_code, b.status_code) == (200, 429)  # spoofed header gives no fresh quota


def test_forwarded_for_used_when_trusted(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_parse", 1)
    monkeypatch.setattr(settings, "trust_proxy", True)
    with TestClient(app) as c:
        a = c.post("/api/scenarios/parse", json={"text": "x"}, headers={"X-Forwarded-For": "1.1.1.1"})
        b = c.post("/api/scenarios/parse", json={"text": "x"}, headers={"X-Forwarded-For": "2.2.2.2"})
    assert (a.status_code, b.status_code) == (200, 200)


def test_cors_preflight_allows_key_header_only_for_allowed_origin():
    with TestClient(app) as c:
        ok = c.options("/api/simulation/start", headers={
            "Origin": settings.cors_origins[0], "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key,content-type"})
        bad = c.options("/api/simulation/start", headers={
            "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert ok.status_code == 200 and "x-api-key" in ok.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-origin" not in bad.headers
    assert "access-control-allow-credentials" not in ok.headers


def test_websocket_origin_checks():
    with TestClient(app) as c:
        with c.websocket_connect("/ws/simulation") as ws:  # no Origin header: allowed
            assert "state" in ws.receive_json()
        with c.websocket_connect("/ws/simulation", headers={"Origin": settings.cors_origins[0]}) as ws:
            assert "state" in ws.receive_json()
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/ws/simulation", headers={"Origin": "https://evil.example"}):
                pass


def test_websocket_connection_cap(monkeypatch):
    monkeypatch.setattr(settings, "ws_max_per_ip", 1)
    with TestClient(app) as c:
        with c.websocket_connect("/ws/simulation") as first:
            first.receive_json()
            with pytest.raises(WebSocketDisconnect):
                with c.websocket_connect("/ws/simulation"):
                    pass
        # slot released after disconnect
        with c.websocket_connect("/ws/simulation") as again:
            assert "state" in again.receive_json()
    assert security.ws_connections.total == 0
