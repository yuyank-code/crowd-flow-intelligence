from dataclasses import dataclass
from typing import Literal
EdgeStatus=Literal["open","congested","closed","emergency-closed","recommended"]
@dataclass
class GraphEdge:
    id:str; from_node:str; to_node:str; width:float; length:float; base_cost:float; capacity:int; status:EdgeStatus="open"; flow:float=0.0; density:float=0.0; current_occupancy:int=0; disabled:bool=False; cctv_density:float=0.0; cctv_flow_in:float=0.0; cctv_flow_out:float=0.0; cctv_utilization:float=0.0; cctv_people:int=0
    @property
    def utilization(self): return min(1.0,self.flow/max(1,self.capacity))
    @property
    def dynamic_cost(self): return self.base_cost + max(self.density,self.cctv_density)*3 + max(self.utilization,self.cctv_utilization)*1.5
    @property
    def is_traversable(self): return not self.disabled and self.status not in ("closed","emergency-closed")
    def to_frontend_dict(self): return {"id":self.id,"from":self.from_node,"to":self.to_node,"width":self.width,"length":self.length,"capacity":self.capacity,"cost":self.base_cost,"status":self.status,"flow":round(self.flow,1),"density":round(self.density,4)}
