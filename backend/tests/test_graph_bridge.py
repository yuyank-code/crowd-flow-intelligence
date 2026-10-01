from app.engine import build_demo_venue
from app.graph.bridge import graph_from_venue, sync_venue_to_graph

def test_demo_venue_bridges_to_graph():
    venue = build_demo_venue()
    graph = graph_from_venue(venue)
    assert set(graph.nodes) == set(venue.nodes)
    assert set(graph.edges) == set(venue.edges)

def test_closed_node_disables_incident_edges():
    venue = build_demo_venue()
    graph = graph_from_venue(venue)
    sync_venue_to_graph(venue, graph, {"j-c"})
    assert graph.get_edge("e-cs").disabled
    assert graph.get_edge("e-cn").disabled
    assert not graph.get_edge("e-w").disabled
