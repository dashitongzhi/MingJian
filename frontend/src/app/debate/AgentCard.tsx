"use client";

import type { DebateRound, DebateVote } from "@/lib/api";
import { useTranslation } from "@/contexts/LanguageContext";
import { toText, type VoteValue } from "./utils";

function VoteControls({
  round,
  votes,
  comment,
  submitting,
  onCommentChange,
  onVote,
}: {
  round: DebateRound;
  votes: DebateVote[];
  comment: string;
  submitting: boolean;
  onCommentChange: (value: string) => void;
  onVote: (round: DebateRound, vote: VoteValue) => void;
}) {
  const counts = votes.reduce<Record<VoteValue, number>>(
    (acc, item) => {
      acc[item.vote] += 1;
      return acc;
    },
    { agree: 0, disagree: 0, neutral: 0 },
  );
  const total = votes.length;
  const latestComments = votes.filter((item) => item.comment).slice(0, 2);

  return (
    <div className="mt-5 divider-subtle pt-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="section-label !text-[var(--muted)]">用户投票</div>
        <div className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-[var(--muted)]">
          <span>同意 {counts.agree}</span>
          <span>不同意 {counts.disagree}</span>
          <span>中立 {counts.neutral}</span>
          <span>总计 {total}</span>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-[1fr_auto]">
        <input
          className="min-w-0 rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-xs outline-none placeholder:text-[var(--muted)]"
          placeholder="可选评论"
          value={comment}
          onChange={(event) => onCommentChange(event.target.value)}
        />
        <div className="grid grid-cols-3 gap-2">
          {([
            ["agree", "同意 👍"],
            ["disagree", "不同意 👎"],
            ["neutral", "中立 🤔"],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              disabled={submitting}
              onClick={() => onVote(round, value)}
              className="rounded-md border border-[var(--card-border)] px-3 py-2 text-xs transition-colors hover:border-[var(--muted)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {latestComments.length > 0 && (
        <div className="mt-3 space-y-1">
          {latestComments.map((item) => (
            <div key={item.id} className="truncate border-l border-[var(--card-border)] pl-3 text-xs text-[var(--muted-foreground)]">
              {item.comment}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function DebateRoundBlock({
  round,
  votes,
  comment,
  submitting,
  onCommentChange,
  onVote,
}: {
  round: DebateRound;
  votes: DebateVote[];
  comment: string;
  submitting: boolean;
  onCommentChange: (value: string) => void;
  onVote: (round: DebateRound, vote: VoteValue) => void;
}) {
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
          <VoteControls
            round={round}
            votes={votes}
            comment={comment}
            submitting={submitting}
            onCommentChange={onCommentChange}
            onVote={onVote}
          />
        </div>
      </div>
    </article>
  );
}
