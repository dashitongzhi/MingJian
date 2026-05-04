"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Toaster, toast } from "sonner";
import UpdateBanner, { type UpdateBannerProps } from "@/components/UpdateBanner";
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
const MAX_NOTIFICATIONS = 20;

type NotificationSeverity = "high" | "medium" | "low";

interface NotificationMessage {
  type: "notification";
  title: string;
  body: string;
  severity: NotificationSeverity;
  session_id: string;
}

interface NotificationItem extends NotificationMessage {
  id: string;
  receivedAt: string;
}

function notificationWebSocketUrl() {
  const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (configuredApiUrl && configuredApiUrl !== "/api") {
    const url = new URL(configuredApiUrl, window.location.origin);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = "/ws/notifications";
    url.search = "";
    return url.toString();
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws/notifications`;
}

function isNotificationMessage(value: unknown): value is NotificationMessage {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return (
    record.type === "notification" &&
    typeof record.title === "string" &&
    typeof record.body === "string" &&
    (record.severity === "high" || record.severity === "medium" || record.severity === "low")
  );
}

function formatNotificationTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

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
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [currentBanner, setCurrentBanner] = useState<Omit<UpdateBannerProps, "onDismiss"> | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const notificationPanelRef = useRef<HTMLDivElement | null>(null);
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
    setNotificationsOpen(false);
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

  const openNotificationSession = useCallback((sessionId: string) => {
    if (!sessionId) {
      router.push("/monitoring");
      return;
    }
    window.sessionStorage.setItem("planagent_notification_session_id", sessionId);
    window.dispatchEvent(new CustomEvent("planagent-open-session", { detail: sessionId }));
    router.push(`/assistant#session-${encodeURIComponent(sessionId)}`);
  }, [router]);

  const handleNotificationMessage = useCallback((message: NotificationMessage) => {
    const item: NotificationItem = {
      ...message,
      session_id: message.session_id || "",
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      receivedAt: new Date().toISOString(),
    };

    setNotifications((prev) => [item, ...prev].slice(0, MAX_NOTIFICATIONS));
    setUnreadCount((prev) => Math.min(prev + 1, 99));

    toast(message.title, {
      description: message.body,
      action: item.session_id
        ? {
            label: t("notifications.open"),
            onClick: () => openNotificationSession(item.session_id),
          }
        : undefined,
    });

    // Show UpdateBanner for high-severity notifications
    if (message.severity === "high") {
      setCurrentBanner({
        type: "notification",
        title: message.title,
        body: message.body || "",
        sessionId: item.session_id,
        severity: message.severity === "high" ? "high" : message.severity === "medium" ? "medium" : "low",
        actionUrl: item.session_id
          ? `/workbench?session=${item.session_id}`
          : undefined,
        onAction: item.session_id
          ? () => openNotificationSession(item.session_id)
          : undefined,
      });
    }
  }, [openNotificationSession, t]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(notificationWebSocketUrl());
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (isNotificationMessage(data)) {
            handleNotificationMessage(data);
          }
        } catch (error) {
          console.error(error);
        }
      };
      socket.onerror = () => {
        socket?.close();
      };
      socket.onclose = () => {
        if (!closed) {
          reconnectTimer = setTimeout(connect, 3_000);
        }
      };
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [handleNotificationMessage]);

  useEffect(() => {
    if (!notificationsOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!notificationPanelRef.current?.contains(event.target as Node)) {
        setNotificationsOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [notificationsOpen]);

  const toggleNotifications = useCallback(() => {
    setNotificationsOpen((prev) => {
      const next = !prev;
      if (next) setUnreadCount(0);
      return next;
    });
  }, []);

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
            <div ref={notificationPanelRef} className="relative hidden sm:block">
              <button
                className="btn btn-ghost btn-sm relative flex"
                aria-label={t("notifications.title")}
                aria-expanded={notificationsOpen}
                onClick={toggleNotifications}
              >
                <Bell size={16} />
                {unreadCount > 0 && (
                  <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-[var(--accent-red)] px-1 text-[10px] font-semibold leading-none text-white">
                    {unreadCount > 99 ? "99+" : unreadCount}
                  </span>
                )}
              </button>
              {notificationsOpen && (
                <div className="absolute right-0 top-[calc(100%+8px)] z-30 w-[340px] overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--card)] shadow-xl">
                  <div className="flex items-center justify-between divider-subtle px-4 py-3">
                    <div className="text-sm font-semibold">{t("notifications.title")}</div>
                    <span className="font-mono text-[11px] text-[var(--muted)]">{notifications.length}</span>
                  </div>
                  <div className="max-h-[360px] overflow-y-auto">
                    {notifications.length === 0 ? (
                      <div className="px-4 py-8 text-center text-sm text-[var(--muted)]">
                        {t("notifications.empty")}
                      </div>
                    ) : (
                      notifications.map((notification) => (
                        <button
                          key={notification.id}
                          type="button"
                          onClick={() => {
                            setNotificationsOpen(false);
                            setUnreadCount(0);
                            openNotificationSession(notification.session_id);
                          }}
                          className="grid w-full grid-cols-[8px_minmax(0,1fr)] gap-3 divider-subtle px-4 py-3 text-left outline-none transition-colors hover:bg-[var(--sidebar-accent)]/60 focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
                        >
                          <span
                            className={`mt-1.5 h-2 w-2 rounded-full ${
                              notification.severity === "high"
                                ? "bg-[var(--accent-red)]"
                                : notification.severity === "medium"
                                  ? "bg-[var(--accent-yellow)]"
                                  : "bg-[var(--accent-green)]"
                            }`}
                          />
                          <span className="min-w-0">
                            <span className="flex items-start justify-between gap-3">
                              <span className="truncate text-sm font-medium text-[var(--foreground)]">
                                {notification.title}
                              </span>
                              <span className="shrink-0 font-mono text-[10px] text-[var(--muted)]">
                                {formatNotificationTime(notification.receivedAt)}
                              </span>
                            </span>
                            <span className="mt-1 line-clamp-2 block text-xs leading-5 text-[var(--muted-foreground)]">
                              {notification.body}
                            </span>
                          </span>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </header>

        <div className="p-5 md:p-7 animate-fadeIn">{children}</div>
      </main>

      {/* ── Global Command Palette (⌘K) ──────────────────────────────── */}
      <CommandPalette />
      {currentBanner && (
        <UpdateBanner
          {...currentBanner}
          onDismiss={() => setCurrentBanner(null)}
        />
      )}
      <Toaster position="top-right" richColors closeButton theme={resolvedTheme as "light" | "dark" | undefined} />
    </div>
  );
}
