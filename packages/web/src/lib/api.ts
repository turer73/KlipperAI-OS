// ═══════════════════════════════════════════════
// KlipperOS-AI Dashboard — API Client
// JWT auth + typed fetch wrapper
// ═══════════════════════════════════════════════

// API_BASE bos — tum istekler relative path ile gider (/api/v1/...)
// Next.js rewrites bu istekleri FastAPI backend'ine proxy eder
const API_BASE = "";

let _token: string | null = null;

/** Token kaydet (login sonrasi) */
export function setToken(token: string) {
  _token = token;
  if (typeof window !== "undefined") {
    localStorage.setItem("kos_token", token);
  }
}

/** Kayitli token'i yukle */
export function loadToken(): string | null {
  if (_token) return _token;
  if (typeof window !== "undefined") {
    _token = localStorage.getItem("kos_token");
  }
  return _token;
}

/** Token temizle (logout) */
export function clearToken() {
  _token = null;
  if (typeof window !== "undefined") {
    localStorage.removeItem("kos_token");
  }
}

/** Auth header'li fetch wrapper */
async function authFetch(
  path: string,
  opts: RequestInit = {}
): Promise<Response> {
  const token = loadToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.href = "/";
    }
  }
  return res;
}

/** Typed GET */
export async function apiGet<T>(path: string): Promise<T> {
  const res = await authFetch(path);
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

/** Typed POST */
export async function apiPost<T>(
  path: string,
  body?: unknown
): Promise<T> {
  const res = await authFetch(path, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

/** Typed PUT */
export async function apiPut<T>(
  path: string,
  body: unknown
): Promise<T> {
  const res = await authFetch(path, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

/** Typed DELETE */
export async function apiDelete<T>(path: string): Promise<T> {
  const res = await authFetch(path, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

/** Login */
export async function login(
  username: string,
  password: string
): Promise<boolean> {
  try {
    const data = await apiPost<{ access_token: string }>(
      "/api/v1/auth/login",
      { username, password }
    );
    setToken(data.access_token);
    return true;
  } catch {
    return false;
  }
}

/** Health check */
export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/health`);
    return res.ok;
  } catch {
    return false;
  }
}
