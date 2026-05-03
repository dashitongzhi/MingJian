"use client";

import { useState, useCallback, useEffect } from "react";
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

function HamburgerIcon({ open }: { open: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {open ? (
        <>
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </>
      ) : (
        <>
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </>
      )}
    </svg>
  );
}

function SidebarContent({ onNavClick }: { onNavClick?: () => void }) {
  const { t } = useTranslation();
  const pathname = usePathname() || "/";

  return (
    <>
      {/* Brand */}
      <div className="h-[var(--header-height)] flex items-center px-5 border-b border-[var(--card-border)]">
        <Link href="/" className="flex items-center gap-3 group" onClick={onNavClick}>
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
              onClick={onNavClick}
              className={`
                relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-medium
                transition-all duration-200 magnetic-hover min-h-[44px]
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
    </>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const pathname = usePathname() || "/";

  // Close drawer on route change
  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  // Close drawer on ESC
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, []);

  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  return (
    <div className="flex min-h-screen">
      {/* ── Desktop Sidebar ───────────────────────────────────────────────── */}
      <aside className="hidden md:flex w-[var(--sidebar-width)] border-r border-[var(--card-border)] bg-[var(--card)] flex-col">
        <SidebarContent />
      </aside>

      {/* ── Mobile Drawer Overlay ─────────────────────────────────────────── */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden animate-fadeIn"
          onClick={closeDrawer}
          aria-hidden="true"
        />
      )}

      {/* ── Mobile Drawer ─────────────────────────────────────────────────── */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 w-[280px] bg-[var(--card)] border-r border-[var(--card-border)]
          flex flex-col transition-transform duration-300 ease-out md:hidden
          ${drawerOpen ? "translate-x-0" : "-translate-x-full"}
        `}
      >
        <SidebarContent onNavClick={closeDrawer} />
      </aside>

      {/* ── Main Content ───────────────────────────────────────────────────── */}
      <main className="flex-1 overflow-auto min-w-0">
        <header className="h-[var(--header-height)] border-b border-[var(--card-border)] glass sticky top-0 z-10 flex items-center justify-between px-4 md:px-6">
          <div className="flex items-center gap-3">
            {/* Mobile hamburger */}
            <button
              className="md:hidden flex items-center justify-center w-10 h-10 rounded-lg text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)] transition-colors"
              onClick={() => setDrawerOpen(!drawerOpen)}
              aria-label="Toggle menu"
            >
              <HamburgerIcon open={drawerOpen} />
            </button>
            <h1 className="text-[13px] font-medium text-[var(--muted-foreground)] tracking-wide">
              {t("layout.platform")}
            </h1>
          </div>
          <div className="flex items-center gap-2 md:gap-3">
            <div className="hidden sm:flex items-center gap-2">
              <span className="status-dot online" />
              <span className="text-[11px] text-[var(--muted)] font-medium">{t("layout.systemOnline")}</span>
            </div>
            <LanguageSwitcher />
            <WelcomeGuide />
            <button className="btn btn-ghost btn-sm magnetic-hover hidden sm:flex" aria-label="Notifications">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
            </button>
          </div>
        </header>

        <div className="p-4 md:p-6 animate-fadeIn">{children}</div>
      </main>
    </div>
  );
}
