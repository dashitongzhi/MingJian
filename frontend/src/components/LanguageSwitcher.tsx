"use client";

import { useTranslation } from "@/contexts/LanguageContext";

export default function LanguageSwitcher() {
  const { locale, toggleLocale, t } = useTranslation();
  const nextLabel = locale === "zh" ? t("language.switchToEnglish") : t("language.switchToChinese");

  return (
    <button
      type="button"
      onClick={toggleLocale}
      className="btn btn-ghost btn-sm h-9 px-3 text-xs font-semibold"
      aria-label={nextLabel}
      title={nextLabel}
    >
      <span aria-hidden="true">{locale === "zh" ? "🇨🇳" : "🇺🇸"}</span>
      <span>{locale === "zh" ? "中" : "EN"}</span>
    </button>
  );
}
