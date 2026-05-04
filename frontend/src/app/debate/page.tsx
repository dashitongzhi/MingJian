"use client";
import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { fetchDebateDetail, fetchDebates, type DebateRound, type DebateSummary } from "@/lib/api";
import { useTranslation } from "@/contexts/LanguageContext";
import { toast } from "@/lib/toast";

function toText(value: unknown) {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function PriorityBadge({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    high: "badge badge-error",
    medium: "badge badge-warning",
    low: "badge badge-success",
  };
  return (
    <span className={colors[priority] || "badge badge-warning"}>
      {priority}
    </span>
  );
}

function RecommendationCard({ rec, index }: { rec: { title: string; priority: string; rationale: string; action_items: string[] }; index: number }) {
  return (
    <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5 animate-fadeIn" style={{ animationDelay: `${index * 80}ms` }}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-3">
          <span className="font-mono text-lg text-[var(--accent)]">{String(index + 1).padStart(2, "0")}</span>
          <h4 className="heading-section !text-sm">{rec.title}</h4>
        </div>
        <PriorityBadge priority={rec.priority} />
      </div>
      {rec.rationale && (
        <p className="text-xs leading-6 text-[var(--muted-foreground)] mb-3 pl-8">{rec.rationale}</p>
      )}
      {rec.action_items.length > 0 && (
        <div className="divider-subtle pt-3 pl-8 mt-3">
          <div className="section-label !text-[var(--muted)] mb-2">行动项</div>
          <div className="space-y-1.5">
            {rec.action_items.map((item, i) => (
              <div key={i} className="grid grid-cols-[18px_1fr] text-xs leading-5">
                <span className="text-[var(--accent)]">→</span>
                <span className="text-[var(--muted-foreground)]">{toText(item)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function DebateRoundBlock({ round }: { round: DebateRound }) {
  const { t } = useTranslation();
  const roleConfig: Record<string, { tone: string; marker: string; label: string; align: string }> = {
    strategist: {
      tone: "text-[var(--accent-green)]",
      marker: "S",
      label: "战略顾问",
      align: "md:mr-16",
    },
    risk_analyst: {
      tone: "text-[var(--accent-red)]",
      marker: "R",
      label: "风险分析",
      align: "md:ml-16",
    },
    opportunist: {
      tone: "text-[var(--accent)]",
      marker: "O",
      label: "机会评估",
      align: "md:mx-8",
    },
    advocate: {
      tone: "text-[var(--accent-green)]",
      marker: "S",
      label: "战略顾问",
      align: "md:mr-16",
    },
    challenger: {
      tone: "text-[var(--accent-red)]",
      marker: "R",
      label: "风险分析",
      align: "md:ml-16",
    },
    arbitrator: {
      tone: "text-[var(--accent)]",
      marker: "O",
      label: "机会评估",
      align: "md:mx-8",
    },
  };

  const config = roleConfig[round.role] || roleConfig.strategist;

  return (
    <article className={`${config.align} animate-fadeIn rounded-lg border border-[var(--card-border)] bg-[var(--card)]`}>
      <div className="grid grid-cols-[44px_1fr]">
        <div className={`border-r border-[var(--card-border)] px-3 py-4 text-center font-mono text-lg ${config.tone}`}>{config.marker}</div>
        <div className="min-w-0 p-4">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <div className={`section-label ${config.tone}`}>{config.label}</div>
              <div className="mt-1 text-xs text-[var(--muted)]">{t("debate.position")}</div>
            </div>
            <div className={`flex min-w-[122px] items-center gap-2 ${config.tone}`}>
              <div className="h-1.5 flex-1 bg-[var(--card-border)] rounded-full overflow-hidden">
                <div
                  className="h-full bg-current transition-[width,opacity] duration-500 rounded-full"
                  style={{ width: `${round.confidence * 100}%` }}
                />
              </div>
              <span className="font-mono text-xs text-[var(--muted)]">{(round.confidence * 100).toFixed(0)}%</span>
            </div>
          </div>

          <p className="mb-5 text-sm leading-7 text-[var(--muted-foreground)]">{round.position}</p>

          {round.arguments.length > 0 && (
            <div className="divider-subtle pt-4">
              <div className="mb-2 section-label !text-[var(--muted)]">{t("debate.arguments")}</div>
              <div className="space-y-2">
                {round.arguments.map((argument, i) => (
                  <div key={i} className="grid grid-cols-[22px_1fr] text-xs leading-6">
                    <span className="font-mono text-[var(--accent-green)]">+</span>
                    <span>{toText(argument)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {round.rebuttals.length > 0 && (
            <div className="mt-4 divider-subtle pt-4">
              <div className="mb-2 section-label !text-[var(--accent-red)]">{t("debate.rebuttals")}</div>
              <div className="space-y-2">
                {round.rebuttals.map((rebuttal, i) => (
                  <div key={i} className="grid grid-cols-[22px_1fr] text-xs leading-6 text-[var(--muted-foreground)]">
                    <span className="font-mono text-[var(--accent-red)]">-</span>
                    <span>{toText(rebuttal)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

function StateBlock({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex min-h-[420px] items-center justify-center text-center">
      <div>
        <div className="mx-auto mb-4 h-px w-16 bg-[var(--accent)]" />
        <div className="heading-section">{title}</div>
        {description && <div className="mx-auto mt-2 max-w-md text-sm text-[var(--muted)]">{description}</div>}
      </div>
    </div>
  );
}

function DebateSkeleton() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5 animate-pulse">
          <div className="h-3 w-32 bg-[var(--card-hover)]" />
          <div className="mt-4 h-3 w-full bg-[var(--card-hover)]" />
          <div className="mt-3 h-3 w-2/3 bg-[var(--card-hover)]" />
        </div>
      ))}
    </div>
  );
}

export default function DebatePage() {
  return (
    <Suspense fallback={<DebateSkeleton />}>
      <DebatePageInner />
    </Suspense>
  );
}

function DebatePageInner() {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const [inputId, setInputId] = useState("");
  const [qId, setQId] = useState<string | null>(null);

  useEffect(() => {
    const urlId = searchParams.get("id");
    if (urlId && !qId) {
      setQId(urlId);
      setInputId(urlId);
    }
  }, [searchParams, qId]);
  const { data: debate, error, isLoading } = useSWR(qId ? `debate-${qId}` : null, () => fetchDebateDetail(qId!));
  const { data: debateList } = useSWR("debates-list", () => fetchDebates(20), { refreshInterval: 30000 });

  const grouped = (debate?.rounds || []).reduce<Record<number, DebateRound[]>>((a, r) => {
    (a[r.round_number] ??= []).push(r);
    return a;
  }, {});

  const verdict = debate?.verdict;
  const recommendations = (verdict as any)?.recommendations || [];
  const riskFactors = (verdict as any)?.risk_factors || [];
  const alternativeScenarios = (verdict as any)?.alternative_scenarios || [];
  const conclusionSummary = (verdict as any)?.conclusion_summary;

  const handleLoad = () => {
    if (inputId.trim()) {
      setQId(inputId.trim());
      toast.info('分析报告已加载');
    }
  };

  return (
    <div className="mx-auto max-w-[1450px] space-y-8">
      {/* ── Page Header ── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_460px]">
        <div>
          <div className="section-label">{t("debate.title")}</div>
          <h1 className="heading-display mt-3">{t("debate.subtitle")}</h1>
        </div>

        <section className="content-end self-end rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
          <h2 className="mb-3 flex items-center gap-2 heading-section">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent)]">
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            {t("debate.loadDebate")}
          </h2>
          <div className="flex gap-3">
            <input
              className="min-w-0 flex-1 rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 font-mono text-sm outline-none placeholder:text-[var(--muted)]"
              placeholder={t("debate.debateIdPlaceholder")}
              value={inputId}
              onChange={(event) => setInputId(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && handleLoad()}
            />
            <button onClick={handleLoad} className="btn btn-primary">
              {t("common.load")}
            </button>
          </div>
          {error && (
            <div className="mt-3 border-l border-[var(--accent-red)] pl-3 text-sm text-[var(--accent-red)]">
              {t("debate.debateNotFound")}
            </div>
          )}
        </section>
      </div>
      <div className="divider-line" />

      {isLoading && <DebateSkeleton />}

      {debate ? (
        <div className="space-y-8">
          {/* Header */}
          <section className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-6">
            <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
              <div>
                <div className="section-label !text-[var(--muted)]">{t("debate.trigger")}: {debate.trigger_type}</div>
                <h2 className="heading-display !text-2xl mt-3">{debate.topic}</h2>
                <div className="mt-3 text-sm text-[var(--muted)]">{t("debate.rounds")}: {Object.keys(grouped).length}</div>
              </div>
              <span className={debate.status === "COMPLETED" ? "badge badge-success" : "badge badge-warning"}>
                {debate.status}
              </span>
            </div>
          </section>

          {/* Conclusion Summary */}
          {conclusionSummary && (
            <section className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-6">
              <h3 className="flex items-center gap-2 heading-section mb-3">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent)]">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                结论摘要
              </h3>
              <p className="text-sm leading-7 text-[var(--muted-foreground)]">{conclusionSummary}</p>
              {verdict && (
                <div className="mt-4 flex items-center gap-4 text-xs text-[var(--muted)]">
                  <span>置信度: <span className="font-mono text-[var(--foreground)]">{((verdict.confidence || 0) * 100).toFixed(0)}%</span></span>
                  <span>综合评估: <span className="font-mono text-[var(--foreground)] uppercase">{verdict.verdict}</span></span>
                </div>
              )}
            </section>
          )}

          {/* Recommendations */}
          {recommendations.length > 0 && (
            <section>
              <h3 className="flex items-center gap-2 heading-section mb-4">
                <span className="font-mono text-[var(--accent)]">📋</span>
                行动建议
                <span className="badge">{recommendations.length}</span>
              </h3>
              <div className="space-y-3">
                {recommendations.map((rec: any, i: number) => (
                  <RecommendationCard key={i} rec={rec} index={i} />
                ))}
              </div>
            </section>
          )}

          {/* Risk Factors */}
          {riskFactors.length > 0 && (
            <section>
              <h3 className="flex items-center gap-2 heading-section mb-4">
                <span className="font-mono text-[var(--accent-red)]">⚠️</span>
                风险提示
                <span className="badge badge-error">{riskFactors.length}</span>
              </h3>
              <div className="overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--card)] divide-y divide-[var(--card-border)]">
                {riskFactors.map((risk: string, i: number) => (
                  <div key={i} className="flex items-start gap-3 p-4">
                    <span className="font-mono text-xs text-[var(--accent-red)] shrink-0">{String(i + 1).padStart(2, "0")}</span>
                    <span className="text-sm leading-6 text-[var(--muted-foreground)]">{toText(risk)}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Alternative Scenarios */}
          {alternativeScenarios.length > 0 && (
            <section>
              <h3 className="flex items-center gap-2 heading-section mb-4">
                <span className="font-mono text-[var(--accent)]">🔀</span>
                参考方案
              </h3>
              <div className="grid gap-4 md:grid-cols-2">
                {alternativeScenarios.map((scenario: any, i: number) => (
                  <div key={i} className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
                    <h4 className="heading-section !text-sm mb-2">{scenario.name}</h4>
                    <p className="text-xs leading-6 text-[var(--muted-foreground)] mb-3">{scenario.description}</p>
                    {scenario.expected_outcome && (
                      <div className="divider-subtle pt-3 mt-3">
                        <div className="section-label !text-[var(--muted)] mb-1">预期结果</div>
                        <p className="text-xs leading-5 text-[var(--muted-foreground)]">{scenario.expected_outcome}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Analysis Rounds (collapsed by default) */}
          {Object.keys(grouped).length > 0 && (
            <details className="overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--card)]">
              <summary className="cursor-pointer px-5 py-4 heading-section hover:bg-[var(--card-hover)] transition-colors">
                分析过程详情
                <span className="ml-2 font-mono text-[11px] text-[var(--muted)]">({Object.keys(grouped).length} 轮)</span>
              </summary>
              <div className="px-5 pb-6 space-y-7">
                {Object.entries(grouped)
                  .sort(([a], [b]) => +a - +b)
                  .map(([rn, rounds]) => (
                    <div key={rn} className="space-y-4">
                      <div className="sticky top-14 z-10 flex items-center gap-4 bg-[var(--background)] py-2">
                        <span className="section-label">{t("debate.round")} {rn}</span>
                        <span className="divider-subtle flex-1" />
                      </div>
                      {rounds.map((r, i) => (
                        <DebateRoundBlock key={i} round={r} />
                      ))}
                    </div>
                  ))}
              </div>
            </details>
          )}
        </div>
      ) : (
        !error && !isLoading && (
          <section>
            <div className="mb-6 flex items-center justify-between">
              <h2 className="heading-section">{t("debate.recentDebates") || "最近分析报告"}</h2>
              <span className="font-mono text-xs text-[var(--muted)]">{debateList?.length || 0} {t("debate.total") || "份报告"}</span>
            </div>
            {debateList && debateList.length > 0 ? (
              <div className="space-y-3">
                {debateList.map((d) => (
                  <button
                    key={d.debate_id}
                    onClick={() => { setQId(d.debate_id); setInputId(d.debate_id); }}
                    className="w-full rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5 text-left transition-colors duration-150 hover:border-[var(--muted)]"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="section-label !text-[var(--muted)] mb-2">
                          {d.trigger_type} · {new Date(d.created_at).toLocaleDateString("zh-CN")}
                        </div>
                        <h3 className="text-sm font-medium leading-relaxed text-[var(--foreground)] group-hover:text-[var(--accent)] transition-colors">
                          {d.topic}
                        </h3>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        {d.confidence != null && (
                          <span className="font-mono text-xs text-[var(--muted)]">
                            {(d.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                        <span className="text-[var(--muted)] group-hover:text-[var(--accent)] transition-colors">→</span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <StateBlock title={t("debate.enterDebateId")} description={t("debate.enterDebateIdDescription") || "输入ID或通过战略助手发起分析"} />
            )}
          </section>
        )
      )}
    </div>
  );
}
