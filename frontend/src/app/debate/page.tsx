"use client";

import { Suspense } from "react";
import { DebateSkeleton, DebateWorkspace } from "./RoundTimeline";

export default function DebatePage() {
  return (
    <div className="flex flex-col gap-6 pb-8">
      <Suspense fallback={<DebateSkeleton />}>
        <DebateWorkspace />
      </Suspense>
    </div>
  );
}
