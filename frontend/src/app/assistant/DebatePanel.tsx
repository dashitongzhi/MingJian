"use client";

import { useTranslation } from "@/contexts/LanguageContext";
import { toText } from "@/lib/utils";
import type { DebateRound, DebateVerdict } from "@/lib/api";
import type { CurrentDebateRound } from "./hooks";
import { EmptyState, RichText, StreamingSkeleton } from "./ProcessPanel";

function debateRoleLabel(role: string) {
  const labels: Record<string, string> = {
    advocate: "支持方",
    challenger: "反对方",
    arbitrator: "裁决方",
    strategist: "支持方",
    risk_analyst: "反对方",
    opportunist: "裁决方",
  };
  return labels[role] || role;
}

function debateArgumentText(value: unknown) {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["content", "text", "argument", "summary", "title"]) {
      if (typeof record[key] === "string" && record[key]) return record[key] as string;
    }
  }
  return toText(value ?? "");
}

function DebateRoundCard({ round }: { round: DebateRound }) {
  const { t } = useTranslation();
  const confidence = Math.max(0, Math.min(1, round.confidence));
  const confidenceBadge = confidence >= 0.7 ? "badge-success" : confidence >= 0.4 ? "badge badge-warning" : "badge-error";
  const keyArguments = (round.arguments || []).map(debateArgumentText).filter(Boolean).slice(0, 4);

  return (
    <div className="grid grid-cols-[48px_minmax(0,1fr)] divider-subtle py-5 motion-safe:animate-[slideIn_0.25s_ease-out]">
      <div className="font-mono text-xs text-[var(--muted)]">{String(round.round_number).padStart(2, "0")}</div>
      <div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium capitalize">{round.role}</span>
            <span className="text-xs text-[var(--muted)]">{t("assistant.round")} {round.round_number}</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="h-1 w-24 overflow-hidden bg-[var(--code-bg)]">
              <div className="h-full origin-left bg-[var(--accent)] motion-safe:transition-transform" style={{ transform: `scaleX(${confidence})` }} />
            </div>
            <span className={`badge ${confidenceBadge}`}>{(confidence * 100).toFixed(0)}%</span>
          </div>
        </div>
        <div className="mt-3">
          <RichText text={round.position} />
        </div>
        {keyArguments.length > 0 && (
          <div className="mt-4 border-l border-[var(--card-border)] pl-4">
            <div className="mb-2 section-label !text-[var(--muted)]">关键论据</div>
            <div className="space-y-1.5">
              {keyArguments.map((argument, index) => (
                <div key={`${argument}-${index}`} className="grid grid-cols-[22px_1fr] text-xs leading-5 text-[var(--muted-foreground)]">
                  <span className="font-mono text-[var(--accent)]">+</span>
                  <span>{argument}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DebateStatusBar({ status, currentRound }: { status: "idle" | "in_progress" | "complete"; currentRound: CurrentDebateRound }) {
  if (status !== "in_progress" || !currentRound) return null;
  return (
    <div className="mt-5 flex items-center gap-3 rounded-md border border-[var(--card-border)] bg-[var(--background)] px-4 py-3 text-sm text-[var(--foreground)] motion-safe:animate-[fadeIn_0.25s_ease-out]">
      <span className="h-2 w-2 rounded-full bg-[var(--accent)] motion-safe:animate-pulse" />
      <span>第{currentRound.round_number}/4轮 · {debateRoleLabel(currentRound.role)}正在陈述...</span>
    </div>
  );
}

function DebateVerdictCard({ verdict }: { verdict: Pick<DebateVerdict, "verdict" | "confidence" | "winning_arguments"> }) {
  return (
    <div className="my-5 rounded-lg border border-[var(--accent)]/40 bg-[var(--background)] p-5 motion-safe:animate-[scaleIn_0.25s_ease-out]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="section-label !text-[var(--accent)]">最终裁决</div>
          <div className="mt-2 text-lg font-semibold uppercase">{verdict.verdict}</div>
        </div>
        <span className="badge badge-success">{(Math.max(0, Math.min(1, verdict.confidence)) * 100).toFixed(0)}%</span>
      </div>
      {verdict.winning_arguments.length > 0 && (
        <div className="space-y-2">
          {verdict.winning_arguments.map((argument, index) => (
            <div key={`${argument}-${index}`} className="grid grid-cols-[28px_1fr] text-sm leading-6 text-[var(--muted-foreground)]">
              <span className="font-mono text-xs text-[var(--accent)]">{String(index + 1).padStart(2, "0")}</span>
              <span>{argument}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function DebatePanel({
  debateRounds,
  debateStatus,
  currentDebateRound,
  debateVerdict,
  streaming,
}: {
  debateRounds: DebateRound[];
  debateStatus: "idle" | "in_progress" | "complete";
  currentDebateRound: CurrentDebateRound;
  debateVerdict: DebateVerdict | null;
  streaming: boolean;
}) {
  const { t } = useTranslation();

  if (debateRounds.length > 0) {
    return (
      <div>
        <DebateStatusBar status={debateStatus} currentRound={currentDebateRound} />
        {debateRounds.map((round, index) => (
          <DebateRoundCard key={index} round={round} />
        ))}
        {debateVerdict && <DebateVerdictCard verdict={debateVerdict} />}
        {streaming && <StreamingSkeleton label={t("assistant.debateTrace")} />}
      </div>
    );
  }

  if (streaming) {
    return (
      <div>
        <DebateStatusBar status={debateStatus} currentRound={currentDebateRound} />
        <StreamingSkeleton label={t("assistant.debateTrace")} />
      </div>
    );
  }

  if (debateVerdict) return <DebateVerdictCard verdict={debateVerdict} />;
  return <EmptyState title={t("assistant.noDebate")} description={t("assistant.noDebateDescription")} />;
}
