import { useEffect, useRef, useState } from "react";
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
  Lock,
  Play,
  RotateCcw,
  Share2,
  Shuffle,
  Sparkles,
  Timer,
  Upload,
  Users,
  Zap,
} from "lucide-react";
import { api } from "../api";
import { useApp } from "../App";
import { Credit, DiffBadge, LoadError, Ring, Scoreboard, Who, Zoomable } from "../components/bits";
import { useMatch, useServerNow, useWakeLock } from "../lib/hooks";
import { beep, buzz, DIFF_LABEL, fmtPts, fmtTime, joinNames, nameOf, ranked, seatColor, share, shrinkImage } from "../lib/util";
import type { Difficulty, EntryState, MatchState, PowerupKind, RoundState } from "../types";

type Setter = (s: MatchState) => void;

const judgeLabel = (j: string) => (j === "voto" ? "voto fra voi" : j === "ai" ? "giudice AI" : "voto + AI");
const timerLabel = (t: string) => (t === "rigido" ? "timer rigido" : t === "nessuno" ? "senza tempo" : "timer libero");

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
      {state.you !== null && <Scoreboard state={state} />}

      {state.you === null && (state.joinable ?? state.status === "lobby") ? (
        <JoinForm
          code={code}
          state={state}
          onJoined={(s) => {
            setState(s);
            relink(); // il WebSocket era aperto da «ospite»: lo riapro da giocatore
          }}
        />
      ) : state.status === "lobby" ? (
        <Lobby state={state} setState={setState} />
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

function Rules({ state }: { state: MatchState }) {
  const s = state.settings;
  return (
    <p className="muted rules">
      {s.rounds} round · tema {s.theme} · {judgeLabel(s.judge)} · {timerLabel(s.timer)}
      {s.rush && ` · rincorsa dopo ${s.rush_after} consegne (${s.rush_minutes} min)`}
      {s.colors ? " · paste colorate" : " · solo DAS bianco"}
    </p>
  );
}

function JoinForm({ code, state, onJoined }: { code: string; state: MatchState; onJoined: Setter }) {
  const { toast } = useApp();
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    try {
      const r = await api.join(code);
      onJoined(r.state);
      buzz(60);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }
  const others = state.players.slice(1).map((p) => p.name);
  return (
    <section className="card pop center">
      <div className="big-emoji wobble">⚔️</div>
      <h2>
        <Who state={state} seat={0} /> ti sfida!
      </h2>
      {others.length > 0 && <p>Ci sono già {joinNames(others)}.</p>}
      {state.status !== "lobby" && (
        <p>
          <b>La partita è già cominciata:</b> entri adesso e giochi dal prossimo round.
        </p>
      )}
      <Rules state={state} />
      <button className="btn btn-big btn-pink" disabled={busy} onClick={go}>
        {busy ? "Entro…" : "Accetto la sfida"}
      </button>
      <small className="muted">
        {state.players.length}/{state.max_players} giocatori
      </small>
    </section>
  );
}

function PlayerList({ state }: { state: MatchState }) {
  return (
    <ul className="player-list">
      {state.players.map((p) => (
        <li key={p.seat} style={{ ["--pc" as any]: seatColor(p.seat) }}>
          <span className={`dot ${p.online ? "on" : ""}`} />
          <b>{p.name}</b>
          {p.seat === 0 && <small>ha creato la sfida</small>}
          {p.seat === state.you && <small>(tu)</small>}
        </li>
      ))}
      {Array.from({ length: Math.max(0, Math.min(2, state.max_players - state.players.length)) }).map((_, i) => (
        <li key={`free-${i}`} className="free">
          <span className="dot" /> posto libero
        </li>
      ))}
    </ul>
  );
}

function Lobby({ state, setState }: { state: MatchState; setState: Setter }) {
  const { toast } = useApp();
  const url = `${location.origin}/p/${state.code}`;
  const isHost = state.you === 0;
  const full = state.players.length >= state.max_players;
  return (
    <>
      <section className="card pop center">
        <h2 className="card-title center-title">
          <Users size={22} /> Sala d'attesa · {state.players.length}/{state.max_players}
        </h2>
        <PlayerList state={state} />
        {!full && (
          <>
            <p className="muted">Manda il link agli avversari, oppure dite il codice:</p>
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
          </>
        )}
        <Rules state={state} />
        {!isHost && (
          <div className="waiting">
            <div className="dots">
              <span />
              <span />
              <span />
            </div>
            Sei dentro! Aspetta che {nameOf(state, 0)} faccia partire la sfida.
          </div>
        )}
      </section>
      {isHost &&
        (state.players.length < 2 ? (
          <section className="card center">
            <div className="waiting">
              <div className="dots">
                <span />
                <span />
                <span />
              </div>
              Aspetto almeno un avversario…
            </div>
          </section>
        ) : (
          <StartRound state={state} setState={setState} first />
        ))}
    </>
  );
}

// ── fra un round e l'altro ────────────────────────────────────────────────────

function StartRound({ state, setState, first }: { state: MatchState; setState: Setter; first?: boolean }) {
  const { toast } = useApp();
  const [diff, setDiff] = useState<Difficulty | "casuale">(state.suggested_difficulty || "facile");
  const [busy, setBusy] = useState(false);
  const timed = state.settings.timer !== "nessuno";

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
    <section className="card pop">
      <h2 className="card-title">
        <Play size={22} /> Round {state.rounds.length + 1}
      </h2>
      <p className="muted">
        Scegli la difficoltà: più è alta, più punti vale.
        {first && " Quando parte, nessun altro può più entrare."}
      </p>
      <div className="diff-pick">
        {(["facile", "media", "difficile"] as Difficulty[]).map((d) => (
          <button key={d} className={`diff-card diff-${d} ${diff === d ? "on" : ""}`} onClick={() => setDiff(d)}>
            <b>{DIFF_LABEL[d]}</b>
            <small>
              {timed ? `${state.settings.minutes[d]} min · ` : ""}×{d === "facile" ? 1 : d === "media" ? 1.5 : 2}
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
        {busy ? "Pesco la reference…" : first ? "Via alla sfida!" : "Via al round!"}
      </button>
      {!first && state.rounds.length > 0 && (
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
  );
}

function Between({ state, setState }: { state: MatchState; setState: Setter }) {
  const last = state.rounds[state.rounds.length - 1];
  return (
    <>
      {last?.status === "done" && <RoundResult state={state} r={last} />}
      {state.you === 0 ? (
        <StartRound state={state} setState={setState} />
      ) : (
        <section className="card center">
          <div className="waiting">
            <div className="dots">
              <span />
              <span />
              <span />
            </div>
            {nameOf(state, 0)} sta scegliendo il prossimo round…
          </div>
        </section>
      )}
    </>
  );
}

// ── il round ──────────────────────────────────────────────────────────────────

function RoundPlay({ state, r, now, setState }: { state: MatchState; r: RoundState; now: number; setState: Setter }) {
  const { toast } = useApp();
  const you = state.you;
  const me = r.entries.find((e) => e.seat === you) || null;
  const plays = me !== null;
  const others = r.entries.filter((e) => e.seat !== you);
  const before = now < r.starts_at;
  const delivered = me?.delivered ?? false;
  const memoryHidden = r.memory && r.memory_hide_at != null && now > r.memory_hide_at;
  const seenEvents = useRef(r.events.length);
  const seenRush = useRef(r.rush_end_at);

  // Il tempo che conta per me: il mio timer o la rincorsa. Senza nessuno dei due, il cronometro.
  const dl = me?.deadline ?? (!plays ? r.entries[0]?.deadline ?? null : null);
  const left = dl != null ? dl - now : Infinity;
  const closeLeft = me?.close_at != null ? me.close_at - now : null;
  const closed = closeLeft != null && closeLeft <= 0;
  const warned = useRef({ min: left < 60, end: left <= 0 });

  useWakeLock(!delivered && plays);

  // Bip all'ultimo minuto e allo scadere.
  useEffect(() => {
    if (before || delivered || !plays || dl == null) return;
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
  }, [left, before, delivered, plays, dl]);

  // Power-up degli altri: lo si viene a sapere.
  useEffect(() => {
    const fresh = r.events.slice(seenEvents.current);
    seenEvents.current = r.events.length;
    for (const ev of fresh) {
      if (ev.by === you) continue;
      const who = nameOf(state, ev.by);
      if (ev.kind === "sabotage") {
        if (ev.target === you) toast(`💣 ${who} ti ha sabotato: −1 minuto!`, "bad");
        else toast(`💣 ${who} ha sabotato ${nameOf(state, ev.target)}`, "info");
      }
      if (ev.kind === "extra") toast(`⏰ ${who} si è preso 2 minuti in più`, "info");
      buzz(200);
    }
  }, [r.events, you, state, toast]);

  // Parte la rincorsa: chi non ha consegnato deve saperlo subito.
  useEffect(() => {
    if (r.rush_end_at && !seenRush.current) {
      seenRush.current = r.rush_end_at;
      if (!delivered && plays) {
        toast(`⚡ Rincorsa! Hai ${state.settings.rush_minutes} minuti per finire`, "bad");
        beep(880, 160, 3);
        buzz([200, 80, 200]);
      }
    }
  }, [r.rush_end_at, delivered, plays, state.settings.rush_minutes, toast]);

  // L'anello si svuota sulla durata di ciò che sta finendo: il round o la rincorsa.
  const span = r.rush_end_at && dl === r.rush_end_at ? state.settings.rush_minutes * 60 : dl != null ? dl - r.starts_at : 1;
  const total = Math.max(1, span);
  const frac = dl != null ? Math.max(0, left) / total : 1;
  const doneOthers = others.filter((e) => e.delivered).map((e) => nameOf(state, e.seat));

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
          {state.settings.timer === "rigido" && (
            <span className="badge badge-strict">
              <Lock size={13} /> Timer rigido
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

      {r.rush_end_at && (
        <section className={`card rush-card ${delivered ? "" : "pulse"}`}>
          <Zap size={22} />
          <div>
            <b>Rincorsa!</b>
            <small>
              {joinNames(r.entries.filter((e) => e.delivered).map((e) => (e.seat === you ? "tu" : nameOf(state, e.seat))))}{" "}
              {r.entries.filter((e) => e.delivered).length === 1 ? "ha" : "hanno"} consegnato: chi manca ha tempo fino a{" "}
              {fmtTime(Math.max(0, r.rush_end_at - now))}
            </small>
          </div>
        </section>
      )}

      {r.entries.some((e) => e.handicap) && (
        <section className="handicaps">
          {r.entries
            .filter((e) => e.handicap)
            .map((e) => (
              <div key={e.seat} className={`handicap-card ${e.seat === you ? "mine" : ""}`}>
                <small>{e.seat === you ? "🎲 Il tuo handicap" : `Handicap di ${nameOf(state, e.seat)}`}</small>
                <b>{e.handicap}</b>
              </div>
            ))}
        </section>
      )}

      <section className="card timer-card">
        {delivered ? (
          <div className="delivered">
            <Check size={36} />
            <div>
              <b>Consegnata!</b>
              <small>
                {others.every((e) => e.delivered)
                  ? "Ci siete tutti…"
                  : `Aspetto ${joinNames(others.filter((e) => !e.delivered).map((e) => nameOf(state, e.seat)))}`}
              </small>
            </div>
          </div>
        ) : dl == null ? (
          <Ring frac={1}>
            <span className="time">{fmtTime(Math.max(0, now - r.starts_at))}</span>
            <small>senza tempo</small>
          </Ring>
        ) : (
          <Ring frac={frac} danger={left < 60}>
            <span className="time">{left > 0 ? fmtTime(left) : closeLeft != null && !closed ? fmtTime(closeLeft) : "0:00"}</span>
            <small>
              {left > 0 ? "rimasti" : closed ? "consegne chiuse" : closeLeft != null ? "per la foto!" : "tempo scaduto!"}
            </small>
          </Ring>
        )}
        <ul className="opp-list">
          {others.map((e) => (
            <OtherStatus key={e.seat} state={state} e={e} now={now} />
          ))}
        </ul>
        {!delivered && doneOthers.length > 0 && state.settings.rush && !r.rush_end_at && (
          <small className="muted">
            ⚡ Quando avranno consegnato in {state.settings.rush_after}, chi manca avrà {state.settings.rush_minutes} minuti
          </small>
        )}
      </section>

      {you !== null && !plays && (
        <section className="card center">
          <Hourglass /> Sei entrato a round cominciato: guardi questo, e giochi dal prossimo.
        </section>
      )}

      {plays && !delivered && !before && state.settings.powerups && (
        <Powerups state={state} r={r} now={now} setState={setState} />
      )}

      {plays && !before && !closed && (
        <Deliver state={state} r={r} timeUp={dl != null && left <= 0} strict={closeLeft != null} setState={setState} />
      )}
      {plays && closed && !delivered && (
        <section className="card center warn-card">
          <Lock /> Tempo scaduto: le consegne sono chiuse. Questo round vale 0 per te, ma potrai votare gli altri.
        </section>
      )}
    </>
  );
}

function OtherStatus({ state, e, now }: { state: MatchState; e: EntryState; now: number }) {
  return (
    <li className={`opp-status ${e.delivered ? "done" : ""}`} style={{ ["--pc" as any]: seatColor(e.seat) }}>
      {e.delivered ? (
        <>
          <Check size={16} /> {nameOf(state, e.seat)} ha consegnato
        </>
      ) : (
        <>
          <Hourglass size={16} /> {nameOf(state, e.seat)} sta scolpendo
          {e.deadline != null && <> · {fmtTime(e.deadline - now)}</>}
        </>
      )}
    </li>
  );
}

function Powerups({ state, r, now, setState }: { state: MatchState; r: RoundState; now: number; setState: Setter }) {
  const { toast } = useApp();
  const you = state.you!;
  const pu = state.players.find((p) => p.seat === you)?.powerups || {};
  const [confirm, setConfirm] = useState<PowerupKind | null>(null);
  const [busy, setBusy] = useState(false);
  const rerollOpen = now - r.starts_at < 120 && !r.entries.some((e) => e.delivered);
  const targets = r.entries.filter((e) => e.seat !== you && !e.delivered && e.end_at != null && e.end_at > now);
  const single = r.entries.length === 2;

  async function use(kind: PowerupKind, target?: number) {
    setBusy(true);
    try {
      setState(await api.powerup(state.code, kind, target));
      buzz(80);
      toast(
        kind === "extra"
          ? "⏰ +2 minuti per te!"
          : kind === "sabotage"
            ? `💣 −1 minuto a ${nameOf(state, target ?? targets[0]?.seat)}!`
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

  const items: { kind: PowerupKind; icon: React.ReactNode; label: string; disabled: boolean }[] = [];
  if (r.timed) {
    items.push({ kind: "extra", icon: <Clock />, label: "+2 min", disabled: !pu.extra });
    items.push({
      kind: "sabotage",
      icon: <Bomb />,
      label: single ? `−1 min a ${nameOf(state, r.entries.find((e) => e.seat !== you)?.seat)}` : "−1 min a…",
      disabled: !pu.sabotage || targets.length === 0,
    });
  }
  items.push({ kind: "reroll", icon: <Shuffle />, label: "Cambia soggetto", disabled: !pu.reroll || !rerollOpen });

  return (
    <section className="powerups-wrap">
      <div className="powerups">
        {items.map((it) => (
          <button
            key={it.kind}
            className={`pu pu-${it.kind} ${confirm === it.kind ? "armed" : ""}`}
            disabled={it.disabled || busy}
            onClick={() => {
              if (confirm !== it.kind) return setConfirm(it.kind);
              if (it.kind === "sabotage" && !single) return; // si sceglie sotto
              use(it.kind);
            }}
          >
            {it.icon}
            <span>{confirm === it.kind ? (it.kind === "sabotage" && !single ? "Chi?" : "Sicuro? Tocca ancora") : it.label}</span>
            {!pu[it.kind] && <em>usato</em>}
          </button>
        ))}
      </div>
      {confirm === "sabotage" && !single && (
        <div className="target-pick">
          {targets.map((e) => (
            <button
              key={e.seat}
              className="btn btn-small"
              style={{ background: seatColor(e.seat) }}
              disabled={busy}
              onClick={() => use("sabotage", e.seat)}
            >
              <Bomb size={16} /> {nameOf(state, e.seat)}
            </button>
          ))}
          <button className="link-btn" onClick={() => setConfirm(null)}>
            annulla
          </button>
        </div>
      )}
      {confirm === "reroll" && <p className="muted small">Il cambio fa ripartire il round per tutti, con un soggetto nuovo.</p>}
    </section>
  );
}

function Deliver({
  state,
  r,
  timeUp,
  strict,
  setState,
}: {
  state: MatchState;
  r: RoundState;
  timeUp: boolean;
  strict: boolean;
  setState: Setter;
}) {
  const { toast } = useApp();
  const you = state.you!;
  const [file, setFile] = useState<Blob | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const cam = useRef<HTMLInputElement>(null);
  const lib = useRef<HTMLInputElement>(null);
  const mine = r.entries.find((e) => e.seat === you)?.photo || null;

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
      <h3>
        {mine
          ? "La tua foto"
          : timeUp
            ? strict
              ? "Tempo! Hai un minuto per consegnare"
              : "Tempo! Fotografa la tua creazione"
            : "Hai finito? Consegna la foto"}
      </h3>
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
      {mine && !preview && <small className="muted">Puoi sostituirla finché non hanno consegnato tutti.</small>}
      {!mine && !timeUp && state.settings.timer === "rigido" && (
        <small className="muted">
          <Timer size={13} /> Timer rigido: allo scadere hai {Math.round(state.grace_s / 60)} minuto per consegnare, poi si chiude.
        </small>
      )}
    </section>
  );
}

// ── giudizio ──────────────────────────────────────────────────────────────────

function Compare({ state, r }: { state: MatchState; r: RoundState }) {
  const entries = r.status === "done" ? ranked(r.entries, (e) => e.points ?? 0) : r.entries;
  return (
    <div className={`compare ${r.entries.length > 2 ? "many" : ""}`}>
      <figure className="cmp-ref">
        {r.image ? <Zoomable src={r.image} alt="reference" /> : <div className="ref-missing small">{r.subject}</div>}
        <figcaption>Reference</figcaption>
      </figure>
      {entries.map((e) => (
        <figure key={e.seat} style={{ ["--pc" as any]: seatColor(e.seat) }}>
          {e.photo ? (
            <Zoomable src={e.photo} alt={nameOf(state, e.seat)} />
          ) : (
            <div className="ref-missing small no-photo">non consegnata</div>
          )}
          <figcaption>
            {nameOf(state, e.seat)}
            {e.points != null && <b> {fmtPts(e.points)} pt</b>}
          </figcaption>
        </figure>
      ))}
    </div>
  );
}

const face = (v: number) => (v >= 9 ? "🤩" : v >= 7 ? "😍" : v >= 5 ? "🙂" : v >= 3 ? "😬" : "💀");

function Judging({ state, r, setState }: { state: MatchState; r: RoundState; setState: Setter }) {
  const { toast } = useApp();
  const you = state.you;
  const targets = r.votes.targets;
  const [values, setValues] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const plays = you !== null && r.entries.some((e) => e.seat === you);
  const iVoted = plays && r.votes.voted.includes(you!);
  const missing = state.players.filter((p) => r.entries.some((e) => e.seat === p.seat) && !r.votes.voted.includes(p.seat));

  async function send() {
    setBusy(true);
    try {
      const votes = Object.fromEntries(targets.map((t) => [String(t), values[t] ?? 5]));
      setState(await api.vote(state.code, r.number, votes));
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function closeVotes() {
    try {
      setState(await api.closeVotes(state.code, r.number));
    } catch (e: any) {
      toast(e.message, "error");
    }
  }

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

      {r.votes.needed && you !== null && !plays && (
        <section className="card center muted">Questo round lo votano gli altri: tu giochi dal prossimo.</section>
      )}
      {r.votes.needed && plays && (
        <section className="card pop center">
          {!iVoted && targets.length > 0 ? (
            <>
              <h3>Quanto si avvicinano alla reference?</h3>
              <div className="vote-list">
                {targets.map((t) => {
                  const e = r.entries.find((x) => x.seat === t)!;
                  const v = values[t] ?? 5;
                  return (
                    <div key={t} className="vote-row" style={{ ["--pc" as any]: seatColor(t) }}>
                      {e.photo && <img src={e.photo} alt="" className="vote-thumb" />}
                      <div className="vote-body">
                        <div className="vote-head">
                          <b>{nameOf(state, t)}</b>
                          <span className="vote-val">
                            {face(v)} {fmtPts(v)}
                          </span>
                        </div>
                        <input
                          className="slider"
                          type="range"
                          min={0}
                          max={10}
                          step={0.5}
                          value={v}
                          aria-label={`Voto a ${nameOf(state, t)}`}
                          onChange={(ev) => setValues((x) => ({ ...x, [t]: Number(ev.target.value) }))}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
              <button className="btn btn-big btn-yellow" disabled={busy} onClick={send}>
                Vota
              </button>
              <small className="muted">I voti restano segreti finché non hanno votato tutti.</small>
            </>
          ) : (
            <div className="waiting">
              <Check />{" "}
              {iVoted && targets.length > 0
                ? `Hai votato: ${targets.map((t) => `${nameOf(state, t)} ${fmtPts(r.votes.mine?.[String(t)])}`).join(", ")}.`
                : "Non c'è niente da votare per te."}{" "}
              {missing.length === 0 ? "Calcolo i punti…" : `Aspetto ${joinNames(missing.map((p) => p.name))}…`}
            </div>
          )}
          {you === 0 && missing.length > 0 && (iVoted || targets.length === 0) && (
            <button className="link-btn" onClick={closeVotes}>
              Chiudi la votazione senza aspettare
            </button>
          )}
        </section>
      )}
    </>
  );
}

function RoundResult({ state, r }: { state: MatchState; r: RoundState }) {
  if (r.status !== "done") return null;
  const order = ranked(r.entries, (e) => e.points ?? 0);
  const best = order[0]?.points ?? 0;
  const top = order.filter((e) => (e.points ?? 0) === best && best > 0);
  const ai = r.ai.result;
  return (
    <section className="card result reveal">
      <h2 className="card-title">
        Round {r.number}: {r.subject} <DiffBadge d={r.difficulty} mult={r.multiplier} />
      </h2>
      <div className="round-winner">
        {top.length === 1 ? (
          <>
            <Crown /> Round a <Who state={state} seat={top[0].seat} />
          </>
        ) : top.length > 1 ? (
          `Pari fra ${joinNames(top.map((e) => nameOf(state, e.seat)))}!`
        ) : (
          "Nessuno ha fatto punti"
        )}
      </div>
      <Compare state={state} r={r} />
      {ai?.verdict && <blockquote className="verdict">“{ai.verdict}”</blockquote>}
      <div className={`breakdown ${order.length > 2 ? "many" : ""}`}>
        {order.map((e, i) => (
          <div key={e.seat} className="bd" style={{ ["--pc" as any]: seatColor(e.seat) }}>
            <b>
              {i + 1}. {nameOf(state, e.seat)}
            </b>
            {e.delivered ? (
              <div className="bd-score">
                {fmtPts(e.score)}
                <small>/10 × {r.multiplier}</small> = <span>{fmtPts(e.points)}</span>
              </div>
            ) : (
              <small className="muted">non ha consegnato · 0</small>
            )}
            {e.votes_received && e.votes_received.length > 0 && (
              <small className="muted">voti ricevuti: {e.votes_received.map(fmtPts).join(" · ")}</small>
            )}
            {ai?.entries?.[String(e.seat)] && (
              <p className="ai-comment">
                <Sparkles size={14} /> {ai.entries[String(e.seat)].comment}{" "}
                <small>({fmtPts(ai.entries[String(e.seat)].score)})</small>
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
  const w = state.winners || [];
  const fired = useRef(false);
  const fresh = state.finished_at != null && Date.now() / 1000 - state.finished_at < 600;
  const allTied = w.length === state.players.length && state.players.length > 1;

  useEffect(() => {
    if (fired.current || !fresh || w.length === 0) return;
    fired.current = true;
    const colors = ["#ffd23f", "#ff5d8f", "#3bceac", "#7b61ff"];
    confetti({ particleCount: 160, spread: 90, origin: { y: 0.3 }, colors });
    window.setTimeout(() => confetti({ particleCount: 120, angle: 60, spread: 70, origin: { x: 0 }, colors }), 400);
    window.setTimeout(() => confetti({ particleCount: 120, angle: 120, spread: 70, origin: { x: 1 }, colors }), 700);
  }, [fresh, w.length]);

  async function rematch() {
    setBusy(true);
    try {
      if (state.rematch_code) {
        // Se la rivincita l'ha creata un altro ci entro; se è mia, il server dice
        // di no e vado comunque alla pagina.
        await api.join(state.rematch_code).catch(() => {});
        nav(`/p/${state.rematch_code}`);
      } else {
        const r = await api.rematch(state.code);
        nav(`/p/${r.code}`);
      }
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  const last = state.rounds[state.rounds.length - 1];
  const standings = ranked(state.players, (p) => p.total);
  const medal = ["🥇", "🥈", "🥉"];
  // posizione con i pari merito: 10, 10, 7 → 1°, 1°, 3°
  const place = (i: number) => standings.findIndex((p) => p.total === standings[i].total);
  return (
    <>
      {fresh && last?.status === "done" && <RoundResult state={state} r={last} />}
      <section className="card pop center final">
        <div className="trophy">🏆</div>
        {allTied ? (
          <h1 className="title">Pareggio!</h1>
        ) : w.length === 1 ? (
          <h1 className="title">
            Vince <Who state={state} seat={w[0]} />
          </h1>
        ) : w.length > 1 ? (
          <h1 className="title">Pari fra {joinNames(w.map((s) => nameOf(state, s)))}</h1>
        ) : null}
        <ol className="standings">
          {standings.map((p, i) => (
            <li key={p.seat} className={state.you === p.seat ? "me" : ""} style={{ ["--pc" as any]: seatColor(p.seat) }}>
              <span className="st-pos">{medal[place(i)] || `${place(i) + 1}°`}</span>
              <b>{p.name}</b>
              <span className="st-pts">{fmtPts(p.total)}</span>
            </li>
          ))}
        </ol>
        {state.you !== null && (
          <button className="btn btn-big btn-yellow" disabled={busy} onClick={rematch}>
            <RotateCcw size={20} />
            {state.rematch_code ? "Entra nella rivincita!" : "Rivincita"}
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
