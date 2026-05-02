"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { defaultLocale, isLocale, type Locale, translations, type TranslationKey } from "@/i18n";

const STORAGE_KEY = "mingjian_lang";

type LanguageContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLocale: () => void;
  t: (key: TranslationKey) => string;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

function getByPath(source: unknown, path: string): string | undefined {
  const value = path.split(".").reduce<unknown>((current, segment) => {
    if (current && typeof current === "object" && segment in current) {
      return (current as Record<string, unknown>)[segment];
    }
    return undefined;
  }, source);

  return typeof value === "string" ? value : undefined;
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(defaultLocale);

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (isLocale(saved)) {
      setLocaleState(saved);
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
    window.localStorage.setItem(STORAGE_KEY, locale);
  }, [locale]);

  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(nextLocale);
  }, []);

  const toggleLocale = useCallback(() => {
    setLocaleState((current) => (current === "zh" ? "en" : "zh"));
  }, []);

  const t = useCallback(
    (key: TranslationKey) => {
      return getByPath(translations[locale], key) ?? getByPath(translations.en, key) ?? key;
    },
    [locale],
  );

  const value = useMemo(
    () => ({ locale, setLocale, toggleLocale, t }),
    [locale, setLocale, toggleLocale, t],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useTranslation() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useTranslation must be used within LanguageProvider");
  }
  return context;
}
