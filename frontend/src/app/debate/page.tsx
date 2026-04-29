"use client";
import { useState } from "react";
import useSWR from "swr";
import { fetchDebateDetail, type DebateRound } from "@/lib/api";

const ROLE_COLORS: Record<string, string> = { advocate: "border-[var(--accent-green)]", challenger: "border-[var(--accent-red)]", arbitrator: "border-[var(--accent)]" };
const ROLE_BADGE: Record<string, string> = { advocate: "bg-[var(--accent-green)]/20 text-[var(--accent-green)]", challenger: "bg-[var(--accent-red)]/20 text-[var(--accent-red)]", arbitrator: "bg-[var(--accent)]/20 text-[var(--accent)]" };

export default function DebatePage() {
  const [inputId, setInputId] = useState("");
  const [qId, setQId] = useState<string | null>(null);
  const { data: debate, error } = useSWR(qId ? `debate-${qId}` : null, () => fetchDebateDetail(qId!));
  const grouped = (debate?.rounds || []).reduce<Record<number, DebateRound[]>>((a, r) => { (a[r.round_number] ??= []).push(r); return a; }, {});

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-bold">Debate Center</h1>
      <div className="flex gap-2"><input className="flex-1 bg-[var(--card)] border border-[var(--card-border)] rounded p-2 text-sm focus:border-[var(--accent)] outline-none" placeholder="Enter debate ID..." value={inputId} onChange={(e) => setInputId(e.target.value)} onKeyDown={(e) => e.key === "Enter" && setQId(inputId.trim())} /><button onClick={() => setQId(inputId.trim())} className="bg-[var(--accent)] text-white px-4 py-2 rounded text-sm">Load</button></div>
      {error && <div className="text-sm text-[var(--accent-red)]">Debate not found</div>}
      {debate && <div className="space-y-4">
        <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-lg p-4"><div className="flex justify-between"><div><h2 className="text-sm font-semibold">{debate.topic}</h2><div className="text-xs text-[var(--muted)] mt-1">Trigger: {debate.trigger_type}</div></div><span className={`text-xs px-3 py-1 rounded ${debate.status === "COMPLETED" ? "bg-[var(--accent-green)]/20 text-[var(--accent-green)]" : "bg-[var(--accent-yellow)]/20 text-[var(--accent-yellow)]"}`}>{debate.status}</span></div></div>
        {debate.verdict && <div className="bg-[var(--card)] border border-[var(--accent)] rounded-lg p-4"><h3 className="text-sm font-semibold mb-2">Verdict</h3><div className="grid grid-cols-3 gap-4"><div><div className="text-xs text-[var(--muted)]">Outcome</div><div className="text-lg font-bold capitalize">{debate.verdict.verdict}</div></div><div><div className="text-xs text-[var(--muted)]">Confidence</div><div className="text-lg font-bold">{(debate.verdict.confidence * 100).toFixed(0)}%</div></div><div><div className="text-xs text-[var(--muted)]">Rounds</div><div className="text-lg font-bold">{debate.verdict.winning_arguments.length > 0 ? debate.verdict.winning_arguments.length : "—"}</div></div></div>{debate.verdict.winning_arguments.length > 0 && <div className="mt-3"><div className="text-xs text-[var(--muted)] mb-1">Winning Arguments</div><ul className="list-disc list-inside text-xs">{debate.verdict.winning_arguments.map((a, i) => <li key={i}>{a}</li>)}</ul></div>}{debate.verdict.minority_opinion && <div className="mt-2 text-xs text-[var(--accent-yellow)]">Minority: {debate.verdict.minority_opinion}</div>}</div>}
        {Object.entries(grouped).sort(([a], [b]) => +a - +b).map(([rn, rounds]) => <div key={rn}><h3 className="text-xs text-[var(--muted)] mb-2 uppercase">Round {rn}</h3><div className="grid grid-cols-1 md:grid-cols-3 gap-3">{rounds.map((r, i) => <div key={i} className={`bg-[var(--card)] border-l-2 ${ROLE_COLORS[r.role] || "border-[var(--card-border)]"} rounded-lg p-4`}><div className="flex justify-between mb-2"><span className={`text-xs px-2 py-0.5 rounded ${ROLE_BADGE[r.role] || ""}`}>{r.role}</span><span className="text-xs text-[var(--muted)]">{(r.confidence * 100).toFixed(0)}%</span></div><div className="text-xs font-medium mb-2 capitalize">{r.position}</div>{r.arguments.map((a, j) => <div key={j} className="text-xs text-[var(--muted)] mb-1">{"•"} {typeof a === "string" ? a : JSON.stringify(a)}</div>)}{r.rebuttals.length > 0 && <div className="mt-2"><div className="text-xs text-[var(--accent-red)]">Rebuttals</div>{r.rebuttals.map((rb, j) => <div key={j} className="text-xs text-[var(--muted)]">{"•"} {typeof rb === "string" ? rb : JSON.stringify(rb)}</div>)}</div>}</div>)}</div></div>)}
      </div>}
      {!debate && !error && <div className="text-sm text-[var(--muted)] text-center py-16">Enter a debate ID to view the full trace</div>}
    </div>
  );
}
