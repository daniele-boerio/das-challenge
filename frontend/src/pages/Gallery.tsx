import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Trophy } from "lucide-react";
import { api } from "../api";
import { DiffBadge, LoadError } from "../components/bits";
import { fmtDate, fmtPts } from "../lib/util";
import type { Gallery } from "../types";

export default function GalleryPage() {
  const [data, setData] = useState<Gallery | null>(null);
  const [error, setError] = useState<{ msg: string; status: number } | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .gallery()
      .then(setData)
      .catch((e) => setError({ msg: e.message, status: e.status }));
  }, []);
  useEffect(load, [load]);

  if (error) return <LoadError message={error.msg} onRetry={load} />;
  if (!data)
    return (
      <div className="card center">
        <div className="spinner" /> Carico la galleria…
      </div>
    );

  return (
    <div className="gallery">
      <div className="topbar">
        <Link to="/" className="chip">
          ← Home
        </Link>
      </div>
      <h1 className="title small-title">Galleria</h1>
      <p className="gal-note">Qui ci sono solo le sfide che hai giocato tu.</p>

      {data.head_to_head.map((h) => {
        const [a, b] = h.players;
        return (
          <section key={h.players.join("|")} className="card h2h pop">
            <Trophy />
            <div className="h2h-row">
              <div>
                <b>{a}</b>
                <span className="h2h-n">{h.wins[a] || 0}</span>
              </div>
              <small>
                {h.matches} sfide{h.draws ? ` · ${h.draws} pari` : ""}
              </small>
              <div>
                <span className="h2h-n">{h.wins[b] || 0}</span>
                <b>{b}</b>
              </div>
            </div>
          </section>
        );
      })}

      {data.matches.length === 0 && (
        <section className="card center">
          <div className="big-emoji">🏺</div>
          <p>Ancora nessuna sfida finita. La prima è la più bella!</p>
          <Link to="/" className="btn btn-yellow">
            Crea una sfida
          </Link>
        </section>
      )}

      {data.matches.map((m) => (
        <Link key={m.code} to={`/p/${m.code}`} className="card gal-match">
          <div className="gal-head">
            <span>
              <b className={m.winner === "host" ? "c-host" : ""}>{m.host.name}</b> {fmtPts(m.host.total)} –{" "}
              {fmtPts(m.guest.total)} <b className={m.winner === "guest" ? "c-guest" : ""}>{m.guest.name}</b>
            </span>
            <small className="muted">{fmtDate(m.finished_at)}</small>
          </div>
          <div className="gal-rounds">
            {m.rounds.map((r, i) => (
              <div key={i} className="gal-round">
                <div className="gal-thumbs">
                  {r.image && <img src={r.image} alt="" loading="lazy" />}
                  {r.host_photo && <img src={r.host_photo} alt="" loading="lazy" />}
                  {r.guest_photo && <img src={r.guest_photo} alt="" loading="lazy" />}
                </div>
                <small>
                  {r.subject} <DiffBadge d={r.difficulty} />
                </small>
              </div>
            ))}
          </div>
        </Link>
      ))}
    </div>
  );
}
