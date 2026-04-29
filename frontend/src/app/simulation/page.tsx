"use client";
import { useState } from "react";
import useSWR from "swr";
import { fetchSimulationRuns, fetchWorkbench, createSimulationRun, type WorkbenchData } from "@/lib/api";

function StateChart({ wb }: { wb: WorkbenchData }) {
  const metrics = wb.kpi_comparator?.metrics || [];
  if (!metrics.length) return null;
  const mx = Math.max(...metrics.map((m) => Math.abs(m.delta ?? 0)), 1);
  return <div className="space-y-2">{metrics.map((m) => {
    const pct = ((m.delta ?? 0) / mx) * 50;
    return <div key={m.metric} className="flex items-center gap-2 text-xs"><div className="w-32 text-right text-[var(--muted)] truncate">{m.metric}</div><div className="flex-1 h-4 bg-[var(--background)] rounded relative overflow-hidden"><div className={`absolute top-0 h-full rounded ${(m.delta ?? 0) >= 0 ? "bg-[var(--accent-green)]" : "bg-[var(--accent-red)]"}`} style={{ left: pct >= 0 ? "50%" : `${50 + pct}%`, width: `${Math.abs(pct)}%` }} /><div className="absolute top-0 left-1/2 w-px h-full bg-[var(--muted)]/30" /></div><div className="w-16 text-right font-mono">{(m.delta ?? 0).toFixed(3)}</div></div>;
  })}</div>;
}

export default function SimulationPage() {
  const { data: runs, mutate } = useSWR("sim-runs", () => fetchSimulationRuns(30));
  const [sel, setSel] = useState<string | null>(null);
  const { data: wb } = useSWR(sel ? `wb-${sel}` : null, () => fetchWorkbench(sel!));
  const [showCreate, setShowCreate] = useState(false);
  const [domain, setDomain] = useState("corporate");
  const [ticks, setTicks] = useState(6);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-6">
      <div className="space-y-4">
        <div className="flex items-center justify-between"><h1 className="text-lg font-bold">Simulation Runs</h1><button onClick={() => setShowCreate(!showCreate)} className="text-xs bg-[var(--accent)] text-white px-3 py-1.5 rounded">New Run</button></div>
        {showCreate && <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4 space-y-2">
          <select className="w-full bg-[var(--background)] border border-[var(--card-border)] rounded p-2 text-sm" value={domain} onChange={(e) => setDomain(e.target.value)}><option value="corporate">Corporate</option><option value="military">Military</option></select>
          <div className="text-xs text-[var(--muted)]">Ticks: {ticks}</div><input type="range" min={2} max={12} value={ticks} onChange={(e) => setTicks(Number(e.target.value))} className="w-full" />
          <button onClick={async () => { await createSimulationRun({ domain_id: domain, tick_count: ticks, actor_template: domain === "military" ? "brigade" : "ai_model_provider" }); setShowCreate(false); mutate(); }} className="w-full bg-[var(--accent-green)] text-white rounded py-2 text-xs">Create & Run</button>
        </div>}
        <div className="space-y-2 max-h-[calc(100vh-200px)] overflow-y-auto">{runs?.map((r) => <button key={r.id} onClick={() => setSel(r.id)} className={`w-full text-left p-3 rounded border transition-colors ${sel === r.id ? "border-[var(--accent)] bg-[var(--accent)]/10" : "border-[var(--card-border)] bg-[var(--card)]"}`}>
          <div className="flex justify-between"><span className="text-xs font-mono">{r.id.slice(0, 8)}</span><span className={`text-xs ${r.status === "COMPLETED" ? "text-[var(--accent-green)]" : r.status === "FAILED" ? "text-[var(--accent-red)]" : "text-[var(--accent-yellow)]"}`}>{r.status}</span></div>
          <div className="text-xs text-[var(--muted)] mt-1">{r.domain_id} &middot; {r.tick_count} ticks &middot; {r.actor_template}</div>
        </button>)}{(!runs || !runs.length) && <div className="text-sm text-[var(--muted)] text-center py-8">No runs yet</div>}</div>
      </div>
      <div className="space-y-4">{wb ? (<>
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4"><h2 className="text-sm font-semibold mb-3">KPI Comparator</h2><StateChart wb={wb} /></div>
        {wb.timeline.length > 0 && <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4"><h2 className="text-sm font-semibold mb-2">Timeline ({wb.timeline.length})</h2><div className="space-y-1 max-h-60 overflow-y-auto">{wb.timeline.map((e) => <div key={e.event_id} className="text-xs py-1 border-b border-[var(--card-border)] last:border-0"><span className="text-[var(--accent)] font-mono mr-2">{e.tick != null ? `T${e.tick}` : "—"}</span><span className="text-[var(--muted)] mr-2">[{e.event_type}]</span>{e.title}</div>)}</div></div>}
        {wb.geo_map?.assets?.length > 0 && <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4"><h2 className="text-sm font-semibold mb-2">Geo Assets {wb.geo_map.theater ? `— ${wb.geo_map.theater}` : ""}</h2><div className="grid grid-cols-2 gap-2">{wb.geo_map.assets.map((a, i) => <div key={i} className="text-xs p-2 rounded bg-[var(--background)]"><div className="font-medium">{a.name}</div><div className="text-[var(--muted)]">{a.asset_type} &middot; {a.latitude.toFixed(2)}, {a.longitude.toFixed(2)}</div></div>)}</div></div>}
      </>) : <div className="text-sm text-[var(--muted)] text-center py-16">Select a simulation run</div>}</div>
    </div>
  );
}
