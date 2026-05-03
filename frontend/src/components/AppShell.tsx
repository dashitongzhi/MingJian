"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import WelcomeGuide from "@/components/WelcomeGuide";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import ThemeToggle from "@/components/ThemeToggle";
import CommandPalette from "@/components/CommandPalette";
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
    icon: <LayoutDashboard size={16} />,
  },
  {
    labelKey: "nav.assistant",
    href: "/assistant",
    icon: <Brain size={16} />,
  },
  {
    labelKey: "nav.simulation",
    href: "/simulation",
    icon: <Clock size={16} />,
  },
  {
    labelKey: "nav.debate",
    href: "/debate",
    icon: <MessageSquare size={16} />,
  },
  {
    labelKey: "nav.evidence",
    href: "/evidence",
    icon: <Search size={16} />,
  },
  {
    labelKey: "nav.predictions",
    href: "/predictions",
    icon: <TrendingUp size={16} />,
  },
  {
    labelKey: "nav.monitoring",
    href: "/monitoring",
    icon: <Shield size={16} />,
  },
  {
    labelKey: "nav.providers",
    href: "/providers",
    icon: <Building2 size={16} />,
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
      {/* Brand — minimal */}
      <div className="h-[var(--header-height)] flex items-center px-5">
        <Link href="/" className="flex items-center gap-2.5 group" onClick={onNavClick}>
          <Image
            src="/mingjian-icon.jpg"
            alt="明鉴"
            width={24}
            height={24}
            className="rounded-md object-cover"
            priority
          />
          <span className="text-[13px] font-semibold tracking-wide text-[var(--foreground)]">
            明鉴
          </span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-2 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const isActive = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavClick}
              className={`
                relative flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] font-medium
                transition-colors duration-150 min-h-[36px] group
                ${isActive
                  ? "text-[var(--foreground)]"
                  : "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)]"
                }
              `}
            >
              {/* Animated active indicator via Framer Motion layoutId */}
              {isActive && (
                <motion.div
                  layoutId="nav-active-indicator"
                  className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-full bg-[var(--accent)]"
                  transition={{ type: "spring", stiffness: 380, damping: 30 }}
                />
              )}
              <span className={isActive ? "text-[var(--accent)]" : "opacity-70 group-hover:opacity-100 transition-opacity"}>
                {item.icon}
              </span>
              <span>{t(item.labelKey)}</span>
            </Link>
          );
        })}
      </nav>

      {/* Gradient divider */}
      <div className="mx-4 h-px bg-gradient-to-r from-transparent via-[var(--card-border)] to-transparent" />

      {/* User section */}
      <div className="p-4">
        <div className="flex items-center gap-3 px-3 py-2">
          <div className="w-7 h-7 rounded-full border border-[var(--card-border)] bg-[var(--accent)]/10 flex items-center justify-center text-[var(--accent)] text-[11px] font-semibold">
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
      <aside className="hidden md:flex w-[var(--sidebar-width)] backdrop-blur-md bg-[var(--sidebar)]/80 flex-col border-r border-[var(--card-border)]/50">
        <SidebarContent />
      </aside>

      {/* ── Mobile Drawer Overlay ─────────────────────────────────────────── */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-[var(--overlay)] backdrop-blur-sm md:hidden animate-fadeIn"
          onClick={closeDrawer}
          aria-hidden="true"
        />
      )}

      {/* ── Mobile Drawer ─────────────────────────────────────────────────── */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 w-[280px] backdrop-blur-xl bg-[var(--sidebar)]/90
          border-r border-[var(--card-border)]/50 flex flex-col
          transition-transform duration-300 ease-out md:hidden
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

      {/* ── Global Command Palette (⌘K) ──────────────────────────────── */}
      <CommandPalette />
    </div>
  );
}
