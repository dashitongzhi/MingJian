"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

type ViewMode = "default" | "compact";
const STORAGE_KEY = "mingjian_view_mode";

type ViewModeContextValue = {
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
  toggleViewMode: () => void;
  isCompact: boolean;
};

const ViewModeContext = createContext<ViewModeContextValue | null>(null);

export function ViewModeProvider({ children }: { children: React.ReactNode }) {
  const [viewMode, setViewModeState] = useState<ViewMode>("default");

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "compact" || saved === "default") {
      setViewModeState(saved);
    }
  }, []);

  const setViewMode = useCallback((mode: ViewMode) => {
    setViewModeState(mode);
    window.localStorage.setItem(STORAGE_KEY, mode);
  }, []);

  const toggleViewMode = useCallback(() => {
    setViewModeState((current) => {
      const next = current === "default" ? "compact" : "default";
      window.localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({
      viewMode,
      setViewMode,
      toggleViewMode,
      isCompact: viewMode === "compact",
    }),
    [viewMode, setViewMode, toggleViewMode]
  );

  return <ViewModeContext.Provider value={value}>{children}</ViewModeContext.Provider>;
}

export function useViewMode() {
  const context = useContext(ViewModeContext);
  if (!context) {
    throw new Error("useViewMode must be used within ViewModeProvider");
  }
  return context;
}
