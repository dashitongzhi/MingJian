"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { motion, AnimatePresence } from "framer-motion";
import {
  Clock,
  History,
  Loader2,
  MessageSquarePlus,
  Play,
  Radio,
  RefreshCw,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import {
  createDebateVote,
  fetchDebateDetail,
  fetchDebateReplay,
  fetchDebateVotes,
  fetchDebates,
  fetchSimulationRuns,
  postDebateInterrupt,
  streamDebate,
  type DebateReplay,
  type DebateRound,
  type DebateVerdict,
  type InterruptType,
  type ReplayEvent,
} from "@/lib/api";
import { useTranslation } from "@/contexts/LanguageContext";
import { toast } from "@/lib/toast";
import { roleLabel, toText, canonicalVoteRole, voteKey, formatTimestamp, stanceLabel, stanceBadgeColor, stanceColor } from "./utils";
import type { VoteValue, RoundData } from "./types";
import { buildRoundData, extractDisputes, roleToSide, AGENTS } from "./types";
import { DebateTopicHeader } from "./DebateTopicHeader";
import { RoundTimeline } from "./RoundTimeline";
import { AgentMessage } from "./AgentMessage";
import { AgentStatusPanel } from "./AgentStatusPanel";
import { VerdictResult } from "./VerdictResult";
import { DisputeFocus } from "./DisputeFocus";
import { LiveVerdictCard } from "./AdjudicationPanel";

/* ═══════════════════════════════════════════════════════════════════════════
   DEBATE CENTER — Main Page (Refactored)
   ═══════════════════════════════════════════════════════════════════════════ */

export default function DebatePage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <DebateCenter />
    </Suspense>
  );
}

/* ── Page Skeleton ────────────────────────────────────────────────────────── */

function PageSkeleton() {
  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="h-32 rounded-xl bg-[var(--card)] border border-[var(--card-border)] animate-pulse" />
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-48 rounded-xl bg-[var(--card)] border border-[var(--card-border)] animate-pulse" />
          ))}
        </div>
        <div className="space-y-4">
          <div className="h-64 rounded-xl bg-[var(--card)] border border-[var(--card-border)] animate-pulse" />
          <div className="h-48 rounded-xl bg-[var(--card)] border border-[var(--card-border)] animate-pulse" />
        </div>
      </div>
    </div>
  );
}

/* ── Main Component ───────────────────────────────────────────────────────── */

function DebateCenter() {
  const { t } = useTranslation();
  const searchParams = useSearchParams();

  // State
  const [qId, setQId] = useState<string | null>(null);
  const [inputId, setInputId] = useState("");
  const [voteComments, setVoteComments] = useState<Record<string, string>>({});
  const [submittingVoteKey, setSubmittingVoteKey] = useState<string | null>(null);

  // Live debate state
  const [liveTopic, setLiveTopic] = useState("");
  const [liveTargetId, setLiveTargetId] = useState("");
  const [liveTargetType, setLiveTargetType] = useState<"run" | "claim">("run");
  const [liveStatus, setLiveStatus] = useState<"idle" | "in_progress" | "complete">("idle");
  const [liveCurrentRound, setLiveCurrentRound] = useState<{ round_number: number; role: string } | null>(null);
  const [liveRounds, setLiveRounds] = useState<DebateRound[]>([]);
  const [liveVerdict, setLiveVerdict] = useState<DebateVerdict | null>(null);
  const [liveDebateId, setLiveDebateId] = useState<string | null>(null);
  const liveAbortRef = useRef<AbortController | null>(null);

  // Replay state
  const [showReplay, setShowReplay] = useState(false);
  const [replay, setReplay] = useState<DebateReplay | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [expandedReplayRounds, setExpandedReplayRounds] = useState<Set<number>>(new Set());

  // Interrupt state
  const [interruptOpen, setInterruptOpen] = useState(false);
  const [interruptMsg, setInterruptMsg] = useState("");
  const [interruptType, setInterruptType] = useState<InterruptType>("supplementary_info");
  const [interruptSubmitting, setInterruptSubmitting] = useState(false);

  // Data fetching
  const { data: debate, error, isLoading } = useSWR(qId ? `debate-${qId}` : null, () => fetchDebateDetail(qId!));
  const { data: debateList, mutate: refreshDebateList } = useSWR("debates-list", () => fetchDebates(20), { refreshInterval: 30000 });
  const { data: votes = [], mutate: refreshVotes } = useSWR(qId ? `debate-votes-${qId}` : null, () => fetchDebateVotes(qId!));
  const { data: simulationRuns } = useSWR("debate-sim-runs", () => fetchSimulationRuns(10));

  // URL param handling
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

  // Computed data
  const rounds = useMemo(() => buildRoundData(debate?.rounds || []), [debate]);
  const disputes = useMemo(() => extractDisputes(debate?.rounds || []), [debate]);
  const verdict = debate?.verdict;
  const activeRound = liveStatus === "in_progress" ? liveCurrentRound?.round_number : undefined;

  // Handlers
  const handleLoad = useCallback(() => {
    if (inputId.trim()) {
      setQId(inputId.trim());
      toast.info("分析报告已加载");
    }
  }, [inputId]);

  const handleVote = useCallback(async (round: DebateRound, vote: VoteValue) => {
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
  }, [debate, voteComments, refreshVotes]);

  const votesForRound = useCallback((round: DebateRound) => {
    const role = canonicalVoteRole(round.role);
    return votes.filter((v) => v.round_number === round.round_number && v.role === role);
  }, [votes]);

  const handleStartLiveDebate = useCallback(async () => {
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
              arguments: evt.payload.key_arguments.map((a) => ({ content: a })),
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
      toast.success("辩论完成");
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      setLiveStatus("idle");
      toast.error(err instanceof Error ? err.message : "实时辩论失败");
    }
  }, [liveTargetId, liveTopic, liveTargetType, simulationRuns, debateList, refreshDebateList]);

  const handleNextRound = useCallback(() => {
    toast.info("推进下一轮...");
    // In a real implementation, this would trigger the next round
  }, []);

  const handleEndDebate = useCallback(() => {
    liveAbortRef.current?.abort();
    setLiveStatus("idle");
    toast.info("辩论已结束");
  }, []);

  const handleLoadReplay = useCallback(async () => {
    if (!debate) return;
    if (replay) {
      setShowReplay(!showReplay);
      return;
    }
    setReplayLoading(true);
    try {
      const data = await fetchDebateReplay(debate.id);
      setReplay(data);
      setShowReplay(true);
      setExpandedReplayRounds(new Set(data.events.map((e) => e.round_number)));
    } catch {
      toast.error("加载回放失败");
    } finally {
      setReplayLoading(false);
    }
  }, [debate, replay, showReplay]);

  const handleInterrupt = useCallback(async () => {
    if (!liveDebateId || !interruptMsg.trim()) return;
    setInterruptSubmitting(true);
    try {
      await postDebateInterrupt(liveDebateId, interruptMsg.trim(), interruptType);
      toast.success("中断已发送");
      setInterruptMsg("");
      setInterruptOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "发送失败");
    } finally {
      setInterruptSubmitting(false);
    }
  }, [liveDebateId, interruptMsg, interruptType]);

  // ── Render ──

  const showDebateContent = debate && !isLoading;
  const isLive = liveStatus === "in_progress";

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      {/* ════════════════════════════════════════════════════════════════════════
         PAGE HEADER — Title + Live Debate Launcher
         ════════════════════════════════════════════════════════════════════════ */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="relative overflow-hidden rounded-xl border border-[var(--card-border)] bg-[var(--card)]"
      >
        {/* Top gradient stripe */}
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[var(--accent)]/50 to-transparent" />
        <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-[var(--accent)]/4 to-transparent pointer-events-none" />

        <div className="relative p-6 md:p-8">
          <div className="grid gap-8 lg:grid-cols-[1fr_420px]">
            {/* Left: Title */}
            <div>
              <div className="section-label flex items-center gap-2 mb-3">
                <Sparkles size={12} className="text-[var(--accent)]" />
                {t("debate.title")}
              </div>
              <h1 className="heading-display text-2xl md:text-3xl mb-4">{t("debate.subtitle")}</h1>
              <p className="text-sm text-[var(--muted)] leading-relaxed max-w-lg">
                多智能体辩论系统，通过正方、反方和仲裁三方协作，对复杂议题进行深度分析和结构化论证。
              </p>
            </div>

            {/* Right: Quick launch */}
            <div className="space-y-3 self-end">
              {/* Live debate launcher */}
              <div className="rounded-lg border border-[var(--card-border)] bg-[var(--background)]/50 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Radio size={14} className="text-[var(--accent)]" />
                  <span className="text-xs font-medium text-[var(--foreground)]">实时辩论</span>
                  {isLive && <span className="badge badge-warning text-[9px]">LIVE</span>}
                </div>
                <div className="grid gap-2.5 sm:grid-cols-[80px_1fr]">
                  <select
                    value={liveTargetType}
                    onChange={(e) => setLiveTargetType(e.target.value as "run" | "claim")}
                    disabled={isLive}
                    className="rounded-md border border-[var(--input)] bg-[var(--background)] px-2.5 py-2 text-xs outline-none focus:border-[var(--accent)] disabled:opacity-50"
                  >
                    <option value="run">Run</option>
                    <option value="claim">Claim</option>
                  </select>
                  <input
                    className="min-w-0 rounded-md border border-[var(--input)] bg-[var(--background)] px-2.5 py-2 font-mono text-xs outline-none placeholder:text-[var(--muted)] focus:border-[var(--accent)]"
                    placeholder={simulationRuns?.[0]?.id ? `默认: ${simulationRuns[0].id.slice(0, 8)}` : "Run ID / Claim ID"}
                    value={liveTargetId}
                    disabled={isLive}
                    onChange={(e) => setLiveTargetId(e.target.value)}
                  />
                </div>
                <input
                  className="mt-2.5 w-full rounded-md border border-[var(--input)] bg-[var(--background)] px-2.5 py-2 text-xs outline-none placeholder:text-[var(--muted)] focus:border-[var(--accent)]"
                  placeholder="辩论主题"
                  value={liveTopic}
                  disabled={isLive}
                  onChange={(e) => setLiveTopic(e.target.value)}
                />
                <button
                  type="button"
                  onClick={handleStartLiveDebate}
                  disabled={isLive}
                  className="btn btn-primary mt-3 w-full justify-center py-2.5 text-sm disabled:opacity-50"
                >
                  {isLive ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
                  {isLive ? "辩论进行中..." : "发起实时辩论"}
                </button>
                {isLive && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    className="mt-3"
                  >
                    <div className="flex items-center justify-between text-[11px] text-[var(--muted)] mb-1.5">
                      <span>{liveCurrentRound ? `Round ${liveCurrentRound.round_number}/4 · ${roleLabel(liveCurrentRound.role)}` : "连接中..."}</span>
                      <span className="font-mono">{Math.min(95, Math.max(8, liveRounds.length * 25)).toFixed(0)}%</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[var(--card-border)]">
                      <motion.div
                        className="h-full rounded-full bg-[var(--accent)]"
                        animate={{ width: `${Math.min(95, Math.max(8, liveRounds.length * 25))}%` }}
                        transition={{ duration: 0.5 }}
                      />
                    </div>
                  </motion.div>
                )}
              </div>

              {/* Load debate by ID */}
              <div className="rounded-lg border border-[var(--card-border)] bg-[var(--background)]/50 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Search size={14} className="text-[var(--accent)]" />
                  <span className="text-xs font-medium text-[var(--foreground)]">{t("debate.loadDebate")}</span>
                </div>
                <div className="flex gap-2">
                  <input
                    className="min-w-0 flex-1 rounded-md border border-[var(--input)] bg-[var(--background)] px-2.5 py-2 font-mono text-xs outline-none placeholder:text-[var(--muted)] focus:border-[var(--accent)]"
                    placeholder={t("debate.debateIdPlaceholder")}
                    value={inputId}
                    onChange={(e) => setInputId(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleLoad()}
                  />
                  <button onClick={handleLoad} className="btn btn-primary btn-sm">
                    {t("common.load")}
                  </button>
                </div>
                {error && (
                  <p className="mt-2 text-[11px] text-[var(--accent-red)]">{t("debate.debateNotFound")}</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </motion.div>

      {/* ════════════════════════════════════════════════════════════════════════
         LOADING STATE
         ════════════════════════════════════════════════════════════════════════ */}
      {isLoading && <PageSkeleton />}

      {/* ════════════════════════════════════════════════════════════════════════
         LIVE DEBATE PROGRESS
         ════════════════════════════════════════════════════════════════════════ */}
      <AnimatePresence>
        {(liveStatus === "in_progress" || liveStatus === "complete") && !debate && (
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-4"
          >
            <div className="flex items-center justify-between">
              <h2 className="heading-section">实时辩论进度</h2>
              <span className={liveStatus === "complete" ? "badge badge-success" : "badge badge-warning"}>
                {liveStatus === "complete" ? "COMPLETE" : "LIVE"}
              </span>
            </div>

            {liveDebateId && isLive && (
              <InterruptBar
                open={interruptOpen}
                onToggle={() => setInterruptOpen(!interruptOpen)}
                message={interruptMsg}
                onMessageChange={setInterruptMsg}
                interruptType={interruptType}
                onTypeChange={setInterruptType}
                submitting={interruptSubmitting}
                onSubmit={handleInterrupt}
              />
            )}

            <div className="space-y-3">
              {liveRounds.map((round, i) => (
                <AgentMessage
                  key={`${round.round_number}-${round.role}-${i}`}
                  round={round}
                  votes={[]}
                  submitting={false}
                  onVote={() => undefined}
                />
              ))}
            </div>

            {liveVerdict && <LiveVerdictCard verdict={liveVerdict} />}
          </motion.section>
        )}
      </AnimatePresence>

      {/* ════════════════════════════════════════════════════════════════════════
         DEBATE DETAIL VIEW
         ════════════════════════════════════════════════════════════════════════ */}
      {showDebateContent && (
        <div className="space-y-6">
          {/* Topic Header */}
          <DebateTopicHeader
            debate={debate}
            roundCount={rounds.length}
            liveStatus={liveStatus}
            onNextRound={handleNextRound}
            onEndDebate={handleEndDebate}
          />

          {/* Main layout: 2-column on desktop */}
          <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
            {/* Left column: Timeline + Messages */}
            <div className="space-y-6 min-w-0">
              {/* Round Timeline */}
              {rounds.length > 0 && (
                <RoundTimeline rounds={rounds} activeRound={activeRound} />
              )}

              {/* Agent Messages (grouped by round) */}
              {rounds.length > 0 && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.2 }}
                >
                  <h2 className="heading-section mb-4">辩论对话</h2>
                  <div className="space-y-4">
                    {rounds.map((rd) => (
                      <RoundMessages
                        key={rd.roundNumber}
                        roundData={rd}
                        votes={votes}
                        submittingVoteKey={submittingVoteKey}
                        onVote={handleVote}
                      />
                    ))}
                  </div>
                </motion.div>
              )}

              {/* Verdict */}
              {verdict && <VerdictResult verdict={verdict} />}

              {/* Replay */}
              {debate.status === "COMPLETED" && (
                <ReplaySection
                  debateId={debate.id}
                  showReplay={showReplay}
                  replay={replay}
                  loading={replayLoading}
                  expandedRounds={expandedReplayRounds}
                  onLoad={handleLoadReplay}
                  onToggleRound={(rn) => {
                    setExpandedReplayRounds((prev) => {
                      const next = new Set(prev);
                      if (next.has(rn)) next.delete(rn);
                      else next.add(rn);
                      return next;
                    });
                  }}
                />
              )}
            </div>

            {/* Right column: Status + Disputes */}
            <div className="space-y-6">
              <AgentStatusPanel rounds={debate.rounds} />
              <DisputeFocus disputes={disputes} />
            </div>
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════════════════
         RECENT DEBATES LIST (when no debate selected)
         ════════════════════════════════════════════════════════════════════════ */}
      {!debate && !error && !isLoading && liveStatus === "idle" && (
        <RecentDebatesList
          debates={debateList}
          onSelect={(id) => { setQId(id); setInputId(id); }}
        />
      )}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════════════
   SUB-COMPONENTS
   ════════════════════════════════════════════════════════════════════════════ */

/* ── Round Messages (grouped) ─────────────────────────────────────────────── */

function RoundMessages({
  roundData,
  votes,
  submittingVoteKey,
  onVote,
}: {
  roundData: RoundData;
  votes: import("@/lib/api").DebateVote[];
  submittingVoteKey: string | null;
  onVote: (round: DebateRound, vote: VoteValue) => void;
}) {
  const allRounds = [roundData.proRound, roundData.conRound, roundData.arbiterRound].filter(Boolean) as DebateRound[];

  return (
    <div className="space-y-3">
      <div className="sticky top-14 z-10 flex items-center gap-3 bg-[var(--background)] py-2">
        <span className="section-label text-[var(--accent)]">Round {roundData.roundNumber}</span>
        <span className="flex-1 h-px bg-[var(--card-border)]" />
      </div>
      {allRounds.map((round, i) => {
        const role = canonicalVoteRole(round.role);
        const key = `${round.round_number}:${role}`;
        const roundVotes = votes.filter((v) => v.round_number === round.round_number && v.role === role);

        return (
          <AgentMessage
            key={`${round.round_number}-${round.role}-${i}`}
            round={round}
            votes={roundVotes}
            submitting={submittingVoteKey === key}
            onVote={onVote}
          />
        );
      })}
    </div>
  );
}

/* ── Interrupt Bar ────────────────────────────────────────────────────────── */

const INTERRUPT_TYPES: { value: InterruptType; label: string; icon: string }[] = [
  { value: "supplementary_info", label: "补充信息", icon: "📋" },
  { value: "direction_correction", label: "方向修正", icon: "🧭" },
  { value: "new_evidence", label: "新证据", icon: "🔍" },
  { value: "general", label: "一般中断", icon: "💬" },
];

function InterruptBar({
  open,
  onToggle,
  message,
  onMessageChange,
  interruptType,
  onTypeChange,
  submitting,
  onSubmit,
}: {
  open: boolean;
  onToggle: () => void;
  message: string;
  onMessageChange: (v: string) => void;
  interruptType: InterruptType;
  onTypeChange: (v: InterruptType) => void;
  submitting: boolean;
  onSubmit: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      className="rounded-lg border border-[var(--accent)]/20 bg-[var(--card)] overflow-hidden"
    >
      {!open ? (
        <button
          type="button"
          onClick={onToggle}
          className="flex w-full items-center gap-2 px-4 py-3 text-sm text-[var(--accent)] hover:bg-[var(--accent)]/5 transition-colors"
        >
          <MessageSquarePlus size={15} />
          发送中断指令
        </button>
      ) : (
        <div className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[var(--accent)]">中断类型</span>
            <button type="button" onClick={onToggle} className="text-[var(--muted)] hover:text-[var(--foreground)]">
              <X size={14} />
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {INTERRUPT_TYPES.map((it) => (
              <button
                key={it.value}
                type="button"
                onClick={() => onTypeChange(it.value)}
                className={`flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-[11px] transition-colors ${
                  interruptType === it.value
                    ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                    : "border-[var(--card-border)] text-[var(--muted)] hover:border-[var(--muted)]"
                }`}
              >
                <span>{it.icon}</span>
                {it.label}
              </button>
            ))}
          </div>
          <textarea
            className="w-full rounded-md border border-[var(--input)] bg-[var(--background)] px-3 py-2 text-xs outline-none placeholder:text-[var(--muted)] focus:border-[var(--accent)] resize-none"
            rows={2}
            placeholder="输入中断内容..."
            value={message}
            onChange={(e) => onMessageChange(e.target.value)}
            disabled={submitting}
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onSubmit}
              disabled={submitting || !message.trim()}
              className="btn btn-primary btn-sm disabled:opacity-50"
            >
              {submitting ? <Loader2 size={12} className="animate-spin" /> : <MessageSquarePlus size={12} />}
              {submitting ? "发送中..." : "发送"}
            </button>
          </div>
        </div>
      )}
    </motion.div>
  );
}

/* ── Replay Section ───────────────────────────────────────────────────────── */

function ReplaySection({
  debateId,
  showReplay,
  replay,
  loading,
  expandedRounds,
  onLoad,
  onToggleRound,
}: {
  debateId: string;
  showReplay: boolean;
  replay: DebateReplay | null;
  loading: boolean;
  expandedRounds: Set<number>;
  onLoad: () => void;
  onToggleRound: (rn: number) => void;
}) {
  return (
    <motion.section
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.3 }}
      className="space-y-3"
    >
      <button
        type="button"
        onClick={onLoad}
        disabled={loading}
        className="flex w-full items-center gap-2.5 rounded-lg border border-[var(--card-border)] bg-[var(--card)] px-5 py-3.5 text-left transition-colors hover:border-[var(--muted)]"
      >
        <History size={15} className="text-[var(--accent)]" />
        <span className="heading-section">查看回放</span>
        {loading && <Loader2 size={13} className="animate-spin text-[var(--muted)]" />}
      </button>

      <AnimatePresence>
        {showReplay && replay && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="space-y-2 overflow-hidden"
          >
            {Object.entries(
              replay.events.reduce<Record<number, ReplayEvent[]>>((acc, evt) => {
                (acc[evt.round_number] ??= []).push(evt);
                return acc;
              }, {})
            )
              .sort(([a], [b]) => +a - +b)
              .map(([rn, events]) => {
                const roundNum = +rn;
                const isExpanded = expandedRounds.has(roundNum);
                return (
                  <div key={rn} className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] overflow-hidden">
                    <button
                      type="button"
                      onClick={() => onToggleRound(roundNum)}
                      className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-[var(--card-hover)] transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium">Round {rn}</span>
                        <span className="font-mono text-[10px] text-[var(--muted)]">{events.length} events</span>
                      </div>
                    </button>
                    {isExpanded && (
                      <div className="px-4 pb-3 space-y-2 border-t border-[var(--card-border)]">
                        {events.map((evt, i) => (
                          <div key={`${evt.timestamp}-${i}`} className={`border-l-2 pl-3 py-1.5 ${stanceColor(evt.stance)}`}>
                            <div className="flex items-center gap-2 mb-0.5">
                              <Clock size={10} className="text-[var(--muted)]" />
                              <span className="font-mono text-[10px] text-[var(--muted)]">{formatTimestamp(evt.timestamp)}</span>
                              <span className="text-[11px] font-medium">{roleLabel(evt.role)}</span>
                              {evt.stance && (
                                <span className={`rounded px-1 py-0.5 text-[9px] font-medium ${stanceBadgeColor(evt.stance)}`}>
                                  {stanceLabel(evt.stance, (k: string) => k)}
                                </span>
                              )}
                            </div>
                            <p className="text-xs leading-5 text-[var(--muted-foreground)]">{evt.content}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  );
}

/* ── Recent Debates List ──────────────────────────────────────────────────── */

function RecentDebatesList({
  debates,
  onSelect,
}: {
  debates: import("@/lib/api").DebateSummary[] | undefined;
  onSelect: (id: string) => void;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 }}
    >
      <div className="flex items-center justify-between mb-4">
        <h2 className="heading-section">最近分析报告</h2>
        <span className="font-mono text-[11px] text-[var(--muted)]">{debates?.length || 0} 份</span>
      </div>

      {debates && debates.length > 0 ? (
        <div className="space-y-3">
          {debates.map((d, index) => (
            <motion.button
              key={d.debate_id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 + index * 0.04 }}
              type="button"
              onClick={() => onSelect(d.debate_id)}
              className="w-full rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5 text-left transition-all duration-200 hover:border-[var(--muted)] hover:bg-[var(--card-hover)] group"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="section-label !text-[var(--muted)]">{d.trigger_type}</span>
                    <span className="text-[var(--muted)]/30">|</span>
                    <span className="text-[10px] text-[var(--muted)]">
                      {new Date(d.created_at).toLocaleDateString("zh-CN")}
                    </span>
                  </div>
                  <h3 className="text-sm font-medium leading-relaxed text-[var(--foreground)] group-hover:text-[var(--accent)] transition-colors">
                    {d.topic}
                  </h3>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {d.confidence != null && (
                    <span className="font-mono text-xs text-[var(--muted)]">
                      {(d.confidence * 100).toFixed(0)}%
                    </span>
                  )}
                  <span className="text-[var(--muted)] group-hover:text-[var(--accent)] transition-colors text-sm">&rarr;</span>
                </div>
              </div>
            </motion.button>
          ))}
        </div>
      ) : (
        <div className="flex min-h-[300px] items-center justify-center rounded-xl border border-dashed border-[var(--card-border)]">
          <div className="text-center px-6">
            <div className="mx-auto mb-3 h-px w-12 bg-[var(--accent)]/30" />
            <p className="text-sm text-[var(--muted)]">输入辩论 ID 或通过战略助手发起分析</p>
          </div>
        </div>
      )}
    </motion.section>
  );
}
