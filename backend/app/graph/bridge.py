from __future__ import annotations
from .graph.graph import VenueGraph, GraphNode
from .graph.edges import GraphEdge
from .models import Venue

def graph_from_venue(venue: Venue) -> VenueGraph:
    graph = VenueGraph(venue.id, venue.name, 100.0, 100.0)
    for n in venue.nodes.values():
        graph.add_node(GraphNode(n.id, n.label, n.kind, n.x, n.y, n.capacity, n.occupancy))
    for e in venue.edges.values():
        graph.add_edge(GraphEdge(e.id, e.source, e.target, e.width_m, e.length_m, max(0.1, e.length_m / max(e.capacity_per_min, 1)), e.capacity_per_min))
    return graph

def sync_venue_to_graph(venue: Venue, graph: VenueGraph, closed_nodes: set[str]) -> None:
    graph.reset_node_occupancy()
    for node_id, node in graph.nodes.items():
        source = venue.nodes.get(node_id)
        if source:
            node.current_occupancy = source.occupancy
    for edge_id, edge in graph.edges.items():
        source = venue.edges.get(edge_id)
        if not source:
            continue
        edge.flow = source.flow_per_min
        edge.density = source.density
        edge.status = source.status
        edge.disabled = source.source in closed_nodes or source.target in closed_nodes

def sync_graph_to_venue(venue: Venue, graph: VenueGraph) -> None:
    for edge_id, edge in graph.edges.items():
        target = venue.edges.get(edge_id)
        if target:
            target.status = edge.status
            target.flow_per_min = edge.flow
            target.density = edge.density
