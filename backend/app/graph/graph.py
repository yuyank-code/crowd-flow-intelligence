import heapq, math
from dataclasses import dataclass, field
from .nodes import GraphNode
from .edges import GraphEdge
@dataclass
class VenueGraph:
    venue_id:str; name:str; width:float; height:float
    _nodes:dict[str,GraphNode]=field(default_factory=dict); _edges:dict[str,GraphEdge]=field(default_factory=dict); _adj:dict[str,list[tuple[str,str]]]=field(default_factory=dict)
    def add_node(self,n): self._nodes[n.id]=n; self._adj.setdefault(n.id,[])
    def add_edge(self,e,bidirectional=True):
        self._edges[e.id]=e; self._adj.setdefault(e.from_node,[]).append((e.to_node,e.id))
        if bidirectional:self._adj.setdefault(e.to_node,[]).append((e.from_node,e.id))
    @property
    def nodes(self): return self._nodes
    @property
    def edges(self): return self._edges
    def get_node(self,i): return self._nodes.get(i)
    def get_edge(self,i): return self._edges.get(i)
    def neighbors(self,i): return [(n,eid) for n,eid in self._adj.get(i,[]) if self._edges[eid].is_traversable]
    def get_edge_between(self,a,b):
        for n,eid in self._adj.get(a,[]):
            if n==b:return self._edges[eid]
        return None
    def find_path(self,source,destination,cost_fn=None,excluded_edges=None):
        if source==destination:return [source]
        if source not in self._nodes or destination not in self._nodes:return None
        excluded_edges=excluded_edges or set(); q=[(0,source)]; g={source:0}; prev={}
        def h(a,b):
            x,y=self._nodes[a],self._nodes[b]; return math.hypot(x.x-y.x,x.y-y.y)/100
        while q:
            _,cur=heapq.heappop(q)
            if cur==destination:
                p=[cur]
                while cur in prev:cur=prev[cur];p.append(cur)
                return p[::-1]
            for nxt,eid in self._adj.get(cur,[]):
                e=self._edges[eid]
                if not e.is_traversable or eid in excluded_edges:continue
                c=cost_fn(e) if cost_fn else e.dynamic_cost
                ng=g[cur]+c
                if ng<g.get(nxt,float("inf")):
                    g[nxt]=ng;prev[nxt]=cur;heapq.heappush(q,(ng+h(nxt,destination),nxt))
        return None
    def find_path_edges(self,a,b,cost_fn=None,excluded_edges=None):
        p=self.find_path(a,b,cost_fn,excluded_edges)
        if not p or len(p)<2:return []
        return [self.get_edge_between(p[i],p[i+1]) for i in range(len(p)-1)]
    def close_edge(self,eid,emergency=False):
        if eid in self._edges:self._edges[eid].disabled=True;self._edges[eid].status="emergency-closed" if emergency else "closed"
    def open_edge(self,eid):
        if eid in self._edges:self._edges[eid].disabled=False;self._edges[eid].status="open"
    def reset_edge_flows(self):
        for e in self._edges.values(): e.flow=e.density=e.current_occupancy=0;e.status="open" if not e.disabled else e.status
    def reset_node_occupancy(self):
        for n in self._nodes.values():n.current_occupancy=0
    def to_frontend_dict(self): return {"id":self.venue_id,"name":self.name,"width":self.width,"height":self.height,"nodes":[n.to_frontend_dict() for n in self._nodes.values()],"edges":[e.to_frontend_dict() for e in self._edges.values()]}
