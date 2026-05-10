"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useTranslation } from "@/contexts/LanguageContext";

const VISITED_KEY = "planagent_visited";

const AGENTS = [
  { name: "战略分析师", icon: "🎯", role: "战略规划", model: "Claude Opus" },
  { name: "风险评估师", icon: "⚠️", role: "风险识别", model: "Claude Sonnet" },
  { name: "机会挖掘师", icon: "💡", role: "机会发现", model: "Claude Sonnet" },
  { name: "数据分析师", icon: "📊", role: "数据洞察", model: "Claude Haiku" },
  { name: "情报收集员", icon: "🔍", role: "信息采集", model: "Claude Haiku" },
  { name: "支持方辩手", icon: "✅", role: "论证支持", model: "Claude Opus" },
  { name: "质询方辩手", icon: "❌", role: "质疑挑战", model: "Claude Opus" },
  { name: "裁决方仲裁", icon: "⚖️", role: "最终裁决", model: "Claude Opus" },
  { name: "综合协调员", icon: "🎭", role: "流程协调", model: "Claude Sonnet" },
];

export default function WelcomeGuide() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!window.localStorage.getItem(VISITED_KEY)) {
      setOpen(true);
    }
  }, []);

  const closeGuide = () => {
    window.localStorage.setItem(VISITED_KEY, "true");
    setOpen(false);
    setStep(0);
  };

  const nextStep = () => {
    if (step < 4) setStep(step + 1);
    else closeGuide();
  };

  const prevStep = () => {
    if (step > 0) setStep(step - 1);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="btn btn-ghost btn-sm w-9 h-9 rounded-full p-0 text-base"
        aria-label={t("welcome.open")}
      >
        ?
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] px-4 animate-fadeIn">
          <div className="w-full max-w-3xl rounded-xl border border-[var(--card-border)] bg-[var(--card)] shadow-2xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-[var(--card-border)] px-6 py-4">
              <div className="flex items-center gap-3">
                <h2 className="text-xl font-bold">{t("welcome.title")}</h2>
                <span className="text-xs text-[var(--muted)]">
                  {t("welcome.stepProgress")} {step + 1}/5
                </span>
              </div>
              <button
                type="button"
                onClick={closeGuide}
                className="flex h-8 w-8 items-center justify-center rounded-md text-[var(--muted-foreground)] transition-colors hover:bg-[var(--card-hover)] hover:text-[var(--foreground)]"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            {/* Progress bar */}
            <div className="h-1 bg-[var(--background)]">
              <div
                className="h-full bg-[var(--accent)] transition-all duration-300"
                style={{ width: `${((step + 1) / 5) * 100}%` }}
              />
            </div>

            {/* Content */}
            <div className="p-6 min-h-[400px]">
              {step === 0 && (
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold">{t("welcome.step1Title")}</h3>
                  <p className="text-sm text-[var(--muted-foreground)] leading-7">
                    {t("welcome.step1Description")}
                  </p>
                  <div className="grid gap-3 md:grid-cols-3 mt-6">
                    <div className="rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-4">
                      <div className="text-sm font-semibold">{t("welcome.strategicAssistant")}</div>
                      <p className="mt-2 text-xs leading-5 text-[var(--muted-foreground)]">
                        {t("welcome.strategicAssistantDescription")}
                      </p>
                    </div>
                    <div className="rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-4">
                      <div className="text-sm font-semibold">{t("welcome.scenarioSimulation")}</div>
                      <p className="mt-2 text-xs leading-5 text-[var(--muted-foreground)]">
                        {t("welcome.scenarioSimulationDescription")}
                      </p>
                    </div>
                    <div className="rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-4">
                      <div className="text-sm font-semibold">{t("welcome.evidenceIntelligence")}</div>
                      <p className="mt-2 text-xs leading-5 text-[var(--muted-foreground)]">
                        {t("welcome.evidenceIntelligenceDescription")}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {step === 1 && (
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold">{t("welcome.step2Title")}</h3>
                  <p className="text-sm text-[var(--muted-foreground)] leading-7">
                    {t("welcome.step2Description")}
                  </p>
                  <div className="space-y-3 mt-6">
                    <div className="flex items-start gap-3 rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-4">
                      <span className="text-2xl">🧠</span>
                      <div>
                        <div className="text-sm font-semibold">战略助手</div>
                        <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                          实时证据采集 + 多智能体辩论，为您的决策提供全方位支持
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3 rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-4">
                      <span className="text-2xl">⚔️</span>
                      <div>
                        <div className="text-sm font-semibold">辩论系统</div>
                        <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                          支持方、质询方、裁决方三方辩论，确保决策的全面性和可靠性
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3 rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-4">
                      <span className="text-2xl">🎲</span>
                      <div>
                        <div className="text-sm font-semibold">情景推演</div>
                        <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                          模拟不同场景下的发展路径，评估各种可能性和风险
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {step === 2 && (
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold">{t("welcome.step3Title")}</h3>
                  <p className="text-sm text-[var(--muted-foreground)] leading-7">
                    {t("welcome.step3Description")}
                  </p>
                  <div className="grid gap-3 grid-cols-3 mt-6">
                    {AGENTS.map((agent, i) => (
                      <div
                        key={i}
                        className="rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-3 text-center"
                        style={{ animationDelay: `${i * 50}ms` }}
                      >
                        <div className="text-2xl mb-2">{agent.icon}</div>
                        <div className="text-xs font-semibold">{agent.name}</div>
                        <div className="text-[10px] text-[var(--muted)] mt-1">{agent.role}</div>
                        <div className="text-[10px] text-[var(--accent)] mt-1">{agent.model}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {step === 3 && (
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold">{t("welcome.step4Title")}</h3>
                  <p className="text-sm text-[var(--muted-foreground)] leading-7">
                    {t("welcome.step4Description")}
                  </p>
                  <div className="space-y-3 mt-6">
                    <div className="flex items-start gap-3 rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-4">
                      <span className="h-2 w-2 rounded-full bg-[var(--accent)] animate-pulse mt-2" />
                      <div>
                        <div className="text-sm font-semibold">实时更新</div>
                        <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                          分析过程中的每一步都会实时显示，让您随时了解进展
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3 rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-4">
                      <span className="text-xl">⏸️</span>
                      <div>
                        <div className="text-sm font-semibold">暂停控制</div>
                        <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                          可以随时暂停实时更新，控制信息流速度，避免干扰
                        </p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3 rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-4">
                      <span className="text-xl">📊</span>
                      <div>
                        <div className="text-sm font-semibold">简洁模式</div>
                        <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                          提供精简视图，减少信息密度，让您专注于关键信息
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {step === 4 && (
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold">{t("welcome.step5Title")}</h3>
                  <p className="text-sm text-[var(--muted-foreground)] leading-7">
                    {t("welcome.step5Description")}
                  </p>
                  <div className="space-y-2 mt-6">
                    <button
                      type="button"
                      className="w-full text-left rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-3 text-sm transition-colors hover:bg-[var(--card-hover)]"
                    >
                      分析台海局势未来3年发展趋势
                    </button>
                    <button
                      type="button"
                      className="w-full text-left rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-3 text-sm transition-colors hover:bg-[var(--card-hover)]"
                    >
                      评估新能源汽车行业投资机会
                    </button>
                    <button
                      type="button"
                      className="w-full text-left rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-3 text-sm transition-colors hover:bg-[var(--card-hover)]"
                    >
                      分析全球半导体供应链风险
                    </button>
                    <button
                      type="button"
                      className="w-full text-left rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-3 text-sm transition-colors hover:bg-[var(--card-hover)]"
                    >
                      评估中东地区地缘政治风险
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between border-t border-[var(--card-border)] px-6 py-4">
              <button
                type="button"
                onClick={prevStep}
                disabled={step === 0}
                className="btn btn-ghost btn-sm disabled:opacity-30"
              >
                <ChevronLeft size={16} />
                {t("welcome.previousStep")}
              </button>
              <div className="flex gap-2">
                <button type="button" onClick={closeGuide} className="btn btn-ghost btn-sm">
                  {t("welcome.skipGuide")}
                </button>
                <button type="button" onClick={nextStep} className="btn btn-primary btn-sm">
                  {step === 4 ? t("welcome.finishGuide") : t("welcome.nextStep")}
                  {step < 4 && <ChevronRight size={16} />}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
