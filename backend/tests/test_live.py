import time

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core.config import settings
from app.live.store import store
from app.main import app, engine

KEY = {"X-API-Key": "live-key"}


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(settings, "operator_api_key", "live-key")
    monkeypatch.setattr(settings, "cctv_secret_key", Fernet.generate_key().decode())
    store.clear()
    engine.reset()
    yield
    store.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
        for item in c.get("/api/cctv/sources").json()["items"]:
            if item.get("origin") == "registered":
                c.delete(f"/api/cctv/sources/{item['id']}", headers=KEY)


def camera(client):
    r = client.post("/api/cctv/sources", json={"name": "cam", "source_type": "rtsp", "endpoint": "rtsp://192.0.2.10:554/s"}, headers=KEY)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def obs(cid, **kw):
    return {"camera_id": cid, "zone_id": "gate-e", "people": 4, "view_area_m2": 20} | kw


def test_observation_requires_operator_key(client):
    cid = camera(client)
    assert client.post("/api/live/observations", json=obs(cid)).status_code == 401
    assert client.post("/api/live/observations", json=obs(cid), headers=KEY).status_code == 200


def test_live_zone_appears_in_snapshot_separately_from_simulation(client):
    cid = camera(client)
    client.post("/api/live/observations", json=obs(cid, people=10), headers=KEY)
    snap = client.get("/api/simulation").json()
    assert "state" in snap and "nodes" in snap                       # simulation untouched
    (z,) = snap["live"]
    assert z["zone_id"] == "gate-e" and z["people"] == 10 and z["source"] == "camera-count" and z["status"] == "LIVE"
    assert z["capacity_people"] == 40.0 and z["density"] == 0.25      # 20 m2 * 2 persons/m2


def test_risk_uses_deterministic_thresholds(client):
    cid = camera(client)
    levels = {}
    for people in (0, 20, 30, 40, 80):
        client.post("/api/live/observations", json=obs(cid, people=people), headers=KEY)
        levels[people] = client.get("/api/live").json()["live"][0]["density_level"]
    assert levels == {0: "LOW", 20: "MODERATE", 30: "HIGH", 40: "CRITICAL", 80: "CRITICAL"}
    z = client.get("/api/live").json()["live"][0]
    assert z["risk_level"] == "CRITICAL" and z["risk_score"] == 100.0


def test_validation(client):
    cid = camera(client)
    bad = [obs(cid, zone_id="nope"), obs("no-such-camera"), obs(cid, people=-1), obs(cid, people=99999),
           obs(cid, view_area_m2=0), obs(cid, view_area_m2=-5), obs(cid, people="many")]
    codes = [client.post("/api/live/observations", json=b, headers=KEY).status_code for b in bad]
    assert codes == [404, 404, 422, 422, 422, 422, 422]
    assert client.get("/api/live").json()["live"] == []


def test_zone_goes_stale_without_fresh_counts(client, monkeypatch):
    cid = camera(client)
    client.post("/api/live/observations", json=obs(cid), headers=KEY)
    monkeypatch.setattr(settings, "live_stale_after_sec", 0.05)
    time.sleep(0.1)
    z = client.get("/api/live").json()["live"][0]
    assert z["stale"] is True and z["status"] == "STALE"


def test_deleting_camera_or_zone_clears_live_data(client):
    cid = camera(client)
    client.post("/api/live/observations", json=obs(cid), headers=KEY)
    assert client.delete("/api/live/gate-e", headers=KEY).status_code == 204
    assert client.get("/api/live").json()["live"] == []
    client.post("/api/live/observations", json=obs(cid), headers=KEY)
    client.delete(f"/api/cctv/sources/{cid}", headers=KEY)
    assert client.get("/api/live").json()["live"] == []


def test_observation_rate_limit_is_separate_from_operator_limit(client, monkeypatch):
    cid = camera(client)
    monkeypatch.setattr(settings, "rate_limit_live", 3)
    codes = [client.post("/api/live/observations", json=obs(cid), headers=KEY).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert client.post("/api/simulation/pause", headers=KEY).status_code == 200   # operator bucket unaffected


def test_websocket_stream_includes_live_zones(client):
    cid = camera(client)
    client.post("/api/live/observations", json=obs(cid), headers=KEY)
    with client.websocket_connect("/ws/simulation") as ws:
        assert ws.receive_json()["live"][0]["zone_id"] == "gate-e"
