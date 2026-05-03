"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import WelcomeGuide from "@/components/WelcomeGuide";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import ThemeToggle from "@/components/ThemeToggle";
import { useTranslation } from "@/contexts/LanguageContext";
import {
  LayoutDashboard,
  Brain,
  Clock,
  MessageSquare,
  Search,
  TrendingUp,
  Shield,
  Building2,
  Menu,
  X,
  Bell,
} from "lucide-react";

const NAV_ITEMS = [
  {
    labelKey: "nav.dashboard",
    href: "/",
    icon: <LayoutDashboard size={18} />,
  },
  {
    labelKey: "nav.assistant",
    href: "/assistant",
    icon: <Brain size={18} />,
  },
  {
    labelKey: "nav.simulation",
    href: "/simulation",
    icon: <Clock size={18} />,
  },
  {
    labelKey: "nav.debate",
    href: "/debate",
    icon: <MessageSquare size={18} />,
  },
  {
    labelKey: "nav.evidence",
    href: "/evidence",
    icon: <Search size={18} />,
  },
  {
    labelKey: "nav.predictions",
    href: "/predictions",
    icon: <TrendingUp size={18} />,
  },
  {
    labelKey: "nav.monitoring",
    href: "/monitoring",
    icon: <Shield size={18} />,
  },
  {
    labelKey: "nav.providers",
    href: "/providers",
    icon: <Building2 size={18} />,
  },
];

function HamburgerIcon({ open }: { open: boolean }) {
  return open ? <X size={20} /> : <Menu size={20} />;
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
            <ThemeToggle />
            <WelcomeGuide />
            <button className="btn btn-ghost btn-sm magnetic-hover hidden sm:flex" aria-label="Notifications">
              <Bell size={16} />
            </button>
          </div>
        </header>

        <div className="p-4 md:p-6 animate-fadeIn">{children}</div>
      </main>
    </div>
  );
}
