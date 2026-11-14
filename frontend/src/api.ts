// Tutte le chiamate al backend passano da qui.
import type { AppConfig, Gallery, MatchState, PowerupKind, Settings } from "./types";

const store = {
  get(k: string): string | null {
    try {
      return localStorage.getItem(k);
    } catch {
      return null;
    }
  },
  set(k: string, v: string) {
    try {
      localStorage.setItem(k, v);
    } catch {
      /* navigazione privata: pazienza */
    }
  },
};

export const tokens = {
  get: (code: string) => store.get(`das:tok:${code.toUpperCase()}`),
  set: (code: string, t: string) => store.set(`das:tok:${code.toUpperCase()}`, t),
};
export const prefs = {
  name: () => store.get("das:name") || "",
  setName: (n: string) => store.set("das:name", n),
  access: () => store.get("das:access") || "",
  setAccess: (c: string) => store.set("das:access", c),
  settings: (): Partial<Settings> | null => {
    try {
      return JSON.parse(store.get("das:settings") || "null");
    } catch {
      return null;
    }
  },
  setSettings: (s: Settings) => store.set("das:settings", JSON.stringify(s)),
};

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function call<T>(path: string, opts: RequestInit & { code?: string } = {}): Promise<T> {
  const headers = new Headers(opts.headers);
  if (opts.code) {
    const t = tokens.get(opts.code);
    if (t) headers.set("X-Player-Token", t);
  }
  const access = prefs.access();
  if (access) headers.set("X-Access-Code", access);
  if (opts.body && typeof opts.body === "string") headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(path, { ...opts, headers });
  } catch {
    throw new ApiError("Connessione assente: riprova fra un attimo", 0);
  }
  if (!res.ok) {
    let msg = `Errore ${res.status}`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") msg = j.detail;
    } catch {
      /* risposta non JSON */
    }
    throw new ApiError(msg, res.status);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown, code?: string) =>
  call<T>(path, { method: "POST", body: JSON.stringify(body ?? {}), code });

export const api = {
  config: () => call<AppConfig>("/api/config"),
  checkAccess: () => post<{ ok: true }>("/api/access/check", {}),
  create: (name: string, settings: Settings) =>
    post<{ code: string; token: string; state: MatchState }>("/api/matches", { name, settings }),
  state: (code: string) => call<MatchState>(`/api/matches/${code}`, { code }),
  join: (code: string, name: string) =>
    post<{ token: string; state: MatchState }>(`/api/matches/${code}/join`, { name }),
  startRound: (code: string, difficulty: string) =>
    post<MatchState>(`/api/matches/${code}/rounds`, { difficulty }, code),
  powerup: (code: string, kind: PowerupKind) =>
    post<MatchState>(`/api/matches/${code}/powerups`, { kind }, code),
  vote: (code: string, n: number, value: number) =>
    post<MatchState>(`/api/matches/${code}/rounds/${n}/vote`, { value }, code),
  finish: (code: string) => post<MatchState>(`/api/matches/${code}/finish`, {}, code),
  rematch: (code: string) =>
    post<{ code: string; token: string; state: MatchState }>(`/api/matches/${code}/rematch`, {}, code),
  gallery: () => call<Gallery>("/api/gallery"),
  upload: (code: string, n: number, file: Blob, onProgress?: (p: number) => void) =>
    new Promise<MatchState>((resolve, reject) => {
      // XHR e non fetch: serve l'avanzamento, le foto dal telefono pesano.
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/matches/${code}/rounds/${n}/photo`);
      const t = tokens.get(code);
      if (t) xhr.setRequestHeader("X-Player-Token", t);
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
      xhr.onload = () => {
        let body: any = null;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* niente */
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body);
        else reject(new ApiError(body?.detail || `Errore ${xhr.status}`, xhr.status));
      };
      xhr.onerror = () => reject(new ApiError("Caricamento non riuscito: controlla la connessione", 0));
      const fd = new FormData();
      fd.append("photo", file, "foto.jpg");
      xhr.send(fd);
    }),
};

export function wsUrl(code: string) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const t = tokens.get(code);
  return `${proto}://${location.host}/api/ws/${code}${t ? `?token=${encodeURIComponent(t)}` : ""}`;
}
