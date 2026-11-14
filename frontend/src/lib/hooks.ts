import { useCallback, useEffect, useRef, useState } from "react";
import { api, wsUrl } from "../api";
import type { MatchState } from "../types";

/** Lo stato della partita, tenuto in sincronia dal WebSocket (con riconnessione)
 *  e lo scarto fra l'orologio del telefono e quello del server. */
export function useMatch(code: string) {
  const [state, setRaw] = useState<MatchState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const offset = useRef(0); // server - client, in secondi
  const [, bump] = useState(0);
  // Cambia quando cambia il token (chi entra dal link): il WebSocket va riaperto
  // con il token nuovo, altrimenti il server continua a vederci come spettatori.
  const [link, setLink] = useState(0);
  const relink = useCallback(() => setLink((x) => x + 1), []);

  const setState = useCallback((s: MatchState) => {
    offset.current = s.server_now - Date.now() / 1000;
    setRaw(s);
    setError(null);
  }, []);

  const refresh = useCallback(async () => {
    try {
      setState(await api.state(code));
    } catch (e: any) {
      setError(e.message);
    }
  }, [code, setState]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry = 0;
    let ping: number | undefined;
    let timer: number | undefined;

    const open = () => {
      ws = new WebSocket(wsUrl(code));
      ws.onopen = () => {
        retry = 0;
        setConnected(true);
        ping = window.setInterval(() => ws?.readyState === 1 && ws.send("ping"), 20000);
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "state") setState(msg.state);
        else if (msg.type === "pong") {
          offset.current = msg.server_now - Date.now() / 1000;
          bump((x) => x + 1);
        }
      };
      ws.onclose = (ev) => {
        setConnected(false);
        window.clearInterval(ping);
        if (closed) return;
        if (ev.code === 4404 || ev.code === 4403) {
          setError(ev.code === 4404 ? "Partita non trovata" : "Questa partita non è tua: la vedono solo i due giocatori");
          return;
        }
        retry = Math.min(retry + 1, 6);
        timer = window.setTimeout(open, 500 * 2 ** retry);
      };
    };
    refresh();
    open();
    // Tornando in primo piano (telefono bloccato durante il round) si riallinea subito.
    const onVis = () => document.visibilityState === "visible" && refresh();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      closed = true;
      window.clearTimeout(timer);
      window.clearInterval(ping);
      document.removeEventListener("visibilitychange", onVis);
      ws?.close();
    };
  }, [code, refresh, setState, link]);

  return { state, setState, error, connected, refresh, offset, relink };
}

/** «Adesso» secondo il server, aggiornato più volte al secondo. */
export function useServerNow(offset: React.RefObject<number>, every = 250) {
  const [now, setNow] = useState(() => Date.now() / 1000 + (offset.current ?? 0));
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now() / 1000 + (offset.current ?? 0)), every);
    return () => window.clearInterval(id);
  }, [offset, every]);
  return now;
}

/** Tiene lo schermo acceso mentre si scolpisce (dove il browser lo permette). */
export function useWakeLock(active: boolean) {
  useEffect(() => {
    if (!active || !("wakeLock" in navigator)) return;
    let lock: any = null;
    let gone = false;
    const get = async () => {
      try {
        lock = await (navigator as any).wakeLock.request("screen");
      } catch {
        /* non concesso */
      }
    };
    get();
    const onVis = () => !gone && document.visibilityState === "visible" && get();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      gone = true;
      document.removeEventListener("visibilitychange", onVis);
      lock?.release?.().catch(() => {});
    };
  }, [active]);
}
