import type { DebateRound } from "@/lib/api";

export type VoteValue = "agree" | "disagree" | "neutral";

export type RoundData = {
  roundNumber: number;
  proRound?: DebateRound;
  conRound?: DebateRound;
  arbiterRound?: DebateRound;
  otherRounds: DebateRound[];
};

export const AGENTS = [
  { role: "advocate", name: "支持方", side: "support" },
  { role: "challenger", name: "反对方", side: "challenge" },
  { role: "arbitrator", name: "仲裁方", side: "neutral" },
];

export function buildRoundData(rounds: DebateRound[]): RoundData[] {
  const grouped = new Map<number, RoundData>();
  for (const round of rounds) {
    const current = grouped.get(round.round_number) || {
      roundNumber: round.round_number,
      otherRounds: [],
    };
    if (round.role === "advocate" || round.role === "strategist") {
      current.proRound = round;
    } else if (round.role === "challenger" || round.role === "risk_analyst") {
      current.conRound = round;
    } else if (round.role === "arbitrator" || round.role === "opportunist") {
      current.arbiterRound = round;
    } else {
      current.otherRounds.push(round);
    }
    grouped.set(round.round_number, current);
  }
  return Array.from(grouped.values()).sort((a, b) => a.roundNumber - b.roundNumber);
}

export function extractDisputes(rounds: DebateRound[]): string[] {
  return rounds
    .flatMap((round) => round.rebuttals || [])
    .map((item) => String(item.counter || item.claim || item.reason || ""))
    .filter(Boolean)
    .slice(0, 6);
}

export function roleToSide(role: string): string {
  const agent = AGENTS.find(a => a.role === role);
  return agent?.side || "neutral";
}
