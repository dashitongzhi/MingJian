export type VoteValue = "agree" | "disagree" | "neutral";

export type RoundData = {
  round_number: number;
  role: string;
  position: string;
  confidence: number;
  arguments: any[];
  rebuttals: any[];
  concessions: any[];
};

export const AGENTS = [
  { role: "advocate", name: "支持方", side: "support" },
  { role: "challenger", name: "反对方", side: "challenge" },
  { role: "arbitrator", name: "仲裁方", side: "neutral" },
];

export function buildRoundData(rounds: any[]): RoundData[] {
  return rounds;
}

export function extractDisputes(rounds: any[]): any[] {
  return [];
}

export function roleToSide(role: string): string {
  const agent = AGENTS.find(a => a.role === role);
  return agent?.side || "neutral";
}
