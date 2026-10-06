from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from .graph.bridge import graph_from_venue, sync_venue_to_graph
from .models import Edge, Node, Scenario, SimulationState, Venue
from .risk.thresholds import THRESHOLDS


@dataclass
class CrowdAgent:
    id: int
    node_id: str
    destination: str
    path: list[str]
    path_index: int = 0
    progress_m: float = 0.0
    speed_m_per_min: float = 75.0
    active: bool = True

    @property
    def next_node(self):
        return self.path[self.path_index + 1] if self.path_index + 1 < len(self.path) else None


class CrowdEngine:
    def __init__(self, venue: Venue, scenario: Scenario | None = None, seed: int = 42):
        self.venue, self.scenario = venue, scenario or Scenario()
        self.state = SimulationState()
        self.seed = seed
        self.rng = random.Random(seed)
        self.closed_nodes = set()
        self.graph = graph_from_venue(venue)
        self.agents: dict[int, CrowdAgent] = {}
        self.next_agent_id = 1
        self.reroute_count = 0

    def start(self):
        if self.state.status in {"standby", "paused"}: self.state.status = "running"

    def pause(self):
        if self.state.status == "running": self.state.status = "paused"

    def reset(self):
        self.state = SimulationState()
        self.rng = random.Random(self.seed)
        self.closed_nodes.clear(); self.agents.clear(); self.next_agent_id = 1; self.reroute_count = 0
        for n in self.venue.nodes.values(): n.occupancy = 0
        for e in self.venue.edges.values(): e.flow_per_min = 0; e.density = 0; e.status = "open"
        self.graph = graph_from_venue(self.venue)

    def emergency(self, kind: str, node_id: str):
        if node_id not in self.venue.nodes: return
        self.closed_nodes.add(node_id)
        self.venue.nodes[node_id].occupancy = 0
        self.state.events.append({"type": kind, "node_id": node_id, "time": round(self.state.sim_time_min, 2)})
        self._sync_graph(); self._reroute_agents(); self._recalculate()

    def clear_emergency(self):
        self.closed_nodes.clear()
        for e in self.venue.edges.values(): e.status = "open"
        self._sync_graph(); self._reroute_agents()
        self.state.events.append({"type": "clear", "time": round(self.state.sim_time_min, 2)})

    def tick(self, dt_min: float = 0.5):
        if self.state.status != "running": return self.snapshot()
        s, sc = self.state, self.scenario
        inside = s.total_entered - s.total_exited
        natural_exits = min(inside, int(sc.exit_rate * dt_min)) if inside > 0 else 0
        entering_capacity = max(0, sc.crowd_size - s.total_entered)\n        entering = min(entering_capacity, int(sc.arrival_rate * dt_min))
        if entering:
            s.total_entered += entering
            self._spawn_agents()
        self._move_agents(dt_min)
        self._update_flows()
        s.sim_time_min += dt_min
        self._recalculate()
        return self.snapshot()

    def _retire_for_exit_rate(self, count: int):\n        """Apply the configured aggregate exit throughput without inventing paths."""\n        remaining = count\n        for agent in self.agents.values():\n            if remaining <= 0:\n                break\n            if agent.active and agent.destination == "exit-n" and agent.node_id == "exit-n":\n                agent.active = False\n                self.state.total_exited += 1\n                remaining -= 1\n\n    def _spawn_agents(self):
        target = min(self.scenario.crowd_size, 20000)
        while len(self.agents) < min(target, self.state.total_entered):
            gate = self._choose_gate()
            destination = "stage" if self.rng.random() < .82 else "exit-n"
            path = self.graph.find_path(gate, destination) or [gate]
            a = CrowdAgent(self.next_agent_id, gate, destination, path, speed_m_per_min=65 + self.rng.random() * 25)
            self.agents[a.id] = a; self.next_agent_id += 1

    def _choose_gate(self):
        r, cumulative = self.rng.random(), 0.0
        for gate, fraction in self.scenario.entry_distribution.items():
            cumulative += fraction
            if r <= cumulative and gate in self.venue.nodes: return gate
        return "gate-e"

    def _move_agents(self, dt):
        for a in self.agents.values():
            if not a.active: continue
            if a.node_id in self.closed_nodes: self._reroute_agent(a); continue
            remaining = a.speed_m_per_min * dt
            while remaining > 0 and a.active:
                nxt = a.next_node
                if nxt is None:
                    if a.destination == "stage":
                        a.destination = "exit-n"; a.path = self.graph.find_path(a.node_id, a.destination) or [a.node_id]; a.path_index = 0; a.progress_m = 0
                        continue
                    a.active = False
                    self.state.total_exited += 1
                    break
                edge = self.graph.get_edge_between(a.node_id, nxt)
                if edge is None or not edge.is_traversable: self._reroute_agent(a); break
                step = min(remaining, max(1.0, edge.length - a.progress_m))
                a.progress_m += step; remaining -= step
                if a.progress_m >= edge.length - 1e-6:
                    a.node_id, a.path_index, a.progress_m = nxt, a.path_index + 1, 0.0

    def _reroute_agent(self, a):
        path = self.graph.find_path(a.node_id, a.destination)
        if not path:
            a.active = False; return False
        changed = path != a.path
        a.path, a.path_index, a.progress_m = path, 0, 0.0
        return changed

    def _reroute_agents(self):
        self.reroute_count += sum(1 for a in self.agents.values() if a.active and self._reroute_agent(a))

    def _update_flows(self):
        active = [a for a in self.agents.values() if a.active]
        weight = self.state.total_entered / max(1, len(active))
        counts = {e: 0.0 for e in self.venue.edges}
        for a in active:
            if a.next_node:
                edge = self.graph.get_edge_between(a.node_id, a.next_node)
                if edge: counts[edge.id] += weight
        for e in self.venue.edges.values():
            if e.source in self.closed_nodes or e.target in self.closed_nodes:
                e.status, e.flow_per_min, e.density = "emergency-closed", 0.0, 0.0
                continue
            e.flow_per_min = min(e.capacity_per_min * 1.5, counts[e.id] * 2.0 + e.capacity_per_min * 0.03)
            e.density = min(1.0, e.flow_per_min / max(1, e.capacity_per_min))
            e.status = "congested" if e.density >= THRESHOLDS.density_high else "open"
        self.state.people_inside = max(0, self.state.total_entered - self.state.total_exited)

    def _sync_graph(self):
        sync_venue_to_graph(self.venue, self.graph, self.closed_nodes)

    def _recalculate(self):
        self._sync_graph()
        densities = [e.density for e in self.venue.edges.values() if e.status in {"open", "congested"}]
        peak = max(densities, default=0.0)
        count = sum(e.density >= THRESHOLDS.density_high for e in self.venue.edges.values() if e.status in {"open", "congested"})
        self.state.risk_score = min(100.0, peak * 78 + count * 4 + (15 if self.closed_nodes else 0))
        self.state.risk_level = THRESHOLDS.classify(peak)
        if self.closed_nodes and self.state.risk_level == "LOW": self.state.risk_level = "MODERATE"
        self.state.bottlenecks = [e.id for e in self.venue.edges.values() if e.status in {"open", "congested"} and e.density >= THRESHOLDS.density_high]

    def snapshot(self):
        self._sync_graph()
        return {"venue": {"id": self.venue.id, "name": self.venue.name, "latitude": self.venue.latitude, "longitude": self.venue.longitude},
                "state": asdict(self.state) | {"active_agents": sum(a.active for a in self.agents.values()), "reroutes": self.reroute_count},
                "nodes": [asdict(n) for n in self.venue.nodes.values()], "edges": [asdict(e) for e in self.venue.edges.values()],
                "graph": self.graph.to_frontend_dict()}


def build_demo_venue() -> Venue:
    nodes = {
        "gate-w": Node("gate-w","West Gate","gate",10,50,1200), "gate-e": Node("gate-e","East Gate","gate",90,50,1800),
        "gate-s": Node("gate-s","South Gate","gate",50,90,800), "j-w": Node("j-w","West Junction","junction",30,50,1500),
        "j-e": Node("j-e","East Junction","junction",70,50,1500), "j-c": Node("j-c","Central Plaza","zone",50,50,5000),
        "stage": Node("stage","Main Stage","zone",50,25,12000), "exit-n": Node("exit-n","North Exit","exit",50,8,2000)}
    def E(i,a,b,l,c,w): return Edge(i,a,b,l,c,w)
    edges = [E("e-w","gate-w","j-w",160,900,6),E("e-e","gate-e","j-e",160,1200,7),E("e-s","gate-s","j-c",140,700,5),
             E("e-wc","j-w","j-c",180,1000,5),E("e-ec","j-e","j-c",180,1000,5),E("e-cs","j-c","stage",120,1400,6),
             E("e-cn","j-c","exit-n",170,1600,6),E("e-we","j-w","j-e",420,700,4)]
    return Venue("venue-stadium-a","Stadium A",28.6139,77.2090,nodes,{e.id:e for e in edges})
