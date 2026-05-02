"use client";
import { useState } from "react";
import useSWR from "swr";
import { fetchSimulationRuns, fetchWorkbench, createSimulationRun, type WorkbenchData } from "@/lib/api";
import { useTranslation } from "@/contexts/LanguageContext";

function KPIBar({ metric, delta }: { metric: string; delta: number }) {
  const maxDelta = Math.abs(delta);
  const pct = (delta / Math.max(maxDelta, 1)) * 50;
  const isPositive = delta >= 0;

  return (
    <div className="flex items-center gap-3 py-2">
      <div className="w-32 text-right text-xs text-[var(--muted)] truncate">{metric}</div>
      <div className="flex-1 h-6 bg-[var(--background)] rounded-full relative overflow-hidden">
        <div className="absolute top-0 left-1/2 w-px h-full bg-[var(--muted)]/20" />
        <div
          className={`absolute top-0 h-full rounded-full transition-all duration-500 ${isPositive ? "bg-[var(--accent-green)]" : "bg-[var(--accent-red)]"}`}
          style={{
            left: isPositive ? "50%" : `${50 + pct}%`,
            width: `${Math.abs(pct)}%`,
          }}
        />
      </div>
      <div className={`w-20 text-right text-xs font-mono ${isPositive ? "text-[var(--accent-green)]" : "text-[var(--accent-red)]"}`}>
        {isPositive ? "+" : ""}{delta.toFixed(3)}
      </div>
    </div>
  );
}

function TimelineEvent({ event }: { event: { event_id: string; tick?: number | null; event_type: string; title: string } }) {
  const typeColors: Record<string, string> = {
    decision: "bg-blue-500",
    outcome: "bg-green-500",
    risk: "bg-red-500",
    opportunity: "bg-yellow-500",
    default: "bg-gray-500",
  };

  return (
    <div className="flex items-start gap-3 py-3 border-b border-[var(--card-border)] last:border-0">
      <div className={`w-2 h-2 rounded-full mt-2 ${typeColors[event.event_type] || typeColors.default}`} />
      <div className="flex-1">
        <div className="flex items-center gap-2">
          {event.tick != null && (
            <span className="text-xs font-mono text-[var(--accent)] bg-[var(--accent)]/10 px-2 py-0.5 rounded">
              T{event.tick}
            </span>
          )}
          <span className="text-xs text-[var(--muted)] uppercase">{event.event_type}</span>
        </div>
        <p className="text-sm mt-1">{event.title}</p>
      </div>
    </div>
  );
}

function GeoAssetCard({ asset }: { asset: { name: string; asset_type: string; latitude: number; longitude: number } }) {
  return (
    <div className="p-3 rounded-lg border border-[var(--card-border)] hover:border-[var(--accent)] transition-colors">
      <div className="flex items-center gap-2 mb-1">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent)]">
          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
          <circle cx="12" cy="10" r="3" />
        </svg>
        <span className="text-sm font-medium">{asset.name}</span>
      </div>
      <div className="text-xs text-[var(--muted)]">
        {asset.asset_type} &middot; {asset.latitude.toFixed(4)}, {asset.longitude.toFixed(4)}
      </div>
    </div>
  );
}

export default function SimulationPage() {
  const { t } = useTranslation();
  const { data: runs, mutate } = useSWR("sim-runs", () => fetchSimulationRuns(30));
  const [sel, setSel] = useState<string | null>(null);
  const { data: wb } = useSWR(sel ? `wb-${sel}` : null, () => fetchWorkbench(sel!));
  const [showCreate, setShowCreate] = useState(false);
  const [domain, setDomain] = useState("corporate");
  const [ticks, setTicks] = useState(6);
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    setCreating(true);
    try {
      await createSimulationRun({
        domain_id: domain,
        tick_count: ticks,
        actor_template: domain === "military" ? "brigade" : "ai_model_provider",
      });
      setShowCreate(false);
      mutate();
    } finally {
      setCreating(false);
    }
  };

  const statusColors: Record<string, { bg: string; text: string }> = {
    COMPLETED: { bg: "badge-success", text: "text-[var(--accent-green)]" },
    FAILED: { bg: "badge-error", text: "text-[var(--accent-red)]" },
    RUNNING: { bg: "badge-warning", text: "text-[var(--accent-yellow)]" },
    PENDING: { bg: "badge-warning", text: "text-[var(--accent-yellow)]" },
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("simulation.title")}</h1>
          <p className="text-[var(--muted)] mt-1">{t("simulation.subtitle")}</p>
        </div>
        <button onClick={() => setShowCreate(!showCreate)} className="btn btn-primary">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          {t("simulation.newSimulation")}
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5 animate-fadeIn">
          <h2 className="text-sm font-semibold mb-4">{t("simulation.createNewSimulation")}</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="text-xs text-[var(--muted)] mb-1 block">{t("simulation.domain")}</label>
              <select className="input select" value={domain} onChange={(e) => setDomain(e.target.value)}>
                <option value="corporate">{t("simulation.corporate")}</option>
                <option value="military">{t("simulation.military")}</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-[var(--muted)] mb-1 block">{t("simulation.timeSteps")}: {ticks}</label>
              <div className="flex items-center gap-3">
                <input type="range" min={2} max={12} value={ticks} onChange={(e) => setTicks(Number(e.target.value))} className="flex-1" />
                <span className="text-sm font-mono w-8 text-center">{ticks}</span>
              </div>
            </div>
            <div className="flex items-end">
              <button onClick={handleCreate} disabled={creating} className="btn btn-primary w-full">
                {creating ? (
                  <>
                    <div className="spinner" />
                    {t("common.creating")}
                  </>
                ) : (
                  t("simulation.createAndRun")
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6">
        {/* Left panel - Runs list */}
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>
            {t("simulation.simulationRuns")} ({runs?.length ?? 0})
          </h2>
          <div className="space-y-2 max-h-[calc(100vh-300px)] overflow-y-auto">
            {runs?.map((r) => {
              const status = statusColors[r.status] || statusColors.PENDING;
              return (
                <button
                  key={r.id}
                  onClick={() => setSel(r.id)}
                  className={`w-full text-left p-4 rounded-lg border transition-all ${
                    sel === r.id
                      ? "border-[var(--accent)] bg-[var(--accent)]/10"
                      : "border-[var(--card-border)] hover:border-[var(--muted)] hover:bg-[var(--card-hover)]"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-mono text-[var(--muted)]">{r.id.slice(0, 8)}</span>
                    <span className={`badge ${status.bg}`}>{r.status}</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
                    <span className="capitalize">{r.domain_id}</span>
                    <span>•</span>
                    <span>{r.tick_count} {t("simulation.ticks")}</span>
                    <span>•</span>
                    <span>{r.actor_template}</span>
                  </div>
                </button>
              );
            })}
            {(!runs || runs.length === 0) && (
              <div className="empty-state py-8">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 6v6l4 2" />
                </svg>
                <div className="empty-state-title">{t("simulation.noSimulations")}</div>
                <div className="empty-state-description">{t("simulation.noSimulationsDescription")}</div>
              </div>
            )}
          </div>
        </div>

        {/* Right panel - Workbench */}
        <div className="space-y-4">
          {wb ? (
            <>
              {/* KPI Comparator */}
              <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
                <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                  </svg>
                  {t("simulation.kpiComparator")}
                </h2>
                <KPIBar metric={t("simulation.overall")} delta={wb.kpi_comparator?.metrics?.[0]?.delta ?? 0} />
                {wb.kpi_comparator?.metrics?.slice(1).map((m) => (
                  <KPIBar key={m.metric} metric={m.metric} delta={m.delta ?? 0} />
                ))}
              </div>

              {/* Timeline */}
              {wb.timeline.length > 0 && (
                <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
                  <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="12 6 12 12 16 14" />
                    </svg>
                    {t("simulation.timeline")} ({wb.timeline.length})
                  </h2>
                  <div className="max-h-[300px] overflow-y-auto">
                    {wb.timeline.map((e) => (
                      <TimelineEvent key={e.event_id} event={e} />
                    ))}
                  </div>
                </div>
              )}

              {/* Geo Assets */}
              {wb.geo_map?.assets?.length > 0 && (
                <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
                  <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                      <circle cx="12" cy="10" r="3" />
                    </svg>
                    {t("simulation.geoAssets")} {wb.geo_map.theater ? `— ${wb.geo_map.theater}` : ""}
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {wb.geo_map.assets.map((a, i) => (
                      <GeoAssetCard key={i} asset={a} />
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5 min-h-[400px] flex items-center justify-center">
              <div className="empty-state">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 6v6l4 2" />
                </svg>
                <div className="empty-state-title">{t("simulation.selectRun")}</div>
                <div className="empty-state-description">{t("simulation.selectRunDescription")}</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
