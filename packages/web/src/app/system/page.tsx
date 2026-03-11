"use client";

import { DashboardShell } from "../DashboardShell";
import { Card } from "@/components/Card";
import { StatusBadge } from "@/components/StatusBadge";
import { usePolling, useFetch } from "@/lib/hooks";
import { apiPost } from "@/lib/api";
import { formatDuration } from "@/lib/utils";
import type {
  SystemInfo,
  ServiceStatus,
  MaintenanceAlert,
  RecoveryStatus,
} from "@/lib/types";

function SystemContent() {
  const { data: system } = usePolling<SystemInfo>(
    "/api/v1/system/info",
    5000
  );
  const { data: services } = usePolling<ServiceStatus[]>(
    "/api/v1/system/services",
    10000
  );
  const { data: maintenance } = usePolling<{
    alerts: MaintenanceAlert[];
    count: number;
  }>("/api/v1/maintenance/alerts", 30000);
  const { data: recovery } = usePolling<RecoveryStatus>(
    "/api/v1/recovery/status",
    10000
  );

  const ramPct = system
    ? (system.ram_used_mb / system.ram_total_mb) * 100
    : 0;
  const diskPct = system
    ? (system.disk_used_gb / system.disk_total_gb) * 100
    : 0;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-kos-text">Sistem Yonetimi</h1>
        <p className="text-sm text-kos-muted">
          Kaynaklar, servisler, bakim ve kurtarma
        </p>
      </div>

      {/* Resource bars */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {[
          {
            label: "CPU",
            value: system?.cpu_percent ?? 0,
            detail: `${system?.cpu_percent?.toFixed(1) ?? 0}%`,
          },
          {
            label: "RAM",
            value: ramPct,
            detail: `${system?.ram_used_mb?.toFixed(0) ?? 0} / ${system?.ram_total_mb?.toFixed(0) ?? 0} MB`,
          },
          {
            label: "Disk",
            value: diskPct,
            detail: `${system?.disk_used_gb?.toFixed(1) ?? 0} / ${system?.disk_total_gb?.toFixed(0) ?? 0} GB`,
          },
        ].map((res) => (
          <Card key={res.label}>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-kos-text">
                  {res.label}
                </span>
                <span className="text-xs text-kos-muted">{res.detail}</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-700/50">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    res.value > 90
                      ? "bg-kos-danger"
                      : res.value > 70
                      ? "bg-kos-warning"
                      : "bg-kos-accent"
                  }`}
                  style={{ width: `${Math.min(res.value, 100)}%` }}
                />
              </div>
            </div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Services */}
        <Card title="Servis Durumu" icon="⚡">
          {services ? (
            <div className="space-y-2">
              {services.map((svc) => (
                <div
                  key={svc.name}
                  className="flex items-center justify-between rounded-lg bg-slate-800/30 px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <div
                      className={`h-2.5 w-2.5 rounded-full ${
                        svc.active ? "bg-kos-success" : "bg-kos-danger"
                      }`}
                    />
                    <span className="text-sm text-kos-text">{svc.name}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-kos-muted">
                      {svc.memory_mb.toFixed(0)} MB
                    </span>
                    <StatusBadge variant={svc.active ? "ok" : "error"}>
                      {svc.active ? "Aktif" : "Kapali"}
                    </StatusBadge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-kos-muted">
              Yukleniyor...
            </div>
          )}
        </Card>

        {/* Maintenance */}
        <Card title="Bakim Uyarilari" icon="🔔">
          {maintenance && maintenance.count > 0 ? (
            <div className="space-y-2">
              {maintenance.alerts.map((alert, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-kos-border bg-slate-800/30 p-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-kos-text">
                      {alert.component}
                    </span>
                    <StatusBadge
                      variant={
                        alert.severity === "critical"
                          ? "error"
                          : alert.severity === "warning"
                          ? "warning"
                          : "info"
                      }
                    >
                      {alert.severity}
                    </StatusBadge>
                  </div>
                  <p className="mt-1 text-xs text-kos-muted">
                    {alert.message}
                  </p>
                  <div className="mt-1 text-[10px] text-kos-muted">
                    {alert.hours_used.toFixed(0)}h / {alert.limit_hours}h
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-sm text-kos-success">
              ✓ Bakim uyarisi yok
            </div>
          )}
        </Card>

        {/* Recovery Engine */}
        <Card title="Kurtarma Motoru" icon="🛡️">
          {recovery ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-kos-muted">Durum</span>
                <StatusBadge variant={recovery.enabled ? "ok" : "muted"}>
                  {recovery.enabled ? "AKTIF" : "KAPALI"}
                </StatusBadge>
              </div>
              {recovery.active_recovery && (
                <div className="rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
                  Aktif kurtarma: {recovery.active_recovery}
                </div>
              )}
              <div className="space-y-1">
                {Object.entries(recovery.attempt_counts).map(([cat, count]) => (
                  <div
                    key={cat}
                    className="flex justify-between text-xs text-kos-muted"
                  >
                    <span>{cat}</span>
                    <span>{count} deneme</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex h-24 items-center justify-center text-kos-muted">
              Yukleniyor...
            </div>
          )}
        </Card>

        {/* System Info */}
        <Card title="Sistem Bilgisi" icon="ℹ️">
          {system ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-kos-muted">Uptime</span>
                <span className="text-kos-text">
                  {formatDuration(system.uptime_seconds)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-kos-muted">Toplam RAM</span>
                <span className="font-mono text-kos-text">
                  {(system.ram_total_mb / 1024).toFixed(1)} GB
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-kos-muted">Toplam Disk</span>
                <span className="font-mono text-kos-text">
                  {system.disk_total_gb.toFixed(0)} GB
                </span>
              </div>
            </div>
          ) : (
            <div className="flex h-24 items-center justify-center text-kos-muted">
              Yukleniyor...
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

export default function SystemPage() {
  return (
    <DashboardShell>
      <SystemContent />
    </DashboardShell>
  );
}
