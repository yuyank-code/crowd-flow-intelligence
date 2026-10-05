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



def test_scenario_interpretation_is_structured_and_does_not_score_risk():
    from app.ai.service import interpret
    result = interpret("30000 people arriving at 900 per minute")
    assert result.crowd_size == 30000
    assert result.arrival_rate == 900
    assert result.exit_rate == 800
    assert not hasattr(result, "risk_score")


def test_decision_explanation_uses_engine_output_only():
    from app.ai.service import explain
    result = explain({"state": {"risk_score": 42, "risk_level": "MODERATE", "bottlenecks": ["e-w"], "events": []}})
    assert result["risk_score"] == 42
    assert result["bottlenecks"] == ["e-w"]
    assert "deterministic" in result["safety_note"]



def test_invalid_entry_distribution_is_rejected():
    from pydantic import ValidationError
    from app.main import ScenarioRequest
    try:
        ScenarioRequest(entry_distribution={"gate-e": 2.0})
        assert False, "expected validation error"
    except ValidationError:
        pass
