"use client";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { fetchEvidence, fetchClaims, fetchKnowledgeGraph, searchKnowledge, fetchSourceReputations, fetchScoreboard } from "@/lib/api";
import { useTranslation } from "@/contexts/LanguageContext";

type Tab = "evidence" | "claims" | "graph" | "reputation" | "calibration";
type ConfidenceFilter = "all" | "high" | "medium" | "low";

const TAB_CONFIG: { key: Tab; labelKey: string; icon: React.ReactNode }[] = [
  {
    key: "evidence",
    labelKey: "evidence.evidence",
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10 9 9 9 8 9" />
      </svg>
    ),
  },
  {
    key: "claims",
    labelKey: "evidence.claims",
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
        <polyline points="22 4 12 14.01 9 11.01" />
      </svg>
    ),
  },
  {
    key: "graph",
    labelKey: "evidence.knowledgeGraph",
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="2" y1="12" x2="22" y2="12" />
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      </svg>
    ),
  },
  {
    key: "reputation",
    labelKey: "evidence.sourceReputation",
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
  },
  {
    key: "calibration",
    labelKey: "evidence.calibration",
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="18" y1="20" x2="18" y2="10" />
        <line x1="12" y1="20" x2="12" y2="4" />
        <line x1="6" y1="20" x2="6" y2="14" />
      </svg>
    ),
  },
];

function toneForConfidence(value: number) {
  if (value >= 0.7) return "text-[var(--accent-green)]";
  if (value >= 0.4) return "text-[var(--accent-yellow)]";
  return "text-[var(--accent-red)]";
}

function ConfidenceBadge({ value }: { value: number }) {
  return (
    <span className={`font-mono text-xs ${toneForConfidence(value)}`}>
      {(value * 100).toFixed(0)}%
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const config: Record<string, { class: string; label: string }> = {
    ACCEPTED: { class: "text-[var(--accent-green)]", label: t("common.accepted") },
    REJECTED: { class: "text-[var(--accent-red)]", label: t("common.rejected") },
    PENDING: { class: "text-[var(--accent-yellow)]", label: t("common.pending") },
  };
  const cfg = config[status] || config.PENDING;
  return <span className={`font-mono text-xs ${cfg.class}`}>{cfg.label}</span>;
}

function SkeletonRows({ count = 6 }: { count?: number }) {
  return (
    <div className="divide-y divide-[var(--card-border)]/70">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="py-4 animate-pulse">
          <div className="h-3 w-2/3 bg-[var(--card-hover)]" />
          <div className="mt-3 h-3 w-full bg-[var(--card-hover)]" />
        </div>
      ))}
    </div>
  );
}

function StateBlock({ title, description }: { title: string; description?: string }) {
  return (
    <div className="min-h-[260px] border-y border-[var(--card-border)]/80 py-16 text-center">
      <div className="mx-auto mb-4 h-px w-16 bg-[var(--accent)]/60" />
      <div className="text-sm font-medium">{title}</div>
      {description && <div className="mx-auto mt-2 max-w-sm text-sm text-[var(--muted)]">{description}</div>}
    </div>
  );
}

function EditorShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-hidden border border-[var(--card-border)] bg-[#0d0d0d]">
      <div className="flex items-center justify-between border-b border-[var(--card-border)] bg-[var(--card)] px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[var(--accent-red)]/70" />
          <span className="h-2 w-2 rounded-full bg-[var(--accent-yellow)]/70" />
          <span className="h-2 w-2 rounded-full bg-[var(--accent-green)]/70" />
        </div>
        <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-[var(--muted)]">evidence.md</div>
      </div>
      {children}
    </div>
  );
}

export default function EvidencePage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("evidence");
  const [listQuery, setListQuery] = useState("");
  const [confidenceFilter, setConfidenceFilter] = useState<ConfidenceFilter>("all");
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [graphQuery, setGraphQuery] = useState("");
  const { data: ev, error: evError, isLoading: evLoading } = useSWR(tab === "evidence" ? "ev" : null, () => fetchEvidence(100));
  const { data: cl, error: clError, isLoading: clLoading } = useSWR(tab === "claims" ? "cl" : null, () => fetchClaims(100));
  const { data: graph, error: graphError, isLoading: graphLoading } = useSWR(tab === "graph" ? "graph" : null, () => fetchKnowledgeGraph(200));
  const { data: rep, error: repError, isLoading: repLoading } = useSWR(tab === "reputation" ? "rep" : null, fetchSourceReputations);
  const { data: sb, error: sbError, isLoading: sbLoading } = useSWR(tab === "calibration" ? "sb" : null, fetchScoreboard);
  const { data: sr, error: srError, isLoading: srLoading } = useSWR(tab === "graph" && graphQuery.length > 2 ? `sr-${graphQuery}` : null, () => searchKnowledge(graphQuery), { dedupingInterval: 1000 });

  const filteredEvidence = useMemo(() => {
    const query = listQuery.trim().toLowerCase();
    return (ev || []).filter((item) => {
      const matchesQuery = !query || item.title.toLowerCase().includes(query) || item.summary.toLowerCase().includes(query);
      const matchesConfidence =
        confidenceFilter === "all" ||
        (confidenceFilter === "high" && item.confidence >= 0.7) ||
        (confidenceFilter === "medium" && item.confidence >= 0.4 && item.confidence < 0.7) ||
        (confidenceFilter === "low" && item.confidence < 0.4);
      return matchesQuery && matchesConfidence;
    });
  }, [confidenceFilter, ev, listQuery]);

  const selectedEvidence = filteredEvidence.find((item) => item.id === selectedEvidenceId) || filteredEvidence[0] || null;
  const sortedReputation = useMemo(() => [...(rep || [])].sort((a, b) => b.reputation_score - a.reputation_score), [rep]);

  return (
    <div className="mx-auto max-w-[1500px] space-y-8">
      <div className="grid gap-6 border-b border-[var(--card-border)] pb-8 lg:grid-cols-[minmax(0,1fr)_520px]">
        <div>
          <div className="font-mono text-xs uppercase tracking-[0.28em] text-[var(--accent)]">{t("evidence.title")}</div>
          <h1 className="mt-4 max-w-3xl text-3xl font-semibold tracking-tight md:text-5xl">{t("evidence.subtitle")}</h1>
        </div>
        <div className="grid content-end gap-2 sm:grid-cols-5">
          {TAB_CONFIG.map((tabItem) => (
            <button
              key={tabItem.key}
              onClick={() => setTab(tabItem.key)}
              className={`flex items-center gap-2 border-b px-2 py-3 text-left text-xs transition-[color,opacity,transform] duration-200 hover:-translate-y-0.5 ${
                tab === tabItem.key
                  ? "border-[var(--accent)] text-[var(--foreground)]"
                  : "border-[var(--card-border)] text-[var(--muted)] hover:text-[var(--muted-foreground)]"
              }`}
            >
              {tabItem.icon}
              <span className="truncate">{t(tabItem.labelKey)}</span>
            </button>
          ))}
        </div>
      </div>

      {tab === "evidence" && (
        <div className="grid gap-8 lg:grid-cols-[minmax(360px,0.9fr)_minmax(0,1.25fr)]">
          <section>
            <div className="mb-5 grid gap-3 border-b border-[var(--card-border)] pb-5 md:grid-cols-[1fr_180px]">
              <div className="relative">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="absolute left-0 top-1/2 -translate-y-1/2 text-[var(--muted)]">
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.35-4.35" />
                </svg>
                <input
                  className="w-full bg-transparent py-3 pl-7 text-sm outline-none placeholder:text-[var(--muted)] focus:text-[var(--foreground)]"
                  placeholder={t("evidence.searchPlaceholder")}
                  value={listQuery}
                  onChange={(event) => setListQuery(event.target.value)}
                />
              </div>
              <select
                className="bg-transparent py-3 text-sm text-[var(--muted-foreground)] outline-none"
                value={confidenceFilter}
                onChange={(event) => setConfidenceFilter(event.target.value as ConfidenceFilter)}
              >
                <option value="all">{t("evidence.confidence")}</option>
                <option value="high">70%+</option>
                <option value="medium">40-69%</option>
                <option value="low">&lt;40%</option>
              </select>
            </div>

            {evLoading && <SkeletonRows />}
            {evError && <StateBlock title={t("common.failed")} description={String(evError.message || evError)} />}
            {!evLoading && !evError && filteredEvidence.length === 0 && <StateBlock title={t("evidence.noEvidence")} description={t("evidence.noEvidenceDescription")} />}

            {!evLoading && !evError && filteredEvidence.length > 0 && (
              <div className="divide-y divide-[var(--card-border)]/80">
                {filteredEvidence.map((e) => (
                  <button
                    key={e.id}
                    onClick={() => setSelectedEvidenceId(e.id)}
                    className={`group w-full py-5 text-left transition-[opacity,transform,background-color] duration-200 hover:translate-x-1 ${
                      selectedEvidence?.id === e.id ? "opacity-100" : "opacity-70 hover:opacity-100"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="text-sm font-medium">{e.title}</div>
                        <div className="mt-2 line-clamp-2 text-sm leading-6 text-[var(--muted)]">{e.summary}</div>
                      </div>
                      <ConfidenceBadge value={e.confidence} />
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section>
            <EditorShell>
              {selectedEvidence ? (
                <div className="grid grid-cols-[44px_1fr] font-mono text-sm leading-7">
                  <div className="select-none border-r border-[var(--card-border)] bg-[var(--card)]/60 py-5 text-right text-xs text-[var(--muted)]">
                    {Array.from({ length: 10 }).map((_, i) => (
                      <div key={i} className="px-3">{i + 1}</div>
                    ))}
                  </div>
                  <div className="min-h-[520px] px-5 py-5">
                    <div className="text-[var(--muted)]"># {t("common.title")}</div>
                    <h2 className="mb-5 text-xl font-semibold font-sans leading-tight">{selectedEvidence.title}</h2>
                    <div className="text-[var(--muted)]">## {t("common.summary")}</div>
                    <p className="mb-6 whitespace-pre-wrap font-sans text-sm leading-7 text-[var(--muted-foreground)]">{selectedEvidence.summary}</p>
                    <div className="text-[var(--muted)]">## {t("evidence.confidence")}</div>
                    <div className="mt-3 flex items-center gap-4">
                      <div className="h-1.5 flex-1 bg-[var(--card-border)]">
                        <div className="h-full bg-[var(--accent)] transition-[width] duration-500" style={{ width: `${selectedEvidence.confidence * 100}%` }} />
                      </div>
                      <ConfidenceBadge value={selectedEvidence.confidence} />
                    </div>
                    <div className="mt-8 border-t border-[var(--card-border)] pt-5 text-xs text-[var(--muted)]">
                      <span className="mr-4">id: {selectedEvidence.id}</span>
                      <span>{selectedEvidence.created_at}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <StateBlock title={t("evidence.noEvidence")} description={t("evidence.noEvidenceDescription")} />
              )}
            </EditorShell>
          </section>
        </div>
      )}

      {tab === "claims" && (
        <section className="max-w-5xl">
          {clLoading && <SkeletonRows />}
          {clError && <StateBlock title={t("common.failed")} description={String(clError.message || clError)} />}
          {!clLoading && !clError && (!cl || cl.length === 0) && <StateBlock title={t("evidence.noClaims")} description={t("evidence.noClaimsDescription")} />}
          {!clLoading && !clError && cl && cl.length > 0 && (
            <div className="divide-y divide-[var(--card-border)]">
              <div className="grid grid-cols-[1fr_100px_100px] gap-4 pb-3 text-xs uppercase tracking-[0.18em] text-[var(--muted)]">
                <span>{t("evidence.statement")}</span>
                <span className="text-right">{t("evidence.confidence")}</span>
                <span className="text-right">{t("evidence.status")}</span>
              </div>
              {cl.map((c) => (
                <div key={c.id} className="grid grid-cols-[1fr_100px_100px] gap-4 py-4 text-sm">
                  <div className="min-w-0 leading-6 text-[var(--muted-foreground)]">{c.statement}</div>
                  <div className="text-right"><ConfidenceBadge value={c.confidence} /></div>
                  <div className="text-right"><StatusBadge status={c.status} /></div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {tab === "graph" && (
        <section className="grid gap-8 lg:grid-cols-[420px_1fr]">
          <div className="space-y-6">
            <div className="border-b border-[var(--card-border)] pb-5">
              <label className="mb-2 block text-xs uppercase tracking-[0.22em] text-[var(--muted)]">{t("evidence.searchResults")}</label>
              <div className="relative">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="absolute left-0 top-1/2 -translate-y-1/2 text-[var(--accent)]">
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.35-4.35" />
                </svg>
                <input
                  className="w-full bg-transparent py-4 pl-7 text-sm outline-none placeholder:text-[var(--muted)]"
                  placeholder={t("evidence.searchPlaceholder")}
                  value={graphQuery}
                  onChange={(event) => setGraphQuery(event.target.value)}
                />
              </div>
            </div>

            {srLoading && <SkeletonRows count={3} />}
            {srError && <StateBlock title={t("common.failed")} description={String(srError.message || srError)} />}
            {sr && sr.length > 0 && (
              <div className="divide-y divide-[var(--card-border)]">
                {sr.map((r) => (
                  <div key={r.node_id} className="flex items-center justify-between gap-4 py-4">
                    <div className="text-sm">{r.label}</div>
                    <span className="font-mono text-xs text-[var(--accent)]">{(r.score * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="min-h-[460px] border-l border-[var(--card-border)] pl-8">
            {graphLoading && <SkeletonRows count={8} />}
            {graphError && <StateBlock title={t("common.failed")} description={String(graphError.message || graphError)} />}
            {graph && (
              <>
                <div className="mb-6 flex items-end justify-between gap-6">
                  <h2 className="text-xl font-semibold">{t("evidence.knowledgeGraph")}</h2>
                  <div className="font-mono text-xs text-[var(--muted)]">
                    {graph.nodes.length} {t("evidence.nodes")} / {graph.edges.length} {t("evidence.edges")}
                  </div>
                </div>
                <div className="grid max-h-[520px] grid-cols-1 gap-x-8 overflow-y-auto md:grid-cols-2 xl:grid-cols-3">
                  {graph.nodes.slice(0, 80).map((n) => (
                    <div key={n.node_id} className="border-t border-[var(--card-border)] py-4">
                      <div className="truncate text-sm font-medium">{n.label}</div>
                      <div className="mt-1 font-mono text-xs text-[var(--muted)]">{n.node_type}</div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </section>
      )}

      {tab === "reputation" && (
        <section className="max-w-6xl">
          {repLoading && <SkeletonRows count={8} />}
          {repError && <StateBlock title={t("common.failed")} description={String(repError.message || repError)} />}
          {!repLoading && !repError && sortedReputation.length === 0 && <StateBlock title={t("evidence.noReputation")} description={t("evidence.noReputationDescription")} />}
          {!repLoading && !repError && sortedReputation.length > 0 && (
            <div className="divide-y divide-[var(--card-border)]">
              <div className="grid grid-cols-[1fr_120px_120px_100px_100px] gap-4 pb-3 text-xs uppercase tracking-[0.18em] text-[var(--muted)]">
                <span>{t("common.source")}</span>
                <span>{t("common.type")}</span>
                <span className="text-right">{t("evidence.reputation")}</span>
                <span className="text-right">{t("evidence.confirmed")}</span>
                <span className="text-right">{t("evidence.refuted")}</span>
              </div>
              {sortedReputation.map((r, i) => (
                <div key={i} className="grid grid-cols-[1fr_120px_120px_100px_100px] gap-4 py-4 text-sm">
                  <div className="min-w-0 font-medium">{r.display_name || r.source_key}</div>
                  <div className="text-[var(--muted)]">{r.source_type || "-"}</div>
                  <div className="text-right font-mono text-[var(--accent)]">{r.reputation_score.toFixed(3)}</div>
                  <div className="text-right font-mono text-[var(--accent-green)]">{r.confirmed_count}</div>
                  <div className="text-right font-mono text-[var(--accent-red)]">{r.refuted_count}</div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {tab === "calibration" && (
        <section>
          {sbLoading && (
            <div className="py-12">
              <div className="spinner mx-auto mb-4" />
              <div className="text-center text-sm text-[var(--muted)]">{t("evidence.loadingCalibration")}</div>
            </div>
          )}
          {sbError && <StateBlock title={t("common.failed")} description={String(sbError.message || sbError)} />}
          {sb && (
            <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
              <div className="grid grid-cols-2 gap-x-8 gap-y-10 border-y border-[var(--card-border)] py-8 md:grid-cols-4">
                <div>
                  <div className="text-4xl font-semibold">{sb.total_hypotheses}</div>
                  <div className="mt-2 text-xs text-[var(--muted)]">{t("evidence.totalHypotheses")}</div>
                </div>
                <div>
                  <div className="text-4xl font-semibold text-[var(--accent-green)]">{(sb.accuracy * 100).toFixed(0)}%</div>
                  <div className="mt-2 text-xs text-[var(--muted)]">{t("evidence.accuracy")}</div>
                </div>
                <div>
                  <div className="text-4xl font-semibold">{sb.brier_score?.toFixed(3) ?? "-"}</div>
                  <div className="mt-2 text-xs text-[var(--muted)]">{t("evidence.brierScore")}</div>
                </div>
                <div>
                  <div className="text-4xl font-semibold text-[var(--accent)]">
                    {sb.human_baseline_accuracy != null ? `${((sb.lift_over_human_baseline ?? 0) * 100).toFixed(1)}%` : "-"}
                  </div>
                  <div className="mt-2 text-xs text-[var(--muted)]">{t("evidence.vsHuman")}</div>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-px bg-[var(--card-border)]">
                <div className="bg-[var(--background)] p-6">
                  <div className="text-3xl font-semibold text-[var(--accent-green)]">{sb.confirmed}</div>
                  <div className="mt-2 text-xs text-[var(--muted)]">{t("evidence.confirmed")}</div>
                </div>
                <div className="bg-[var(--background)] p-6">
                  <div className="text-3xl font-semibold text-[var(--accent-red)]">{sb.refuted}</div>
                  <div className="mt-2 text-xs text-[var(--muted)]">{t("evidence.refuted")}</div>
                </div>
                <div className="bg-[var(--background)] p-6">
                  <div className="text-3xl font-semibold text-[var(--accent-yellow)]">{sb.pending}</div>
                  <div className="mt-2 text-xs text-[var(--muted)]">{t("common.pending")}</div>
                </div>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
