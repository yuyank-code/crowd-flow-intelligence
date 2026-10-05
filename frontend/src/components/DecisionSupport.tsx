import { useEffect, useState } from "react";

type Props={api:string};
type Advice={risk_level:string;risk_score:number;bottlenecks:string[];active_incidents:any[];operator_action:string;safety_note:string};
export default function DecisionSupport({api}:Props){
 const [advice,setAdvice]=useState<Advice|null>(null);
 useEffect(()=>{let live=true; const load=async()=>{try{const r=await fetch(api+"/api/decision-support"); if(live)setAdvice(await r.json())}catch{}}; load(); const id=setInterval(load,2000); return()=>{live=false;clearInterval(id)}},[api]);
 if(!advice)return <p className="muted">Decision support unavailable.</p>;
 return <div><p><b>{advice.risk_level}</b> · {Math.round(advice.risk_score)}/100</p><p>{advice.operator_action}</p><small className="muted">{advice.safety_note}</small></div>
}
