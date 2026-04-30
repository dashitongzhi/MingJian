"use client";

import { useEffect, useState } from "react";

const VISITED_KEY = "planagent_visited";

const features = [
  {
    title: "Strategic Assistant",
    description: "Enter any topic and get real-time AI analysis with multi-agent debate",
  },
  {
    title: "Scenario Simulation",
    description: "Run what-if simulations with branching timelines and KPI tracking",
  },
  {
    title: "Evidence Intelligence",
    description: "Gather, verify, and synthesize evidence from multiple sources",
  },
];

export default function WelcomeGuide() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!window.localStorage.getItem(VISITED_KEY)) {
      setOpen(true);
    }
  }, []);

  const closeGuide = () => {
    window.localStorage.setItem(VISITED_KEY, "true");
    setOpen(false);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="btn btn-ghost btn-sm w-9 h-9 rounded-full p-0 text-base"
        aria-label="Open welcome guide"
      >
        ?
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 animate-fadeIn">
          <div className="w-full max-w-2xl rounded-xl border border-[var(--card-border)] bg-[var(--card)] p-6 shadow-2xl">
            <div className="mb-6">
              <h2 className="text-2xl font-bold">Welcome to PlanAgent</h2>
              <p className="mt-2 text-sm text-[var(--muted)]">Your AI-Powered Decision Intelligence Platform</p>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              {features.map((feature) => (
                <div key={feature.title} className="rounded-lg border border-[var(--card-border)] bg-[var(--background)] p-4">
                  <div className="text-sm font-semibold">{feature.title}</div>
                  <p className="mt-2 text-xs leading-5 text-[var(--muted-foreground)]">{feature.description}</p>
                </div>
              ))}
            </div>

            <div className="mt-6 flex justify-end">
              <button type="button" onClick={closeGuide} className="btn btn-primary">
                Get Started
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
