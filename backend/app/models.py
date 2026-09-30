from dataclasses import dataclass, field
from typing import Literal

NodeKind = Literal["gate","junction","zone","exit","facility"]

@dataclass
class Node:
    id: str
    label: str
    kind: NodeKind
    x: float
    y: float
    capacity: int
    occupancy: int = 0

@dataclass
class Edge:
    id: str
    source: str
    target: str
    length_m: float
    capacity_per_min: int
    width_m: float
    status: str = "open"
    flow_per_min: float = 0.0
    density: float = 0.0

@dataclass
class Venue:
    id: str
    name: str
    latitude: float
    longitude: float
    nodes: dict[str, Node]
    edges: dict[str, Edge]

@dataclass
class Scenario:
    crowd_size: int = 20000
    arrival_rate: int = 600
    exit_rate: int = 800
    entry_distribution: dict[str, float] = field(default_factory=lambda: {"gate-e": .55, "gate-w": .30, "gate-s": .15})

@dataclass
class SimulationState:
    status: str = "standby"
    sim_time_min: float = 0.0
    people_inside: int = 0
    total_entered: int = 0
    total_exited: int = 0
    risk_score: float = 0.0
    risk_level: str = "LOW"
    bottlenecks: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
