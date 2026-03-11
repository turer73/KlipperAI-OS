"use client";

import { cn, tempColor } from "@/lib/utils";

interface TempGaugeProps {
  label: string;
  current: number;
  target: number;
  icon?: React.ReactNode;
}

export function TempGauge({ label, current, target, icon }: TempGaugeProps) {
  const pct = target > 0 ? Math.min((current / target) * 100, 100) : 0;
  const color = tempColor(current, target);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-1.5 text-kos-muted">
          {icon}
          {label}
        </span>
        <span className={cn("font-mono font-bold", color)}>
          {current.toFixed(1)}°C
          {target > 0 && (
            <span className="ml-1 text-xs text-kos-muted">/ {target}°C</span>
          )}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-700/50">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            target > 0
              ? pct >= 95
                ? "bg-kos-success"
                : pct >= 60
                ? "bg-amber-400"
                : "bg-blue-400"
              : "bg-slate-600"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
