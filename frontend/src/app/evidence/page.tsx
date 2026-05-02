"use client";
import { useState } from "react";
import useSWR from "swr";
import { fetchEvidence, fetchClaims, fetchKnowledgeGraph, searchKnowledge, fetchSourceReputations, fetchScoreboard } from "@/lib/api";
import { useTranslation } from "@/contexts/LanguageContext";

type Tab = "evidence" | "claims" | "graph" | "reputation" | "calibration";

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

function ConfidenceBadge({ value }: { value: number }) {
  const color = value >= 0.7 ? "badge-success" : value >= 0.4 ? "badge-warning" : "badge-error";
  return <span className={`badge ${color}`}>{(value * 100).toFixed(0)}%</span>;
}

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const config: Record<string, { class: string; label: string }> = {
    ACCEPTED: { class: "badge-success", label: t("common.accepted") },
    REJECTED: { class: "badge-error", label: t("common.rejected") },
    PENDING: { class: "badge-warning", label: t("common.pending") },
  };
  const cfg = config[status] || config.PENDING;
  return <span className={`badge ${cfg.class}`}>{cfg.label}</span>;
}

export default function EvidencePage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("evidence");
  const [q, setQ] = useState("");
  const { data: ev } = useSWR(tab === "evidence" ? "ev" : null, () => fetchEvidence(100));
  const { data: cl } = useSWR(tab === "claims" ? "cl" : null, () => fetchClaims(100));
  const { data: graph } = useSWR(tab === "graph" ? "graph" : null, () => fetchKnowledgeGraph(200));
  const { data: rep } = useSWR(tab === "reputation" ? "rep" : null, fetchSourceReputations);
  const { data: sb } = useSWR(tab === "calibration" ? "sb" : null, fetchScoreboard);
  const { data: sr } = useSWR(q.length > 2 ? `sr-${q}` : null, () => searchKnowledge(q), { dedupingInterval: 1000 });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">{t("evidence.title")}</h1>
        <p className="text-[var(--muted)] mt-1">{t("evidence.subtitle")}</p>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 p-1 bg-[var(--card)] rounded-xl border border-[var(--card-border)]">
        {TAB_CONFIG.map((tabItem) => (
          <button
            key={tabItem.key}
            onClick={() => setTab(tabItem.key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              tab === tabItem.key
                ? "bg-[var(--accent)] text-white"
                : "text-[var(--muted)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)]"
            }`}
          >
            {tabItem.icon}
            {t(tabItem.labelKey)}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === "evidence" && (
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[var(--card-border)]">
                <th className="text-left p-4 text-xs font-medium text-[var(--muted)] uppercase">{t("common.title")}</th>
                <th className="text-left p-4 text-xs font-medium text-[var(--muted)] uppercase">{t("common.summary")}</th>
                <th className="text-right p-4 text-xs font-medium text-[var(--muted)] uppercase">{t("evidence.confidence")}</th>
              </tr>
            </thead>
            <tbody>
              {ev?.map((e) => (
                <tr key={e.id} className="border-b border-[var(--card-border)] last:border-0 hover:bg-[var(--card-hover)] transition-colors">
                  <td className="p-4 max-w-xs">
                    <div className="text-sm font-medium truncate">{e.title}</div>
                  </td>
                  <td className="p-4 max-w-md">
                    <div className="text-sm text-[var(--muted)] truncate">{e.summary}</div>
                  </td>
                  <td className="p-4 text-right">
                    <ConfidenceBadge value={e.confidence} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(!ev || ev.length === 0) && (
            <div className="empty-state py-12">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              <div className="empty-state-title">{t("evidence.noEvidence")}</div>
              <div className="empty-state-description">{t("evidence.noEvidenceDescription")}</div>
            </div>
          )}
        </div>
      )}

      {tab === "claims" && (
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[var(--card-border)]">
                <th className="text-left p-4 text-xs font-medium text-[var(--muted)] uppercase">{t("evidence.statement")}</th>
                <th className="text-right p-4 text-xs font-medium text-[var(--muted)] uppercase">{t("evidence.confidence")}</th>
                <th className="text-right p-4 text-xs font-medium text-[var(--muted)] uppercase">{t("evidence.status")}</th>
              </tr>
            </thead>
            <tbody>
              {cl?.map((c) => (
                <tr key={c.id} className="border-b border-[var(--card-border)] last:border-0 hover:bg-[var(--card-hover)] transition-colors">
                  <td className="p-4 max-w-xl">
                    <div className="text-sm truncate">{c.statement}</div>
                  </td>
                  <td className="p-4 text-right">
                    <ConfidenceBadge value={c.confidence} />
                  </td>
                  <td className="p-4 text-right">
                    <StatusBadge status={c.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(!cl || cl.length === 0) && (
            <div className="empty-state py-12">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <div className="empty-state-title">{t("evidence.noClaims")}</div>
              <div className="empty-state-description">{t("evidence.noClaimsDescription")}</div>
            </div>
          )}
        </div>
      )}

      {tab === "graph" && (
        <div className="space-y-4">
          {/* Search */}
          <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
            <div className="flex gap-3">
              <div className="relative flex-1">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]">
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.35-4.35" />
                </svg>
                <input
                  className="input pl-10"
                  placeholder={t("evidence.searchPlaceholder")}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </div>
            </div>
          </div>

          {/* Search results */}
          {sr && sr.length > 0 && (
            <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
              <h3 className="text-sm font-semibold mb-3">{t("evidence.searchResults")} ({sr.length})</h3>
              <div className="space-y-2">
                {sr.map((r) => (
                  <div key={r.node_id} className="flex items-center justify-between p-3 rounded-lg hover:bg-[var(--card-hover)] transition-colors">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded bg-[var(--accent)]/10 flex items-center justify-center text-[var(--accent)]">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="12" cy="12" r="10" />
                          <line x1="2" y1="12" x2="22" y2="12" />
                          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                        </svg>
                      </div>
                      <span className="text-sm">{r.label}</span>
                    </div>
                    <span className="badge badge-info">{(r.score * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Graph stats */}
          {graph && (
            <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold">{t("evidence.knowledgeGraph")}</h3>
                <div className="flex items-center gap-4 text-xs text-[var(--muted)]">
                  <span>{graph.nodes.length} {t("evidence.nodes")}</span>
                  <span>•</span>
                  <span>{graph.edges.length} {t("evidence.edges")}</span>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 max-h-[400px] overflow-y-auto">
                {graph.nodes.slice(0, 80).map((n) => (
                  <div key={n.node_id} className="p-3 rounded-lg border border-[var(--card-border)] hover:border-[var(--accent)] transition-colors">
                    <div className="text-sm font-medium truncate">{n.label}</div>
                    <div className="text-xs text-[var(--muted)] mt-1">{n.node_type}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "reputation" && (
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[var(--card-border)]">
                <th className="text-left p-4 text-xs font-medium text-[var(--muted)] uppercase">{t("common.source")}</th>
                <th className="text-left p-4 text-xs font-medium text-[var(--muted)] uppercase">{t("common.type")}</th>
                <th className="text-right p-4 text-xs font-medium text-[var(--muted)] uppercase">{t("evidence.reputation")}</th>
                <th className="text-right p-4 text-xs font-medium text-[var(--muted)] uppercase">{t("evidence.confirmed")}</th>
                <th className="text-right p-4 text-xs font-medium text-[var(--muted)] uppercase">{t("evidence.refuted")}</th>
              </tr>
            </thead>
            <tbody>
              {rep
                ?.sort((a, b) => b.reputation_score - a.reputation_score)
                .map((r, i) => (
                  <tr key={i} className="border-b border-[var(--card-border)] last:border-0 hover:bg-[var(--card-hover)] transition-colors">
                    <td className="p-4">
                      <div className="text-sm font-medium">{r.display_name || r.source_key}</div>
                    </td>
                    <td className="p-4">
                      <span className="text-sm text-[var(--muted)]">{r.source_type || "—"}</span>
                    </td>
                    <td className="p-4 text-right">
                      <span className={`text-sm font-mono ${r.reputation_score >= 0.6 ? "text-[var(--accent-green)]" : "text-[var(--accent-yellow)]"}`}>
                        {r.reputation_score.toFixed(3)}
                      </span>
                    </td>
                    <td className="p-4 text-right">
                      <span className="text-sm text-[var(--accent-green)]">{r.confirmed_count}</span>
                    </td>
                    <td className="p-4 text-right">
                      <span className="text-sm text-[var(--accent-red)]">{r.refuted_count}</span>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
          {(!rep || rep.length === 0) && (
            <div className="empty-state py-12">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
              <div className="empty-state-title">{t("evidence.noReputation")}</div>
              <div className="empty-state-description">{t("evidence.noReputationDescription")}</div>
            </div>
          )}
        </div>
      )}

      {tab === "calibration" && (
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-6">
          {sb ? (
            <div className="space-y-6">
              {/* Main stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                <div className="text-center p-4 rounded-lg bg-[var(--background)]">
                  <div className="text-3xl font-bold">{sb.total_hypotheses}</div>
                  <div className="text-xs text-[var(--muted)] mt-1">{t("evidence.totalHypotheses")}</div>
                </div>
                <div className="text-center p-4 rounded-lg bg-[var(--background)]">
                  <div className="text-3xl font-bold text-[var(--accent-green)]">{(sb.accuracy * 100).toFixed(0)}%</div>
                  <div className="text-xs text-[var(--muted)] mt-1">{t("evidence.accuracy")}</div>
                </div>
                <div className="text-center p-4 rounded-lg bg-[var(--background)]">
                  <div className="text-3xl font-bold">{sb.brier_score?.toFixed(3) ?? "—"}</div>
                  <div className="text-xs text-[var(--muted)] mt-1">{t("evidence.brierScore")}</div>
                </div>
                <div className="text-center p-4 rounded-lg bg-[var(--background)]">
                  <div className="text-3xl font-bold text-[var(--accent)]">
                    {sb.human_baseline_accuracy != null ? `${((sb.lift_over_human_baseline ?? 0) * 100).toFixed(1)}%` : "—"}
                  </div>
                  <div className="text-xs text-[var(--muted)] mt-1">{t("evidence.vsHuman")}</div>
                </div>
              </div>

              {/* Status breakdown */}
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-4 rounded-lg bg-[var(--accent-green-bg)]">
                  <div className="text-2xl font-bold text-[var(--accent-green)]">{sb.confirmed}</div>
                  <div className="text-xs text-[var(--muted)] mt-1">{t("evidence.confirmed")}</div>
                </div>
                <div className="text-center p-4 rounded-lg bg-[var(--accent-red-bg)]">
                  <div className="text-2xl font-bold text-[var(--accent-red)]">{sb.refuted}</div>
                  <div className="text-xs text-[var(--muted)] mt-1">{t("evidence.refuted")}</div>
                </div>
                <div className="text-center p-4 rounded-lg bg-[var(--accent-yellow-bg)]">
                  <div className="text-2xl font-bold text-[var(--accent-yellow)]">{sb.pending}</div>
                  <div className="text-xs text-[var(--muted)] mt-1">{t("common.pending")}</div>
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state py-12">
              <div className="spinner mx-auto mb-4" />
              <div className="empty-state-title">{t("evidence.loadingCalibration")}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
