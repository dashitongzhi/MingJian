"use client";
import { useState } from "react";
import useSWR from "swr";
import { fetchDebateDetail, type DebateRound } from "@/lib/api";

function DebateRoundCard({ round }: { round: DebateRound }) {
  const roleConfig: Record<string, { color: string; icon: string; label: string }> = {
    advocate: {
      color: "border-[var(--accent-green)] bg-[var(--accent-green-bg)]",
      icon: "✓",
      label: "Advocate",
    },
    challenger: {
      color: "border-[var(--accent-red)] bg-[var(--accent-red-bg)]",
      icon: "✗",
      label: "Challenger",
    },
    arbitrator: {
      color: "border-[var(--accent-purple)] bg-[var(--accent-purple-bg)]",
      icon: "⚖",
      label: "Arbitrator",
    },
  };

  const config = roleConfig[round.role] || roleConfig.arbitrator;

  return (
    <div className={`p-4 rounded-xl border-l-4 ${config.color} animate-fadeIn`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">{config.icon}</span>
          <span className="text-sm font-semibold">{config.label}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-20 h-2 bg-[var(--background)] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                round.confidence > 0.7 ? "bg-[var(--accent-green)]" : round.confidence > 0.4 ? "bg-[var(--accent-yellow)]" : "bg-[var(--accent-red)]"
              }`}
              style={{ width: `${round.confidence * 100}%` }}
            />
          </div>
          <span className="text-xs font-mono text-[var(--muted)]">{(round.confidence * 100).toFixed(0)}%</span>
        </div>
      </div>

      <div className="mb-3">
        <div className="text-xs text-[var(--muted)] uppercase mb-1">Position</div>
        <p className="text-sm font-medium">{round.position}</p>
      </div>

      {round.arguments.length > 0 && (
        <div className="mb-3">
          <div className="text-xs text-[var(--muted)] uppercase mb-2">Arguments</div>
          <ul className="space-y-1">
            {round.arguments.map((a, i) => (
              <li key={i} className="flex items-start gap-2 text-xs">
                <span className="text-[var(--muted)] mt-0.5">•</span>
                <span>{typeof a === "string" ? a : JSON.stringify(a)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {round.rebuttals.length > 0 && (
        <div>
          <div className="text-xs text-[var(--accent-red)] uppercase mb-2">Rebuttals</div>
          <ul className="space-y-1">
            {round.rebuttals.map((rb, i) => (
              <li key={i} className="flex items-start gap-2 text-xs">
                <span className="text-[var(--accent-red)] mt-0.5">•</span>
                <span className="text-[var(--muted-foreground)]">{typeof rb === "string" ? rb : JSON.stringify(rb)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function DebatePage() {
  const [inputId, setInputId] = useState("");
  const [qId, setQId] = useState<string | null>(null);
  const { data: debate, error } = useSWR(qId ? `debate-${qId}` : null, () => fetchDebateDetail(qId!));

  const grouped = (debate?.rounds || []).reduce<Record<number, DebateRound[]>>((a, r) => {
    (a[r.round_number] ??= []).push(r);
    return a;
  }, {});

  const handleLoad = () => {
    if (inputId.trim()) setQId(inputId.trim());
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Debate Center</h1>
        <p className="text-[var(--muted)] mt-1">View multi-agent debate traces and verdicts</p>
      </div>

      {/* Search */}
      <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          Load Debate
        </h2>
        <div className="flex gap-3">
          <input
            className="input flex-1"
            placeholder="Enter debate ID..."
            value={inputId}
            onChange={(e) => setInputId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleLoad()}
          />
          <button onClick={handleLoad} className="btn btn-primary">
            Load
          </button>
        </div>
        {error && (
          <div className="flex items-center gap-2 mt-3 p-3 rounded-lg bg-[var(--accent-red-bg)] text-[var(--accent-red)] text-sm">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
            Debate not found
          </div>
        )}
      </div>

      {/* Debate content */}
      {debate ? (
        <div className="space-y-6 animate-fadeIn">
          {/* Topic and status */}
          <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-lg font-semibold">{debate.topic}</h2>
                <div className="flex items-center gap-3 mt-2">
                  <span className="text-xs text-[var(--muted)]">Trigger: {debate.trigger_type}</span>
                  <span className="text-xs text-[var(--muted)]">•</span>
                  <span className="text-xs text-[var(--muted)]">Rounds: {Object.keys(grouped).length}</span>
                </div>
              </div>
              <span className={`badge ${debate.status === "COMPLETED" ? "badge-success" : "badge-warning"}`}>
                {debate.status}
              </span>
            </div>
          </div>

          {/* Verdict */}
          {debate.verdict && (
            <div className="bg-[var(--card)] border-2 border-[var(--accent)] rounded-xl p-6">
              <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                Final Verdict
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="text-center p-4 rounded-lg bg-[var(--background)]">
                  <div className="text-xs text-[var(--muted)] uppercase mb-1">Outcome</div>
                  <div className={`text-2xl font-bold capitalize ${debate.verdict.verdict === "support" ? "text-[var(--accent-green)]" : "text-[var(--accent-red)]"}`}>
                    {debate.verdict.verdict}
                  </div>
                </div>
                <div className="text-center p-4 rounded-lg bg-[var(--background)]">
                  <div className="text-xs text-[var(--muted)] uppercase mb-1">Confidence</div>
                  <div className="text-2xl font-bold">{(debate.verdict.confidence * 100).toFixed(0)}%</div>
                </div>
                <div className="text-center p-4 rounded-lg bg-[var(--background)]">
                  <div className="text-xs text-[var(--muted)] uppercase mb-1">Winning Args</div>
                  <div className="text-2xl font-bold">{debate.verdict.winning_arguments.length}</div>
                </div>
              </div>

              {debate.verdict.winning_arguments.length > 0 && (
                <div className="mt-4 pt-4 border-t border-[var(--card-border)]">
                  <div className="text-xs text-[var(--muted)] uppercase mb-2">Winning Arguments</div>
                  <ul className="space-y-2">
                    {debate.verdict.winning_arguments.map((a, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent-green)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mt-0.5 flex-shrink-0">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                        {a}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {debate.verdict.minority_opinion && (
                <div className="mt-4 pt-4 border-t border-[var(--card-border)]">
                  <div className="text-xs text-[var(--accent-yellow)] uppercase mb-2">Minority Opinion</div>
                  <p className="text-sm text-[var(--muted-foreground)]">{debate.verdict.minority_opinion}</p>
                </div>
              )}
            </div>
          )}

          {/* Rounds */}
          {Object.entries(grouped)
            .sort(([a], [b]) => +a - +b)
            .map(([rn, rounds]) => (
              <div key={rn}>
                <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <span className="w-6 h-6 rounded-full bg-[var(--accent)] text-white text-xs flex items-center justify-center">
                    {rn}
                  </span>
                  Round {rn}
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {rounds.map((r, i) => (
                    <DebateRoundCard key={i} round={r} />
                  ))}
                </div>
              </div>
            ))}
        </div>
      ) : (
        !error && (
          <div className="bg-[var(--card)] border border-[var(--card-border)] rounded-xl p-5 min-h-[400px] flex items-center justify-center">
            <div className="empty-state">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="empty-state-icon">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              <div className="empty-state-title">Enter a debate ID</div>
              <div className="empty-state-description">Load a debate to view the full multi-agent discussion trace</div>
            </div>
          </div>
        )
      )}
    </div>
  );
}