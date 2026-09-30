from app.engine import CrowdEngine, build_demo_venue


def test_engine_reset_and_start():
    engine = CrowdEngine(build_demo_venue())
    assert engine.state.status == "standby"
    engine.start()
    assert engine.state.status == "running"
    engine.tick(0.5)
    assert engine.state.people_inside >= 0


def test_emergency_closes_node_paths():
    engine = CrowdEngine(build_demo_venue())
    engine.start()
    engine.emergency("gate-failure", "gate-e")
    assert "gate-e" in engine.closed_nodes
    assert any(e.status == "emergency-closed" for e in engine.venue.edges.values())
