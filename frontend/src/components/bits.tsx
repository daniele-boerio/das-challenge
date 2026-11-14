import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import type { Attribution, Difficulty, MatchState, Role } from "../types";
import { DIFF_LABEL, fmtPts } from "../lib/util";

export function DiffBadge({ d, mult }: { d: Difficulty; mult?: number }) {
  return (
    <span className={`badge diff-${d}`}>
      {DIFF_LABEL[d]}
      {mult ? ` ×${mult}` : ""}
    </span>
  );
}

export function Scoreboard({ state, bump }: { state: MatchState; bump?: boolean }) {
  const { host, guest } = state.players;
  const lead =
    guest && host.total !== guest.total ? (host.total > guest.total ? "host" : "guest") : null;
  const p = (role: Role) => {
    const pl = role === "host" ? host : guest;
    return (
      <div className={`sb-player sb-${role} ${lead === role ? "lead" : ""} ${state.you === role ? "me" : ""}`}>
        <div className="sb-name">
          <span className={`dot ${pl?.online ? "on" : ""}`} />
          {pl ? pl.name : "In attesa…"}
          {state.you === role && <small> (tu)</small>}
        </div>
        <div className={`sb-total ${bump ? "bump" : ""}`}>{pl ? fmtPts(pl.total) : "–"}</div>
        {lead === role && <div className="crown">👑</div>}
      </div>
    );
  };
  return (
    <div className="scoreboard">
      {p("host")}
      <div className="sb-vs">VS</div>
      {p("guest")}
    </div>
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
