import math
import random
from dataclasses import asdict
from .models import Venue, Node, Edge, Scenario, SimulationState
from .risk.thresholds import THRESHOLDS
from .graph.bridge import graph_from_venue, sync_venue_to_graph

class CrowdEngine:
    def __init__(self, venue: Venue, scenario: Scenario | None = None, seed: int = 42):
        self.venue = venue
        self.scenario = scenario or Scenario()
        self.state = SimulationState()
        self.rng = random.Random(seed)
        self.closed_nodes: set[str] = set()\n        self.graph = graph_from_venue(venue)

    def start(self):
        if self.state.status in {"standby", "paused"}: self.state.status = "running"

    def pause(self):
        if self.state.status == "running": self.state.status = "paused"

    def reset(self):
        self.state = SimulationState()
        for n in self.venue.nodes.values(): n.occupancy = 0
        for e in self.venue.edges.values(): e.flow_per_min = 0; e.density = 0; e.status = "open"
        self.closed_nodes.clear()\n        self.graph = graph_from_venue(self.venue)

    def emergency(self, kind: str, node_id: str):
        if node_id in self.venue.nodes:
            self.closed_nodes.add(node_id)
            self.venue.nodes[node_id].occupancy = 0
            self.state.events.append({"type": kind, "node_id": node_id, "time": round(self.state.sim_time_min, 2)})
            self._recalculate()

    def clear_emergency(self):
        self.closed_nodes.clear()
        self.state.events.append({"type": "clear", "time": round(self.state.sim_time_min, 2)})

    def tick(self, dt_min: float = 0.5):
        if self.state.status != "running": return self.snapshot()
        s = self.state; sc = self.scenario
        if s.total_entered < sc.crowd_size:
            entering = min(sc.crowd_size - s.total_entered, int(sc.arrival_rate * dt_min))
            s.total_entered += entering
        inside_target = min(sc.crowd_size, s.total_entered)
        exits = min(s.people_inside, int(sc.exit_rate * dt_min * max(0.0, s.sim_time_min / 180.0)))
        s.total_exited += exits
        s.people_inside = max(0, inside_target - s.total_exited)
        for nid, frac in sc.entry_distribution.items():
            if nid in self.venue.nodes:
                self.venue.nodes[nid].occupancy = int(s.people_inside * frac * 0.18)
        # distribute load into the graph with deterministic, bounded formulas
        load = s.people_inside / max(1, sc.crowd_size)
        for e in self.venue.edges.values():
            if e.source in self.closed_nodes or e.target in self.closed_nodes:
                e.status = "emergency-closed"; e.flow_per_min = 0; e.density = 0; continue
            e.status = "open"
            phase = (math.sin((s.sim_time_min + len(e.id)) * .09) + 1) / 2
            e.flow_per_min = max(0.0, load * e.capacity_per_min * (.35 + .65 * phase))
            e.density = min(1.0, e.flow_per_min / max(1, e.capacity_per_min))
        s.sim_time_min += dt_min
        self._recalculate()
        return self.snapshot()

    def _recalculate(self):
        densities = [e.density for e in self.venue.edges.values() if e.status == "open"]
        peak = max(densities, default=0.0)
        count = sum(1 for e in self.venue.edges.values() if e.status == "open" and e.density >= .70)
        emergency = bool(self.closed_nodes)
        s = self.state
        s.risk_score = min(100.0, peak * 78 + count * 4 + (15 if emergency else 0))
        s.risk_level = THRESHOLDS.classify(peak)
        if emergency and s.risk_level == "LOW": s.risk_level = "MODERATE"
        s.bottlenecks = [e.id for e in self.venue.edges.values() if e.status == "open" and e.density >= THRESHOLDS.density_high]

    def snapshot(self):
        return {
            "venue": {"id": self.venue.id, "name": self.venue.name, "latitude": self.venue.latitude, "longitude": self.venue.longitude},
            "state": asdict(self.state),
            "nodes": [asdict(n) for n in self.venue.nodes.values()],
            "edges": [asdict(e) for e in self.venue.edges.values()],
        }

def build_demo_venue() -> Venue:
    nodes = {
        "gate-w": Node("gate-w","West Gate","gate",10,50,1200),
        "gate-e": Node("gate-e","East Gate","gate",90,50,1800),
        "gate-s": Node("gate-s","South Gate","gate",50,90,800),
        "j-w": Node("j-w","West Junction","junction",30,50,1500),
        "j-e": Node("j-e","East Junction","junction",70,50,1500),
        "j-c": Node("j-c","Central Plaza","zone",50,50,5000),
        "stage": Node("stage","Main Stage","zone",50,25,12000),
        "exit-n": Node("exit-n","North Exit","exit",50,8,2000),
    }
    def E(i,a,b,l,c,w): return Edge(i,a,b,l,c,w)
    edges = [
        E("e-w","gate-w","j-w",160,900,6), E("e-e","gate-e","j-e",160,1200,7), E("e-s","gate-s","j-c",140,700,5),
        E("e-wc","j-w","j-c",180,1000,5), E("e-ec","j-e","j-c",180,1000,5),
        E("e-cs","j-c","stage",120,1400,6), E("e-cn","j-c","exit-n",170,1600,6),
        E("e-we","j-w","j-e",420,700,4),
    ]
    return Venue("venue-stadium-a","Stadium A",28.6139,77.2090,nodes,{e.id:e for e in edges})
