import pytest
from fastapi.testclient import TestClient

from app.ai.service import interpret
from app.db import database
from app.db.repository import count, history, prune, save_snapshot
from app.main import app, engine


@pytest.fixture(autouse=True)
def fresh_engine():
    engine.reset()
    yield
    engine.reset()


def snap(t, risk, level="LOW"):
    return {"state": {"sim_time_min": t, "risk_score": risk, "risk_level": level}}


async def test_history_save_filter_order_and_prune():
    await database.init_db()
    sim = "pytest-sim"
    await prune(sim, 0)
    for i in range(10):
        await save_snapshot(sim, snap(i, i * 10, "HIGH" if i >= 6 else "LOW"))
    rows = await history(sim, limit=50)
    assert [r["sim_time_min"] for r in rows] == list(range(9, -1, -1))          # newest first
    assert all(r["risk_level"] == "HIGH" for r in await history(sim, risk_level="high"))
    assert len(await history(sim, min_risk=50)) == 5
    assert [r["sim_time_min"] for r in await history(sim, limit=3, offset=3)] == [6, 5, 4]
    removed = await prune(sim, 4)
    assert removed == 6 and await count(sim) == 4
    assert [r["sim_time_min"] for r in await history(sim)] == [9, 8, 7, 6]       # newest kept
    await prune(sim, 0)


def test_history_endpoint_validation():
    with TestClient(app) as c:
        assert c.get("/api/simulation/history?offset=-1").status_code == 422
        assert c.get("/api/simulation/history?risk_level=bogus").status_code == 422
        assert c.get("/api/simulation/history?min_risk=101").status_code == 422
        assert c.get("/api/simulation/history?limit=5&offset=0").status_code == 200


def test_scenario_validation_and_start_stop_flow():
    with TestClient(app) as c:
        bad = c.post("/api/simulation/scenario", json={"entry_distribution": {"gate-e": 0.2}})
        assert bad.status_code == 422
        ok = c.post("/api/simulation/scenario", json={"crowd_size": 100, "arrival_rate": 60, "exit_rate": 60})
        assert ok.status_code == 200
        assert c.post("/api/simulation/start").json()["status"] == "running"
        assert c.post("/api/simulation/pause").json()["status"] == "paused"
        assert c.post("/api/simulation/reset").json()["state"]["status"] == "standby"


def test_emergency_clear_selective_and_unknown():
    with TestClient(app) as c:
        c.post("/api/simulation/emergency", json={"kind": "fire", "node_id": "j-c"})
        c.post("/api/simulation/emergency", json={"kind": "gate-failure", "node_id": "gate-e"})
        r = c.post("/api/simulation/emergency/clear", json={"node_id": "j-c"})
        assert r.json()["state"]["closed_nodes"] == ["gate-e"]
        assert c.post("/api/simulation/emergency/clear", json={"node_id": "j-c"}).status_code == 404
        assert c.post("/api/simulation/emergency/clear").json()["state"]["closed_nodes"] == []


def test_text_endpoints_reject_oversized_input():
    with TestClient(app) as c:
        assert c.post("/api/scenarios/interpret", json={"text": "x" * 2001}).status_code == 422
        assert c.post("/api/scenarios/parse", json={"text": "5000 people"}).json()["crowd_size"] == 5000


@pytest.mark.parametrize("text,crowd,arrival", [
    ("30,000 people arriving at 900 per minute", 30000, 900),
    ("2k people", 2000, 600),
    ("1.5 million people", 1_000_000, 600),   # clamped to the 1,000,000 limit
    ("5 min warm-up for 8000 attendees", 8000, 600),   # 'min' must not read as millions
    ("", 20000, 600),
    ("gibberish !!!", 20000, 600),
    ("999999999999 people", 1_000_000, 600),
])
def test_interpreter_edge_cases(text, crowd, arrival):
    r = interpret(text)
    assert r.crowd_size == crowd and r.arrival_rate == arrival
    assert abs(sum(r.entry_distribution.values()) - 1.0) < 0.01
