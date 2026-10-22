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
    stranded: bool = False          # no valid route right now; still inside the venue
    waiting_exit: bool = False      # reached an exit node, queued for exit throughput
    retry_version: int = -1         # topology version at which a stranded agent last retried

    @property
    def next_node(self):
        return self.path[self.path_index + 1] if self.path_index + 1 < len(self.path) else None


class CrowdEngine:
    """Graph-based agent simulation.

    Invariants (checked by ``check_invariants`` and the test-suite):
      * every agent in ``self.agents`` is a person inside the venue
      * people_inside == total_entered - total_exited == len(self.agents)
      * people leave only through the exit-throughput limiter
      * sum(node.occupancy) == people_inside
    """

    MAX_EVENTS = 200

    def __init__(self, venue: Venue, scenario: Scenario | None = None, seed: int = 42,
                 max_agents: int = 20000):
        self.venue, self.scenario = venue, scenario or Scenario()
        self.state = SimulationState()
        self.seed = seed
        self.max_agents = max_agents
        self.rng = random.Random(seed)
        self.closed_nodes: set[str] = set()
        self.graph = graph_from_venue(venue)
        self.exit_ids = [n.id for n in venue.nodes.values() if n.kind == "exit"]
        self.agents: dict[int, CrowdAgent] = {}
        self.next_agent_id = 1
        self.reroute_count = 0
        self.topology_version = 0
        self._arrival_carry = 0.0
        self._exit_carry = 0.0

    # ---- lifecycle -------------------------------------------------------
    def start(self):
        if self.state.status in {"standby", "paused"}: self.state.status = "running"

    def pause(self):
        if self.state.status == "running": self.state.status = "paused"

    def reset(self):
        self.state = SimulationState()
        self.rng = random.Random(self.seed)
        self.closed_nodes.clear(); self.agents.clear()
        self.next_agent_id = 1; self.reroute_count = 0; self.topology_version += 1
        self._arrival_carry = self._exit_carry = 0.0
        for n in self.venue.nodes.values(): n.occupancy = 0
        for e in self.venue.edges.values(): e.flow_per_min = 0; e.density = 0; e.status = "open"
        self.graph = graph_from_venue(self.venue)

    @property
    def effective_crowd_size(self) -> int:
        """Agents are 1:1 with people, so the crowd is capped at max_agents."""
        return min(self.scenario.crowd_size, self.max_agents)

    # ---- incidents -------------------------------------------------------
    def _log(self, event: dict):
        self.state.events.append(event)
        if len(self.state.events) > self.MAX_EVENTS:
            del self.state.events[: len(self.state.events) - self.MAX_EVENTS]

    def emergency(self, kind: str, node_id: str):
        if node_id not in self.venue.nodes: return
        self.closed_nodes.add(node_id)
        self._log({"type": kind, "node_id": node_id, "time": round(self.state.sim_time_min, 2)})
        self._topology_changed()

    def clear_emergency(self, node_id: str | None = None):
        """Reopen one incident node, or all of them when node_id is None.

        Edge state is recomputed from the remaining closed nodes, so clearing one
        incident never reopens edges that another incident still closes.
        """
        if node_id is None: self.closed_nodes.clear()
        else: self.closed_nodes.discard(node_id)
        self._log({"type": "clear", "node_id": node_id, "time": round(self.state.sim_time_min, 2)})
        self._topology_changed()

    def _topology_changed(self):
        self.topology_version += 1
        # edge statuses must be recomputed from closed_nodes *before* syncing to the routing graph
        self._update_flows(); self._sync_graph(); self._reroute_agents(); self._update_flows(); self._recalculate()

    # ---- main tick -------------------------------------------------------
    def tick(self, dt_min: float = 0.5):
        if self.state.status != "running": return self.snapshot()
        self._spawn(dt_min)
        self._move_agents(dt_min)
        self._retire_at_exits(dt_min)
        self._update_flows()
        self.state.sim_time_min += dt_min
        self._recalculate()
        return self.snapshot()

    def _spawn(self, dt_min: float):
        s = self.state
        self._arrival_carry += self.scenario.arrival_rate * dt_min
        want = int(self._arrival_carry)
        room = max(0, self.effective_crowd_size - s.total_entered)
        n = min(want, room)
        self._arrival_carry = 0.0 if room == 0 else self._arrival_carry - n
        for _ in range(n):
            gate = self._choose_gate()
            dest = "stage" if self.rng.random() < .82 else self._nearest_exit(gate)
            path = self.graph.find_path(gate, dest) if dest else None
            a = CrowdAgent(self.next_agent_id, gate, dest or "", path or [gate],
                           speed_m_per_min=65 + self.rng.random() * 25, stranded=path is None,
                           retry_version=self.topology_version)
            self.agents[a.id] = a; self.next_agent_id += 1; s.total_entered += 1

    def _choose_gate(self):
        """Pick an entry gate by the configured mix; closed gates are skipped and the mix renormalised."""
        mix = {g: f for g, f in self.scenario.entry_distribution.items()
               if g in self.venue.nodes and g not in self.closed_nodes and f > 0}
        if not mix:  # every configured gate is closed: people still arrive at the first gate and become stranded
            return next(iter(self.scenario.entry_distribution), "gate-e")
        r, cumulative, total = self.rng.random() * sum(mix.values()), 0.0, sum(mix.values())
        for gate, fraction in mix.items():
            cumulative += fraction
            if r <= cumulative: return gate
        return next(reversed(mix))

    def _nearest_exit(self, node_id: str):
        best, best_len = None, float("inf")
        for ex in self.exit_ids:
            if ex in self.closed_nodes: continue
            path = self.graph.find_path(node_id, ex)
            if not path: continue
            length = sum(self.graph.get_edge_between(path[i], path[i + 1]).length for i in range(len(path) - 1))
            if length < best_len: best, best_len = ex, length
        return best

    def _move_agents(self, dt):
        for a in self.agents.values():
            if a.waiting_exit: continue
            if a.stranded:
                # retry once per topology change, not every tick
                if a.retry_version != self.topology_version: self._reroute_agent(a)
                continue
            if a.node_id in self.closed_nodes:
                self._reroute_agent(a); continue
            remaining = a.speed_m_per_min * dt
            while remaining > 0 and not a.stranded and not a.waiting_exit:
                nxt = a.next_node
                if nxt is None:
                    if a.destination in self.exit_ids:
                        a.waiting_exit = True           # now subject to exit throughput
                    else:
                        self._reroute_agent(a, to_exit=True)   # reached stage -> head to an exit
                        if a.destination == a.node_id: a.waiting_exit = True
                    break
                edge = self.graph.get_edge_between(a.node_id, nxt)
                if edge is None or not edge.is_traversable:
                    self._reroute_agent(a); break
                step = min(remaining, max(1.0, edge.length - a.progress_m))
                a.progress_m += step; remaining -= step
                if a.progress_m >= edge.length - 1e-6:
                    a.node_id, a.path_index, a.progress_m = nxt, a.path_index + 1, 0.0

    def _retire_at_exits(self, dt):
        """The only place people leave: bounded by the configured exit rate (people/min)."""
        self._exit_carry += self.scenario.exit_rate * dt
        budget = int(self._exit_carry)
        self._exit_carry -= budget
        if budget <= 0: return
        for aid in [a.id for a in self.agents.values() if a.waiting_exit][:budget]:
            del self.agents[aid]; self.state.total_exited += 1

    def _reroute_agent(self, a, to_exit: bool = False) -> bool:
        """Re-plan from the agent's current node. No route -> stranded (kept inside, counted, retried on topology change)."""
        dest = self._nearest_exit(a.node_id) if to_exit or a.destination in self.exit_ids else a.destination
        if dest == a.node_id:
            a.destination, a.path, a.path_index, a.progress_m, a.stranded = dest, [a.node_id], 0, 0.0, False
            return False
        path = self.graph.find_path(a.node_id, dest) if dest else None
        a.retry_version = self.topology_version
        if not path:
            a.stranded = True; return False
        changed = path != a.path or a.stranded
        a.destination, a.path, a.path_index, a.progress_m, a.stranded = dest, path, 0, 0.0, False
        return changed

    def _reroute_agents(self):
        self.reroute_count += sum(1 for a in self.agents.values() if not a.waiting_exit and self._reroute_agent(a))

    # ---- state derivation ------------------------------------------------
    def _update_flows(self):
        for n in self.venue.nodes.values(): n.occupancy = 0
        counts = {e: 0.0 for e in self.venue.edges}
        for a in self.agents.values():
            self.venue.nodes[a.node_id].occupancy += 1
            if not a.stranded and not a.waiting_exit and a.next_node:
                edge = self.graph.get_edge_between(a.node_id, a.next_node)
                if edge: counts[edge.id] += 1
        for e in self.venue.edges.values():
            if e.source in self.closed_nodes or e.target in self.closed_nodes:
                e.status, e.flow_per_min, e.density = "emergency-closed", 0.0, 0.0
                continue
            e.flow_per_min = min(e.capacity_per_min * 1.5, counts[e.id] * 2.0 + e.capacity_per_min * 0.03)
            e.density = min(1.0, e.flow_per_min / max(1, e.capacity_per_min))
            e.status = "congested" if e.density >= THRESHOLDS.density_high else "open"
        self.state.people_inside = self.state.total_entered - self.state.total_exited

    def _sync_graph(self):
        sync_venue_to_graph(self.venue, self.graph, self.closed_nodes)

    def _recalculate(self):
        self._sync_graph()
        live = [e for e in self.venue.edges.values() if e.status in {"open", "congested"}]
        peak = max((e.density for e in live), default=0.0)
        count = sum(e.density >= THRESHOLDS.density_high for e in live)
        self.state.risk_score = min(100.0, peak * 78 + count * 4 + (15 if self.closed_nodes else 0))
        self.state.risk_level = THRESHOLDS.classify(peak)
        if self.closed_nodes and self.state.risk_level == "LOW": self.state.risk_level = "MODERATE"
        self.state.bottlenecks = [e.id for e in live if e.density >= THRESHOLDS.density_high]

    def check_invariants(self) -> list[str]:
        """Return a list of violated invariants (empty when consistent)."""
        s, problems = self.state, []
        if s.total_entered - s.total_exited != len(self.agents): problems.append("agents != entered - exited")
        if s.people_inside != len(self.agents) and s.status != "standby": problems.append("people_inside mismatch")
        if sum(n.occupancy for n in self.venue.nodes.values()) != len(self.agents): problems.append("node occupancy sum mismatch")
        if s.total_exited > s.total_entered: problems.append("exited > entered")
        return problems

    def snapshot(self):
        self._sync_graph()
        stranded = sum(a.stranded for a in self.agents.values())
        extra = {"active_agents": len(self.agents) - stranded, "stranded_agents": stranded,
                 "waiting_to_exit": sum(a.waiting_exit for a in self.agents.values()),
                 "reroutes": self.reroute_count, "effective_crowd_size": self.effective_crowd_size,
                 "crowd_capped": self.scenario.crowd_size > self.max_agents,
                 "closed_nodes": sorted(self.closed_nodes)}
        return {"venue": {"id": self.venue.id, "name": self.venue.name, "latitude": self.venue.latitude, "longitude": self.venue.longitude},
                "state": asdict(self.state) | extra,
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
