"use client";

import { useState } from "react";
import { DashboardShell } from "../DashboardShell";
import { Card } from "@/components/Card";
import { StatusBadge } from "@/components/StatusBadge";
import { ProgressRing } from "@/components/ProgressRing";
import { usePolling } from "@/lib/hooks";
import { apiPost } from "@/lib/api";
import type { CalibrationStatus, CalibStartRequest } from "@/lib/types";

const STEP_LABELS: Record<string, string> = {
  pid_extruder: "PID Nozul",
  pid_bed: "PID Tabla",
  input_shaper: "Input Shaper",
  pressure_advance: "Pressure Advance",
  flow_rate: "Flow Rate",
  idle: "Beklemede",
};

function CalibrationContent() {
  const { data: status } = usePolling<CalibrationStatus>(
    "/api/v1/calibration/status",
    2000
  );

  const [config, setConfig] = useState<CalibStartRequest>({
    extruder_temp: 210,
    bed_temp: 60,
    skip_pid: false,
    skip_shaper: false,
    skip_pa: false,
    skip_flow: false,
  });
  const [feedback, setFeedback] = useState("");

  const startCalibration = async () => {
    try {
      setFeedback("Kalibrasyon baslatiliyor...");
      await apiPost("/api/v1/calibration/start", config);
      setFeedback("Kalibrasyon baslatildi ✓");
    } catch (e) {
      setFeedback(`Hata: ${e}`);
    }
  };

  const abortCalibration = async () => {
    try {
      await apiPost("/api/v1/calibration/abort");
      setFeedback("Kalibrasyon iptal edildi");
    } catch (e) {
      setFeedback(`Hata: ${e}`);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-kos-text">
          Otomatik Kalibrasyon
        </h1>
        <p className="text-sm text-kos-muted">
          PID → Input Shaper → Pressure Advance → Flow Rate
        </p>
      </div>

      {feedback && (
        <div className="rounded-lg border border-kos-border bg-kos-card px-4 py-2 text-sm text-kos-text">
          {feedback}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Calibration Status */}
        <Card title="Kalibrasyon Durumu" icon="🔧">
          {status ? (
            <div className="flex flex-col items-center gap-4">
              <ProgressRing
                percent={status.progress_percent}
                label={STEP_LABELS[status.current_step] || status.current_step}
              />

              <StatusBadge
                variant={status.running ? "ok" : "muted"}
                pulse={status.running}
              >
                {status.running ? "CALISIYOR" : "BEKLEMEDE"}
              </StatusBadge>

              {status.error && (
                <div className="w-full rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">
                  {status.error}
                </div>
              )}

              {/* Step details */}
              <div className="w-full space-y-1">
                {Object.entries(status.steps).map(([step, info]) => (
                  <div
                    key={step}
                    className="flex items-center justify-between rounded-lg bg-slate-800/30 px-3 py-1.5"
                  >
                    <span className="text-xs text-kos-text">
                      {STEP_LABELS[step] || step}
                    </span>
                    <StatusBadge
                      variant={
                        (info as { status: string }).status === "completed"
                          ? "ok"
                          : (info as { status: string }).status === "running"
                          ? "warning"
                          : (info as { status: string }).status === "failed"
                          ? "error"
                          : (info as { status: string }).status === "skipped"
                          ? "info"
                          : "muted"
                      }
                    >
                      {(info as { status: string }).status}
                    </StatusBadge>
                  </div>
                ))}
              </div>

              {status.running && (
                <button
                  onClick={abortCalibration}
                  className="w-full rounded-lg bg-red-500/20 py-2 text-sm font-medium text-red-400 hover:bg-red-500/30"
                >
                  Kalibrasyonu Iptal Et
                </button>
              )}
            </div>
          ) : (
            <div className="flex h-40 items-center justify-center text-kos-muted">
              Durum bilgisi bekleniyor...
            </div>
          )}
        </Card>

        {/* Calibration Config */}
        <Card title="Kalibrasyon Ayarlari" icon="⚙️">
          <div className="space-y-4">
            {/* Temperatures */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs text-kos-muted">
                  Nozul (°C)
                </label>
                <input
                  type="number"
                  value={config.extruder_temp}
                  onChange={(e) =>
                    setConfig({ ...config, extruder_temp: +e.target.value })
                  }
                  className="w-full rounded-lg border border-kos-border bg-kos-bg px-3 py-2 text-sm text-kos-text outline-none focus:border-kos-accent"
                  min={150}
                  max={300}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-kos-muted">
                  Tabla (°C)
                </label>
                <input
                  type="number"
                  value={config.bed_temp}
                  onChange={(e) =>
                    setConfig({ ...config, bed_temp: +e.target.value })
                  }
                  className="w-full rounded-lg border border-kos-border bg-kos-bg px-3 py-2 text-sm text-kos-text outline-none focus:border-kos-accent"
                  min={0}
                  max={120}
                />
              </div>
            </div>

            {/* Skip options */}
            <div className="space-y-2">
              <p className="text-xs font-medium text-kos-muted">
                Atlanacak Adimlar
              </p>
              {[
                { key: "skip_pid", label: "PID Tune" },
                { key: "skip_shaper", label: "Input Shaper" },
                { key: "skip_pa", label: "Pressure Advance" },
                { key: "skip_flow", label: "Flow Rate" },
              ].map((opt) => (
                <label
                  key={opt.key}
                  className="flex items-center gap-2 text-sm text-kos-text"
                >
                  <input
                    type="checkbox"
                    checked={
                      config[opt.key as keyof CalibStartRequest] as boolean
                    }
                    onChange={(e) =>
                      setConfig({ ...config, [opt.key]: e.target.checked })
                    }
                    className="h-4 w-4 rounded border-kos-border bg-kos-bg accent-kos-accent"
                  />
                  {opt.label} atla
                </label>
              ))}
            </div>

            <button
              onClick={startCalibration}
              disabled={status?.running}
              className="w-full rounded-lg bg-kos-accent py-3 text-sm font-semibold text-white transition hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {status?.running
                ? "Kalibrasyon Devam Ediyor..."
                : "Kalibrasyonu Baslat"}
            </button>
          </div>
        </Card>
      </div>
    </div>
  );
}

export default function CalibrationPage() {
  return (
    <DashboardShell>
      <CalibrationContent />
    </DashboardShell>
  );
}
