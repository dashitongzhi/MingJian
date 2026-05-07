"use client";

import { TextReveal } from "@/components/ui/aceternity";
import { SectionLabel, SkeletonLine } from "@/components/ui/status";
import { useTranslation } from "@/contexts/LanguageContext";
import { AssistantOnboarding, ChatPanel, PanelDiscussionPanel } from "./ChatPanel";
import { DebatePanel } from "./DebatePanel";
import { useAssistantController } from "./hooks";
import { ProcessTimeline, ReasoningPanel } from "./ProcessPanel";
import { ResultSection, SessionDetailPanel, SourcePanel } from "./SourcePanel";

export default function AssistantPage() {
  const { t } = useTranslation();
  const controller = useAssistantController();
  const {
    activeTab,
    currentDebateRound,
    currentStage,
    debateMessages,
    debateRounds,
    debateStatus,
    debateVerdict,
    discussions,
    handleExport,
    handleReanalyze,
    processSteps,
    result,
    selectedSessionId,
    sessionDetail,
    setActiveTab,
    setSelectedSessionId,
    showGuide,
    sourceSearches,
    sources,
    steps,
    streaming,
    tabs,
  } = controller;

  return (
    <div className="space-y-6">
      <header className="divider-subtle pb-7">
        <TextReveal>
          <SectionLabel>{t("assistant.title")}</SectionLabel>
        </TextReveal>
        <TextReveal delay={0.1}>
          <h1 className="heading-display mt-4 max-w-3xl text-balance">{t("assistant.subtitle")}</h1>
        </TextReveal>
      </header>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[390px_minmax(0,1fr)]">
        <ChatPanel controller={controller} />

        <main className="min-w-0">
          {selectedSessionId && sessionDetail ? (
            <section className="min-h-[560px] rounded-lg border border-[var(--card-border)] bg-[var(--card)]">
              <SessionDetailPanel detail={sessionDetail} onBack={() => setSelectedSessionId(null)} />
            </section>
          ) : selectedSessionId ? (
            <section className="min-h-[560px] rounded-lg border border-[var(--card-border)] bg-[var(--card)]">
              <div className="space-y-3 px-5 py-10">
                <SkeletonLine className="h-4 w-8/12" />
                <SkeletonLine className="h-4 w-6/12" />
                <SkeletonLine className="h-4 w-10/12" />
              </div>
            </section>
          ) : (
            <>
              <div className="sticky top-[52px] z-10 -mx-1 mb-4 bg-[var(--background)]/95 px-1 py-2">
                <div className="flex gap-0 overflow-x-auto">
                  {tabs.map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`relative min-w-28 flex-1 px-4 py-3 text-sm outline-none motion-safe:transition-colors focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--background)] ${
                        activeTab === tab.id ? "text-[var(--foreground)]" : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                      }`}
                    >
                      <span>{tab.label}</span>
                      {tab.count > 0 && <span className="ml-2 font-mono text-[11px] opacity-70">{tab.count}</span>}
                      {activeTab === tab.id && <span className="absolute inset-x-4 bottom-0 h-px bg-[var(--accent)]" />}
                    </button>
                  ))}
                </div>
                <div className="divider-line" />
              </div>

              <section className="min-h-[560px] rounded-lg border border-[var(--card-border)] bg-[var(--card)]">
                <div className="flex items-center justify-between divider-subtle px-5 py-4">
                  <SectionLabel>{tabs.find((tab) => tab.id === activeTab)?.label}</SectionLabel>
                  {streaming ? (
                    <span className="badge badge-warning">{t("common.running")}</span>
                  ) : result ? (
                    <span className="badge badge-success">{t("assistant.analysisComplete")}</span>
                  ) : (
                    <span className="badge">{t("common.auto")}</span>
                  )}
                </div>
                <div className="px-5">
                  {activeTab === "process" && <ProcessTimeline steps={processSteps} debateMessages={debateMessages} sourceSearches={sourceSearches} currentStage={currentStage} isStreaming={streaming} />}
                  {activeTab === "reasoning" && <ReasoningPanel steps={steps} streaming={streaming} />}
                  {activeTab === "sources" && <SourcePanel sources={sources} streaming={streaming} />}
                  {activeTab === "panel" && <PanelDiscussionPanel discussions={discussions} streaming={streaming} />}
                  {activeTab === "debate" && <DebatePanel debateRounds={debateRounds} debateStatus={debateStatus} currentDebateRound={currentDebateRound} debateVerdict={debateVerdict} streaming={streaming} />}
                </div>
              </section>

              {result && <ResultSection result={result} onExport={handleExport} onReanalyze={handleReanalyze} streaming={streaming} />}
            </>
          )}
        </main>
      </div>

      {showGuide && <AssistantOnboarding controller={controller} />}
    </div>
  );
}
