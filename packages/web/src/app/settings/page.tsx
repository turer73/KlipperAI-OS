"use client";

import { useState, useEffect } from "react";
import { DashboardShell } from "../DashboardShell";
import { Card } from "@/components/Card";
import { StatusBadge } from "@/components/StatusBadge";
import { useFetch } from "@/lib/hooks";
import { apiGet, apiPut, apiPost, clearToken } from "@/lib/api";
import type { NotificationConfig, RecoveryStatus } from "@/lib/types";

function SettingsContent() {
  // -- Notification config --
  const [notifConfig, setNotifConfig] = useState<NotificationConfig | null>(
    null
  );
  const [notifLoading, setNotifLoading] = useState(true);
  const [notifFeedback, setNotifFeedback] = useState("");

  // -- Recovery --
  const { data: recovery, refetch: refetchRecovery } =
    useFetch<RecoveryStatus>("/api/v1/recovery/status");

  useEffect(() => {
    apiGet<NotificationConfig>("/api/v1/notifications/config")
      .then(setNotifConfig)
      .catch(() => {})
      .finally(() => setNotifLoading(false));
  }, []);

  const saveNotifConfig = async () => {
    if (!notifConfig) return;
    try {
      setNotifFeedback("Kaydediliyor...");
      await apiPut("/api/v1/notifications/config", notifConfig);
      setNotifFeedback("Bildirim ayarlari kaydedildi ✓");
    } catch (e) {
      setNotifFeedback(`Hata: ${e}`);
    }
    setTimeout(() => setNotifFeedback(""), 3000);
  };

  const sendTestNotif = async () => {
    try {
      setNotifFeedback("Test bildirimi gonderiliyor...");
      await apiPost("/api/v1/notifications/test", {
        title: "Test Bildirimi",
        message: "KlipperOS-AI dashboard test mesaji",
        severity: "info",
      });
      setNotifFeedback("Test bildirimi gonderildi ✓");
    } catch (e) {
      setNotifFeedback(`Hata: ${e}`);
    }
    setTimeout(() => setNotifFeedback(""), 3000);
  };

  const toggleRecovery = async () => {
    if (!recovery) return;
    try {
      await apiPost("/api/v1/recovery/enable", {
        enabled: !recovery.enabled,
      });
      refetchRecovery();
    } catch {
      // silent
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-kos-text">Ayarlar</h1>
        <p className="text-sm text-kos-muted">
          Bildirimler, kurtarma motoru ve hesap ayarlari
        </p>
      </div>

      {notifFeedback && (
        <div
          className={`rounded-lg px-4 py-2 text-sm ${
            notifFeedback.includes("Hata")
              ? "border border-red-500/30 bg-red-500/10 text-red-400"
              : "border border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
          }`}
        >
          {notifFeedback}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Telegram */}
        <Card title="Telegram Bildirimi" icon="📱">
          {notifConfig ? (
            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm text-kos-text">
                <input
                  type="checkbox"
                  checked={notifConfig.telegram.enabled}
                  onChange={(e) =>
                    setNotifConfig({
                      ...notifConfig,
                      telegram: {
                        ...notifConfig.telegram,
                        enabled: e.target.checked,
                      },
                    })
                  }
                  className="h-4 w-4 accent-kos-accent"
                />
                Telegram aktif
              </label>
              <div>
                <label className="mb-1 block text-xs text-kos-muted">
                  Bot Token
                </label>
                <input
                  type="password"
                  value={notifConfig.telegram.bot_token}
                  onChange={(e) =>
                    setNotifConfig({
                      ...notifConfig,
                      telegram: {
                        ...notifConfig.telegram,
                        bot_token: e.target.value,
                      },
                    })
                  }
                  placeholder="123456:ABC-DEF..."
                  className="w-full rounded-lg border border-kos-border bg-kos-bg px-3 py-2 text-sm text-kos-text outline-none focus:border-kos-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-kos-muted">
                  Chat ID
                </label>
                <input
                  type="text"
                  value={notifConfig.telegram.chat_id}
                  onChange={(e) =>
                    setNotifConfig({
                      ...notifConfig,
                      telegram: {
                        ...notifConfig.telegram,
                        chat_id: e.target.value,
                      },
                    })
                  }
                  placeholder="-1001234567890"
                  className="w-full rounded-lg border border-kos-border bg-kos-bg px-3 py-2 text-sm text-kos-text outline-none focus:border-kos-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-kos-muted">
                  Min. Onem Seviyesi
                </label>
                <select
                  value={notifConfig.telegram.min_severity}
                  onChange={(e) =>
                    setNotifConfig({
                      ...notifConfig,
                      telegram: {
                        ...notifConfig.telegram,
                        min_severity: e.target.value,
                      },
                    })
                  }
                  className="w-full rounded-lg border border-kos-border bg-kos-bg px-3 py-2 text-sm text-kos-text outline-none focus:border-kos-accent"
                >
                  <option value="info">Info</option>
                  <option value="notice">Notice</option>
                  <option value="warning">Warning</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-kos-muted">
              {notifLoading ? "Yukleniyor..." : "Yapilandirma alinamadi"}
            </div>
          )}
        </Card>

        {/* Discord */}
        <Card title="Discord Bildirimi" icon="💬">
          {notifConfig ? (
            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm text-kos-text">
                <input
                  type="checkbox"
                  checked={notifConfig.discord.enabled}
                  onChange={(e) =>
                    setNotifConfig({
                      ...notifConfig,
                      discord: {
                        ...notifConfig.discord,
                        enabled: e.target.checked,
                      },
                    })
                  }
                  className="h-4 w-4 accent-kos-accent"
                />
                Discord aktif
              </label>
              <div>
                <label className="mb-1 block text-xs text-kos-muted">
                  Webhook URL
                </label>
                <input
                  type="password"
                  value={notifConfig.discord.webhook_url}
                  onChange={(e) =>
                    setNotifConfig({
                      ...notifConfig,
                      discord: {
                        ...notifConfig.discord,
                        webhook_url: e.target.value,
                      },
                    })
                  }
                  placeholder="https://discord.com/api/webhooks/..."
                  className="w-full rounded-lg border border-kos-border bg-kos-bg px-3 py-2 text-sm text-kos-text outline-none focus:border-kos-accent"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-kos-muted">
                  Min. Onem Seviyesi
                </label>
                <select
                  value={notifConfig.discord.min_severity}
                  onChange={(e) =>
                    setNotifConfig({
                      ...notifConfig,
                      discord: {
                        ...notifConfig.discord,
                        min_severity: e.target.value,
                      },
                    })
                  }
                  className="w-full rounded-lg border border-kos-border bg-kos-bg px-3 py-2 text-sm text-kos-text outline-none focus:border-kos-accent"
                >
                  <option value="info">Info</option>
                  <option value="notice">Notice</option>
                  <option value="warning">Warning</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-kos-muted">
              {notifLoading ? "Yukleniyor..." : "Yapilandirma alinamadi"}
            </div>
          )}
        </Card>

        {/* General notification settings + save */}
        <Card title="Genel Bildirim Ayarlari" icon="🔔">
          {notifConfig ? (
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs text-kos-muted">
                  Bekleme Suresi (saniye)
                </label>
                <input
                  type="number"
                  value={notifConfig.cooldown_seconds}
                  onChange={(e) =>
                    setNotifConfig({
                      ...notifConfig,
                      cooldown_seconds: +e.target.value,
                    })
                  }
                  min={0}
                  max={3600}
                  className="w-full rounded-lg border border-kos-border bg-kos-bg px-3 py-2 text-sm text-kos-text outline-none focus:border-kos-accent"
                />
                <p className="mt-1 text-[10px] text-kos-muted">
                  Ayni kategoride tekrar bildirim icin minimum bekleme
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={saveNotifConfig}
                  className="flex-1 rounded-lg bg-kos-accent py-2.5 text-sm font-semibold text-white hover:bg-blue-600"
                >
                  Kaydet
                </button>
                <button
                  onClick={sendTestNotif}
                  className="flex-1 rounded-lg border border-kos-border bg-slate-800 py-2.5 text-sm font-medium text-kos-text hover:bg-slate-700"
                >
                  Test Gonder
                </button>
              </div>
            </div>
          ) : (
            <div className="flex h-24 items-center justify-center text-kos-muted">
              Yukleniyor...
            </div>
          )}
        </Card>

        {/* Recovery Engine Toggle */}
        <Card title="Kurtarma Motoru" icon="🛡️">
          {recovery ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-kos-text">Otomatik Kurtarma</span>
                <button
                  onClick={toggleRecovery}
                  className={`relative h-6 w-11 rounded-full transition-colors ${
                    recovery.enabled ? "bg-kos-success" : "bg-slate-600"
                  }`}
                >
                  <span
                    className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                      recovery.enabled ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
              <p className="text-xs text-kos-muted">
                Aktif oldugunda, baski hatalarini otomatik tespit edip kurtarma
                islemleri baslatir.
              </p>

              {Object.keys(recovery.attempt_counts).length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-kos-muted">
                    Kurtarma Denemeleri
                  </p>
                  {Object.entries(recovery.attempt_counts).map(
                    ([cat, count]) => (
                      <div
                        key={cat}
                        className="flex justify-between rounded bg-slate-800/30 px-2 py-1 text-xs"
                      >
                        <span className="text-kos-text">{cat}</span>
                        <span className="text-kos-muted">{count}x</span>
                      </div>
                    )
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="flex h-24 items-center justify-center text-kos-muted">
              Yukleniyor...
            </div>
          )}
        </Card>
      </div>

      {/* Logout */}
      <Card>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-kos-text">Oturum</p>
            <p className="text-xs text-kos-muted">
              Dashboard oturumunu sonlandir
            </p>
          </div>
          <button
            onClick={() => {
              clearToken();
              window.location.href = "/";
            }}
            className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-400 hover:bg-red-500/20"
          >
            Cikis Yap
          </button>
        </div>
      </Card>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <DashboardShell>
      <SettingsContent />
    </DashboardShell>
  );
}
