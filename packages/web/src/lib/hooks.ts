// ═══════════════════════════════════════════════
// KlipperOS-AI Dashboard — Custom React Hooks
// WebSocket, polling, auto-refresh
// ═══════════════════════════════════════════════

"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { apiGet } from "./api";

/** Auto-refresh polling hook */
export function usePolling<T>(
  path: string,
  intervalMs: number = 3000
): { data: T | null; error: string | null; loading: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    const fetchData = async () => {
      try {
        const result = await apiGet<T>(path);
        if (active) {
          setData(result);
          setError(null);
        }
      } catch (e) {
        if (active) setError(String(e));
      } finally {
        if (active) setLoading(false);
      }
    };

    fetchData();
    const timer = setInterval(fetchData, intervalMs);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [path, intervalMs]);

  return { data, error, loading };
}

/** WebSocket hook — printer realtime stream */
export function usePrinterWS() {
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Record<string, unknown> | null>(
    null
  );
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    // WS dogrudan ayni host'a baglanir — Next.js WS proxy yapamaz
    // Bu yuzden WS icin backend port'u kullaniyoruz
    const wsHost = window.location.hostname;
    const wsPort = "8470"; // FastAPI backend port

    const ws = new WebSocket(`${proto}//${wsHost}:${wsPort}/api/v1/ws/printer`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      // 3sn sonra yeniden baglan
      setTimeout(connect, 3000);
    };
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "printer_update") {
          setLastUpdate(msg.data);
        }
      } catch {
        // geçersiz JSON — atla
      }
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected, lastUpdate };
}

/** Tek seferlik fetch hook */
export function useFetch<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const result = await apiGet<T>(path);
      setData(result);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, loading, refetch };
}
