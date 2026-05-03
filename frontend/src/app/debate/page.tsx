"use client";
import { useState } from "react";
import useSWR from "swr";
import { fetchDebateDetail, type DebateRound } from "@/lib/api";
import { useTranslation } from "@/contexts/LanguageContext";

function toText(value: unknown) {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function DebateRoundBlock({ round }: { round: DebateRound }) {
  const { t } = useTranslation();
  const roleConfig: Record<string, { tone: string; rail: string; marker: string; label: string; align: string }> = {
    advocate: {
      tone: "text-[var(--accent-green)]",
      rail: "border-[var(--accent-green)] bg-[var(--accent-green-bg)]",
      marker: "+",
      label: t("debate.advocate"),
      align: "md:mr-16",
    },
    challenger: {
      tone: "text-[var(--accent-red)]",
      rail: "border-[var(--accent-red)] bg-[var(--accent-red-bg)]",
      marker: "-",
      label: t("debate.challenger"),
      align: "md:ml-16",
    },
    arbitrator: {
      tone: "text-[var(--accent)]",
      rail: "border-[var(--accent)] bg-[var(--accent)]/10",
      marker: "=",
      label: t("debate.arbitrator"),
      align: "md:mx-8",
    },
  };

  const config = roleConfig[round.role] || roleConfig.arbitrator;

  return (
    <article className={`${config.align} animate-fadeIn border-l-2 ${config.rail}`}>
      <div className="grid grid-cols-[44px_1fr]">
        <div className={`border-r border-[var(--card-border)] px-3 py-4 text-center font-mono text-lg ${config.tone}`}>{config.marker}</div>
        <div className="min-w-0 p-4">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <div className={`font-mono text-[10px] uppercase tracking-[0.24em] ${config.tone}`}>{config.label}</div>
              <div className="mt-1 text-xs text-[var(--muted)]">{t("debate.position")}</div>
            </div>
            <div className={`flex min-w-[122px] items-center gap-2 ${config.tone}`}>
              <div className="h-1.5 flex-1 bg-[var(--card-border)]">
                <div
                  className="h-full bg-current transition-[width,opacity] duration-500"
                  style={{ width: `${round.confidence * 100}%` }}
                />
              </div>
              <span className="font-mono text-xs text-[var(--muted)]">{(round.confidence * 100).toFixed(0)}%</span>
            </div>
          </div>

          <p className="mb-5 text-sm leading-7 text-[var(--muted-foreground)]">{round.position}</p>

          {round.arguments.length > 0 && (
            <div className="border-t border-[var(--card-border)] pt-4">
              <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted)]">{t("debate.arguments")}</div>
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
            <div className="mt-4 border-t border-[var(--card-border)] pt-4">
              <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--accent-red)]">{t("debate.rebuttals")}</div>
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
    <div className="flex min-h-[420px] items-center justify-center border-y border-[var(--card-border)] text-center">
      <div>
        <div className="mx-auto mb-4 h-px w-16 bg-[var(--accent)]" />
        <div className="text-sm font-medium">{title}</div>
        {description && <div className="mx-auto mt-2 max-w-md text-sm text-[var(--muted)]">{description}</div>}
      </div>
    </div>
  );
}

function DebateSkeleton() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="border-l-2 border-[var(--card-border)] bg-[var(--card)]/50 p-5 animate-pulse">
          <div className="h-3 w-32 bg-[var(--card-hover)]" />
          <div className="mt-4 h-3 w-full bg-[var(--card-hover)]" />
          <div className="mt-3 h-3 w-2/3 bg-[var(--card-hover)]" />
        </div>
      ))}
    </div>
  );
}

export default function DebatePage() {
  const { t } = useTranslation();
  const [inputId, setInputId] = useState("");
  const [qId, setQId] = useState<string | null>(null);
  const { data: debate, error, isLoading } = useSWR(qId ? `debate-${qId}` : null, () => fetchDebateDetail(qId!));

  const grouped = (debate?.rounds || []).reduce<Record<number, DebateRound[]>>((a, r) => {
    (a[r.round_number] ??= []).push(r);
    return a;
  }, {});

  const handleLoad = () => {
    if (inputId.trim()) setQId(inputId.trim());
  };

  return (
    <div className="mx-auto max-w-[1450px] space-y-8">
      <div className="grid gap-6 border-b border-[var(--card-border)] pb-8 lg:grid-cols-[1fr_460px]">
        <div>
          <div className="font-mono text-xs uppercase tracking-[0.28em] text-[var(--accent)]">{t("debate.title")}</div>
          <h1 className="mt-4 max-w-3xl text-3xl font-semibold tracking-tight md:text-5xl">{t("debate.subtitle")}</h1>
        </div>

        <section className="content-end self-end border-l border-[var(--card-border)] pl-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent)]">
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            {t("debate.loadDebate")}
          </h2>
          <div className="flex gap-3 border-b border-[var(--card-border)] pb-3">
            <input
              className="min-w-0 flex-1 bg-transparent py-2 font-mono text-sm outline-none placeholder:text-[var(--muted)]"
              placeholder={t("debate.debateIdPlaceholder")}
              value={inputId}
              onChange={(event) => setInputId(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && handleLoad()}
            />
            <button onClick={handleLoad} className="border border-[var(--accent)] px-4 py-2 text-sm text-[var(--accent)] transition-[background-color,color,transform] duration-200 hover:-translate-y-0.5 hover:bg-[var(--accent)] hover:text-[var(--accent-foreground)]">
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

      {isLoading && <DebateSkeleton />}

      {debate ? (
        <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_360px]">
          <main className="min-w-0 space-y-8">
            <section className="border-y border-[var(--card-border)] py-6">
              <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-[var(--muted)]">{t("debate.trigger")}: {debate.trigger_type}</div>
                  <h2 className="mt-3 text-2xl font-semibold leading-tight">{debate.topic}</h2>
                  <div className="mt-3 text-sm text-[var(--muted)]">{t("debate.rounds")}: {Object.keys(grouped).length}</div>
                </div>
                <span className={`w-fit border px-3 py-1 font-mono text-[10px] uppercase tracking-[0.18em] ${debate.status === "COMPLETED" ? "border-[var(--accent-green)] text-[var(--accent-green)]" : "border-[var(--accent-yellow)] text-[var(--accent-yellow)]"}`}>
                  {debate.status}
                </span>
              </div>
            </section>

            <section className="space-y-7">
              {Object.entries(grouped)
                .sort(([a], [b]) => +a - +b)
                .map(([rn, rounds]) => (
                  <div key={rn} className="space-y-4">
                    <div className="sticky top-14 z-10 flex items-center gap-4 bg-[var(--background)] py-2">
                      <span className="font-mono text-xs text-[var(--accent)]">{t("debate.round")} {rn}</span>
                      <span className="h-px flex-1 bg-[var(--card-border)]" />
                    </div>
                    {rounds.map((r, i) => (
                      <DebateRoundBlock key={i} round={r} />
                    ))}
                  </div>
                ))}
            </section>
          </main>

          <aside className="xl:sticky xl:top-20 xl:self-start">
            {debate.verdict && (
              <section className="border border-[var(--accent)] bg-[var(--accent)]/10 p-5 shadow-[0_0_40px_rgba(194,161,90,0.08)]">
                <h3 className="mb-5 flex items-center gap-2 text-sm font-semibold">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent)]">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                    <polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                  {t("debate.finalVerdict")}
                </h3>

                <div className="space-y-5">
                  <div className="border-b border-[var(--card-border)] pb-4">
                    <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted)]">{t("debate.outcome")}</div>
                    <div className={`mt-2 text-4xl font-semibold capitalize ${debate.verdict.verdict === "support" ? "text-[var(--accent-green)]" : "text-[var(--accent-red)]"}`}>
                      {debate.verdict.verdict}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-px bg-[var(--card-border)]">
                    <div className="bg-[var(--code-bg)] p-4">
                      <div className="text-xs text-[var(--muted)]">{t("debate.confidence")}</div>
                      <div className="mt-2 font-mono text-2xl">{(debate.verdict.confidence * 100).toFixed(0)}%</div>
                    </div>
                    <div className="bg-[var(--code-bg)] p-4">
                      <div className="text-xs text-[var(--muted)]">{t("debate.winningArgs")}</div>
                      <div className="mt-2 font-mono text-2xl">{debate.verdict.winning_arguments.length}</div>
                    </div>
                  </div>

                  {debate.verdict.winning_arguments.length > 0 && (
                    <div className="border-t border-[var(--card-border)] pt-4">
                      <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--muted)]">{t("debate.winningArguments")}</div>
                      <div className="space-y-3">
                        {debate.verdict.winning_arguments.map((argument, i) => (
                          <div key={i} className="grid grid-cols-[20px_1fr] text-sm leading-6">
                            <span className="font-mono text-[var(--accent)]">{i + 1}</span>
                            <span>{argument}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {debate.verdict.minority_opinion && (
                    <div className="border-t border-[var(--card-border)] pt-4">
                      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.22em] text-[var(--accent-yellow)]">{t("debate.minorityOpinion")}</div>
                      <p className="text-sm leading-6 text-[var(--muted-foreground)]">{debate.verdict.minority_opinion}</p>
                    </div>
                  )}
                </div>
              </section>
            )}
          </aside>
        </div>
      ) : (
        !error && !isLoading && (
          <StateBlock title={t("debate.enterDebateId")} description={t("debate.enterDebateIdDescription")} />
        )
      )}
    </div>
  );
}
