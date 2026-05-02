import en from "./en";
import zh from "./zh";

export const locales = ["zh", "en"] as const;
export type Locale = (typeof locales)[number];

// Recursively replace all leaf values with `string`
type DeepString<T> = T extends string
  ? string
  : T extends object
    ? { [K in keyof T]: DeepString<T[K]> }
    : string;

export type Translations = DeepString<typeof en>;
export type TranslationKey = string;

export const localeLabels: Record<Locale, string> = {
  zh: "中",
  en: "EN",
};

export const translations: Record<Locale, Translations> = {
  en: en as unknown as Translations,
  zh: zh as unknown as Translations,
};

export const defaultLocale: Locale = "zh";

export function isLocale(value: string | null | undefined): value is Locale {
  return locales.includes(value as Locale);
}
