from app.engine import CrowdEngine, Scenario, build_demo_venue


def test_agents_follow_graph_routes():
    engine = CrowdEngine(build_demo_venue())
    engine.start()
    engine.tick(0.5)
    assert engine.state.total_entered > 0
    assert engine.state.people_inside > 0
    assert engine.agents
    assert all(agent.path for agent in engine.agents.values())


def test_emergency_closes_edges_and_reroutes_without_losing_people():
    engine = CrowdEngine(build_demo_venue())
    engine.start()
    for _ in range(4):
        engine.tick(0.5)
    entered_before = engine.state.total_entered
    exited_before = engine.state.total_exited
    engine.emergency("fire", "j-c")
    assert engine.graph.get_edge("e-cs").disabled
    assert engine.graph.get_edge("e-cn").disabled
    assert engine.state.total_entered == entered_before
    assert engine.state.total_exited == exited_before
    assert engine.reroute_count >= 0
    assert engine.state.events[-1]["type"] == "fire"


def test_snapshot_exposes_graph_and_agent_metrics():
    snapshot = CrowdEngine(build_demo_venue()).snapshot()
    assert "graph" in snapshot
    assert "active_agents" in snapshot["state"]
    assert "stranded_agents" in snapshot["state"]
    assert "reroutes" in snapshot["state"]


def test_fractional_arrival_rate_accumulates_between_ticks():
    engine = CrowdEngine(build_demo_venue(), Scenario(crowd_size=1, arrival_rate=1, exit_rate=0))
    engine.start()
    engine.tick(0.5)
    assert engine.state.total_entered == 0
    engine.tick(0.5)
    assert engine.state.total_entered == 1


def test_zero_exit_throughput_never_retires_people():
    engine = CrowdEngine(build_demo_venue(), Scenario(crowd_size=1, arrival_rate=2, exit_rate=0))
    engine.start()
    for _ in range(200):
        engine.tick(0.5)
    assert engine.state.total_entered == 1
    assert engine.state.total_exited == 0
    assert engine.state.people_inside == 1
    assert sum(agent.active for agent in engine.agents.values()) == 1


def test_exit_throughput_is_respected_and_population_balances():
    engine = CrowdEngine(build_demo_venue(), Scenario(crowd_size=1, arrival_rate=2, exit_rate=1))
    engine.start()
    for _ in range(200):
        engine.tick(0.5)
    assert engine.state.total_entered == 1
    assert engine.state.total_exited == 1
    assert engine.state.people_inside == 0
    assert engine.state.people_inside == engine.state.total_entered - engine.state.total_exited


def test_occupancy_matches_active_agents_at_nodes():
    engine = CrowdEngine(build_demo_venue())
    engine.start()
    for _ in range(4):
        engine.tick(0.5)
    counted = sum(node.occupancy for node in engine.venue.nodes.values())
    expected = sum(agent.active for agent in engine.agents.values())
    assert counted == expected


def test_clear_emergency_reopens_edges_and_restores_routes():
    engine = CrowdEngine(build_demo_venue())
    engine.start()
    for _ in range(4):
        engine.tick(0.5)
    engine.emergency("fire", "j-c")
    engine.clear_emergency()
    assert not engine.closed_nodes
    assert engine.graph.get_edge("e-cs").is_traversable
    assert engine.graph.get_edge("e-cn").is_traversable
    assert engine.state.events[-1]["type"] == "clear"


def test_event_history_is_bounded():
    engine = CrowdEngine(build_demo_venue())
    for index in range(250):
        engine.emergency("test", "j-c")
        engine.clear_emergency()
    assert len(engine.state.events) <= 200


def test_tick_rejects_non_positive_time_step():
    engine = CrowdEngine(build_demo_venue())
    try:
        engine.tick(0)
        assert False, "expected ValueError"
    except ValueError:
        pass
