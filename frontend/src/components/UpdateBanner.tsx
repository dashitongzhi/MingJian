"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Info, CheckCircle, X, ExternalLink } from "lucide-react";

export interface UpdateBannerProps {
  type: string;
  title: string;
  body: string;
  sessionId?: string;
  severity: "high" | "medium" | "low";
  actionUrl?: string;
  onDismiss: () => void;
  onAction?: () => void;
}

const severityConfig = {
  high: {
    bg: "bg-red-500/10 border-red-500/30",
    text: "text-red-400",
    icon: AlertTriangle,
    autoDismiss: false,
    pulse: true,
  },
  medium: {
    bg: "bg-yellow-500/10 border-yellow-500/30",
    text: "text-yellow-400",
    icon: Info,
    autoDismiss: true,
    dismissDelay: 5000,
    pulse: false,
  },
  low: {
    bg: "bg-green-500/10 border-green-500/30",
    text: "text-green-400",
    icon: CheckCircle,
    autoDismiss: true,
    dismissDelay: 3000,
    pulse: false,
  },
};

export default function UpdateBanner({
  type,
  title,
  body,
  severity,
  actionUrl,
  onDismiss,
  onAction,
}: UpdateBannerProps) {
  const [visible, setVisible] = useState(true);
  const [fading, setFading] = useState(false);
  const config = severityConfig[severity];
  const Icon = config.icon;

  useEffect(() => {
    if (config.autoDismiss && "dismissDelay" in config) {
      const fadeTimer = setTimeout(() => setFading(true), (config.dismissDelay as number) - 500);
      const hideTimer = setTimeout(() => {
        setVisible(false);
        onDismiss();
      }, config.dismissDelay as number);
      return () => {
        clearTimeout(fadeTimer);
        clearTimeout(hideTimer);
      };
    }
  }, [config, onDismiss]);

  const handleAction = () => {
    if (onAction) onAction();
    else if (actionUrl) window.location.href = actionUrl;
    setVisible(false);
    onDismiss();
  };

  if (!visible) return null;

  return (
    <div
      className={`fixed top-0 left-0 right-0 z-50 transition-opacity duration-500 ${fading ? "opacity-0" : "opacity-100"}`}
    >
      <div
        className={`flex items-center gap-3 px-4 py-3 border-b backdrop-blur-md ${config.bg} ${config.pulse ? "animate-pulse" : ""}`}
      >
        <Icon size={18} className={config.text} />
        <div className="flex-1 min-w-0">
          <span className={`font-medium text-sm ${config.text}`}>{title}</span>
          {body && <span className="ml-2 text-xs text-[var(--text-secondary)] truncate">{body}</span>}
        </div>
        {actionUrl && (
          <button
            onClick={handleAction}
            className={`flex items-center gap-1 px-3 py-1 rounded text-xs font-medium ${config.text} bg-white/5 hover:bg-white/10 transition-colors`}
          >
            <ExternalLink size={12} />
            {type === "debate" ? "查看辩论" : type === "prediction" ? "查看预测" : "查看详情"}
          </button>
        )}
        <button
          onClick={() => {
            setVisible(false);
            onDismiss();
          }}
          className="p-1 rounded hover:bg-white/10 text-[var(--text-secondary)] transition-colors"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
