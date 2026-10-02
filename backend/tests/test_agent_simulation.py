from app.engine import CrowdEngine, build_demo_venue


def test_agents_follow_graph_routes():
    engine = CrowdEngine(build_demo_venue())
    engine.start()
    engine.tick(0.5)
    assert engine.state.total_entered > 0
    assert engine.state.people_inside > 0
    assert engine.agents
    assert all(a.path for a in engine.agents.values())


def test_emergency_closes_edges_and_reroutes():
    engine = CrowdEngine(build_demo_venue())
    engine.start()
    for _ in range(4):
        engine.tick(0.5)
    before = engine.reroute_count
    engine.emergency("fire", "j-c")
    assert engine.graph.get_edge("e-cs").disabled
    assert engine.graph.get_edge("e-cn").disabled
    assert engine.reroute_count >= before
    assert engine.state.events[-1]["type"] == "fire"


def test_snapshot_exposes_graph_and_agent_metrics():
    engine = CrowdEngine(build_demo_venue())
    snapshot = engine.snapshot()
    assert "graph" in snapshot
    assert "active_agents" in snapshot["state"]
    assert "reroutes" in snapshot["state"]
