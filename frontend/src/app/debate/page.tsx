"use client";

import { Suspense } from "react";
import { DebateSkeleton, DebateWorkspace } from "./RoundTimeline";

export default function DebatePage() {
  return (
    <Suspense fallback={<DebateSkeleton />}>
      <DebateWorkspace />
    </Suspense>
  );
}
