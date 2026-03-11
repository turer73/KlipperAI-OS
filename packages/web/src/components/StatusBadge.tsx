"use client";

import { cn } from "@/lib/utils";

const variants: Record<string, string> = {
  ok: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  warning: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  error: "bg-red-500/20 text-red-400 border-red-500/30",
  info: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  muted: "bg-slate-500/20 text-slate-400 border-slate-500/30",
};

interface StatusBadgeProps {
  variant?: keyof typeof variants;
  children: React.ReactNode;
  pulse?: boolean;
  className?: string;
}

export function StatusBadge({
  variant = "muted",
  children,
  pulse = false,
  className,
}: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        variants[variant] || variants.muted,
        className
      )}
    >
      {pulse && (
        <span className="relative flex h-2 w-2">
          <span
            className={cn(
              "absolute inline-flex h-full w-full animate-ping rounded-full opacity-75",
              variant === "ok"
                ? "bg-emerald-400"
                : variant === "error"
                ? "bg-red-400"
                : "bg-amber-400"
            )}
          />
          <span
            className={cn(
              "relative inline-flex h-2 w-2 rounded-full",
              variant === "ok"
                ? "bg-emerald-500"
                : variant === "error"
                ? "bg-red-500"
                : "bg-amber-500"
            )}
          />
        </span>
      )}
      {children}
    </span>
  );
}
