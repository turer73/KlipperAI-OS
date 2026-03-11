"use client";

import { useState } from "react";
import { DashboardShell } from "../DashboardShell";
import { Card } from "@/components/Card";
import { StatusBadge } from "@/components/StatusBadge";
import { usePolling } from "@/lib/hooks";
import { apiPost } from "@/lib/api";
import type { PrintStatus, GCodeFile } from "@/lib/types";

function ControlContent() {
  const { data: printer } = usePolling<PrintStatus>(
    "/api/v1/printer/status",
    2000
  );
  const { data: files } = usePolling<GCodeFile[]>(
    "/api/v1/files/gcodes",
    30000
  );
  const [gcode, setGcode] = useState("");
  const [feedback, setFeedback] = useState("");

  const sendCommand = async (
    endpoint: string,
    body?: unknown,
    label?: string
  ) => {
    try {
      setFeedback(`${label || endpoint} gonderiliyor...`);
      await apiPost(endpoint, body);
      setFeedback(`${label || endpoint} basarili ✓`);
    } catch (e) {
      setFeedback(`Hata: ${e}`);
    }
    setTimeout(() => setFeedback(""), 3000);
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-kos-text">Yazici Kontrol</h1>
        <p className="text-sm text-kos-muted">
          Baski kontrol, sicaklik ayari ve G-code gonderme
        </p>
      </div>

      {feedback && (
        <div
          className={`rounded-lg px-4 py-2 text-sm ${
            feedback.includes("Hata")
              ? "border border-red-500/30 bg-red-500/10 text-red-400"
              : "border border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
          }`}
        >
          {feedback}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Print Controls */}
        <Card title="Baski Kontrol" icon="🎮">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-kos-muted">Durum</span>
              <StatusBadge
                variant={
                  printer?.state === "printing" ? "ok" :
                  printer?.state === "paused" ? "warning" : "muted"
                }
              >
                {printer?.state?.toUpperCase() || "BILINMIYOR"}
              </StatusBadge>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() =>
                  sendCommand("/api/v1/printer/control/pause", {}, "Duraklat")
                }
                className="rounded-lg bg-amber-500/20 px-4 py-3 text-sm font-medium text-amber-400 transition hover:bg-amber-500/30 active:scale-95"
              >
                ⏸ Duraklat
              </button>
              <button
                onClick={() =>
                  sendCommand("/api/v1/printer/control/resume", {}, "Devam")
                }
                className="rounded-lg bg-emerald-500/20 px-4 py-3 text-sm font-medium text-emerald-400 transition hover:bg-emerald-500/30 active:scale-95"
              >
                ▶ Devam
              </button>
              <button
                onClick={() =>
                  sendCommand("/api/v1/printer/control/cancel", {}, "Iptal")
                }
                className="rounded-lg bg-red-500/20 px-4 py-3 text-sm font-medium text-red-400 transition hover:bg-red-500/30 active:scale-95"
              >
                ✕ Iptal
              </button>
            </div>
          </div>
        </Card>

        {/* Temperature Control */}
        <Card title="Sicaklik Ayari" icon="🌡️">
          <div className="space-y-3">
            <div className="flex gap-2">
              <button
                onClick={() =>
                  sendCommand(
                    "/api/v1/printer/control/temperature",
                    { heater: "extruder", target: 200 },
                    "Nozul 200°C"
                  )
                }
                className="flex-1 rounded-lg bg-slate-700/50 px-3 py-2 text-xs text-kos-text hover:bg-slate-700"
              >
                Nozul 200°C
              </button>
              <button
                onClick={() =>
                  sendCommand(
                    "/api/v1/printer/control/temperature",
                    { heater: "extruder", target: 210 },
                    "Nozul 210°C"
                  )
                }
                className="flex-1 rounded-lg bg-slate-700/50 px-3 py-2 text-xs text-kos-text hover:bg-slate-700"
              >
                Nozul 210°C
              </button>
              <button
                onClick={() =>
                  sendCommand(
                    "/api/v1/printer/control/temperature",
                    { heater: "extruder", target: 0 },
                    "Nozul Kapat"
                  )
                }
                className="flex-1 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400 hover:bg-red-500/20"
              >
                Nozul OFF
              </button>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() =>
                  sendCommand(
                    "/api/v1/printer/control/temperature",
                    { heater: "heater_bed", target: 60 },
                    "Tabla 60°C"
                  )
                }
                className="flex-1 rounded-lg bg-slate-700/50 px-3 py-2 text-xs text-kos-text hover:bg-slate-700"
              >
                Tabla 60°C
              </button>
              <button
                onClick={() =>
                  sendCommand(
                    "/api/v1/printer/control/temperature",
                    { heater: "heater_bed", target: 0 },
                    "Tabla Kapat"
                  )
                }
                className="flex-1 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400 hover:bg-red-500/20"
              >
                Tabla OFF
              </button>
            </div>
          </div>
        </Card>

        {/* G-code Console */}
        <Card title="G-code Konsol" icon="📝">
          <div className="space-y-2">
            <div className="flex gap-2">
              <input
                type="text"
                value={gcode}
                onChange={(e) => setGcode(e.target.value.toUpperCase())}
                placeholder="G28, G29, M106 S128..."
                className="flex-1 rounded-lg border border-kos-border bg-kos-bg px-3 py-2 font-mono text-sm text-kos-text outline-none focus:border-kos-accent"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && gcode.trim()) {
                    sendCommand(
                      "/api/v1/printer/control/gcode",
                      { script: gcode },
                      gcode
                    );
                    setGcode("");
                  }
                }}
              />
              <button
                onClick={() => {
                  if (gcode.trim()) {
                    sendCommand(
                      "/api/v1/printer/control/gcode",
                      { script: gcode },
                      gcode
                    );
                    setGcode("");
                  }
                }}
                className="rounded-lg bg-kos-accent px-4 py-2 text-sm font-medium text-white hover:bg-blue-600"
              >
                Gonder
              </button>
            </div>
            <div className="flex flex-wrap gap-1">
              {["G28", "G29", "M106 S128", "M107", "BED_MESH_CALIBRATE"].map(
                (cmd) => (
                  <button
                    key={cmd}
                    onClick={() =>
                      sendCommand(
                        "/api/v1/printer/control/gcode",
                        { script: cmd },
                        cmd
                      )
                    }
                    className="rounded bg-slate-800 px-2 py-1 font-mono text-[10px] text-kos-muted hover:text-kos-text"
                  >
                    {cmd}
                  </button>
                )
              )}
            </div>
          </div>
        </Card>

        {/* G-code Files */}
        <Card title="G-code Dosyalari" icon="📁">
          {files && files.length > 0 ? (
            <div className="max-h-48 space-y-1 overflow-y-auto">
              {files.slice(0, 20).map((f) => (
                <div
                  key={f.filename}
                  className="flex items-center justify-between rounded-lg bg-slate-800/30 px-3 py-1.5"
                >
                  <span className="max-w-[200px] truncate text-xs text-kos-text">
                    {f.filename}
                  </span>
                  <span className="text-[10px] text-kos-muted">
                    {(f.size / (1024 * 1024)).toFixed(1)}MB
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex h-24 items-center justify-center text-sm text-kos-muted">
              Dosya bulunamadi
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

export default function ControlPage() {
  return (
    <DashboardShell>
      <ControlContent />
    </DashboardShell>
  );
}
