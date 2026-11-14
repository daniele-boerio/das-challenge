import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Trophy } from "lucide-react";
import { api } from "../api";
import { DiffBadge, LoadError } from "../components/bits";
import { fmtDate, fmtPts, ranked, seatColor } from "../lib/util";
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

      {data.stats.played > 0 && (
        <section className="card h2h-stats pop">
          <Trophy />
          <div>
            <b>
              {data.stats.won} {data.stats.won === 1 ? "vittoria" : "vittorie"}
            </b>
            <small>
              su {data.stats.played} {data.stats.played === 1 ? "sfida" : "sfide"}
            </small>
          </div>
        </section>
      )}

      {data.head_to_head.length > 0 && (
        <section className="card h2h-list">
          <h2 className="card-title">Testa a testa</h2>
          <small className="muted">In quante sfide giocate insieme hai fatto più punti tu o l'altro.</small>
          {data.head_to_head.map((h) => (
            <div key={h.name} className="h2h-row">
              <span>
                Tu vs <b>{h.name}</b>
              </span>
              <span className="h2h-n">
                {h.wins} – {h.losses}
              </span>
              <small className="muted">
                {h.matches} {h.matches === 1 ? "sfida" : "sfide"}
                {h.draws ? ` · ${h.draws} pari` : ""}
              </small>
            </div>
          ))}
        </section>
      )}

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
            <span className="gal-players">
              {ranked(m.players, (p) => p.total).map((p, i) => (
                <span key={p.seat} className={`gal-p ${m.winners.includes(p.seat) ? "win" : ""} ${m.you === p.seat ? "me" : ""}`}>
                  {i > 0 && " · "}
                  <b style={{ color: m.winners.includes(p.seat) ? seatColor(p.seat) : undefined }}>
                    {m.winners.includes(p.seat) && "👑 "}
                    {p.name}
                  </b>{" "}
                  {fmtPts(p.total)}
                </span>
              ))}
            </span>
            <small className="muted">{fmtDate(m.finished_at)}</small>
          </div>
          <div className="gal-rounds">
            {m.rounds.map((r, i) => (
              <div key={i} className="gal-round">
                <div className="gal-thumbs">
                  {r.image && <img src={r.image} alt="" loading="lazy" />}
                  {r.photos.slice(0, 5).map((ph) => (
                    <img key={ph} src={ph} alt="" loading="lazy" />
                  ))}
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
