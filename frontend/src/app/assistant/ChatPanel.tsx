"use client";

import { useTranslation } from "@/contexts/LanguageContext";
import type { PanelMessage } from "@/lib/api";
import { SectionLabel, SkeletonLine } from "@/components/ui/status";
import { StaggerContainer, StaggerItem } from "@/components/ui/aceternity";
import type { AssistantController } from "./hooks";
import { EmptyState, RichText, StreamingSkeleton } from "./ProcessPanel";

function PanelMessageCard({ msg }: { msg: PanelMessage }) {
  const { t } = useTranslation();
  const stance = msg.stance === "support" ? "S" : msg.stance === "challenge" ? "C" : "M";
  const stanceBadge = msg.stance === "support" ? "badge-success" : msg.stance === "challenge" ? "badge-error" : "badge badge-warning";

  return (
    <div className="divider-subtle py-5 motion-safe:animate-[fadeIn_0.25s_ease-out]">
      <div className="mb-3 flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-7 w-7 items-center justify-center border border-[var(--card-border)] font-mono text-[11px] text-[var(--accent)]">
            {stance}
          </span>
          <span className="truncate text-sm font-medium">{msg.label}</span>
        </div>
        <span className={`badge ${stanceBadge}`}>{msg.stance}</span>
      </div>
      <RichText text={msg.summary} />
      {msg.recommendation && (
        <div className="mt-4 border-l border-[var(--accent)] pl-4">
          <div className="mb-1 section-label">{t("assistant.recommendation")}</div>
          <RichText text={msg.recommendation} />
        </div>
      )}
    </div>
  );
}

export function PanelDiscussionPanel({ discussions, streaming }: { discussions: PanelMessage[]; streaming: boolean }) {
  const { t } = useTranslation();

  if (discussions.length > 0) {
    return (
      <div>
        {discussions.map((discussion, index) => (
          <PanelMessageCard key={index} msg={discussion} />
        ))}
        {streaming && <StreamingSkeleton label={t("assistant.panelDiscussion")} />}
      </div>
    );
  }

  if (streaming) return <StreamingSkeleton label={t("assistant.panelDiscussion")} />;
  return <EmptyState title={t("assistant.noPanelDiscussion")} description={t("assistant.noPanelDiscussionDescription")} />;
}

export function ChatPanel({ controller }: { controller: AssistantController }) {
  const { t } = useTranslation();
  const {
    abortRef,
    domainId,
    error,
    handleRun,
    selectedSessionId,
    sessions,
    sessionsError,
    setDomainId,
    setSelectedSessionId,
    setSubjectName,
    setTickCount,
    setTopic,
    streaming,
    subjectName,
    tickCount,
    topic,
  } = controller;

  return (
    <aside className="space-y-6 xl:sticky xl:top-[76px] xl:self-start">
      <section className="overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--card)]">
        <div className="flex items-center justify-between divider-subtle px-5 py-4">
          <h2 className="heading-section">{t("assistant.missionInput")}</h2>
          <span className="badge">CMD</span>
        </div>

        <div className="p-5">
          <div className="overflow-hidden rounded-md border border-[var(--input)] bg-[var(--background)] focus-within:ring-2 focus-within:ring-[var(--accent)] focus-within:ring-offset-1 focus-within:ring-offset-[var(--card)]">
            <div className="divider-subtle px-3 py-2 section-label">
              {t("assistant.topicPlaceholder")}
            </div>
            <textarea
              className="min-h-[150px] w-full resize-none bg-transparent px-4 py-4 text-sm leading-7 text-[var(--foreground)] outline-none placeholder:text-[var(--muted)]"
              placeholder={t("assistant.topicPlaceholder")}
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
          </div>

          <div className="mt-5">
            <label className="mb-3 block section-label">{t("assistant.quickStartExamples")}</label>
            <div className="space-y-1 divider-subtle">
              {[
                { topic: t("assistant.exampleTaiwan"), domain: "military" },
                { topic: t("assistant.exampleEv"), domain: "corporate" },
                { topic: t("assistant.exampleSemiconductor"), domain: "corporate" },
                { topic: t("assistant.exampleMiddleEast"), domain: "military" },
              ].map((example, index) => (
                <button
                  key={example.topic}
                  onClick={() => {
                    setTopic(example.topic);
                    setDomainId(example.domain);
                  }}
                  className="grid w-full grid-cols-[28px_minmax(0,1fr)] gap-3 py-3 text-left text-xs outline-none motion-safe:transition-colors hover:text-[var(--foreground)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
                >
                  <span className="font-mono text-[var(--accent)]">{String(index + 1).padStart(2, "0")}</span>
                  <span className="truncate text-[var(--muted-foreground)]">{example.topic}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-4">
            <label className="block">
              <span className="mb-2 block section-label">{t("assistant.domain")}</span>
              <select
                className="w-full rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-[var(--accent)]"
                value={domainId}
                onChange={(e) => setDomainId(e.target.value)}
              >
                <option value="auto">{t("assistant.autoDetect")}</option>
                <option value="corporate">{t("assistant.corporate")}</option>
                <option value="military">{t("assistant.military")}</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-2 block section-label">{t("assistant.ticks")}</span>
              <div className="flex h-[38px] items-center gap-3 rounded-md border border-[var(--input)] bg-[var(--background)] px-3">
                <input
                  type="range"
                  min={2}
                  max={12}
                  value={tickCount}
                  onChange={(e) => setTickCount(Number(e.target.value))}
                  className="min-w-0 flex-1 accent-[var(--accent)]"
                />
                <span className="w-6 text-right font-mono text-sm text-[var(--accent)]">{tickCount}</span>
              </div>
            </label>
          </div>

          <label className="mt-5 block">
            <span className="mb-2 block section-label">{t("assistant.subjectName")}</span>
            <input
              className="w-full rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm outline-none placeholder:text-[var(--muted)] focus:ring-2 focus:ring-[var(--accent)]"
              placeholder={t("assistant.subjectPlaceholder")}
              value={subjectName}
              onChange={(e) => setSubjectName(e.target.value)}
            />
          </label>

          <div className="mt-5 flex gap-3">
            <button
              onClick={() => handleRun()}
              disabled={streaming || !topic.trim()}
              className="btn btn-primary flex-1 gap-2"
            >
              {streaming ? (
                <>
                  <span className="h-2 w-2 rounded-full bg-[var(--accent-foreground)] motion-safe:animate-pulse" />
                  {t("common.running")}
                </>
              ) : (
                <>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  {t("assistant.runAnalysis")}
                </>
              )}
            </button>
            {streaming && (
              <button
                onClick={() => abortRef.current?.abort()}
                className="badge-error border border-[var(--accent-red)] px-4 py-2.5 text-sm outline-none motion-safe:transition-opacity hover:opacity-85 focus-visible:ring-2 focus-visible:ring-[var(--accent-red)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
              >
                {t("common.cancel")}
              </button>
            )}
          </div>

          {error && (
            <div className="mt-5 border-l border-[var(--accent-red)] bg-[var(--accent-red-bg)] px-4 py-3 text-sm text-[var(--accent-red)]">
              <div>{error}</div>
              <button onClick={() => handleRun()} className="mt-3 text-xs underline underline-offset-4">
                {t("common.retry")}
              </button>
            </div>
          )}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="heading-section">{t("assistant.recentSessions")}</h2>
          <span className="font-mono text-[11px] text-[var(--muted)]">{sessions?.length ?? 0}</span>
        </div>
        <StaggerContainer className="max-h-[310px] overflow-y-auto">
          {!sessions && !sessionsError && (
            <div className="space-y-3 py-4">
              <SkeletonLine className="h-4 w-10/12" />
              <SkeletonLine className="h-4 w-7/12" />
              <SkeletonLine className="h-4 w-9/12" />
            </div>
          )}
          {sessionsError && <div className="py-4 text-sm text-[var(--accent-red)]">{sessionsError.message}</div>}
          {sessions?.map((s) => (
            <StaggerItem
              key={s.id}
              className={`divider-subtle last:border-0 ${
                selectedSessionId === s.id ? "border-l-2 border-l-[var(--accent)] bg-[var(--code-bg)]" : ""
              }`}
            >
              <button
                type="button"
                onClick={() => setSelectedSessionId(s.id)}
                className="w-full py-3 text-left outline-none motion-safe:transition-colors hover:text-[var(--foreground)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="truncate text-sm font-medium">{s.name || s.topic.slice(0, 40)}</div>
                  <span className={`badge shrink-0 ${s.auto_refresh_enabled ? "badge-success" : ""}`}>
                    {s.auto_refresh_enabled ? t("common.auto") : t("common.manual")}
                  </span>
                </div>
                <div className="mt-1 text-xs text-[var(--muted)]">{s.domain_id}</div>
              </button>
            </StaggerItem>
          ))}
          {sessions && sessions.length === 0 && (
            <div className="py-6 text-sm text-[var(--muted)]">{t("assistant.noSessions")}</div>
          )}
        </StaggerContainer>
      </section>
    </aside>
  );
}

export function AssistantOnboarding({ controller }: { controller: AssistantController }) {
  const { t } = useTranslation();
  const { guideStep, setGuideStep, setShowGuide } = controller;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] px-4">
      <div className="w-full max-w-md rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-6 motion-safe:animate-[fadeIn_0.25s_ease-out]">
        <div className="mb-6">
          <SectionLabel>{t("assistant.onboardingTitle")}</SectionLabel>
          <h2 className="heading-display mt-3 text-balance">{t("assistant.onboardingSubtitle")}</h2>
        </div>

        <div className="mb-6">
          {[
            { title: t("assistant.onboardingEnterTopic"), desc: t("assistant.onboardingEnterTopicDesc") },
            { title: t("assistant.onboardingAiAnalysis"), desc: t("assistant.onboardingAiAnalysisDesc") },
            { title: t("assistant.onboardingDebate"), desc: t("assistant.onboardingDebateDesc") },
            { title: t("assistant.onboardingInsights"), desc: t("assistant.onboardingInsightsDesc") },
          ].map((step, index) => (
            <div key={index} className={`grid grid-cols-[34px_minmax(0,1fr)] gap-3 py-4 divider-subtle motion-safe:transition-opacity ${index === guideStep ? "opacity-100" : "opacity-45"}`}>
              <span className="font-mono text-xs text-[var(--accent)]">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <div className="text-sm font-medium">{step.title}</div>
                <div className="mt-1 text-xs leading-5 text-[var(--muted)]">{step.desc}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="flex gap-3">
          <button onClick={() => setShowGuide(false)} className="btn btn-ghost flex-1">
            {t("common.skip")}
          </button>
          <button
            onClick={() => {
              if (guideStep < 3) setGuideStep(guideStep + 1);
              else setShowGuide(false);
            }}
            className="btn btn-primary flex-1"
          >
            {guideStep < 3 ? t("common.next") : t("common.getStarted")}
          </button>
        </div>
      </div>
    </div>
  );
}
