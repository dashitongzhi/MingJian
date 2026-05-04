"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Toaster } from "sonner";
import WelcomeGuide from "@/components/WelcomeGuide";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import ThemeToggle from "@/components/ThemeToggle";
import CommandPalette from "@/components/CommandPalette";
import { useTranslation } from "@/contexts/LanguageContext";
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
  Menu,
  X,
  Bell,
  PanelLeftClose,
  PanelLeftOpen,
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
    labelKey: "nav.workbench",
    href: "/workbench",
    icon: <ClipboardCheck size={16} />,
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

const SIDEBAR_WIDTH = 240;
const SIDEBAR_COLLAPSED_WIDTH = 56;
const COLLAPSE_KEY = "planagent_sidebar_collapsed";

function HamburgerIcon({ open }: { open: boolean }) {
  return open ? <X size={20} /> : <Menu size={20} />;
}

function SidebarContent({
  onNavClick,
  collapsed,
}: {
  onNavClick?: () => void;
  collapsed?: boolean;
}) {
  const { t } = useTranslation();
  const pathname = usePathname() || "/";

  return (
    <>
      {/* Brand */}
      <div className="h-[var(--header-height)] flex items-center px-5">
        <Link href="/" className="flex items-center gap-2.5 group" onClick={onNavClick}>
          <Image
            src="/mingjian-icon.jpg"
            alt="明鉴"
            width={24}
            height={24}
            className="rounded-md object-cover shrink-0"
            priority
          />
          {!collapsed && (
            <span className="text-[13px] font-semibold tracking-[-0.01em] text-[var(--foreground)]">
              明鉴
            </span>
          )}
        </Link>
      </div>

      <div className="mx-4 h-px bg-[var(--sidebar-border)]" />

      {/* Navigation */}
      <nav className={`flex-1 py-2 space-y-0.5 ${collapsed ? "px-2" : "px-3"}`}>
        {NAV_ITEMS.map((item) => {
          const isActive = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavClick}
              title={collapsed ? t(item.labelKey) : undefined}
              className={`
                relative flex items-center text-[13px] font-medium
                transition-colors duration-150 group
                ${collapsed
                  ? "min-h-[32px] justify-center rounded-md mx-1 px-0"
                  : "min-h-[32px] gap-2 border-l px-2.5"
                }
                ${isActive
                  ? collapsed
                    ? "bg-[var(--sidebar-accent)] text-[var(--accent)]"
                    : "border-l-[var(--accent)] bg-[var(--sidebar-accent)] text-[var(--foreground)]"
                  : collapsed
                    ? "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--sidebar-accent)]/50"
                    : "border-l-transparent text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                }
              `}
            >
              <span className={isActive ? "text-[var(--accent)]" : "opacity-70 group-hover:opacity-100 transition-opacity"}>
                {item.icon}
              </span>
              {!collapsed && <span>{t(item.labelKey)}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Section divider */}
      <div className="divider-line mx-4" />

      {/* User section */}
      <div className={collapsed ? "p-3" : "p-4"}>
        <div className={`flex items-center ${collapsed ? "justify-center" : "gap-3 px-3 py-2"}`}>
          <div className="w-7 h-7 rounded-full border border-[var(--card-border)] bg-[var(--accent)]/10 flex items-center justify-center text-[var(--accent)] text-[11px] font-semibold shrink-0">
            U
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <div className="text-[13px] font-medium truncate">{t("layout.user")}</div>
              <div className="text-[11px] text-[var(--muted)] truncate">user@mingjian.ai</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const { resolvedTheme } = useTheme();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname() || "/";

  // Load collapsed state from localStorage
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = localStorage.getItem(COLLAPSE_KEY);
    if (stored === "true") setCollapsed(true);
  }, []);

  // Persist collapsed state
  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(COLLAPSE_KEY, String(next));
      return next;
    });
  }, []);

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

  const sidebarWidth = collapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH;

  return (
    <div className="flex min-h-screen">
      {/* ── Desktop Sidebar ──────────────────────────────────────────────── */}
      <aside
        className="hidden md:flex flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar)] transition-[width] duration-200 ease-out"
        style={{ width: sidebarWidth }}
      >
        <SidebarContent collapsed={collapsed} />

        {/* Collapse toggle */}
        <div className="border-t border-[var(--sidebar-border)] p-2">
          <button
            onClick={toggleCollapsed}
            className="flex w-full items-center justify-center h-8 rounded-md text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)] hover:bg-[var(--sidebar-accent)]/50"
            aria-label={collapsed ? t("layout.expandSidebar") : t("layout.collapseSidebar")}
            title={collapsed ? t("layout.expandSidebar") : t("layout.collapseSidebar")}
          >
            {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        </div>
      </aside>

      {/* ── Mobile Drawer Overlay ────────────────────────────────────────── */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-[var(--overlay)] md:hidden animate-fadeIn"
          onClick={closeDrawer}
          aria-hidden="true"
        />
      )}

      {/* ── Mobile Drawer ────────────────────────────────────────────────── */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 w-[280px] bg-[var(--sidebar)]
          border-r border-[var(--sidebar-border)] flex flex-col
          transition-transform duration-300 ease-out md:hidden
          ${drawerOpen ? "translate-x-0" : "-translate-x-full"}
        `}
      >
        <SidebarContent onNavClick={closeDrawer} />
      </aside>

      {/* ── Main Content Area ─────────────────────────────────────────────── */}
      <main className="flex-1 overflow-auto min-w-0">
        {/* Header */}
        <header className="h-[var(--header-height)] sticky top-0 z-10 flex items-center justify-between border-b border-[var(--card-border)] bg-[var(--background)]/80 px-4 md:px-6">
          <div className="flex items-center gap-3">
            {/* Mobile hamburger */}
            <button
              className="md:hidden flex h-9 w-9 items-center justify-center rounded-md text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
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
            <button className="btn btn-ghost btn-sm hidden sm:flex" aria-label="Notifications">
              <Bell size={16} />
            </button>
          </div>
        </header>

        <div className="p-5 md:p-7 animate-fadeIn">{children}</div>
      </main>

      {/* ── Global Command Palette (⌘K) ──────────────────────────────── */}
      <CommandPalette />
      <Toaster position="top-right" richColors closeButton theme={resolvedTheme as "light" | "dark" | undefined} />
    </div>
  );
}
