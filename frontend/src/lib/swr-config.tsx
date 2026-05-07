"use client";

import { SWRConfig } from "swr";
import type { ReactNode } from "react";

/**
 * Centralized SWR configuration for the MingJian platform.
 *
 * Benefits:
 * - Prevents duplicate requests (dedupingInterval)
 * - Reduces unnecessary refetches (focusThrottleInterval)
 * - Keeps data fresh without polling too aggressively (refreshInterval)
 * - Automatic retry on error with exponential backoff
 * - Global error handler
 */

const SWR_GLOBAL_CONFIG = {
  // Dedupe identical requests within 2 seconds
  dedupingInterval: 2000,

  // Throttle revalidation on window focus to every 30 seconds
  focusThrottleInterval: 30_000,

  // Don't revalidate when reconnecting too aggressively
  revalidateOnReconnect: true,

  // Retry failed requests up to 3 times with backoff
  shouldRetryOnError: true,
  errorRetryCount: 3,
  errorRetryInterval: 5000,

  // Keep previous data while revalidating (smooth transitions)
  keepPreviousData: true,

  // Global error handler
  onError: (error: Error, key: string) => {
    if (process.env.NODE_ENV === "development") {
      console.warn(`[SWR] ${key}:`, error.message);
    }
  },
};

export function SWRProvider({ children }: { children: ReactNode }) {
  return <SWRConfig value={SWR_GLOBAL_CONFIG}>{children}</SWRConfig>;
}

/**
 * Preset refresh intervals for different data types.
 * Use these to keep SWR calls consistent across pages.
 */
export const REFRESH_INTERVALS = {
  /** Real-time data: queue health, streaming status */
  realtime: 10_000,
  /** Active data: sessions, debates */
  active: 30_000,
  /** Moderate data: scoreboard, predictions */
  moderate: 60_000,
  /** Slow data: agents, sources, configuration */
  slow: 300_000,
} as const;
