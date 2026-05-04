"use client";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { fetchSimulationRuns, fetchWorkbench, createSimulationRun, type SimulationRun } from "@/lib/api";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/ui/data-table";
import { useTranslation } from "@/contexts/LanguageContext";
import { toast } from "@/lib/toast";

function MiniSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="divide-y divide-[var(--card-border)]">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="py-4 animate-pulse">
          <div className="h-3 w-1/2 bg-[var(--card-hover)]" />
          <div className="mt-3 h-3 w-4/5 bg-[var(--card-hover)]" />
        </div>
      ))}
    </div>
  );
}

function StateBlock({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex min-h-[360px] items-center justify-center text-center">
      <div>
        <div className="mx-auto mb-4 h-px w-14 bg-[var(--accent)]" />
        <div className="heading-section">{title}</div>
        {description && <div className="mx-auto mt-2 max-w-sm text-sm text-[var(--muted)]">{description}</div>}
      </div>
    </div>
  );
}

function KPIBar({ metric, delta, maxAbs }: { metric: string; delta: number; maxAbs: number }) {
  const pct = Math.min((Math.abs(delta) / Math.max(maxAbs, 0.001)) * 50, 50);
  const isPositive = delta >= 0;

  return (
    <div className="grid grid-cols-[130px_1fr_82px] items-center gap-4 py-3">
      <div className="truncate text-right text-xs text-[var(--muted)]">{metric}</div>
      <div className="relative h-7 bg-[var(--card)]">
        <div className="absolute left-1/2 top-0 h-full w-px bg-[var(--muted)]/30" />
        <div
          className={`absolute top-1/2 h-2 -translate-y-1/2 transition-[width,transform,opacity] duration-500 ${
            isPositive ? "left-1/2 bg-[var(--accent-green)]" : "right-1/2 bg-[var(--accent-red)]"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className={`text-right font-mono text-xs ${isPositive ? "text-[var(--accent-green)]" : "text-[var(--accent-red)]"}`}>
        {isPositive ? "+" : ""}{delta.toFixed(3)}
      </div>
    </div>
  );
}

function TimelineEvent({ event, isLast }: { event: { event_id: string; tick?: number | null; event_type: string; title: string }; isLast: boolean }) {
  const typeColors: Record<string, string> = {
    decision: "bg-[var(--accent)]",
    outcome: "bg-[var(--accent-green)]",
    risk: "bg-[var(--accent-red)]",
    opportunity: "bg-[var(--accent-amber)]",
    default: "bg-[var(--muted)]",
  };

  return (
    <div className="grid grid-cols-[64px_24px_1fr] gap-4">
      <div className="pt-1 text-right font-mono text-xs text-[var(--muted)]">
        {event.tick != null ? `T${event.tick}` : "-"}
      </div>
      <div className="relative flex justify-center">
        <span className={`mt-1.5 h-2.5 w-2.5 rounded-full ${typeColors[event.event_type] || typeColors.default}`} />
        {!isLast && <span className="absolute top-5 h-[calc(100%-8px)] w-px bg-[var(--card-border)]" />}
      </div>
      <div className="pb-7">
        <div className="section-label !text-[var(--muted)]">{event.event_type}</div>
        <p className="mt-1 text-sm leading-6 text-[var(--muted-foreground)]">{event.title}</p>
      </div>
    </div>
  );
}

function GeoAssetRow({ asset }: { asset: { name: string; asset_type: string; latitude: number; longitude: number } }) {
  return (
    <div className="grid grid-cols-[1fr_120px_170px] gap-4 divider-subtle py-3 text-sm">
      <div className="min-w-0 truncate font-medium">{asset.name}</div>
      <div className="text-[var(--muted)]">{asset.asset_type}</div>
      <div className="text-right font-mono text-xs text-[var(--muted-foreground)]">
        {asset.latitude.toFixed(4)}, {asset.longitude.toFixed(4)}
      </div>
    </div>
  );
}

function StatusBadgeSim({ status }: { status: string }) {
  const cls: Record<string, string> = {
    COMPLETED: "badge badge-success",
    FAILED: "badge badge-error",
    RUNNING: "badge badge-warning",
    PENDING: "badge badge-warning",
  };
  return <span className={cls[status] || "badge"}>{status}</span>;
}

export default function SimulationPage() {
  const { t } = useTranslation();
  const { data: runs, error: runsError, isLoading: runsLoading, mutate } = useSWR("sim-runs", () => fetchSimulationRuns(30));
  const [sel, setSel] = useState<string | null>(null);
  const { data: wb, error: wbError, isLoading: wbLoading } = useSWR(sel ? `wb-${sel}` : null, () => fetchWorkbench(sel!));
  const [showCreate, setShowCreate] = useState(false);
  const [domain, setDomain] = useState("corporate");
  const [ticks, setTicks] = useState(6);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const handleCreate = async () => {
    setCreating(true);
    setCreateError(null);
    try {
      await createSimulationRun({
        domain_id: domain,
        tick_count: ticks,
        actor_template: domain === "military" ? "brigade" : "ai_model_provider",
      });
      setShowCreate(false);
      toast.success('推演已启动');
      mutate();
    } catch (error) {
      setCreateError(String(error instanceof Error ? error.message : error));
    } finally {
      setCreating(false);
    }
  };

  const metrics = wb?.kpi_comparator?.metrics || [];
  const maxAbsDelta = useMemo(() => Math.max(0.001, ...metrics.map((m) => Math.abs(m.delta ?? 0))), [metrics]);

  const runColumns = useMemo<ColumnDef<SimulationRun>[]>(
    () => [
      {
        accessorKey: "id",
        header: "ID",
        cell: ({ row }) => <span className="font-mono text-xs">{row.original.id.slice(0, 8)}</span>,
      },
      {
        accessorKey: "status",
        header: t("common.status"),
        cell: ({ row }) => <StatusBadgeSim status={row.original.status} />,
      },
      {
        accessorKey: "domain_id",
        header: t("simulation.domain"),
        cell: ({ row }) => <span className="capitalize">{row.original.domain_id}</span>,
      },
      {
        accessorKey: "tick_count",
        header: t("simulation.ticks"),
      },
      {
        accessorKey: "actor_template",
        header: t("simulation.actorTemplate"),
      },
    ],
    [t],
  );

  return (
    <div className="mx-auto max-w-[1500px] space-y-8">
      {/* ── Page Header ── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_auto]">
        <div>
          <div className="section-label">{t("simulation.title")}</div>
          <h1 className="heading-display mt-3">{t("simulation.subtitle")}</h1>
        </div>
        <div className="flex items-end">
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="btn btn-primary"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            {t("simulation.newSimulation")}
          </button>
        </div>
      </div>
      <div className="divider-line" />

      {/* ── Create Form ── */}
      {showCreate && (
        <section className="animate-fadeIn rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-6">
          <div className="mb-6 flex items-center justify-between gap-6">
            <h2 className="heading-section">{t("simulation.createNewSimulation")}</h2>
            <div className="hidden gap-3 section-label !text-[var(--muted)] md:flex">
              <span className="!text-[var(--accent)]">01 {t("simulation.domain")}</span>
              <span>02 {t("simulation.timeSteps")}</span>
              <span>03 {t("simulation.createAndRun")}</span>
            </div>
          </div>
          <div className="grid gap-6 lg:grid-cols-[0.9fr_1fr_220px]">
            <div className="border-l border-[var(--accent)] pl-5">
              <label className="section-label">{t("simulation.domain")}</label>
              <select className="mt-3 w-full rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-lg outline-none" value={domain} onChange={(event) => setDomain(event.target.value)}>
                <option value="corporate">{t("simulation.corporate")}</option>
                <option value="military">{t("simulation.military")}</option>
              </select>
            </div>
            <div className="border-l border-[var(--card-border)] pl-5">
              <label className="section-label">{t("simulation.timeSteps")}: {ticks}</label>
              <div className="mt-5 flex items-center gap-4">
                <input type="range" min={2} max={12} value={ticks} onChange={(event) => setTicks(Number(event.target.value))} className="flex-1 accent-[var(--accent)]" />
                <span className="w-10 text-right font-mono text-2xl">{ticks}</span>
              </div>
            </div>
            <div className="flex items-end">
              <button
                onClick={handleCreate}
                disabled={creating}
                className="btn btn-primary w-full"
              >
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
          {createError && <div className="mt-5 border-l border-[var(--accent-red)] pl-4 text-sm text-[var(--accent-red)]">{t("common.failed")}: {createError}</div>}
        </section>
      )}

      {/* ── Main Content ── */}
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[390px_1fr]">
        {/* Sidebar — Runs List */}
        <aside className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="heading-section">{t("simulation.simulationRuns")}</h2>
            <span className="font-mono text-xs text-[var(--muted)]">{runs?.length ?? 0}</span>
          </div>

          {runsLoading && <MiniSkeleton rows={7} />}
          {runsError && <StateBlock title={t("common.failed")} description={String(runsError.message || runsError)} />}
          {!runsLoading && !runsError && (!runs || runs.length === 0) && (
            <StateBlock title={t("simulation.noSimulations")} description={t("simulation.noSimulationsDescription")} />
          )}

          {!runsLoading && !runsError && runs && runs.length > 0 && (
            <DataTable
              columns={runColumns}
              data={runs}
              searchColumn="id"
              searchPlaceholder="ID..."
              pageSize={10}
              onRowClick={(r) => setSel(r.id)}
            />
          )}
        </aside>

        {/* Main — Workbench */}
        <main className="min-w-0 space-y-8">
          {wbLoading && <MiniSkeleton rows={8} />}
          {wbError && <StateBlock title={t("common.failed")} description={String(wbError.message || wbError)} />}
          {!sel && !wbLoading && !wbError && <StateBlock title={t("simulation.selectRun")} description={t("simulation.selectRunDescription")} />}
          {sel && !wbLoading && !wbError && wb && (
            <>
              <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
                {/* KPI Comparator */}
                <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
                  <div className="mb-5 flex items-center justify-between">
                    <h2 className="heading-section">{t("simulation.kpiComparator")}</h2>
                    <span className="font-mono text-xs text-[var(--muted)]">{metrics.length}</span>
                  </div>
                  <div className="divide-y divide-[var(--card-border)]/70">
                    <KPIBar metric={t("simulation.overall")} delta={metrics[0]?.delta ?? 0} maxAbs={maxAbsDelta} />
                    {metrics.slice(1).map((m) => (
                      <KPIBar key={m.metric} metric={m.metric} delta={m.delta ?? 0} maxAbs={maxAbsDelta} />
                    ))}
                  </div>
                </div>

                {/* Geo Assets */}
                {wb.geo_map?.assets?.length > 0 && (
                  <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
                    <div className="mb-5 flex items-center justify-between gap-4">
                      <h2 className="heading-section">{t("simulation.geoAssets")}</h2>
                      {wb.geo_map.theater && <span className="font-mono text-xs text-[var(--muted)]">{wb.geo_map.theater}</span>}
                    </div>
                    <div className="max-h-[315px] overflow-y-auto">
                      {wb.geo_map.assets.map((a, i) => (
                        <GeoAssetRow key={i} asset={a} />
                      ))}
                    </div>
                  </div>
                )}
              </section>

              {/* Timeline */}
              {wb.timeline.length > 0 && (
                <section className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-6">
                  <div className="mb-6 flex items-center justify-between">
                    <h2 className="heading-section">{t("simulation.timeline")}</h2>
                    <span className="font-mono text-xs text-[var(--muted)]">{wb.timeline.length}</span>
                  </div>
                  <div className="divider-subtle mb-6" />
                  <div className="max-h-[520px] overflow-y-auto pr-2">
                    {wb.timeline.map((event, index) => (
                      <TimelineEvent key={event.event_id} event={event} isLast={index === wb.timeline.length - 1} />
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
