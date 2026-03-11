"use client";

import { DashboardShell } from "./DashboardShell";
import { Card } from "@/components/Card";
import { StatusBadge } from "@/components/StatusBadge";
import { TempGauge } from "@/components/TempGauge";
import { ProgressRing } from "@/components/ProgressRing";
import { usePolling } from "@/lib/hooks";
import { formatDuration, stateColor } from "@/lib/utils";
import type {
  PrintStatus,
  TemperatureReading,
  SystemInfo,
  FlowGuardStatus,
  ServiceStatus,
} from "@/lib/types";

function DashboardContent() {
  const { data: printer } = usePolling<PrintStatus>(
    "/api/v1/printer/status",
    2000
  );
  const { data: temps } = usePolling<TemperatureReading>(
    "/api/v1/printer/temperatures",
    2000
  );
  const { data: system } = usePolling<SystemInfo>(
    "/api/v1/system/info",
    5000
  );
  const { data: flowguard } = usePolling<FlowGuardStatus>(
    "/api/v1/flowguard/status",
    3000
  );
  const { data: services } = usePolling<ServiceStatus[]>(
    "/api/v1/system/services",
    10000
  );

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-kos-text">Dashboard</h1>
          <p className="text-sm text-kos-muted">
            3D Yazici Durum Paneli
          </p>
        </div>
        {printer && (
          <StatusBadge
            variant={
              printer.state === "printing"
                ? "ok"
                : printer.state === "paused"
                ? "warning"
                : printer.state === "error"
                ? "error"
                : "muted"
            }
            pulse={printer.state === "printing"}
          >
            {printer.state?.toUpperCase() || "BAGLANTI YOK"}
          </StatusBadge>
        )}
      </div>

      {/* Top row — Print Progress + Temperatures */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Print Progress */}
        <Card title="Baski Durumu" icon="🖨️" className="lg:col-span-1">
          {printer ? (
            <div className="flex flex-col items-center gap-3">
              <ProgressRing
                percent={printer.progress * 100}
                label={printer.filename || "Bos"}
              />
              <div className="w-full space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-kos-muted">Dosya</span>
                  <span className="max-w-[160px] truncate text-kos-text">
                    {printer.filename || "—"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-kos-muted">Sure</span>
                  <span className="font-mono text-kos-text">
                    {formatDuration(printer.print_duration)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-kos-muted">Katman</span>
                  <span className="font-mono text-kos-text">
                    {printer.current_layer ?? "—"} / {printer.total_layers ?? "—"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-kos-muted">Filament</span>
                  <span className="font-mono text-kos-text">
                    {(printer.filament_used / 1000).toFixed(1)}m
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex h-40 items-center justify-center text-kos-muted">
              Veri bekleniyor...
            </div>
          )}
        </Card>

        {/* Temperatures */}
        <Card title="Sicakliklar" icon="🌡️" className="lg:col-span-1">
          {temps ? (
            <div className="space-y-4">
              <TempGauge
                label="Nozul"
                current={temps.extruder_current}
                target={temps.extruder_target}
              />
              <TempGauge
                label="Tabla"
                current={temps.bed_current}
                target={temps.bed_target}
              />
              {temps.mcu_temperature !== null && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-kos-muted">MCU</span>
                  <span className="font-mono text-kos-text">
                    {temps.mcu_temperature.toFixed(1)}°C
                  </span>
                </div>
              )}
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-kos-muted">
              Veri bekleniyor...
            </div>
          )}
        </Card>

        {/* FlowGuard AI */}
        <Card title="FlowGuard AI" icon="🛡️" className="lg:col-span-1">
          {flowguard ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-kos-muted">Karar</span>
                <StatusBadge
                  variant={
                    flowguard.verdict === "OK"
                      ? "ok"
                      : flowguard.verdict === "NOTICE"
                      ? "warning"
                      : flowguard.verdict === "PAUSE"
                      ? "error"
                      : "muted"
                  }
                >
                  {flowguard.verdict}
                </StatusBadge>
              </div>
              <div className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-kos-muted">AI Sinifi</span>
                  <span className="text-kos-text">
                    {flowguard.ai_class || "—"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-kos-muted">Filament</span>
                  <StatusBadge
                    variant={flowguard.filament_detected ? "ok" : "error"}
                  >
                    {flowguard.filament_detected ? "OK" : "YOK"}
                  </StatusBadge>
                </div>
                <div className="flex justify-between">
                  <span className="text-kos-muted">Heater Duty</span>
                  <span className="font-mono text-kos-text">
                    {(flowguard.heater_duty * 100).toFixed(0)}%
                  </span>
                </div>
                {flowguard.tmc_sg_result !== null && (
                  <div className="flex justify-between">
                    <span className="text-kos-muted">TMC SG</span>
                    <span className="font-mono text-kos-text">
                      {flowguard.tmc_sg_result}
                    </span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-kos-muted">Z Yukseklik</span>
                  <span className="font-mono text-kos-text">
                    {flowguard.z_height?.toFixed(2) ?? "—"}mm
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-kos-muted">
              FlowGuard verisi yok
            </div>
          )}
        </Card>
      </div>

      {/* Bottom row — System + Services */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* System Resources */}
        <Card title="Sistem Kaynaklari" icon="💻">
          {system ? (
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center">
                <div className="text-2xl font-bold text-kos-accent">
                  {system.cpu_percent.toFixed(0)}%
                </div>
                <div className="text-xs text-kos-muted">CPU</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-kos-accent">
                  {((system.ram_used_mb / system.ram_total_mb) * 100).toFixed(0)}%
                </div>
                <div className="text-xs text-kos-muted">
                  RAM ({system.ram_used_mb.toFixed(0)}MB /{" "}
                  {system.ram_total_mb.toFixed(0)}MB)
                </div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-kos-accent">
                  {((system.disk_used_gb / system.disk_total_gb) * 100).toFixed(0)}%
                </div>
                <div className="text-xs text-kos-muted">
                  Disk ({system.disk_used_gb.toFixed(1)}GB /{" "}
                  {system.disk_total_gb.toFixed(0)}GB)
                </div>
              </div>
              <div className="col-span-3 text-center text-xs text-kos-muted">
                Uptime: {formatDuration(system.uptime_seconds)}
              </div>
            </div>
          ) : (
            <div className="flex h-24 items-center justify-center text-kos-muted">
              Yukleniyor...
            </div>
          )}
        </Card>

        {/* Services */}
        <Card title="Servisler" icon="⚡">
          {services ? (
            <div className="grid grid-cols-2 gap-2">
              {services.map((svc) => (
                <div
                  key={svc.name}
                  className="flex items-center justify-between rounded-lg bg-slate-800/50 px-3 py-2"
                >
                  <span className="text-xs text-kos-text">{svc.name}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-kos-muted">
                      {svc.memory_mb.toFixed(0)}MB
                    </span>
                    <div
                      className={`h-2 w-2 rounded-full ${
                        svc.active ? "bg-kos-success" : "bg-kos-danger"
                      }`}
                    />
                  </div>
                </div>
              ))}
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

export default function Home() {
  return (
    <DashboardShell>
      <DashboardContent />
    </DashboardShell>
  );
}
