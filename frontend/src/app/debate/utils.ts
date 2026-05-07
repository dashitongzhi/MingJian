import type { DebateRound, DebateVote } from "@/lib/api";
import { roleLabel, toText } from "@/lib/utils";

export { roleLabel, toText };

export type VoteValue = "agree" | "disagree" | "neutral";
export type VoteRole = DebateVote["role"];

export function canonicalVoteRole(role: string): VoteRole {
  if (role === "strategist") return "advocate";
  if (role === "risk_analyst") return "challenger";
  if (role === "opportunist") return "arbitrator";
  if (role === "challenger" || role === "arbitrator") return role;
  return "advocate";
}

export function voteKey(round: DebateRound) {
  return round.round_number + ":" + canonicalVoteRole(round.role);
}

export function stanceColor(stance?: string) {
  if (stance === "support") return "border-l-[var(--accent-green)]";
  if (stance === "oppose") return "border-l-[var(--accent-red)]";
  return "border-l-[var(--muted)]";
}

export function stanceLabel(stance: string | undefined, t: (key: string) => string) {
  if (stance === "support") return t("debate.stanceSupport");
  if (stance === "oppose") return t("debate.stanceOppose");
  return t("debate.stanceNeutral");
}

export function stanceBadgeColor(stance?: string) {
  if (stance === "support") return "bg-[var(--accent-green)]/10 text-[var(--accent-green)]";
  if (stance === "oppose") return "bg-[var(--accent-red)]/10 text-[var(--accent-red)]";
  return "bg-[var(--card-hover)] text-[var(--muted)]";
}

export function formatTimestamp(timestamp: string) {
  try {
    return new Date(timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return timestamp;
  }
}
