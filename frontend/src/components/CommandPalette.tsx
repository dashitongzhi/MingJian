"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useTranslation } from "@/contexts/LanguageContext";
import {
  CommandDialog,
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandShortcut,
  CommandSeparator,
} from "@/components/ui/command";
import {
  LayoutDashboard,
  Brain,
  ClipboardCheck,
  Clock,
  MessageSquare,
  Search,
  TrendingUp,
  Shield,
  Building2,
  Sun,
  Moon,
  Monitor,
  Languages,
  type LucideIcon,
} from "lucide-react";

const RECENT_KEY = "mingjian_recent_pages";
const MAX_RECENT = 3;

/** All navigable routes with their icon, i18n key, and shortcut. */
const NAV_ITEMS: {
  href: string;
  labelKey: string;
  icon: LucideIcon;
  shortcut: string;
}[] = [
  { href: "/", labelKey: "nav.dashboard", icon: LayoutDashboard, shortcut: "G D" },
  { href: "/assistant", labelKey: "nav.assistant", icon: Brain, shortcut: "G A" },
  { href: "/workbench", labelKey: "nav.workbench", icon: ClipboardCheck, shortcut: "G W" },
  { href: "/simulation", labelKey: "nav.simulation", icon: Clock, shortcut: "G S" },
  { href: "/debate", labelKey: "nav.debate", icon: MessageSquare, shortcut: "G B" },
  { href: "/evidence", labelKey: "nav.evidence", icon: Search, shortcut: "G E" },
  { href: "/predictions", labelKey: "nav.predictions", icon: TrendingUp, shortcut: "G P" },
  { href: "/monitoring", labelKey: "nav.monitoring", icon: Shield, shortcut: "G M" },
  { href: "/providers", labelKey: "nav.providers", icon: Building2, shortcut: "G C" },
];

/** Read recent pages from localStorage (client-only). */
function getRecentPages(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/** Push a path into the recent-pages list in localStorage. */
function pushRecentPage(path: string) {
  if (typeof window === "undefined") return;
  try {
    const pages = getRecentPages().filter((p) => p !== path);
    pages.unshift(path);
    localStorage.setItem(RECENT_KEY, JSON.stringify(pages.slice(0, MAX_RECENT)));
  } catch {
    // ignore
  }
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const pathname = usePathname() || "/";
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();
  const { locale, toggleLocale } = useTranslation();
  const [recentPages, setRecentPages] = useState<string[]>([]);

  // Track visited pages
  useEffect(() => {
    pushRecentPage(pathname);
    setRecentPages(getRecentPages());
  }, [pathname]);

  // Global ⌘K / Ctrl+K shortcut
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const navigate = useCallback(
    (href: string) => {
      setOpen(false);
      router.push(href);
    },
    [router],
  );

  const cycleTheme = useCallback(() => {
    if (theme === "dark") setTheme("light");
    else if (theme === "light") setTheme("system");
    else setTheme("dark");
    setOpen(false);
  }, [theme, setTheme]);

  const switchLanguage = useCallback(() => {
    toggleLocale();
    setOpen(false);
  }, [toggleLocale]);

  const getThemeIcon = () => {
    if (theme === "dark") return Moon;
    if (theme === "light") return Sun;
    return Monitor;
  };
  const ThemeIcon = getThemeIcon();

  const recentNavItems = recentPages
    .map((href) => NAV_ITEMS.find((item) => item.href === href))
    .filter(Boolean) as (typeof NAV_ITEMS)[number][];

  return (
    <CommandDialog
      open={open}
      onOpenChange={setOpen}
      title={t("commandPalette.title")}
      description={t("commandPalette.description")}
    >
      <Command>
        <CommandInput placeholder={t("commandPalette.placeholder")} />
        <CommandList>
          <CommandEmpty>{t("commandPalette.empty")}</CommandEmpty>

          {/* Recent pages */}
          {recentNavItems.length > 0 && (
            <>
              <CommandGroup heading={t("commandPalette.recent")}>
                {recentNavItems.map((item) => {
                  const Icon = item.icon;
                  return (
                    <CommandItem
                      key={`recent-${item.href}`}
                      onSelect={() => navigate(item.href)}
                      value={t(item.labelKey)}
                    >
                      <Icon className="size-4" />
                      <span>{t(item.labelKey)}</span>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
              <CommandSeparator />
            </>
          )}

          {/* Navigation */}
          <CommandGroup heading={t("commandPalette.navigation")}>
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              return (
                <CommandItem
                  key={item.href}
                  onSelect={() => navigate(item.href)}
                  value={t(item.labelKey)}
                >
                  <Icon className="size-4" />
                  <span>{t(item.labelKey)}</span>
                  <CommandShortcut>{item.shortcut}</CommandShortcut>
                </CommandItem>
              );
            })}
          </CommandGroup>

          <CommandSeparator />

          {/* Actions */}
          <CommandGroup heading={t("commandPalette.actions")}>
            <CommandItem
              onSelect={cycleTheme}
              value={t("commandPalette.toggleTheme")}
            >
              <ThemeIcon className="size-4" />
              <span>{t("commandPalette.toggleTheme")}</span>
              <CommandShortcut>
                {theme === "dark"
                  ? t("commandPalette.currentDark")
                  : theme === "light"
                    ? t("commandPalette.currentLight")
                    : t("commandPalette.currentSystem")}
              </CommandShortcut>
            </CommandItem>
            <CommandItem
              onSelect={switchLanguage}
              value={t("commandPalette.switchLanguage")}
            >
              <Languages className="size-4" />
              <span>{t("commandPalette.switchLanguage")}</span>
              <CommandShortcut>{locale === "zh" ? "中 → EN" : "EN → 中"}</CommandShortcut>
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
