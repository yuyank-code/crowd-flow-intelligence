from dataclasses import dataclass
from typing import Literal
AgentState=Literal["waiting","moving","queued","arrived","exited","rerouting"]
@dataclass
class CrowdGroup:
    id:str; name:str; total_size:int; entry_gate_id:str; destination_node_id:str; arrival_start_min:float; arrival_end_min:float; spawned:int=0; active:int=0; exited:int=0
    @property
    def remaining_to_spawn(self):return max(0,self.total_size-self.spawned)
    def spawn_rate_per_min(self):return self.total_size/max(1,self.arrival_end_min-self.arrival_start_min)
@dataclass
class SimAgent:
    id:int;x:float;y:float;vx:float;vy:float;group_id:str;from_node_id:str;to_node_id:str;edge_id:str;progress:float;speed:float;state:AgentState="moving";destination_node_id:str=""
    def to_frontend_dict(self):return {"id":self.id,"x":round(self.x,2),"y":round(self.y,2),"vx":round(self.vx,3),"vy":round(self.vy,3),"groupId":self.group_id,"fromNodeId":self.from_node_id,"toNodeId":self.to_node_id,"edgeId":self.edge_id,"progress":round(self.progress,4),"speed":round(self.speed,2)}
