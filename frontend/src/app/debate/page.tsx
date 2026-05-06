"use client";
import { useState, useEffect, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { Play, Radio, RefreshCw, MessageSquarePlus, Clock, History, ChevronDown, ChevronUp } from "lucide-react";
import { createDebateVote, fetchDebateDetail, fetchDebates, fetchDebateVotes, fetchSimulationRuns, streamDebate, postDebateInterrupt, fetchDebateReplay, type DebateRound, type DebateSummary, type DebateVote, type DebateVerdict, type InterruptType, type ReplayEvent, type DebateReplay } from "@/lib/api";
import { useTranslation } from "@/contexts/LanguageContext";
import { toast } from "@/lib/toast";
import { PriorityBadge } from "@/components/PriorityBadge";
import { RecommendationCard } from "@/components/RecommendationCard";

function toText(value: unknown) {
  return typeof value === "string" ? value : JSON.stringify(value);
}

type VoteValue = "agree" | "disagree" | "neutral";
type VoteRole = DebateVote["role"];

function canonicalVoteRole(role: string): VoteRole {
  if (role === "strategist") return "advocate";
  if (role === "risk_analyst") return "challenger";
  if (role === "opportunist") return "arbitrator";
  if (role === "challenger" || role === "arbitrator") return role;
  return "advocate";
}

function voteKey(round: DebateRound) {
  return `${round.round_number}:${canonicalVoteRole(round.role)}`;
}

function roleLabel(role: string) {
  const labels: Record<string, string> = {
    advocate: "支持方",
    challenger: "反对方",
    arbitrator: "裁决方",
    strategist: "战略顾问",
    risk_analyst: "风险分析",
    opportunist: "机会评估",
  };
  return labels[role] || role;
}

function LiveProgressBar({ value }: { value: number }) {
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-[var(--card-border)]">
      <div className="h-full rounded-full bg-[var(--accent)] transition-[width] duration-500" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

function LiveVerdictCard({ verdict }: { verdict: DebateVerdict }) {
  return (
    <section className="rounded-lg border border-[var(--accent)]/40 bg-[var(--card)] p-5 animate-scaleIn">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="section-label !text-[var(--accent)]">实时裁决</div>
          <h3 className="mt-2 text-lg font-semibold uppercase">{verdict.verdict}</h3>
        </div>
        <span className="badge badge-success">{(Math.max(0, Math.min(1, verdict.confidence)) * 100).toFixed(0)}%</span>
      </div>
      <div className="space-y-2">
        {verdict.winning_arguments.map((argument, index) => (
          <div key={`${argument}-${index}`} className="grid grid-cols-[28px_1fr] text-sm leading-6 text-[var(--muted-foreground)]">
            <span className="font-mono text-xs text-[var(--accent)]">{String(index + 1).padStart(2, "0")}</span>
            <span>{argument}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

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

function DebateRoundBlock({
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

const INTERRUPT_TYPES: { value: InterruptType; labelKey: string; icon: string }[] = [
  { value: "supplementary_info", labelKey: "debate.supplementaryInfo", icon: "📋" },
  { value: "direction_correction", labelKey: "debate.directionCorrection", icon: "🧭" },
  { value: "new_evidence", labelKey: "debate.newEvidence", icon: "🔍" },
  { value: "general", labelKey: "debate.generalInterrupt", icon: "💬" },
];

function DebateInterruptForm({ debateId, onSubmitted }: { debateId: string; onSubmitted: () => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [interruptType, setInterruptType] = useState<InterruptType>("supplementary_info");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async () => {
    if (!message.trim()) return;
    setSubmitting(true);
    try {
      await postDebateInterrupt(debateId, message.trim(), interruptType);
      toast.success(t("debate.interruptSuccess"));
      setMessage("");
      setSubmitted(true);
      setOpen(false);
      onSubmitted();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("debate.interruptFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-[var(--accent)]/30 bg-[var(--accent)]/5 px-3 py-2 text-xs text-[var(--accent)]">
        <MessageSquarePlus size={14} />
        {t("debate.alreadyInterrupted")}
      </div>
    );
  }

  return (
    <div className="animate-fadeIn">
      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="btn btn-primary flex items-center gap-2 py-2 px-4 text-sm"
        >
          <MessageSquarePlus size={16} />
          {t("debate.interrupt")}
        </button>
      ) : (
        <div className="space-y-3 rounded-lg border border-[var(--accent)]/30 bg-[var(--card)] p-4 animate-scaleIn">
          <div className="section-label !text-[var(--accent)]">{t("debate.interruptType")}</div>
          <div className="flex flex-wrap gap-2">
            {INTERRUPT_TYPES.map((it) => (
              <button
                key={it.value}
                type="button"
                onClick={() => setInterruptType(it.value)}
                className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs transition-colors ${
                  interruptType === it.value
                    ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                    : "border-[var(--card-border)] text-[var(--muted)] hover:border-[var(--muted)]"
                }`}
              >
                <span>{it.icon}</span>
                {t(it.labelKey)}
              </button>
            ))}
          </div>
          <textarea
            className="w-full rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm outline-none placeholder:text-[var(--muted)] focus:border-[var(--accent)] resize-none"
            rows={3}
            placeholder={t("debate.interruptPlaceholder")}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            disabled={submitting}
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleSubmit}
              disabled={submitting || !message.trim()}
              className="btn btn-primary py-2 px-4 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? <RefreshCw size={14} className="animate-spin" /> : <MessageSquarePlus size={14} />}
              {submitting ? t("common.processing") : t("debate.interrupt")}
            </button>
            <button
              type="button"
              onClick={() => { setOpen(false); setMessage(""); }}
              disabled={submitting}
              className="rounded-md border border-[var(--card-border)] px-3 py-2 text-xs text-[var(--muted)] transition-colors hover:border-[var(--muted)]"
            >
              {t("common.cancel")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function stanceColor(stance?: string) {
  if (stance === "support") return "border-l-[var(--accent-green)]";
  if (stance === "oppose") return "border-l-[var(--accent-red)]";
  return "border-l-[var(--muted)]";
}

function stanceLabel(stance: string | undefined, t: (k: string) => string) {
  if (stance === "support") return t("debate.stanceSupport");
  if (stance === "oppose") return t("debate.stanceOppose");
  return t("debate.stanceNeutral");
}

function stanceBadgeColor(stance?: string) {
  if (stance === "support") return "bg-[var(--accent-green)]/10 text-[var(--accent-green)]";
  if (stance === "oppose") return "bg-[var(--accent-red)]/10 text-[var(--accent-red)]";
  return "bg-[var(--card-hover)] text-[var(--muted)]";
}

function formatTimestamp(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return ts;
  }
}

function ReplayTimeline({ replay }: { replay: DebateReplay }) {
  const { t } = useTranslation();
  const [expandedRounds, setExpandedRounds] = useState<Set<number>>(new Set());

  const toggleRound = (rn: number) => {
    setExpandedRounds((prev) => {
      const next = new Set(prev);
      if (next.has(rn)) next.delete(rn);
      else next.add(rn);
      return next;
    });
  };

  // Group events by round number
  const grouped = replay.events.reduce<Record<number, ReplayEvent[]>>((acc, evt) => {
    (acc[evt.round_number] ??= []).push(evt);
    return acc;
  }, {});

  const roundNumbers = Object.keys(grouped).map(Number).sort((a, b) => a - b);

  // Auto-expand all on first render
  useEffect(() => {
    setExpandedRounds(new Set(roundNumbers));
  }, [replay.debate_id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (replay.events.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-[var(--muted)]">
        {t("debate.replayError")}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {roundNumbers.map((rn) => {
        const events = grouped[rn];
        const isExpanded = expandedRounds.has(rn);

        return (
          <div key={rn} className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] overflow-hidden">
            <button
              type="button"
              onClick={() => toggleRound(rn)}
              className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left transition-colors hover:bg-[var(--card-hover)]"
            >
              <div className="flex items-center gap-3">
                <span className="section-label">{t("debate.roundLabel").replace("{round}", String(rn))}</span>
                <span className="font-mono text-[11px] text-[var(--muted)]">{events.length} events</span>
              </div>
              {isExpanded ? <ChevronUp size={14} className="text-[var(--muted)]" /> : <ChevronDown size={14} className="text-[var(--muted)]" />}
            </button>

            {isExpanded && (
              <div className="px-5 pb-5 space-y-3 animate-fadeIn">
                {events.map((evt, i) => {
                  const isInterrupt = evt.event_type === "interrupt";
                  const isPositionChange = evt.event_type === "position_change";

                  return (
                    <div
                      key={`${evt.timestamp}-${i}`}
                      className={`relative border-l-2 pl-4 py-2 ${stanceColor(evt.stance)} ${
                        isInterrupt ? "border-l-[var(--accent-purple)] bg-[var(--accent-purple-bg)] rounded-r-md pr-3" : ""
                      }`}
                    >
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <Clock size={12} className="text-[var(--muted)]" />
                        <span className="font-mono text-[11px] text-[var(--muted)]">{formatTimestamp(evt.timestamp)}</span>
                        <span className="text-[11px] text-[var(--muted)]">·</span>
                        <span className="text-xs font-medium text-[var(--foreground)]">{roleLabel(evt.role)}</span>
                        {evt.stance && (
                          <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${stanceBadgeColor(evt.stance)}`}>
                            {stanceLabel(evt.stance, t)}
                          </span>
                        )}
                        {isInterrupt && (
                          <span className="rounded bg-[var(--accent-purple)]/15 px-1.5 py-0.5 text-[10px] font-medium text-[var(--accent-purple)]">
                            {t("debate.interruptEvent")}
                          </span>
                        )}
                        {isPositionChange && (
                          <span className="rounded bg-[var(--accent)]/10 px-1.5 py-0.5 text-[10px] font-medium text-[var(--accent)]">
                            {t("debate.positionChange")}
                          </span>
                        )}
                        {evt.confidence != null && (
                          <span className="font-mono text-[10px] text-[var(--muted)]">
                            {(evt.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                      <p className="text-sm leading-6 text-[var(--muted-foreground)]">{evt.content}</p>
                      {evt.position && isPositionChange && (
                        <p className="mt-1 text-xs text-[var(--accent)]">→ {evt.position}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function DebateReplaySection({ debateId }: { debateId: string }) {
  const { t } = useTranslation();
  const [showReplay, setShowReplay] = useState(false);
  const [replay, setReplay] = useState<DebateReplay | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLoadReplay = async () => {
    if (replay) {
      setShowReplay(!showReplay);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDebateReplay(debateId);
      setReplay(data);
      setShowReplay(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("debate.replayError"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="space-y-4">
      <button
        type="button"
        onClick={handleLoadReplay}
        disabled={loading}
        className="flex items-center gap-2 rounded-lg border border-[var(--card-border)] bg-[var(--card)] px-5 py-3 text-left transition-colors hover:border-[var(--muted)] w-full"
      >
        <History size={16} className="text-[var(--accent)]" />
        <span className="heading-section">{t("debate.viewReplay")}</span>
        {loading && <RefreshCw size={14} className="animate-spin text-[var(--muted)]" />}
        <span className="ml-auto">
          {showReplay ? <ChevronUp size={14} className="text-[var(--muted)]" /> : <ChevronDown size={14} className="text-[var(--muted)]" />}
        </span>
      </button>

      {error && (
        <div className="border-l border-[var(--accent-red)] pl-3 text-sm text-[var(--accent-red)]">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-8 text-sm text-[var(--muted)]">
          <RefreshCw size={14} className="animate-spin mr-2" />
          {t("debate.replayLoading")}
        </div>
      )}

      {showReplay && replay && (
        <div className="animate-fadeIn">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="heading-section">{t("debate.replay")}</h3>
            <span className="font-mono text-xs text-[var(--muted)]">{replay.events.length} events</span>
          </div>
          <ReplayTimeline replay={replay} />
        </div>
      )}
    </section>
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
  const [voteComments, setVoteComments] = useState<Record<string, string>>({});
  const [submittingVoteKey, setSubmittingVoteKey] = useState<string | null>(null);
  const [liveTopic, setLiveTopic] = useState("");
  const [liveTargetId, setLiveTargetId] = useState("");
  const [liveTargetType, setLiveTargetType] = useState<"run" | "claim">("run");
  const [liveStatus, setLiveStatus] = useState<"idle" | "in_progress" | "complete">("idle");
  const [liveCurrentRound, setLiveCurrentRound] = useState<{ round_number: number; role: string } | null>(null);
  const [liveRounds, setLiveRounds] = useState<DebateRound[]>([]);
  const [liveVerdict, setLiveVerdict] = useState<DebateVerdict | null>(null);
  const [liveDebateId, setLiveDebateId] = useState<string | null>(null);
  const liveAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const urlId = searchParams.get("id");
    if (urlId && !qId) {
      setQId(urlId);
      setInputId(urlId);
    }
  }, [searchParams, qId]);

  useEffect(() => {
    setVoteComments({});
    setSubmittingVoteKey(null);
  }, [qId]);

  const { data: debate, error, isLoading } = useSWR(qId ? `debate-${qId}` : null, () => fetchDebateDetail(qId!));
  const { data: debateList, mutate: refreshDebateList } = useSWR("debates-list", () => fetchDebates(20), { refreshInterval: 30000 });
  const { data: votes = [], mutate: refreshVotes } = useSWR(qId ? `debate-votes-${qId}` : null, () => fetchDebateVotes(qId!));
  const { data: simulationRuns } = useSWR("debate-sim-runs", () => fetchSimulationRuns(10));

  const grouped = (debate?.rounds || []).reduce<Record<number, DebateRound[]>>((a, r) => {
    (a[r.round_number] ??= []).push(r);
    return a;
  }, {});

  const verdict = debate?.verdict;
  const recommendations = verdict?.recommendations || [];
  const riskFactors = verdict?.risk_factors || [];
  const alternativeScenarios = verdict?.alternative_scenarios || [];
  const conclusionSummary = verdict?.conclusion_summary;

  const handleLoad = () => {
    if (inputId.trim()) {
      setQId(inputId.trim());
      toast.info('分析报告已加载');
    }
  };

  const handleStartLiveDebate = async () => {
    const targetId = liveTargetId.trim() || simulationRuns?.[0]?.id || "";
    const topic = liveTopic.trim() || debateList?.[0]?.topic || "实时辩论";
    if (!targetId) {
      toast.error("请先输入 Run ID / Claim ID，或创建一次推演");
      return;
    }

    liveAbortRef.current?.abort();
    const ctrl = new AbortController();
    liveAbortRef.current = ctrl;
    setQId(null);
    setLiveStatus("in_progress");
    setLiveCurrentRound(null);
    setLiveRounds([]);
    setLiveVerdict(null);
    setLiveDebateId(null);
    toast.info("实时辩论已启动");
    let completedDebateId: string | null = null;

    try {
      await streamDebate(
        {
          topic,
          trigger_type: "manual",
          target_type: liveTargetType,
          run_id: liveTargetType === "run" ? targetId : undefined,
          claim_id: liveTargetType === "claim" ? targetId : undefined,
          target_id: targetId,
          context_lines: [],
        },
        (evt) => {
          if (evt.payload.debate_id) {
            completedDebateId = evt.payload.debate_id;
            setLiveDebateId(evt.payload.debate_id);
          }

          if (evt.event === "debate_round_start") {
            setLiveCurrentRound({ round_number: evt.payload.round_number, role: evt.payload.role });
          } else if (evt.event === "debate_round_complete") {
            const round: DebateRound = {
              round_number: evt.payload.round_number,
              role: evt.payload.role,
              position: evt.payload.position,
              confidence: evt.payload.confidence,
              arguments: evt.payload.key_arguments.map((argument) => ({ content: argument })),
              rebuttals: [],
              concessions: [],
            };
            setLiveRounds((prev) => [...prev, round]);
            setLiveCurrentRound({ round_number: evt.payload.round_number, role: evt.payload.role });
          } else if (evt.event === "debate_verdict") {
            setLiveVerdict(evt.payload as DebateVerdict);
            setLiveCurrentRound(null);
          }
        },
        ctrl.signal,
      );

      setLiveStatus("complete");
      setLiveCurrentRound(null);
      const refreshed = await refreshDebateList();
      const nextId = completedDebateId || refreshed?.[0]?.debate_id;
      if (nextId) {
        setQId(nextId);
        setInputId(nextId);
      }
      toast.success("辩论完成，完整数据已刷新");
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      setLiveStatus("idle");
      toast.error(err instanceof Error ? err.message : "实时辩论失败");
    }
  };

  const handleVote = async (round: DebateRound, vote: VoteValue) => {
    if (!debate) return;
    const key = voteKey(round);
    setSubmittingVoteKey(key);
    try {
      await createDebateVote({
        debate_session_id: debate.id,
        round_number: round.round_number,
        role: canonicalVoteRole(round.role),
        vote,
        comment: voteComments[key]?.trim() || null,
      });
      setVoteComments((prev) => ({ ...prev, [key]: "" }));
      await refreshVotes();
      toast.success("投票已记录");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "投票失败");
    } finally {
      setSubmittingVoteKey(null);
    }
  };

  const votesForRound = (round: DebateRound) => {
    const role = canonicalVoteRole(round.role);
    return votes.filter((vote) => vote.round_number === round.round_number && vote.role === role);
  };

  return (
    <div className="mx-auto max-w-[1450px] space-y-8">
      {/* ── Page Header ── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_460px]">
        <div>
          <div className="section-label">{t("debate.title")}</div>
          <h1 className="heading-display mt-3">{t("debate.subtitle")}</h1>
        </div>

        <div className="space-y-3 self-end">
          <section className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="flex items-center gap-2 heading-section">
                <Radio size={16} className="text-[var(--accent)]" />
                实时辩论
              </h2>
              {liveStatus === "in_progress" && <span className="badge badge-warning">LIVE</span>}
            </div>
            <div className="grid gap-3 sm:grid-cols-[96px_1fr]">
              <select
                value={liveTargetType}
                onChange={(event) => setLiveTargetType(event.target.value as "run" | "claim")}
                disabled={liveStatus === "in_progress"}
                className="rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)] disabled:opacity-50"
              >
                <option value="run">Run</option>
                <option value="claim">Claim</option>
              </select>
              <input
                className="min-w-0 rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 font-mono text-sm outline-none placeholder:text-[var(--muted)]"
                placeholder={simulationRuns?.[0]?.id ? `默认最新 Run: ${simulationRuns[0].id.slice(0, 8)}` : "Run ID / Claim ID"}
                value={liveTargetId}
                disabled={liveStatus === "in_progress"}
                onChange={(event) => setLiveTargetId(event.target.value)}
              />
            </div>
            <input
              className="mt-3 w-full rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-sm outline-none placeholder:text-[var(--muted)]"
              placeholder="辩论主题"
              value={liveTopic}
              disabled={liveStatus === "in_progress"}
              onChange={(event) => setLiveTopic(event.target.value)}
            />
            <button
              type="button"
              onClick={handleStartLiveDebate}
              disabled={liveStatus === "in_progress"}
              className="btn btn-primary mt-3 w-full justify-center py-3 text-base"
            >
              {liveStatus === "in_progress" ? <RefreshCw size={18} className="animate-spin" /> : <Play size={18} />}
              {liveStatus === "in_progress" ? "辩论进行中" : "发起实时辩论"}
            </button>
            {liveStatus === "in_progress" && (
              <div className="mt-3 space-y-2">
                <div className="flex items-center justify-between gap-3 text-xs text-[var(--muted)]">
                  <span>{liveCurrentRound ? `第${liveCurrentRound.round_number}/4轮 · ${roleLabel(liveCurrentRound.role)}正在陈述...` : "正在建立实时连接..."}</span>
                  <span className="font-mono">{Math.min(95, Math.max(8, liveRounds.length * 25)).toFixed(0)}%</span>
                </div>
                <LiveProgressBar value={Math.min(95, Math.max(8, liveRounds.length * 25))} />
              </div>
            )}
          </section>

          <section className="content-end rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
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
      </div>
      <div className="divider-line" />

      {isLoading && <DebateSkeleton />}

      {(liveStatus === "in_progress" || liveStatus === "complete") && (
        <section className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <h2 className="heading-section">实时辩论进度</h2>
            <span className={liveStatus === "complete" ? "badge badge-success" : "badge badge-warning"}>
              {liveStatus === "complete" ? "COMPLETE" : "IN PROGRESS"}
            </span>
          </div>
          {liveStatus === "in_progress" && (
            <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
              <div className="mb-3 flex items-center justify-between gap-3 text-sm">
                <span>{liveCurrentRound ? `第${liveCurrentRound.round_number}/4轮 · ${roleLabel(liveCurrentRound.role)}正在陈述...` : "等待首轮陈述..."}</span>
                <span className="font-mono text-xs text-[var(--muted)]">{liveRounds.length}/4</span>
              </div>
              <LiveProgressBar value={Math.min(95, Math.max(8, liveRounds.length * 25))} />
            </div>
          )}
          {liveStatus === "in_progress" && liveDebateId && (
            <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-4">
              <DebateInterruptForm debateId={liveDebateId} onSubmitted={() => undefined} />
            </div>
          )}
          <div className="space-y-4">
            {liveRounds.map((round, index) => (
              <DebateRoundBlock
                key={`${round.round_number}-${round.role}-${index}`}
                round={round}
                votes={[]}
                comment=""
                submitting={false}
                onCommentChange={() => undefined}
                onVote={() => undefined}
              />
            ))}
          </div>
          {liveVerdict && <LiveVerdictCard verdict={liveVerdict} />}
        </section>
      )}

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
                        <DebateRoundBlock
                          key={i}
                          round={r}
                          votes={votesForRound(r)}
                          comment={voteComments[voteKey(r)] || ""}
                          submitting={submittingVoteKey === voteKey(r)}
                          onCommentChange={(value) => setVoteComments((prev) => ({ ...prev, [voteKey(r)]: value }))}
                          onVote={handleVote}
                        />
                      ))}
                    </div>
                  ))}
              </div>
            </details>
          )}

          {/* Debate Replay for completed debates */}
          {debate.status === "COMPLETED" && (
            <DebateReplaySection debateId={debate.id} />
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
                {liveStatus === "in_progress" && (
                  <div className="rounded-lg border border-[var(--accent)]/40 bg-[var(--card)] p-5 text-left animate-fadeIn">
                    <div className="mb-3 flex items-center justify-between gap-4">
                      <div>
                        <div className="section-label !text-[var(--accent)]">LIVE · {liveTargetType}</div>
                        <h3 className="mt-2 text-sm font-medium leading-relaxed">{liveTopic || debateList[0]?.topic || "实时辩论"}</h3>
                      </div>
                      <span className="badge badge-warning">{liveRounds.length}/4</span>
                    </div>
                    <LiveProgressBar value={Math.min(95, Math.max(8, liveRounds.length * 25))} />
                  </div>
                )}
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
                        {!d.verdict && (
                          <div className="mt-3">
                            <LiveProgressBar value={35} />
                          </div>
                        )}
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
