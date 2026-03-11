"use client";

import { useState, useEffect } from "react";
import { Sidebar } from "@/components/Sidebar";
import { loadToken, login, clearToken, healthCheck } from "@/lib/api";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const [authed, setAuthed] = useState(false);
  const [checking, setChecking] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [online, setOnline] = useState(true);

  useEffect(() => {
    const token = loadToken();
    if (token) {
      setAuthed(true);
    }
    setChecking(false);

    // Baglanti kontrolu
    const checkHealth = async () => {
      setOnline(await healthCheck());
    };
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    const ok = await login(username, password);
    if (ok) {
      setAuthed(true);
    } else {
      setError("Giris basarisiz. Kullanici adi veya sifre hatali.");
    }
  };

  if (checking) {
    return (
      <div className="flex h-screen items-center justify-center bg-kos-bg">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-kos-accent border-t-transparent" />
      </div>
    );
  }

  if (!authed) {
    return (
      <div className="flex h-screen items-center justify-center bg-kos-bg">
        <div className="w-full max-w-sm animate-fade-in rounded-2xl border border-kos-border bg-kos-card p-8 shadow-2xl">
          <div className="mb-6 text-center">
            <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-xl bg-kos-accent text-2xl font-bold text-white">
              K
            </div>
            <h1 className="text-xl font-bold text-kos-text">KlipperOS-AI</h1>
            <p className="mt-1 text-xs text-kos-muted">Dashboard&apos;a giris yap</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <input
              type="text"
              placeholder="Kullanici adi"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-kos-border bg-kos-bg px-4 py-2.5 text-sm text-kos-text placeholder-kos-muted outline-none focus:border-kos-accent"
            />
            <input
              type="password"
              placeholder="Sifre"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-kos-border bg-kos-bg px-4 py-2.5 text-sm text-kos-text placeholder-kos-muted outline-none focus:border-kos-accent"
            />
            {error && (
              <p className="text-xs text-kos-danger">{error}</p>
            )}
            <button
              type="submit"
              className="w-full rounded-lg bg-kos-accent py-2.5 text-sm font-semibold text-white transition hover:bg-blue-600 active:scale-[0.98]"
            >
              Giris Yap
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-kos-bg">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        {/* Connection indicator */}
        {!online && (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-400">
            ⚠️ Yazici ile baglanti kesildi. Yeniden baglaniliyor...
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
