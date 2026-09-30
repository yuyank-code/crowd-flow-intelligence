def calculate_metrics(agents,graph,scenario,total_entered,total_exited):
    active=len(agents); occ=sum(e.current_occupancy for e in graph.edges.values()); cap=sum(max(1,e.capacity) for e in graph.edges.values());
    peak=max([e.density for e in graph.edges.values()] or [0]); avg=sum(e.density for e in graph.edges.values())/max(1,len(graph.edges))
    return {"activeAgents":active,"totalEntered":total_entered,"totalExited":total_exited,"networkOccupancy":occ,"peakDensity":round(peak,4),"averageDensity":round(avg,4),"throughputPerMin":round(total_exited/max(1,float(scenario.get("durationMin",60))),2),"capacityUtilization":round(occ/cap,4)}
