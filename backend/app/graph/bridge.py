from __future__ import annotations

from ..models import Venue
from .edges import GraphEdge
from .graph import GraphNode, VenueGraph


def graph_from_venue(venue: Venue) -> VenueGraph:
    graph = VenueGraph(venue.id, venue.name, 100.0, 100.0)
    for node in venue.nodes.values():
        graph.add_node(
            GraphNode(
                node.id,
                node.label,
                node.kind,
                node.x,
                node.y,
                node.capacity,
                node.occupancy,
            )
        )
    for edge in venue.edges.values():
        graph.add_edge(
            GraphEdge(
                edge.id,
                edge.source,
                edge.target,
                edge.width_m,
                edge.length_m,
                max(0.1, edge.length_m / max(edge.capacity_per_min, 1)),
                edge.capacity_per_min,
            )
        )
    return graph


def sync_venue_to_graph(
    venue: Venue,
    graph: VenueGraph,
    closed_nodes: set[str],
) -> None:
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
        edge.disabled = (
            source.source in closed_nodes or source.target in closed_nodes
        )


def sync_graph_to_venue(venue: Venue, graph: VenueGraph) -> None:
    for edge_id, edge in graph.edges.items():
        target = venue.edges.get(edge_id)
        if target:
            target.status = edge.status
            target.flow_per_min = edge.flow
            target.density = edge.density
