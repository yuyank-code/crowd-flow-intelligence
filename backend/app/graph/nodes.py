from dataclasses import dataclass
from typing import Literal

NodeKind = Literal["gate","junction","zone","exit","facility","entry"]

@dataclass
class GraphNode:
    id: str
    label: str
    kind: NodeKind
    x: float
    y: float
    capacity: int
    current_occupancy: int = 0
    @property
    def utilization(self):
        return min(1.0, self.current_occupancy / max(1, self.capacity))
    def to_frontend_dict(self):
        return {"id":self.id,"label":self.label,"kind":self.kind,"x":self.x,"y":self.y,"capacity":self.capacity,"occupancy":self.current_occupancy,"utilization":round(self.utilization,4)}
