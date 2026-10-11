from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from .graph.bridge import graph_from_venue, sync_venue_to_graph
from .models import Edge, Node, Scenario, SimulationState, Venue
from .risk.thresholds import THRESHOLDS


@dataclass
class CrowdAgent:
    """One simulated person moving through the venue graph."""

    id: int
    node_id: str
    destination: str
    path: list[str]
    path_index: int = 0
    progress_m: float = 0.0
    speed_m_per_min: float = 75.0
    active: bool = True
    stranded: bool = False

    @property
    def next_node(self) -> str | None:
        next_index = self.path_index + 1
        return self.path[next_index] if next_index < len(self.path) else None


class CrowdEngine:
    """Deterministic crowd-flow simulation with explicit arrival/exit budgets.

    The model is an operational simulation aid, not a certified life-safety model.
    """

    def __init__(
        self,
        venue: Venue,
        scenario: Scenario | None = None,
        seed: int = 42,
        max_agents: int = 20_000,
    ):
        self.venue = venue
        self.scenario = scenario or Scenario()
        self.seed = seed
        self.max_agents = max(1, int(max_agents))
        self.state = SimulationState()
        self.rng = random.Random(seed)
        self.closed_nodes: set[str] = set()
        self.graph = graph_from_venue(venue)
        self.agents: dict[int, CrowdAgent] = {}
        self.next_agent_id = 1
        self.reroute_count = 0
        self._arrival_credit = 0.0
        self._exit_credit = 0.0
        self._exit_allowance_this_tick = 0

    def start(self) -> None:
        if self.state.status in {"standby", "paused"}:
            self.state.status = "running"

    def pause(self) -> None:
        if self.state.status == "running":
            self.state.status = "paused"

    def reset(self) -> None:
        self.state = SimulationState()
        self.rng = random.Random(self.seed)
        self.closed_nodes.clear()
        self.agents.clear()
        self.next_agent_id = 1
        self.reroute_count = 0
        self._arrival_credit = 0.0
        self._exit_credit = 0.0
        self._exit_allowance_this_tick = 0
        for node in self.venue.nodes.values():
            node.occupancy = 0
        for edge in self.venue.edges.values():
            edge.flow_per_min = 0.0
            edge.density = 0.0
            edge.status = "open"
        self.graph = graph_from_venue(self.venue)

    def emergency(self, kind: str, node_id: str) -> None:
        if node_id not in self.venue.nodes:
            return
        if node_id in self.closed_nodes:
            return
        self.closed_nodes.add(node_id)
        self._record_event(kind, node_id)
        self._sync_graph()
        self._reroute_agents()
        self._update_flows(0.5)
        self._recalculate()

    def clear_emergency(self) -> None:
        if not self.closed_nodes:
            self._record_event("clear", None)
            return
        self.closed_nodes.clear()
        for edge in self.venue.edges.values():
            if edge.status == "emergency-closed":
                edge.status = "open"
        self._sync_graph()
        self._reroute_agents()
        self._update_flows(0.5)
        self._recalculate()
        self._record_event("clear", None)

    def _record_event(self, kind: str, node_id: str | None) -> None:
        self.state.events.append(
            {
                "type": kind,
                "node_id": node_id,
                "time": round(self.state.sim_time_min, 2),
            }
        )
        # Keep the live state bounded; snapshots and database history retain prior runs.
        del self.state.events[:-200]

    def tick(self, dt_min: float = 0.5) -> dict:
        if dt_min <= 0:
            raise ValueError("dt_min must be greater than zero")
        if self.state.status != "running":
            return self.snapshot()

        state, scenario = self.state, self.scenario
        entry_limit = min(max(0, scenario.crowd_size), self.max_agents)
        remaining_capacity = max(0, entry_limit - state.total_entered)

        if remaining_capacity:
            self._arrival_credit += max(0, scenario.arrival_rate) * dt_min
            entering = min(remaining_capacity, int(self._arrival_credit + 1e-9))
            self._arrival_credit -= entering
        else:
            entering = 0
            self._arrival_credit = 0.0

        if entering:
            state.total_entered += entering
            self._spawn_agents()

        # Whole-person capacity applies only in this tick. Unused whole capacity is
        # discarded; only fractional throughput carries forward, preventing bursts.
        self._exit_credit += max(0, scenario.exit_rate) * dt_min
        self._exit_allowance_this_tick = int(self._exit_credit + 1e-9)
        self._exit_credit -= self._exit_allowance_this_tick

        self._move_agents(dt_min)
        self._exit_allowance_this_tick = 0
        self._update_flows(dt_min)
        state.sim_time_min += dt_min
        self._recalculate()
        return self.snapshot()

    def _spawn_agents(self) -> None:
        target = min(self.max_agents, self.state.total_entered, max(0, self.scenario.crowd_size))
        while len(self.agents) < target:
            gate = self._choose_gate()
            destination = "stage" if self.rng.random() < 0.82 else "exit-n"
            path = self.graph.find_path(gate, destination) or [gate]
            agent = CrowdAgent(
                id=self.next_agent_id,
                node_id=gate,
                destination=destination,
                path=path,
                speed_m_per_min=65 + self.rng.random() * 25,
            )
            self.agents[agent.id] = agent
            self.next_agent_id += 1

    def _choose_gate(self) -> str:
        draw = self.rng.random()
        cumulative = 0.0
        for gate, fraction in self.scenario.entry_distribution.items():
            if fraction <= 0:
                continue
            cumulative += fraction
            if draw < cumulative and gate in self.venue.nodes:
                return gate
        valid_gates = [
            gate for gate, fraction in self.scenario.entry_distribution.items()
            if fraction > 0 and gate in self.venue.nodes
        ]
        if valid_gates:
            return valid_gates[-1]
        return next((node.id for node in self.venue.nodes.values() if node.kind == "gate"), "gate-e")

    def _move_agents(self, dt_min: float) -> None:
        for agent in self.agents.values():
            if not agent.active:
                continue
            if agent.stranded or agent.node_id in self.closed_nodes:
                self._reroute_agent(agent)
                if agent.stranded or agent.node_id in self.closed_nodes:
                    continue

            remaining = agent.speed_m_per_min * dt_min
            while remaining > 1e-9 and agent.active:
                if agent.next_node is None:
                    if agent.destination == "stage":
                        if agent.node_id != "stage":
                            if not self._reroute_agent(agent) or agent.next_node is None:
                                break
                            continue
                        agent.destination = "exit-n"
                        path = self.graph.find_path(agent.node_id, agent.destination)
                        if not path:
                            agent.path = [agent.node_id]
                            agent.path_index = 0
                            agent.progress_m = 0.0
                            agent.stranded = True
                            break
                        agent.path = path
                        agent.path_index = 0
                        agent.progress_m = 0.0
                        agent.stranded = False
                        continue

                    if agent.node_id != "exit-n":
                        if not self._reroute_agent(agent) or agent.next_node is None:
                            break
                        continue

                    if self._exit_allowance_this_tick > 0:
                        agent.active = False
                        self.state.total_exited += 1
                        self._exit_allowance_this_tick -= 1
                    break

                next_node = agent.next_node
                edge = self.graph.get_edge_between(agent.node_id, next_node)
                if edge is None or not edge.is_traversable:
                    if not self._reroute_agent(agent) or agent.next_node is None:
                        break
                    continue

                distance_left = max(0.0, edge.length - agent.progress_m)
                step = min(remaining, distance_left)
                if step <= 1e-9:
                    agent.node_id = next_node
                    agent.path_index += 1
                    agent.progress_m = 0.0
                    continue
                agent.progress_m += step
                remaining -= step
                if agent.progress_m >= edge.length - 1e-6:
                    agent.node_id = next_node
                    agent.path_index += 1
                    agent.progress_m = 0.0

    def _reroute_agent(self, agent: CrowdAgent) -> bool:
        path = self.graph.find_path(agent.node_id, agent.destination)
        if not path:
            changed = agent.path != [agent.node_id] or not agent.stranded
            agent.path = [agent.node_id]
            agent.path_index = 0
            agent.progress_m = 0.0
            agent.stranded = True
            return changed

        changed = path != agent.path or agent.stranded
        if changed:
            agent.path_index = 0
            agent.progress_m = 0.0
        agent.path = path
        agent.stranded = False
        return changed

    def _reroute_agents(self) -> None:
        changed = 0
        for agent in self.agents.values():
            if agent.active and self._reroute_agent(agent):
                changed += 1
        self.reroute_count += changed

    def _update_flows(self, dt_min: float) -> None:
        self._sync_graph()
        for node in self.venue.nodes.values():
            node.occupancy = 0
        counts = {edge_id: 0 for edge_id in self.venue.edges}

        for agent in self.agents.values():
            if not agent.active:
                continue
            if agent.node_id in self.venue.nodes:
                self.venue.nodes[agent.node_id].occupancy += 1
            next_node = agent.next_node
            if next_node is None:
                continue
            edge = self.graph.get_edge_between(agent.node_id, next_node)
            if edge and edge.is_traversable:
                counts[edge.id] += 1

        for edge in self.venue.edges.values():
            if edge.source in self.closed_nodes or edge.target in self.closed_nodes:
                edge.status = "emergency-closed"
                edge.flow_per_min = 0.0
                edge.density = 0.0
                continue
            edge.flow_per_min = min(
                edge.capacity_per_min * 1.5,
                counts[edge.id] / max(dt_min, 1e-9),
            )
            edge.density = min(1.0, edge.flow_per_min / max(1, edge.capacity_per_min))
            edge.status = (
                "congested"
                if edge.density >= THRESHOLDS.density_high
                else "open"
            )

        self.state.people_inside = max(0, self.state.total_entered - self.state.total_exited)
        self._sync_graph()

    def _sync_graph(self) -> None:
        sync_venue_to_graph(self.venue, self.graph, self.closed_nodes)

    def _recalculate(self) -> None:
        self._sync_graph()
        active_edges = [
            edge for edge in self.venue.edges.values()
            if edge.status in {"open", "congested"}
        ]
        peak_density = max((edge.density for edge in active_edges), default=0.0)
        bottleneck_count = sum(
            edge.density >= THRESHOLDS.density_high for edge in active_edges
        )
        self.state.risk_score = round(
            min(100.0, peak_density * 78 + bottleneck_count * 4 + (15 if self.closed_nodes else 0)),
            2,
        )
        self.state.risk_level = THRESHOLDS.classify(peak_density)
        if self.closed_nodes and self.state.risk_level == "LOW":
            self.state.risk_level = "MODERATE"
        self.state.bottlenecks = [
            edge.id for edge in active_edges
            if edge.density >= THRESHOLDS.density_high
        ]

    def snapshot(self) -> dict:
        self._sync_graph()
        return {
            "venue": {
                "id": self.venue.id,
                "name": self.venue.name,
                "latitude": self.venue.latitude,
                "longitude": self.venue.longitude,
            },
            "state": asdict(self.state) | {
                "active_agents": sum(agent.active for agent in self.agents.values()),
                "stranded_agents": sum(agent.active and agent.stranded for agent in self.agents.values()),
                "reroutes": self.reroute_count,
            },
            "nodes": [asdict(node) for node in self.venue.nodes.values()],
            "edges": [asdict(edge) for edge in self.venue.edges.values()],
            "graph": self.graph.to_frontend_dict(),
        }


def build_demo_venue() -> Venue:
    nodes = {
        "gate-w": Node("gate-w", "West Gate", "gate", 10, 50, 1200),
        "gate-e": Node("gate-e", "East Gate", "gate", 90, 50, 1800),
        "gate-s": Node("gate-s", "South Gate", "gate", 50, 90, 800),
        "j-w": Node("j-w", "West Junction", "junction", 30, 50, 1500),
        "j-e": Node("j-e", "East Junction", "junction", 70, 50, 1500),
        "j-c": Node("j-c", "Central Plaza", "zone", 50, 50, 5000),
        "stage": Node("stage", "Main Stage", "zone", 50, 25, 12000),
        "exit-n": Node("exit-n", "North Exit", "exit", 50, 8, 2000),
    }

    def edge(edge_id: str, source: str, target: str, length: float, capacity: int, width: float) -> Edge:
        return Edge(edge_id, source, target, length, capacity, width)

    edges = [
        edge("e-w", "gate-w", "j-w", 160, 900, 6),
        edge("e-e", "gate-e", "j-e", 160, 1200, 7),
        edge("e-s", "gate-s", "j-c", 140, 700, 5),
        edge("e-wc", "j-w", "j-c", 180, 1000, 5),
        edge("e-ec", "j-e", "j-c", 180, 1000, 5),
        edge("e-cs", "j-c", "stage", 120, 1400, 6),
        edge("e-cn", "j-c", "exit-n", 170, 1600, 6),
        edge("e-we", "j-w", "j-e", 420, 700, 4),
    ]
    return Venue(
        "venue-stadium-a",
        "Stadium A",
        28.6139,
        77.2090,
        nodes,
        {edge.id: edge for edge in edges},
    )
