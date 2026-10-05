from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioInterpretation:
    crowd_size: int
    arrival_rate: int
    exit_rate: int
    entry_distribution: dict[str, float]
    assumptions: list[str]


def interpret(text: str) -> ScenarioInterpretation:
    """Deterministic fallback interpreter. It never assigns safety/risk scores."""
    t = text.lower().replace(",", "")
    crowd = 20_000
    m = re.search(r"(\d+(?:\.\d+)?)\s*(million|m|thousand|k)?\s*(?:people|persons|crowd)?", t)
    if m:
        value = float(m.group(1))
        unit = m.group(2) or ""
        if unit in ("million", "m"): value *= 1_000_000
        elif unit in ("thousand", "k"): value *= 1_000
        crowd = max(0, min(1_000_000, int(value)))
    arrival = _rate(t, r"(?:arriv(?:al|ing)|entry|entering)[^0-9]{0,20}(\d+)", 600)
    exit_rate = _rate(t, r"(?:exit|exiting|leav(?:e|ing))[^0-9]{0,20}(\d+)", 800)
    distribution = {"gate-e": .55, "gate-w": .30, "gate-s": .15}
    assumptions = ["Risk and routing are calculated separately by deterministic simulation engines."]
    if "west" in t: assumptions.append("West Gate is explicitly mentioned; default entry mix is retained.")
    if "east" in t: assumptions.append("East Gate is explicitly mentioned; default entry mix is retained.")
    return ScenarioInterpretation(crowd, arrival, exit_rate, distribution, assumptions)


def _rate(text: str, pattern: str, default: int) -> int:
    m = re.search(pattern, text)
    return max(0, min(100_000, int(m.group(1)))) if m else default


def explain(snapshot: dict) -> dict:
    state = snapshot.get("state", {})
    risk = float(state.get("risk_score", 0))
    level = state.get("risk_level", "LOW")
    bottlenecks = state.get("bottlenecks", [])
    incidents = state.get("events", [])
    if incidents:
        action = "Review the active incident and confirm affected corridors are clear before reopening them."
    elif bottlenecks:
        action = "Prioritize the listed bottlenecks and compare alternative routes before increasing inflow."
    else:
        action = "Continue monitoring inflow, corridor density, and exits; no deterministic bottleneck is currently flagged."
    return {"risk_level": level, "risk_score": risk, "bottlenecks": bottlenecks,
            "active_incidents": incidents[-5:], "operator_action": action,
            "safety_note": "This explanation summarizes deterministic engine output; it does not create or override safety scores."}
