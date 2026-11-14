// Tutte le chiamate al backend passano da qui.
import type { AppConfig, Gallery, MatchState, PowerupKind, Settings, User } from "./types";

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

export const prefs = {
  name: () => store.get("das:name") || "",
  setName: (n: string) => store.set("das:name", n),
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

async function call<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers = new Headers(opts.headers);
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

const post = <T>(path: string, body?: unknown) =>
  call<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });

export const api = {
  config: () => call<AppConfig>("/api/config"),
  me: () => call<{ user: User | null }>("/api/auth/me"),
  requestCode: (email: string) => post<{ ok: true }>("/api/auth/request", { email }),
  verify: (email: string, code: string) => post<{ user: User }>("/api/auth/verify", { email, code }),
  setName: (name: string) => post<{ user: User }>("/api/auth/name", { name }),
  logout: () => post<{ ok: true }>("/api/auth/logout"),
  create: (settings: Settings) => post<{ code: string; state: MatchState }>("/api/matches", { settings }),
  state: (code: string) => call<MatchState>(`/api/matches/${code}`),
  join: (code: string) => post<{ state: MatchState }>(`/api/matches/${code}/join`),
  startRound: (code: string, difficulty: string) => post<MatchState>(`/api/matches/${code}/rounds`, { difficulty }),
  powerup: (code: string, kind: PowerupKind, target?: number) =>
    post<MatchState>(`/api/matches/${code}/powerups`, { kind, target }),
  vote: (code: string, n: number, votes: Record<string, number>) =>
    post<MatchState>(`/api/matches/${code}/rounds/${n}/vote`, { votes }),
  closeVotes: (code: string, n: number) => post<MatchState>(`/api/matches/${code}/rounds/${n}/close-votes`),
  finish: (code: string) => post<MatchState>(`/api/matches/${code}/finish`),
  rematch: (code: string) => post<{ code: string; state: MatchState }>(`/api/matches/${code}/rematch`),
  gallery: () => call<Gallery>("/api/gallery"),
  upload: (code: string, n: number, file: Blob, onProgress?: (p: number) => void) =>
    new Promise<MatchState>((resolve, reject) => {
      // XHR e non fetch: serve l'avanzamento, le foto dal telefono pesano.
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/matches/${code}/rounds/${n}/photo`);
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
  // Il cookie di sessione parte da solo: stessa origine.
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/api/ws/${code}`;
}
