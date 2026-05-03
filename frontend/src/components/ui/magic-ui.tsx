"use client";

import { cn } from "@/lib/utils";

interface ShimmerProps {
  className?: string;
  children?: React.ReactNode;
}

export function ShimmerButton({ className, children }: ShimmerProps) {
  return (
    <button
      className={cn(
        "group relative inline-flex items-center justify-center overflow-hidden rounded-lg px-4 py-2",
        "bg-[var(--accent)] text-[var(--accent-foreground)]",
        "transition-all duration-300 hover:scale-[1.02] hover:shadow-lg",
        className
      )}
    >
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-white/20 to-transparent" />
      <span className="relative z-10">{children}</span>
    </button>
  );
}

interface MarqueeProps {
  className?: string;
  children: React.ReactNode;
  speed?: "slow" | "normal" | "fast";
  direction?: "left" | "right";
}

export function Marquee({
  className,
  children,
  speed = "normal",
  direction = "left",
}: MarqueeProps) {
  const durationMap = { slow: "40s", normal: "25s", fast: "15s" };
  return (
    <div className={cn("relative overflow-hidden", className)}>
      <div
        className="flex gap-4 whitespace-nowrap"
        style={{
          animation: `marquee-${direction} ${durationMap[speed]} linear infinite`,
        }}
      >
        {children}
        {children}
      </div>
    </div>
  );
}

interface PulsatingDotProps {
  className?: string;
  color?: string;
}

export function PulsatingDot({ className, color = "var(--accent-green)" }: PulsatingDotProps) {
  return (
    <span className={cn("relative inline-flex h-2 w-2", className)}>
      <span
        className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75"
        style={{ backgroundColor: color }}
      />
      <span
        className="relative inline-flex h-2 w-2 rounded-full"
        style={{ backgroundColor: color }}
      />
    </span>
  );
}

interface GradientBorderProps {
  className?: string;
  children: React.ReactNode;
}

export function GradientBorder({ className, children }: GradientBorderProps) {
  return (
    <div className={cn("relative rounded-xl p-[1px]", className)}>
      <div className="absolute inset-0 rounded-xl bg-gradient-to-r from-[var(--accent)] via-[var(--accent-green)] to-[var(--accent)] opacity-30 blur-sm" />
      <div className="relative rounded-xl bg-[var(--card)]">{children}</div>
    </div>
  );
}

interface BlurInProps {
  className?: string;
  children: React.ReactNode;
  delay?: number;
}

export function BlurIn({ className, children, delay = 0 }: BlurInProps) {
  return (
    <div
      className={cn("animate-[blurIn_0.6s_ease-out_forwards] opacity-0", className)}
      style={{ animationDelay: `${delay}ms` }}
    >
      {children}
    </div>
  );
}
