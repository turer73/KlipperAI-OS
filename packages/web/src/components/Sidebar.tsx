"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: "📊" },
  { href: "/control", label: "Kontrol", icon: "🎮" },
  { href: "/bambu", label: "Bambu Lab", icon: "🖨️" },
  { href: "/calibration", label: "Kalibrasyon", icon: "🔧" },
  { href: "/system", label: "Sistem", icon: "💻" },
  { href: "/settings", label: "Ayarlar", icon: "⚙️" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-56 flex-col border-r border-kos-border bg-kos-card">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2 border-b border-kos-border px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-kos-accent text-sm font-bold text-white">
          K
        </div>
        <div>
          <div className="text-sm font-bold text-kos-text">KlipperOS</div>
          <div className="text-[10px] text-kos-accent">AI Dashboard</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-3">
        {NAV_ITEMS.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                active
                  ? "bg-kos-accent/10 text-kos-accent"
                  : "text-kos-muted hover:bg-slate-800 hover:text-kos-text"
              )}
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-kos-border p-3 text-center text-[10px] text-kos-muted">
        KlipperOS-AI v3.0.0
      </div>
    </aside>
  );
}
