import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function toText(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

export function roleLabel(role: string): string {
  const labels: Record<string, string> = {
    advocate: "支持方",
    challenger: "反对方",
    arbitrator: "裁决方",
    strategist: "支持方",
    risk_analyst: "反对方",
    opportunist: "裁决方",
  };
  return labels[role] || role;
}
