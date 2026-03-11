"use client";

import { cn } from "@/lib/utils";

interface CardProps {
  title?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  action?: React.ReactNode;
}

export function Card({ title, icon, children, className, action }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-kos-border bg-kos-card p-4 shadow-lg",
        className
      )}
    >
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {icon && <span className="text-kos-accent">{icon}</span>}
            {title && (
              <h3 className="text-sm font-semibold uppercase tracking-wider text-kos-muted">
                {title}
              </h3>
            )}
          </div>
          {action}
        </div>
      )}
      {children}
    </div>
  );
}
