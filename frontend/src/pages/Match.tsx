import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import confetti from "canvas-confetti";
import {
  Bomb,
  Brain,
  Camera,
  Check,
  Clock,
  Copy,
  Crown,
  Hourglass,
  Images,
  Play,
  RotateCcw,
  Share2,
  Shuffle,
  Sparkles,
  Upload,
} from "lucide-react";
import { api, prefs, tokens } from "../api";
import { useApp } from "../App";
import { Credit, DiffBadge, LoadError, Ring, Scoreboard, Zoomable } from "../components/bits";
import { useMatch, useServerNow, useWakeLock } from "../lib/hooks";
import { beep, buzz, DIFF_LABEL, fmtPts, fmtTime, other, share, shrinkImage } from "../lib/util";
import type { Difficulty, MatchState, PowerupKind, Role, RoundState } from "../types";

type Setter = (s: MatchState) => void;

export default function MatchPage() {
  const code = (useParams().code || "").toUpperCase();
  const { state, setState, error, refresh, offset, connected, relink } = useMatch(code);
  const now = useServerNow(offset);

  if (!state) {
    return error ? (
      <LoadError message={error} onRetry={refresh} />
    ) : (
      <div className="card center">
        <div className="spinner" /> Carico la sfida…
      </div>
    );
  }

  const r = state.rounds[state.rounds.length - 1];
  const live = state.status === "playing" && r && r.status === "sculpting";

  return (
    <div className="match">
      <div className="topbar">
        <Link to="/" className="chip">
          ← Home
        </Link>
        <span className="chip code-chip">#{state.code}</span>
        {!connected && <span className="chip warn">Riconnessione…</span>}
        {state.rounds.length > 0 && (
          <span className="chip">
            Round {Math.min(state.rounds.length, state.settings.rounds)}/{state.settings.rounds}
          </span>
        )}
      </div>
      {!(state.you === null && state.status === "lobby") && <Scoreboard state={state} />}

      {state.you === null && !state.players.guest && state.status === "lobby" ? (
        <JoinForm
          code={code}
          state={state}
          onJoined={(s) => {
            setState(s);
            relink();
          }}
        />
      ) : state.status === "lobby" ? (
        <Lobby state={state} />
      ) : state.status === "finished" ? (
        <Final state={state} />
      ) : live ? (
        <RoundPlay key={`${r.number}-${r.starts_at}`} state={state} r={r} now={now} setState={setState} />
      ) : state.status === "playing" && r?.status === "judging" ? (
        <Judging state={state} r={r} setState={setState} />
      ) : (
        <Between state={state} setState={setState} />
      )}
    </div>
  );
}

// ── entrare ───────────────────────────────────────────────────────────────────

function JoinForm({ code, state, onJoined }: { code: string; state: MatchState; onJoined: Setter }) {
  const { toast } = useApp();
  const [name, setName] = useState(prefs.name());
  const [busy, setBusy] = useState(false);
  async function go() {
    if (!name.trim()) return toast("Scrivi il tuo nome", "error");
    setBusy(true);
    try {
      prefs.setName(name.trim());
      const r = await api.join(code, name.trim());
      tokens.set(code, r.token);
      onJoined(r.state);
      buzz(60);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card pop center">
      <div className="big-emoji wobble">⚔️</div>
      <h2>
        <b className="c-host">{state.players.host.name}</b> ti sfida!
      </h2>
      <p className="muted">
        {state.settings.rounds} round · tema {state.settings.theme} ·{" "}
        {state.settings.judge === "voto" ? "voto reciproco" : state.settings.judge === "ai" ? "giudice AI" : "voto + AI"}
      </p>
      <label className="field">
        <span>Il tuo nome</span>
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} onKeyDown={(e) => e.key === "Enter" && go()} autoFocus />
      </label>
      <button className="btn btn-big btn-pink" disabled={busy} onClick={go}>
        {busy ? "Entro…" : "Accetto la sfida"}
      </button>
    </section>
  );
}

function Lobby({ state }: { state: MatchState }) {
  const { toast } = useApp();
  const url = `${location.origin}/p/${state.code}`;
  if (state.you !== "host") {
    return (
      <section className="card center">
        <div className="spinner" /> In attesa dell'avversario…
      </section>
    );
  }
  return (
    <section className="card pop center">
      <h2>Invita il tuo avversario</h2>
      <p className="muted">Mandale il link, oppure dille il codice:</p>
      <div className="big-code">{state.code}</div>
      <div className="btn-row">
        <button
          className="btn btn-yellow"
          onClick={async () => {
            const r = await share(url, `Ti sfido a DAS! Entra qui:`);
            if (r === "copied") toast("Link copiato", "good");
          }}
        >
          <Share2 size={18} /> Condividi link
        </button>
        <button
          className="btn"
          onClick={() => navigator.clipboard?.writeText(url).then(() => toast("Link copiato", "good"))}
        >
          <Copy size={18} /> Copia
        </button>
      </div>
      <div className="waiting">
        <div className="dots">
          <span />
          <span />
          <span />
        </div>
        Aspetto che entri…
      </div>
    </section>
  );
}

// ── fra un round e l'altro ────────────────────────────────────────────────────

function Between({ state, setState }: { state: MatchState; setState: Setter }) {
  const { toast } = useApp();
  const last = state.rounds[state.rounds.length - 1];
  const [diff, setDiff] = useState<Difficulty | "casuale">(state.suggested_difficulty || "facile");
  const [busy, setBusy] = useState(false);
  const isHost = state.you === "host";

  async function start() {
    setBusy(true);
    try {
      setState(await api.startRound(state.code, diff));
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {last?.status === "done" && <RoundResult state={state} r={last} />}
      <section className="card pop">
        <h2 className="card-title">
          <Play size={22} /> Round {state.rounds.length + 1}
        </h2>
        {isHost ? (
          <>
            <p className="muted">Scegli la difficoltà: più è alta, più punti vale.</p>
            <div className="diff-pick">
              {(["facile", "media", "difficile"] as Difficulty[]).map((d) => (
                <button key={d} className={`diff-card diff-${d} ${diff === d ? "on" : ""}`} onClick={() => setDiff(d)}>
                  <b>{DIFF_LABEL[d]}</b>
                  <small>
                    {state.settings.minutes[d]} min · ×{d === "facile" ? 1 : d === "media" ? 1.5 : 2}
                  </small>
                  {state.suggested_difficulty === d && <span className="tag">consigliata</span>}
                </button>
              ))}
              <button className={`diff-card diff-random ${diff === "casuale" ? "on" : ""}`} onClick={() => setDiff("casuale")}>
                <b>🎲 Casuale</b>
                <small>sorpresa</small>
              </button>
            </div>
            <button className="btn btn-big btn-yellow" disabled={busy} onClick={start}>
              {busy ? "Pesco la reference…" : "Via al round!"}
            </button>
          </>
        ) : (
          <div className="waiting">
            <div className="dots">
              <span />
              <span />
              <span />
            </div>
            {state.players.host.name} sta scegliendo il prossimo round…
          </div>
        )}
        {isHost && state.rounds.length > 0 && (
          <button
            className="link-btn"
            onClick={async () => {
              try {
                setState(await api.finish(state.code));
              } catch (e: any) {
                toast(e.message, "error");
              }
            }}
          >
            Chiudi qui la partita
          </button>
        )}
      </section>
    </>
  );
}

// ── il round ──────────────────────────────────────────────────────────────────

function RoundPlay({ state, r, now, setState }: { state: MatchState; r: RoundState; now: number; setState: Setter }) {
  const { toast } = useApp();
  const you = state.you;
  const opp = you ? other(you) : null;
  const before = now < r.starts_at;
  const myEnd = you ? r.end_at[you] : r.end_at.host;
  const left = myEnd - now;
  const total = Math.max(r.duration_s, myEnd - r.starts_at);
  const delivered = you ? r.delivered[you] : false;
  const memoryHidden = r.memory && r.memory_hide_at != null && now > r.memory_hide_at;
  const seenEvents = useRef(r.events.length);
  const warned = useRef({ min: left < 60, end: left <= 0 });

  useWakeLock(!delivered && !!you);

  // Bip all'ultimo minuto e allo scadere.
  useEffect(() => {
    if (before || delivered || !you) return;
    if (left < 60 && !warned.current.min) {
      warned.current.min = true;
      beep(660, 140, 2);
      buzz([100, 80, 100]);
    }
    if (left <= 0 && !warned.current.end) {
      warned.current.end = true;
      beep(440, 400, 3);
      buzz([300, 100, 300, 100, 300]);
    }
  }, [left, before, delivered, you]);

  // Power-up dell'avversario: lo si viene a sapere.
  useEffect(() => {
    const fresh = r.events.slice(seenEvents.current);
    seenEvents.current = r.events.length;
    for (const ev of fresh) {
      if (ev.by === you) continue;
      const who = state.players[ev.by]?.name;
      if (ev.kind === "sabotage") toast(`💣 ${who} ti ha sabotato: −1 minuto!`, "bad");
      if (ev.kind === "extra") toast(`⏰ ${who} si è preso 2 minuti in più`, "info");
      buzz(200);
    }
  }, [r.events, you, state.players, toast]);

  const frac = Math.max(0, left) / Math.max(1, total);

  return (
    <>
      {before && (
        <div className="countdown-overlay">
          <div className="countdown-num" key={Math.ceil(r.starts_at - now)}>
            {Math.max(1, Math.ceil(r.starts_at - now))}
          </div>
          <p>Preparate il DAS!</p>
        </div>
      )}

      <section className="card ref-card">
        <div className="ref-head">
          <DiffBadge d={r.difficulty} mult={r.multiplier} />
          {r.memory && (
            <span className="badge badge-memory">
              <Brain size={14} /> A memoria
            </span>
          )}
        </div>
        <h2 className="subject">{r.subject || "???"}</h2>
        {r.image && !memoryHidden ? (
          <>
            <Zoomable src={r.image} alt={r.subject || "reference"} className="ref-img" />
            {r.memory && r.memory_hide_at && (
              <div className="memory-bar">
                <Brain size={16} /> Sparisce tra {Math.max(0, Math.ceil(r.memory_hide_at - now))}s: memorizza!
              </div>
            )}
          </>
        ) : memoryHidden ? (
          <div className="ref-missing">
            <Brain size={42} />
            <p>La reference è sparita. Ora vai a memoria!</p>
          </div>
        ) : (
          <div className="ref-missing">
            <span className="big-emoji">🖼️</span>
            <p>Foto non trovata: scolpite il soggetto come ve lo immaginate.</p>
          </div>
        )}
        {!memoryHidden && <Credit a={r.attribution} />}
      </section>

      {you && (r.handicaps[you] || (opp && r.handicaps[opp])) && (
        <section className="handicaps">
          {r.handicaps[you] && (
            <div className="handicap-card mine">
              <small>🎲 Il tuo handicap</small>
              <b>{r.handicaps[you]}</b>
            </div>
          )}
          {opp && r.handicaps[opp] && (
            <div className="handicap-card">
              <small>Handicap di {state.players[opp]?.name}</small>
              <b>{r.handicaps[opp]}</b>
            </div>
          )}
        </section>
      )}

      <section className="card timer-card">
        {delivered ? (
          <div className="delivered">
            <Check size={36} />
            <div>
              <b>Consegnata!</b>
              <small>
                {opp && r.delivered[opp]
                  ? "Ci siete tutti e due…"
                  : `Aspetto la foto di ${opp ? state.players[opp]?.name : ""}`}
              </small>
            </div>
          </div>
        ) : (
          <Ring frac={frac} danger={left < 60}>
            <span className="time">{left > 0 ? fmtTime(left) : "0:00"}</span>
            <small>{left > 0 ? "rimasti" : "tempo scaduto!"}</small>
          </Ring>
        )}
        {opp && (
          <div className={`opp-status ${r.delivered[opp] ? "done" : ""}`}>
            {r.delivered[opp] ? (
              <>
                <Check size={16} /> {state.players[opp]?.name} ha consegnato
              </>
            ) : (
              <>
                <Hourglass size={16} /> {state.players[opp]?.name} sta scolpendo ·{" "}
                {fmtTime(r.end_at[opp] - now)}
              </>
            )}
          </div>
        )}
      </section>

      {you && !delivered && !before && state.settings.powerups && (
        <Powerups state={state} r={r} now={now} setState={setState} />
      )}

      {you && !before && <Deliver state={state} r={r} timeUp={left <= 0} setState={setState} />}
    </>
  );
}

function Powerups({ state, r, now, setState }: { state: MatchState; r: RoundState; now: number; setState: Setter }) {
  const { toast } = useApp();
  const you = state.you!;
  const opp = other(you);
  const pu = state.players[you]?.powerups || {};
  const [confirm, setConfirm] = useState<PowerupKind | null>(null);
  const [busy, setBusy] = useState(false);
  const rerollOpen = now - r.starts_at < 120 && !r.delivered.host && !r.delivered.guest;

  async function use(kind: PowerupKind) {
    setBusy(true);
    try {
      setState(await api.powerup(state.code, kind));
      buzz(80);
      toast(
        kind === "extra"
          ? "⏰ +2 minuti per te!"
          : kind === "sabotage"
            ? `💣 −1 minuto a ${state.players[opp]?.name}!`
            : "🔀 Nuova reference: si riparte!",
        "good",
      );
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  }

  const items: { kind: PowerupKind; icon: React.ReactNode; label: string; disabled: boolean }[] = [
    { kind: "extra", icon: <Clock />, label: "+2 min", disabled: !pu.extra },
    { kind: "sabotage", icon: <Bomb />, label: `−1 min a ${state.players[opp]?.name || ""}`, disabled: !pu.sabotage || r.delivered[opp] },
    { kind: "reroll", icon: <Shuffle />, label: "Cambia soggetto", disabled: !pu.reroll || !rerollOpen },
  ];

  return (
    <section className="powerups">
      {items.map((it) => (
        <button
          key={it.kind}
          className={`pu pu-${it.kind} ${confirm === it.kind ? "armed" : ""}`}
          disabled={it.disabled || busy}
          onClick={() => (confirm === it.kind ? use(it.kind) : setConfirm(it.kind))}
        >
          {it.icon}
          <span>{confirm === it.kind ? "Sicuro? Tocca ancora" : it.label}</span>
          {!pu[it.kind] && <em>usato</em>}
        </button>
      ))}
      {confirm === "reroll" && <p className="muted small">Il cambio fa ripartire il round per tutti e due, con un soggetto nuovo.</p>}
    </section>
  );
}

function Deliver({ state, r, timeUp, setState }: { state: MatchState; r: RoundState; timeUp: boolean; setState: Setter }) {
  const { toast } = useApp();
  const you = state.you!;
  const [file, setFile] = useState<Blob | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const cam = useRef<HTMLInputElement>(null);
  const lib = useRef<HTMLInputElement>(null);
  const mine = r.photos[you];

  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview]);

  async function pick(f: File | undefined) {
    if (!f) return;
    const small = await shrinkImage(f);
    setFile(small);
    setPreview(URL.createObjectURL(small));
  }

  async function send() {
    if (!file) return;
    setProgress(0);
    try {
      setState(await api.upload(state.code, r.number, file, setProgress));
      setFile(null);
      setPreview(null);
      buzz(60);
      toast("📸 Foto consegnata!", "good");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setProgress(null);
    }
  }

  return (
    <section className={`card deliver ${timeUp && !mine ? "pulse" : ""}`}>
      <h3>{mine ? "La tua foto" : timeUp ? "Tempo! Fotografa la tua creazione" : "Hai finito? Consegna la foto"}</h3>
      {(preview || mine) && <img className="preview" src={preview || mine!} alt="la tua creazione" />}
      <input ref={cam} type="file" accept="image/*" capture="environment" hidden onChange={(e) => pick(e.target.files?.[0])} />
      <input ref={lib} type="file" accept="image/*" hidden onChange={(e) => pick(e.target.files?.[0])} />
      {progress != null ? (
        <div className="progress">
          <div style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>
      ) : preview ? (
        <div className="btn-row">
          <button className="btn btn-big btn-yellow" onClick={send}>
            <Upload size={20} /> {mine ? "Sostituisci" : "Consegna"}
          </button>
          <button className="btn" onClick={() => (setFile(null), setPreview(null))}>
            Rifai
          </button>
        </div>
      ) : (
        <div className="btn-row">
          <button className="btn btn-pink" onClick={() => cam.current?.click()}>
            <Camera size={20} /> Scatta
          </button>
          <button className="btn" onClick={() => lib.current?.click()}>
            <Images size={20} /> Dalla galleria
          </button>
        </div>
      )}
      {mine && !preview && <small className="muted">Puoi sostituirla finché anche l'altro non consegna.</small>}
    </section>
  );
}

// ── giudizio ──────────────────────────────────────────────────────────────────

function Compare({ state, r }: { state: MatchState; r: RoundState }) {
  return (
    <div className="compare">
      <figure className="cmp-ref">
        {r.image ? <Zoomable src={r.image} alt="reference" /> : <div className="ref-missing small">{r.subject}</div>}
        <figcaption>Reference</figcaption>
      </figure>
      {(["host", "guest"] as Role[]).map((who) => (
        <figure key={who} className={`cmp-${who}`}>
          {r.photos[who] ? <Zoomable src={r.photos[who]!} alt={state.players[who]?.name || who} /> : <div className="ref-missing small">?</div>}
          <figcaption>
            {state.players[who]?.name}
            {r.points && <b> {fmtPts(r.points[who])} pt</b>}
          </figcaption>
        </figure>
      ))}
    </div>
  );
}

function Judging({ state, r, setState }: { state: MatchState; r: RoundState; setState: Setter }) {
  const { toast } = useApp();
  const you = state.you;
  const opp = you ? other(you) : null;
  const [value, setValue] = useState(5);
  const [busy, setBusy] = useState(false);
  const iVoted = you ? r.votes[`${you}_voted` as "host_voted"] : true;
  const oppVoted = opp ? r.votes[`${opp}_voted` as "host_voted"] : true;

  async function send() {
    setBusy(true);
    try {
      setState(await api.vote(state.code, r.number, value));
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  const face = value >= 9 ? "🤩" : value >= 7 ? "😍" : value >= 5 ? "🙂" : value >= 3 ? "😬" : "💀";

  return (
    <>
      <section className="card">
        <h2 className="card-title">
          ⚖️ {r.subject} <DiffBadge d={r.difficulty} mult={r.multiplier} />
        </h2>
        <Compare state={state} r={r} />
      </section>

      {r.ai.status === "pending" && (
        <section className="card center ai-thinking">
          <div className="judge-anim">🧐</div>
          <b>Il giudice sta osservando le vostre opere…</b>
          <small className="muted">Di solito ci mette meno di un minuto</small>
        </section>
      )}
      {r.ai.status === "failed" && r.ai.error && <section className="card warn-card">{r.ai.error}</section>}

      {r.votes.needed && you && opp && (
        <section className="card pop center">
          {!iVoted ? (
            <>
              <h3>
                Quanto si avvicina <b className={`c-${opp}`}>{state.players[opp]?.name}</b> alla reference?
              </h3>
              <div className="vote-face">{face}</div>
              <div className="vote-num">{fmtPts(value)}</div>
              <input
                className="slider"
                type="range"
                min={0}
                max={10}
                step={0.5}
                value={value}
                onChange={(e) => setValue(Number(e.target.value))}
              />
              <button className="btn btn-big btn-yellow" disabled={busy} onClick={send}>
                Vota
              </button>
              <small className="muted">Il voto resta segreto finché non avete votato tutti e due.</small>
            </>
          ) : (
            <div className="waiting">
              <Check /> Hai votato {fmtPts(r.votes.mine)}.{" "}
              {oppVoted ? "Calcolo i punti…" : `Aspetto il voto di ${state.players[opp]?.name}…`}
            </div>
          )}
        </section>
      )}
    </>
  );
}

function RoundResult({ state, r }: { state: MatchState; r: RoundState }) {
  if (!r.points || !r.scores) return null;
  const w = r.points.host === r.points.guest ? null : r.points.host > r.points.guest ? "host" : "guest";
  const ai = r.ai.result;
  return (
    <section className="card result reveal">
      <h2 className="card-title">
        Round {r.number}: {r.subject} <DiffBadge d={r.difficulty} mult={r.multiplier} />
      </h2>
      <div className="round-winner">
        {w ? (
          <>
            <Crown /> Round a <b className={`c-${w}`}>{state.players[w]?.name}</b>
          </>
        ) : (
          "Pareggio!"
        )}
      </div>
      <Compare state={state} r={r} />
      {ai?.verdict && <blockquote className="verdict">“{ai.verdict}”</blockquote>}
      <div className="breakdown">
        {(["host", "guest"] as Role[]).map((who) => (
          <div key={who} className={`bd bd-${who}`}>
            <b>{state.players[who]?.name}</b>
            <div className="bd-score">
              {fmtPts(r.scores![who])}
              <small>/10 × {r.multiplier}</small> = <span>{fmtPts(r.points![who])}</span>
            </div>
            {r.votes.host != null && (
              <small className="muted">voto ricevuto: {fmtPts(who === "host" ? r.votes.guest : r.votes.host)}</small>
            )}
            {ai && (
              <p className="ai-comment">
                <Sparkles size={14} /> {ai[who].comment} <small>({fmtPts(ai[who].score)})</small>
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

// ── fine partita ──────────────────────────────────────────────────────────────

function Final({ state }: { state: MatchState }) {
  const { toast } = useApp();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const w = state.winner;
  const fired = useRef(false);
  const fresh = state.finished_at != null && Date.now() / 1000 - state.finished_at < 600;

  useEffect(() => {
    if (fired.current || !fresh || !w) return;
    fired.current = true;
    const colors = ["#ffd23f", "#ff5d8f", "#3bceac", "#7b61ff"];
    confetti({ particleCount: 160, spread: 90, origin: { y: 0.3 }, colors });
    window.setTimeout(() => confetti({ particleCount: 120, angle: 60, spread: 70, origin: { x: 0 }, colors }), 400);
    window.setTimeout(() => confetti({ particleCount: 120, angle: 120, spread: 70, origin: { x: 1 }, colors }), 700);
  }, [fresh, w]);

  const rematchMine = useMemo(() => (state.rematch_code ? !!tokens.get(state.rematch_code) : false), [state.rematch_code]);

  async function rematch() {
    setBusy(true);
    try {
      if (state.rematch_code) {
        if (!rematchMine) {
          const r = await api.join(state.rematch_code, state.you ? state.players[state.you]!.name : prefs.name() || "Sfidante");
          tokens.set(state.rematch_code, r.token);
        }
        nav(`/p/${state.rematch_code}`);
      } else {
        const r = await api.rematch(state.code);
        tokens.set(r.code, r.token);
        nav(`/p/${r.code}`);
      }
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  const last = state.rounds[state.rounds.length - 1];
  return (
    <>
      {fresh && last?.status === "done" && <RoundResult state={state} r={last} />}
      <section className="card pop center final">
        <div className="trophy">🏆</div>
        {w === "pari" ? (
          <h1 className="title">Pareggio!</h1>
        ) : w ? (
          <h1 className="title">
            Vince <span className={`c-${w}`}>{state.players[w]?.name}</span>
          </h1>
        ) : null}
        <p className="final-score">
          {fmtPts(state.players.host.total)} – {fmtPts(state.players.guest?.total)}
        </p>
        {state.you && (
          <button className="btn btn-big btn-yellow" disabled={busy} onClick={rematch}>
            <RotateCcw size={20} />
            {state.rematch_code ? (rematchMine ? "Vai alla rivincita" : "Entra nella rivincita!") : "Rivincita"}
          </button>
        )}
        <Link to="/galleria" className="link-btn">
          Vai alla galleria
        </Link>
      </section>
      <section className="recap">
        {state.rounds.map((r) => (
          <div key={r.number} className="card recap-round">
            <div className="recap-head">
              <b>
                {r.number}. {r.subject}
              </b>
              <DiffBadge d={r.difficulty} mult={r.multiplier} />
            </div>
            <Compare state={state} r={r} />
            {r.ai.result?.verdict && <p className="muted small">“{r.ai.result.verdict}”</p>}
          </div>
        ))}
      </section>
    </>
  );
}
