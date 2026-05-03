"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import WelcomeGuide from "@/components/WelcomeGuide";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { useTranslation } from "@/contexts/LanguageContext";

const NAV_ITEMS = [
  {
    labelKey: "nav.dashboard",
    href: "/",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" rx="2" />
        <rect x="14" y="3" width="7" height="7" rx="2" />
        <rect x="3" y="14" width="7" height="7" rx="2" />
        <rect x="14" y="14" width="7" height="7" rx="2" />
      </svg>
    ),
  },
  {
    labelKey: "nav.assistant",
    href: "/assistant",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2L2 7l10 5 10-5-10-5z" />
        <path d="M2 17l10 5 10-5" />
        <path d="M2 12l10 5 10-5" />
      </svg>
    ),
  },
  {
    labelKey: "nav.simulation",
    href: "/simulation",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 6v6l4 2" />
      </svg>
    ),
  },
  {
    labelKey: "nav.debate",
    href: "/debate",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    labelKey: "nav.evidence",
    href: "/evidence",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.35-4.35" />
      </svg>
    ),
  },
  {
    labelKey: "nav.predictions",
    href: "/predictions",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3v18h18" />
        <path d="m19 9-5 5-4-4-3 3" />
      </svg>
    ),
  },
  {
    labelKey: "nav.monitoring",
    href: "/monitoring",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
      </svg>
    ),
  },
  {
    labelKey: "nav.providers",
    href: "/providers",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2L2 7l10 5 10-5-10-5z" />
        <path d="M2 17l10 5 10-5" />
        <path d="M2 12l10 5 10-5" />
      </svg>
    ),
  },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const pathname = usePathname() || "/";

  return (
    <div className="flex min-h-screen">
      {/* ── Sidebar ────────────────────────────────────────────────────────── */}
      <aside className="w-[var(--sidebar-width)] border-r border-[var(--card-border)] bg-[var(--card)] flex flex-col">
        {/* Brand */}
        <div className="h-[var(--header-height)] flex items-center px-5 border-b border-[var(--card-border)]">
          <Link href="/" className="flex items-center gap-3 group">
            <div className="relative">
              <Image
                src="/mingjian-icon.jpg"
                alt="明鉴"
                width={32}
                height={32}
                className="rounded-lg object-cover transition-transform duration-300 group-hover:scale-105"
                priority
              />
              <div className="absolute inset-0 rounded-lg bg-[var(--accent)]/10 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
            </div>
            <div>
              <span className="font-semibold text-sm tracking-wide gradient-text">明鉴</span>
              <div className="text-[10px] text-[var(--muted)] tracking-wider">MINGJIAN</div>
            </div>
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const isActive = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`
                  relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-medium
                  transition-all duration-200 magnetic-hover
                  ${isActive
                    ? "text-[var(--foreground)] bg-[var(--accent)]/8"
                    : "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)]"
                  }
                `}
              >
                {/* Active indicator bar */}
                {isActive && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-full bg-[var(--accent)]" />
                )}
                <span className={isActive ? "text-[var(--accent)]" : ""}>{item.icon}</span>
                <span>{t(item.labelKey)}</span>
              </Link>
            );
          })}
        </nav>

        {/* User */}
        <div className="p-4 border-t border-[var(--card-border)]">
          <div className="flex items-center gap-3 px-3 py-2">
            <div className="w-8 h-8 rounded-full border border-[var(--card-border)] bg-[var(--accent)]/10 flex items-center justify-center text-[var(--accent)] text-xs font-semibold">
              U
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[13px] font-medium truncate">{t("layout.user")}</div>
              <div className="text-[11px] text-[var(--muted)] truncate">user@mingjian.ai</div>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Main Content ───────────────────────────────────────────────────── */}
      <main className="flex-1 overflow-auto">
        <header className="h-[var(--header-height)] border-b border-[var(--card-border)] glass sticky top-0 z-10 flex items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <h1 className="text-[13px] font-medium text-[var(--muted-foreground)] tracking-wide">
              {t("layout.platform")}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="status-dot online" />
              <span className="text-[11px] text-[var(--muted)] font-medium">{t("layout.systemOnline")}</span>
            </div>
            <LanguageSwitcher />
            <WelcomeGuide />
            <button className="btn btn-ghost btn-sm magnetic-hover" aria-label="Notifications">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
            </button>
          </div>
        </header>

        <div className="p-6 animate-fadeIn">{children}</div>
      </main>
    </div>
  );
}
