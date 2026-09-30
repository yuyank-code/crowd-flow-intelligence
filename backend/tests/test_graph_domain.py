from app.graph.edges import GraphEdge
from app.graph.graph import VenueGraph
from app.graph.nodes import GraphNode

def test_a_star_prefers_open_low_cost_path():
    graph=VenueGraph("test","Test",100,100)
    for node in [
        GraphNode("a","A","entry",0,0,100),
        GraphNode("b","B","junction",50,0,100),
        GraphNode("c","C","junction",50,50,100),
        GraphNode("d","D","exit",100,50,100),
    ]:
        graph.add_node(node)
    graph.add_edge(GraphEdge("ab","a","b",4,10,1,100))
    graph.add_edge(GraphEdge("bd","b","d",4,10,1,100))
    graph.add_edge(GraphEdge("ac","a","c",4,10,2,100))
    graph.add_edge(GraphEdge("cd","c","d",4,10,2,100))
    assert graph.find_path("a","d")==["a","b","d"]

def test_closed_edge_is_not_traversable():
    graph=VenueGraph("test","Test",100,100)
    graph.add_node(GraphNode("a","A","entry",0,0,100))
    graph.add_node(GraphNode("b","B","exit",100,0,100))
    graph.add_edge(GraphEdge("ab","a","b",4,10,1,100))
    graph.close_edge("ab")
    assert graph.find_path("a","b") is None
