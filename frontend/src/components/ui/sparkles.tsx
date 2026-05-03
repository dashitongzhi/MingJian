"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";

interface Sparkle {
  id: string;
  x: string;
  y: string;
  color: string;
  delay: number;
  scale: number;
  duration: number;
}

function generateSparkle(): Sparkle {
  return {
    id: Math.random().toString(36).slice(2),
    x: `${Math.random() * 100}%`,
    y: `${Math.random() * 100}%`,
    color: ["#7f9f90", "#5a8a7a", "#a8d8c0", "#e8f5e9"][Math.floor(Math.random() * 4)],
    delay: Math.random() * 2,
    scale: Math.random() * 0.5 + 0.5,
    duration: Math.random() * 1.5 + 1,
  };
}

export function SparklesCore({
  background = "transparent",
  minSize = 0.4,
  maxSize = 1.2,
  particleDensity = 60,
  className = "",
}: {
  background?: string;
  minSize?: number;
  maxSize?: number;
  particleDensity?: number;
  className?: string;
}) {
  const [sparkles, setSparkles] = useState<Sparkle[]>([]);

  useEffect(() => {
    const initial = Array.from({ length: particleDensity }, () => ({
      ...generateSparkle(),
      scale: Math.random() * (maxSize - minSize) + minSize,
    }));
    setSparkles(initial);

    const interval = setInterval(() => {
      setSparkles((prev) => {
        const idx = Math.floor(Math.random() * prev.length);
        const next = [...prev];
        next[idx] = { ...generateSparkle(), scale: Math.random() * (maxSize - minSize) + minSize };
        return next;
      });
    }, 300);

    return () => clearInterval(interval);
  }, [particleDensity, minSize, maxSize]);

  return (
    <div className={`absolute inset-0 overflow-hidden ${className}`} style={{ background }}>
      {sparkles.map((s) => (
        <motion.div
          key={s.id}
          className="absolute rounded-full"
          style={{
            left: s.x,
            top: s.y,
            width: `${s.scale * 4}px`,
            height: `${s.scale * 4}px`,
            background: s.color,
          }}
          animate={{
            opacity: [0, 1, 0],
            scale: [0, 1, 0],
          }}
          transition={{
            duration: s.duration,
            delay: s.delay,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
}

export function SparklesText({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={`relative inline-block ${className}`}>
      <span className="relative z-10">{children}</span>
      <SparklesCore
        className="absolute inset-0 z-0"
        minSize={0.3}
        maxSize={0.8}
        particleDensity={20}
      />
    </span>
  );
}
