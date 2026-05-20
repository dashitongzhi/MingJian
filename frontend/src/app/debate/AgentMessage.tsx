import type { DebateRound, DebateVote } from "@/lib/api";
import { roleLabel, toText } from "./utils";
import type { VoteValue } from "./types";

export function AgentMessage({
  round,
  votes = [],
  submitting = false,
  onVote,
}: {
  round: DebateRound;
  votes?: DebateVote[];
  submitting?: boolean;
  onVote?: (round: DebateRound, vote: VoteValue) => void;
}) {
  const claims = (round.arguments || []).map((argument) => toText(argument)).filter(Boolean);
  return (
    <div className="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="font-medium">{roleLabel(round.role)}</div>
        <div className="font-mono text-xs text-[var(--muted)]">
          Round {round.round_number} · {(round.confidence * 100).toFixed(0)}%
        </div>
      </div>
      <div className="mt-2 space-y-2 text-sm text-[var(--muted-foreground)]">
        {(claims.length ? claims : ["—"]).slice(0, 3).map((claim, index) => (
          <p key={index}>{claim}</p>
        ))}
      </div>
      {onVote && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {(["agree", "disagree", "neutral"] as VoteValue[]).map((vote) => (
            <button
              key={vote}
              type="button"
              disabled={submitting}
              onClick={() => onVote(round, vote)}
              className="rounded border border-[var(--card-border)] px-2 py-1 text-xs text-[var(--muted)] hover:border-[var(--muted)] disabled:opacity-50"
            >
              {vote}
            </button>
          ))}
          {votes.length > 0 && <span className="text-xs text-[var(--muted)]">{votes.length} votes</span>}
        </div>
      )}
    </div>
  );
}
