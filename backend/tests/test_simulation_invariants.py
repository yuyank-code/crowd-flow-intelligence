import time

from app.engine import CrowdEngine, build_demo_venue
from app.models import Scenario


def run(engine, ticks, dt=0.5):
    for _ in range(ticks):
        engine.tick(dt)
        assert engine.check_invariants() == []


def make(**kw):
    e = CrowdEngine(build_demo_venue())
    for k, v in kw.items():
        setattr(e.scenario, k, v)
    e.start()
    return e


def test_invariants_hold_through_normal_run():
    run(make(crowd_size=3000, arrival_rate=600), 200)


def test_exit_throughput_is_respected():
    e = make(crowd_size=3000, arrival_rate=3000, exit_rate=10)
    prev = 0
    for _ in range(300):
        e.tick(0.5)
        assert e.state.total_exited - prev <= 6  # 10/min * 0.5 min (+ carry rounding)
        prev = e.state.total_exited
    assert e.check_invariants() == []


def test_zero_exit_rate_means_nobody_leaves():
    e = make(crowd_size=500, arrival_rate=600, exit_rate=0)
    run(e, 200)
    assert e.state.total_exited == 0
    assert e.state.people_inside == e.state.total_entered


def test_small_arrival_rate_still_admits_people():
    e = make(crowd_size=3, arrival_rate=1)
    run(e, 20)
    assert e.state.total_entered == 3


def test_crowd_is_capped_at_max_agents_and_reported():
    e = CrowdEngine(build_demo_venue(), max_agents=100)
    e.scenario.crowd_size, e.scenario.arrival_rate = 5000, 5000
    e.start()
    run(e, 20)
    assert e.state.total_entered == 100
    assert e.snapshot()["state"]["crowd_capped"] is True


def test_node_occupancy_matches_people_inside_through_emergency_and_reset():
    e = make(crowd_size=2000, arrival_rate=600)
    run(e, 30)
    e.emergency("fire", "j-c")
    assert e.check_invariants() == []
    run(e, 20)
    e.clear_emergency()
    run(e, 20)
    e.reset()
    assert all(n.occupancy == 0 for n in e.venue.nodes.values())
    assert e.state.people_inside == 0 and not e.agents


def test_no_route_agents_are_stranded_not_lost():
    e = make(crowd_size=500, arrival_rate=600)
    run(e, 10)
    inside_before = e.state.people_inside
    e.emergency("fire", "j-c")          # cuts the stage/exit corridors
    run(e, 10)
    snap = e.snapshot()["state"]
    assert snap["stranded_agents"] > 0
    assert e.state.total_entered - e.state.total_exited == len(e.agents) >= inside_before


def test_stranded_agents_recover_when_incident_clears():
    e = make(crowd_size=300, arrival_rate=600, exit_rate=800)
    run(e, 6)
    e.emergency("fire", "j-c")
    run(e, 4)
    assert e.snapshot()["state"]["stranded_agents"] > 0
    e.clear_emergency()
    run(e, 5)
    assert e.snapshot()["state"]["stranded_agents"] == 0


def test_clearing_one_incident_keeps_other_closures():
    e = make()
    e.emergency("gate-failure", "gate-e")
    e.emergency("fire", "j-c")
    e.clear_emergency("j-c")
    assert e.closed_nodes == {"gate-e"}
    assert e.venue.edges["e-e"].status == "emergency-closed"   # still closed by gate-e
    assert e.venue.edges["e-cs"].status != "emergency-closed"  # reopened
    e.clear_emergency()
    assert not any(x.status == "emergency-closed" for x in e.venue.edges.values())


def test_closed_gate_arrivals_are_redirected_to_open_gates():
    e = make(crowd_size=400, arrival_rate=600)
    e.emergency("gate-failure", "gate-e")
    run(e, 5)
    assert all(a.node_id != "gate-e" or a.stranded for a in e.agents.values()) or e.snapshot()["state"]["stranded_agents"] == 0
    assert e.state.total_entered == 400


def test_event_history_is_bounded():
    e = make()
    for i in range(CrowdEngine.MAX_EVENTS + 50):
        e.emergency("drill", "gate-w") if i % 2 == 0 else e.clear_emergency()
    assert len(e.state.events) == CrowdEngine.MAX_EVENTS


def test_stress_at_configured_maximum_agent_count():
    e = CrowdEngine(build_demo_venue(), max_agents=20000)
    e.scenario = Scenario(crowd_size=20000, arrival_rate=20000, exit_rate=800)
    e.start()
    t0 = time.perf_counter()
    for _ in range(40):
        e.tick(0.5)
    per_tick = (time.perf_counter() - t0) / 40
    assert e.state.total_entered == 20000
    assert e.check_invariants() == []
    assert per_tick < 1.0, f"tick too slow at max agents: {per_tick:.2f}s"
