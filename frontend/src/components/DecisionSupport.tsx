import { useEffect, useState } from "react";
import { request } from "../api";

type Advice = {
  risk_level: string;
  risk_score: number;
  bottlenecks: string[];
  active_incidents: unknown[];
  operator_action: string;
  safety_note: string;
};

export default function DecisionSupport({ active }: { active: boolean }) {
  const [advice, setAdvice] = useState<Advice | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return; // don't poll while the backend is unreachable
    let live = true;
    const load = async () => {
      try {
        const a = await request<Advice>("/api/decision-support");
        if (live) { setAdvice(a); setError(null); }
      } catch (e) {
        if (live) setError((e as Error).message);
      }
    };
    load();
    const id = window.setInterval(load, 2000);
    return () => { live = false; window.clearInterval(id); };
  }, [active]);

  if (error && !advice) return <p className="muted">Decision support unavailable: {error}</p>;
  if (!advice) return <p className="muted">Loading…</p>;
  return (
    <div>
      {error && <p className="muted">Showing last result; refresh failed.</p>}
      <p><b>{advice.risk_level}</b> · {Math.round(advice.risk_score)}/100</p>
      <p>{advice.operator_action}</p>
      <small className="muted">{advice.safety_note}</small>
    </div>
  );
}
