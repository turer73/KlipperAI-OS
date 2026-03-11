"use client";

import { useState, useEffect } from "react";
import { DashboardShell } from "../DashboardShell";
import { Card } from "@/components/Card";
import { StatusBadge } from "@/components/StatusBadge";
import { TempGauge } from "@/components/TempGauge";
import { ProgressRing } from "@/components/ProgressRing";
import { usePolling } from "@/lib/hooks";
import { apiPost, apiDelete } from "@/lib/api";
import { formatDuration } from "@/lib/utils";
import type {
  BambuPrinter,
  BambuPrinterAdd,
  BambuPrinterStatus,
  BambuOverview,
  BambuDetection,
} from "@/lib/types";

// ── Yardimci fonksiyonlar ──────────────────────────────────
function stateVariant(
  state: string
): "ok" | "warning" | "error" | "muted" | "info" {
  switch (state?.toLowerCase()) {
    case "printing":
      return "ok";
    case "paused":
      return "warning";
    case "error":
    case "failed":
      return "error";
    case "complete":
      return "info";
    default:
      return "muted";
  }
}

function stateLabel(state: string): string {
  switch (state?.toLowerCase()) {
    case "printing":
      return "YAZDIRIYOR";
    case "paused":
      return "DURAKLATILDI";
    case "error":
    case "failed":
      return "HATA";
    case "complete":
      return "TAMAMLANDI";
    case "idle":
      return "BOSTA";
    default:
      return state?.toUpperCase() || "BILINMIYOR";
  }
}

function detectionVariant(cls: string): "ok" | "warning" | "error" | "muted" {
  switch (cls?.toLowerCase()) {
    case "normal":
      return "ok";
    case "stringing":
    case "under_extrusion":
      return "warning";
    case "spaghetti":
    case "layer_shift":
      return "error";
    default:
      return "muted";
  }
}

// ── Kamera Snapshot (auto-refresh img) ─────────────────────
function CameraFeed({ printerId }: { printerId: string }) {
  const [tick, setTick] = useState(0);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => setTick((t) => t + 1), 5000);
    return () => clearInterval(timer);
  }, []);

  const src = `/api/v1/bambu/printers/${printerId}/camera/snapshot?t=${tick}`;

  if (hasError) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-900/50 text-kos-muted">
        <div className="text-center">
          <div className="text-3xl mb-1">📷</div>
          <div className="text-xs">Kamera baglantisi yok</div>
        </div>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt="Kamera"
      className="h-full w-full object-cover"
      onError={() => setHasError(true)}
      onLoad={() => setHasError(false)}
    />
  );
}

// ── AI Tespit Bilgisi ──────────────────────────────────────
function DetectionBadge({ printerId }: { printerId: string }) {
  const { data: detection } = usePolling<BambuDetection>(
    `/api/v1/bambu/printers/${printerId}/detection`,
    5000
  );

  if (!detection) return null;

  return (
    <div className="flex items-center gap-2">
      <StatusBadge variant={detectionVariant(detection.detection_class)}>
        {detection.detection_class}
      </StatusBadge>
      <span className="font-mono text-xs text-kos-muted">
        {(detection.confidence * 100).toFixed(0)}%
      </span>
    </div>
  );
}


// ── AI Monitor Toggle ─────────────────────────────────────
function MonitorToggle({
  running,
  onFeedback,
}: {
  running: boolean;
  onFeedback: (msg: string) => void;
}) {
  const [loading, setLoading] = useState(false);

  const toggleMonitor = async () => {
    const action = running ? "stop" : "start";
    setLoading(true);
    try {
      const res = await apiPost<{ success: boolean; message: string }>(
        `/api/v1/system/services/kos-bambu-monitor/${action}`
      );
      if (res.success) {
        onFeedback(`ok:${res.message}`);
      } else {
        onFeedback(res.message || "Islem basarisiz");
      }
    } catch (e) {
      onFeedback(`Hata: ${e}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className={`rounded-xl border p-4 ${
        running
          ? "border-emerald-500/20 bg-emerald-500/5"
          : "border-amber-500/20 bg-amber-500/5"
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl">{running ? "🟢" : "⚠️"}</span>
          <div>
            <div
              className={`text-sm font-medium ${
                running ? "text-emerald-400" : "text-amber-400"
              }`}
            >
              {running ? "AI Monitor aktif" : "AI Monitor kapali"}
            </div>
            <div className="text-xs text-kos-muted">
              {running
                ? "Canli AI tespit ve izleme calisiyor"
                : "Canli izleme durmus — baslatin"}
            </div>
          </div>
        </div>
        <button
          onClick={toggleMonitor}
          disabled={loading}
          className={`rounded-lg px-5 py-2.5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${
            running
              ? "bg-red-500/20 text-red-400 hover:bg-red-500/30"
              : "bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30"
          }`}
        >
          {loading ? "..." : running ? "Durdur" : "Baslat"}
        </button>
      </div>
    </div>
  );
}

// ── Canli Yazici Karti ─────────────────────────────────────
function LivePrinterCard({
  printer,
  onDelete,
}: {
  printer: BambuPrinter;
  onDelete: (id: string, name: string) => void;
}) {
  const { data: status } = usePolling<BambuPrinterStatus>(
    `/api/v1/bambu/printers/${printer.id}/status`,
    3000
  );

  const isPrinting = status?.is_printing ?? false;
  const progress = status?.progress_percent ?? 0;
  const state = status?.state ?? "idle";
  const mqttOk = status?.mqtt_connected ?? false;
  const camOk = status?.camera_connected ?? false;

  return (
    <div className="overflow-hidden rounded-xl border border-kos-border bg-kos-card shadow-lg">
      {/* Ust: Kamera + Progress */}
      <div className="relative">
        {/* Kamera goruntusu */}
        <div className="aspect-video w-full overflow-hidden bg-slate-900">
          <CameraFeed printerId={printer.id} />
        </div>

        {/* Baski durumu overlay (sol ust) */}
        <div className="absolute left-3 top-3">
          <StatusBadge
            variant={stateVariant(state)}
            pulse={isPrinting}
          >
            {stateLabel(state)}
          </StatusBadge>
        </div>

        {/* Baglanti durumlari overlay (sag ust) */}
        <div className="absolute right-3 top-3 flex gap-1.5">
          <span
            title={mqttOk ? "MQTT bagli" : "MQTT baglanti yok"}
            className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${
              mqttOk
                ? "bg-emerald-500/20 text-emerald-400"
                : "bg-red-500/20 text-red-400"
            }`}
          >
            📡
          </span>
          <span
            title={camOk ? "Kamera bagli" : "Kamera baglanti yok"}
            className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${
              camOk
                ? "bg-emerald-500/20 text-emerald-400"
                : "bg-red-500/20 text-red-400"
            }`}
          >
            📷
          </span>
        </div>

        {/* Ilerleme bar (kameranin altinda) */}
        {isPrinting && (
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-slate-900/50">
            <div
              className="h-full bg-kos-accent transition-all duration-1000"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
      </div>

      {/* Orta: Yazici bilgileri */}
      <div className="p-4">
        {/* Baslik + Sil */}
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-base font-bold text-kos-text">{printer.name}</h3>
          <button
            onClick={() => onDelete(printer.id, printer.name)}
            className="rounded-lg bg-red-500/10 px-2 py-0.5 text-[10px] text-red-400 transition hover:bg-red-500/20"
            title="Yaziciyi sil"
          >
            Sil
          </button>
        </div>

        {/* Baski yapiliyorsa detayli bilgi goster */}
        {isPrinting && status ? (
          <div className="space-y-4">
            {/* Ilerleme + Dosya bilgisi */}
            <div className="flex items-center gap-4">
              <ProgressRing
                percent={progress}
                size={80}
                strokeWidth={6}
              />
              <div className="flex-1 space-y-1">
                <div className="truncate text-sm font-medium text-kos-text">
                  {status.filename || "Bilinmeyen dosya"}
                </div>
                <div className="flex items-center gap-2 text-xs text-kos-muted">
                  <span>Katman {status.current_layer}/{status.total_layers}</span>
                  <span className="text-kos-border">|</span>
                  <span>{status.remaining_minutes} dk kaldi</span>
                </div>
              </div>
            </div>

            {/* Sicakliklar */}
            <div className="space-y-2">
              <TempGauge
                label="Nozul"
                current={status.nozzle_temp}
                target={status.nozzle_target}
              />
              <TempGauge
                label="Yatak"
                current={status.bed_temp}
                target={status.bed_target}
              />
            </div>

            {/* AI Tespit */}
            <DetectionBadge printerId={printer.id} />
          </div>
        ) : status ? (
          /* Bosta iken ozet bilgi */
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-slate-800/50 p-2.5 text-center">
                <div className="text-lg font-bold text-kos-text">
                  {status.nozzle_temp.toFixed(0)}°
                </div>
                <div className="text-[10px] text-kos-muted">Nozul</div>
              </div>
              <div className="rounded-lg bg-slate-800/50 p-2.5 text-center">
                <div className="text-lg font-bold text-kos-text">
                  {status.bed_temp.toFixed(0)}°
                </div>
                <div className="text-[10px] text-kos-muted">Yatak</div>
              </div>
            </div>
            <div className="flex items-center justify-between text-xs text-kos-muted">
              <span>{printer.hostname}</span>
              <span className="font-mono">{printer.serial.slice(-6)}</span>
            </div>
          </div>
        ) : (
          /* Veri yok */
          <div className="flex h-20 items-center justify-center text-sm text-kos-muted">
            Baglanti bekleniyor...
          </div>
        )}
      </div>
    </div>
  );
}

// ── Yazici Ekleme Formu ────────────────────────────────────
function AddPrinterForm({
  onClose,
  onFeedback,
}: {
  onClose: () => void;
  onFeedback: (msg: string) => void;
}) {
  const [form, setForm] = useState<BambuPrinterAdd>({
    name: "",
    hostname: "",
    access_code: "",
    serial: "",
  });
  const [adding, setAdding] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name || !form.hostname || !form.access_code || !form.serial) {
      onFeedback("Tum alanlari doldurun.");
      return;
    }
    setAdding(true);
    try {
      await apiPost("/api/v1/bambu/printers", form);
      onFeedback("ok:Yazici eklendi");
      onClose();
    } catch (e) {
      onFeedback(`Hata: ${e}`);
    } finally {
      setAdding(false);
    }
  };

  const fields = [
    { key: "name", label: "Yazici Adi", placeholder: "A1 Mini", mono: false },
    { key: "hostname", label: "IP Adresi", placeholder: "192.168.1.50", mono: true },
    { key: "access_code", label: "Erisim Kodu", placeholder: "12345678", mono: true, maxLen: 8 },
    { key: "serial", label: "Seri No", placeholder: "01S00C123456789", mono: true },
  ] as const;

  return (
    <Card title="Yeni Yazici Ekle" icon="➕">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {fields.map((f) => (
            <div key={f.key}>
              <label className="mb-1 block text-xs text-kos-muted">
                {f.label}
              </label>
              <input
                type="text"
                placeholder={f.placeholder}
                value={form[f.key]}
                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                maxLength={"maxLen" in f ? f.maxLen : undefined}
                className={`w-full rounded-lg border border-kos-border bg-kos-bg px-3 py-2 text-sm text-kos-text placeholder-kos-muted outline-none focus:border-kos-accent ${
                  f.mono ? "font-mono" : ""
                }`}
              />
            </div>
          ))}
        </div>
        <div className="flex gap-3">
          <button
            type="submit"
            disabled={adding}
            className="flex-1 rounded-lg bg-kos-accent py-2.5 text-sm font-semibold text-white transition hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {adding ? "Ekleniyor..." : "Yazici Ekle"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-kos-border px-4 py-2.5 text-sm text-kos-muted transition hover:text-kos-text"
          >
            Iptal
          </button>
        </div>
      </form>
    </Card>
  );
}

// ── Ana icerik ──────────────────────────────────────────────
function BambuContent() {
  const { data: printers } = usePolling<BambuPrinter[]>(
    "/api/v1/bambu/printers",
    10000
  );
  const { data: overview } = usePolling<BambuOverview>(
    "/api/v1/bambu/status",
    5000
  );

  const [feedback, setFeedback] = useState("");
  const [showForm, setShowForm] = useState(false);

  const deletePrinter = async (id: string, name: string) => {
    try {
      await apiDelete(`/api/v1/bambu/printers/${id}`);
      setFeedback(`ok:"${name}" silindi`);
    } catch (e) {
      setFeedback(`Silme hatasi: ${e}`);
    }
  };

  const handleFeedback = (msg: string) => {
    setFeedback(msg);
    if (msg.startsWith("ok:")) {
      setTimeout(() => setFeedback(""), 3000);
    }
  };

  const monitorRunning = overview?.monitor_running ?? false;
  const printerCount = printers?.length ?? 0;
  const isOk = feedback.startsWith("ok:");
  const feedbackText = isOk ? feedback.slice(3) : feedback;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-kos-text">Bambu Lab</h1>
          <p className="text-sm text-kos-muted">
            AI Destekli Canli Yazici Izleme
          </p>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge
            variant={monitorRunning ? "ok" : "muted"}
            pulse={monitorRunning}
          >
            {monitorRunning ? "MONITOR AKTIF" : "MONITOR KAPALI"}
          </StatusBadge>
          {printerCount > 0 && (
            <span className="rounded-full bg-slate-800 px-3 py-1 text-xs font-mono text-kos-muted">
              {printerCount} yazici
            </span>
          )}
        </div>
      </div>

      {/* Feedback mesaji */}
      {feedback && (
        <div
          className={`rounded-lg border px-4 py-2 text-sm ${
            isOk
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
              : "border-red-500/30 bg-red-500/10 text-red-400"
          }`}
        >
          {feedbackText}
          <button
            onClick={() => setFeedback("")}
            className="ml-3 text-xs opacity-60 hover:opacity-100"
          >
            ✕
          </button>
        </div>
      )}

      {/* Monitor kontrol paneli */}
      <MonitorToggle running={monitorRunning} onFeedback={handleFeedback} />

      {/* Yazici Kartlari Grid */}
      {printerCount > 0 ? (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 2xl:grid-cols-3">
          {printers?.map((printer) => (
            <LivePrinterCard
              key={printer.id}
              printer={printer}
              onDelete={deletePrinter}
            />
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-kos-border py-16 text-kos-muted">
          <span className="mb-3 text-5xl">🖨️</span>
          <span className="text-lg font-medium">Henuz yazici eklenmedi</span>
          <span className="mt-1 text-sm">
            Asagidaki butona tiklayarak Bambu Lab yazici ekleyin
          </span>
        </div>
      )}

      {/* Yazici Ekle */}
      {!showForm ? (
        <button
          onClick={() => setShowForm(true)}
          className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-kos-border py-4 text-sm text-kos-muted transition hover:border-kos-accent hover:text-kos-accent"
        >
          <span className="text-lg">+</span>
          Yeni Bambu Lab Yazici Ekle
        </button>
      ) : (
        <AddPrinterForm
          onClose={() => setShowForm(false)}
          onFeedback={handleFeedback}
        />
      )}
    </div>
  );
}

// ── Sayfa export ────────────────────────────────────────────
export default function BambuPage() {
  return (
    <DashboardShell>
      <BambuContent />
    </DashboardShell>
  );
}
