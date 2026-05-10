"use client";

import { Pause, Play, SkipForward, Trash2 } from "lucide-react";
import { useTranslation } from "@/contexts/LanguageContext";
import type { AssistantController } from "./hooks";

type PauseControlProps = {
  controller: AssistantController;
};

export default function PauseControl({ controller }: PauseControlProps) {
  const { t } = useTranslation();
  const { isPaused, pausedEvents, togglePause, resumeWithMode, streaming } = controller;

  if (!streaming) return null;

  return (
    <div className="flex items-center gap-3 rounded-lg border border-[var(--card-border)] bg-[var(--card)] px-4 py-2">
      <button
        type="button"
        onClick={togglePause}
        className="flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors hover:bg-[var(--card-hover)]"
        aria-label={isPaused ? t("assistant.resume") : t("assistant.pause")}
      >
        {isPaused ? (
          <>
            <Play className="size-4" />
            <span>{t("assistant.paused")}</span>
          </>
        ) : (
          <>
            <Pause className="size-4" />
            <span>{t("assistant.streaming")}</span>
          </>
        )}
      </button>

      {isPaused && pausedEvents.length > 0 && (
        <>
          <div className="h-4 w-px bg-[var(--border)]" />

          <div className="flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
            <span className="rounded-full bg-[var(--accent-amber-bg)] px-2 py-0.5 text-xs font-medium text-[var(--accent-amber)]">
              {pausedEvents.length} {t("assistant.eventsPending")}
            </span>
          </div>

          <div className="h-4 w-px bg-[var(--border)]" />

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => resumeWithMode("immediate")}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors hover:bg-[var(--card-hover)]"
              title={t("assistant.applyAllImmediately")}
            >
              <SkipForward className="size-3.5" />
              {t("assistant.applyAll")}
            </button>

            <button
              type="button"
              onClick={() => resumeWithMode("sequential")}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors hover:bg-[var(--card-hover)]"
              title={t("assistant.playOneByOne")}
            >
              <Play className="size-3.5" />
              {t("assistant.playSequential")}
            </button>

            <button
              type="button"
              onClick={() => resumeWithMode("discard")}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium text-[var(--destructive)] transition-colors hover:bg-[var(--accent-red-bg)]"
              title={t("assistant.discardAndContinue")}
            >
              <Trash2 className="size-3.5" />
              {t("assistant.discard")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
