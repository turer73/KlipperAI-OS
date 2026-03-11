// ═══════════════════════════════════════════════
// KlipperOS-AI Dashboard — Utility Functions
// ═══════════════════════════════════════════════

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Tailwind class merger — shadcn pattern */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Saniyeyi insanca okuna bilir formata cevir */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}m ${s}s`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

/** Byte'lari insanca formata cevir */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Sicaklik rengi (mavi → kirmizi gradyan) */
export function tempColor(current: number, target: number): string {
  if (target === 0) return "text-kos-muted";
  const ratio = Math.min(current / target, 1.2);
  if (ratio < 0.5) return "text-blue-400";
  if (ratio < 0.9) return "text-amber-400";
  if (ratio <= 1.05) return "text-kos-success";
  return "text-kos-danger"; // aşırı ısınma
}

/** Yazici durumu → renk */
export function stateColor(state: string): string {
  switch (state?.toLowerCase()) {
    case "printing":
      return "text-kos-success";
    case "paused":
      return "text-kos-warning";
    case "error":
    case "shutdown":
      return "text-kos-danger";
    case "complete":
      return "text-kos-accent";
    default:
      return "text-kos-muted";
  }
}

/** Yuzde → progress bar rengi */
export function progressColor(pct: number): string {
  if (pct < 30) return "bg-kos-accent";
  if (pct < 70) return "bg-blue-400";
  if (pct < 95) return "bg-kos-success";
  return "bg-emerald-400";
}
