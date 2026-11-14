import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import type { Attribution, Difficulty, MatchState } from "../types";
import { DIFF_LABEL, fmtPts, leaders, seatColor } from "../lib/util";

export function DiffBadge({ d, mult }: { d: Difficulty; mult?: number }) {
  return (
    <span className={`badge diff-${d}`}>
      {DIFF_LABEL[d]}
      {mult ? ` ×${mult}` : ""}
    </span>
  );
}

export function Scoreboard({ state }: { state: MatchState }) {
  const lead = leaders(state.players);
  const many = state.players.length > 2;
  const solo = state.players.length < 2;
  const cell = (p: MatchState["players"][number] | null, key: string) => (
    <div
      key={key}
      className={`sb-player ${p && lead.has(p.seat) ? "lead" : ""} ${p && state.you === p.seat ? "me" : ""}`}
      style={{ background: p ? seatColor(p.seat) : "#b9b0d0" }}
    >
      <div className="sb-name">
        <span className={`dot ${p?.online ? "on" : ""}`} />
        {p ? p.name : "In attesa…"}
        {p && state.you === p.seat && <small> (tu)</small>}
      </div>
      <div className="sb-total">{p ? fmtPts(p.total) : "–"}</div>
      {p && lead.has(p.seat) && <div className="crown">👑</div>}
    </div>
  );
  if (many) {
    return <div className="scoreboard many">{state.players.map((p) => cell(p, String(p.seat)))}</div>;
  }
  return (
    <div className="scoreboard">
      {cell(state.players[0], "a")}
      <div className="sb-vs">VS</div>
      {cell(solo ? null : state.players[1], "b")}
    </div>
  );
}

/** Il nome di un giocatore col suo colore. */
export function Who({ state, seat }: { state: MatchState; seat: number }) {
  const p = state.players.find((x) => x.seat === seat);
  return (
    <b className="who" style={{ ["--pc" as any]: seatColor(seat) }}>
      {p?.name ?? "?"}
    </b>
  );
}

export function Credit({ a }: { a: Attribution | null }) {
  if (!a) return null;
  return (
    <p className="credit">
      {a.source_url ? (
        <a href={a.source_url} target="_blank" rel="noreferrer">
          {a.title || "Foto"}
        </a>
      ) : (
        a.title || "Foto"
      )}
      {a.creator && <> di {a.creator}</>}
      {a.license && (
        <>
          {" · "}
          {a.license_url ? (
            <a href={a.license_url} target="_blank" rel="noreferrer">
              {a.license}
            </a>
          ) : (
            a.license
          )}
        </>
      )}
      {a.provider && <> · via {a.provider}</>}
    </p>
  );
}

/** Un'immagine che a un tocco va a schermo intero. */
export function Zoomable({ src, alt, className }: { src: string; alt: string; className?: string }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  return (
    <>
      <img src={src} alt={alt} className={`zoomable ${className || ""}`} onClick={() => setOpen(true)} loading="lazy" />
      {open &&
        createPortal(
          <div className="lightbox" onClick={() => setOpen(false)}>
            <button className="lightbox-close" aria-label="Chiudi">
              <X />
            </button>
            <img src={src} alt={alt} />
          </div>,
          document.body,
        )}
    </>
  );
}

export function Ring({ frac, danger, children }: { frac: number; danger?: boolean; children: React.ReactNode }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const f = Math.max(0, Math.min(1, frac));
  return (
    <div className={`ring ${danger ? "danger" : ""}`}>
      <svg viewBox="0 0 120 120">
        <circle cx="60" cy="60" r={r} className="ring-bg" />
        <circle
          cx="60"
          cy="60"
          r={r}
          className="ring-fg"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - f)}
          transform="rotate(-90 60 60)"
        />
      </svg>
      <div className="ring-label">{children}</div>
    </div>
  );
}

export function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="card center">
      <div className="big-emoji">😵</div>
      <p>{message}</p>
      <button className="btn" onClick={onRetry}>
        Riprova
      </button>
    </div>
  );
}
