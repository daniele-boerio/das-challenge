import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Brain, Dices, Hourglass, Images, Palette, Shuffle, Sparkles, Swords, Timer, Users, Zap } from "lucide-react";
import { api, prefs } from "../api";
import { useApp } from "../App";
import type { Difficulty, JudgeMode, Settings, TimerMode } from "../types";
import { DIFF_LABEL } from "../lib/util";

const TIMERS: { id: TimerMode; label: string; hint: string }[] = [
  { id: "libero", label: "Libero", hint: "Allo scadere si può continuare" },
  { id: "rigido", label: "Rigido", hint: "Allo scadere hai 1 minuto per consegnare, poi si chiude" },
  { id: "nessuno", label: "Senza tempo", hint: "Il round finisce quando hanno consegnato tutti" },
];

const JUDGES: { id: JudgeMode; label: string; hint: string }[] = [
  { id: "voto", label: "Voto fra voi", hint: "Ognuno vota le creazioni degli altri" },
  { id: "ai", label: "Giudice AI", hint: "Decide l'AI, con commento" },
  { id: "entrambi", label: "Entrambi", hint: "Media fra il vostro voto e l'AI" },
];

export default function Home() {
  const { config, toast, user, setUser } = useApp();
  const nav = useNavigate();
  const [joinCode, setJoinCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState<Settings | null>(null);

  const s: Settings | null =
    settings ??
    (config
      ? {
          ...config.defaults,
          ...(prefs.settings() || {}),
          minutes: { ...config.defaults.minutes, ...(prefs.settings()?.minutes || {}) },
        }
      : null);
  const upd = (patch: Partial<Settings>) => s && setSettings({ ...s, ...patch });
  const aiOk = !!config?.ai_available;

  async function create() {
    if (!s) return;
    setBusy(true);
    try {
      const settingsToSend = { ...s, judge: aiOk ? s.judge : "voto" } as Settings;
      prefs.setSettings(settingsToSend);
      const r = await api.create(settingsToSend);
      nav(`/p/${r.code}`);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function join() {
    const c = joinCode.trim().toUpperCase();
    if (c.length < 4) return toast("Il codice ha 4 lettere", "error");
    nav(`/p/${c}`);
  }

  return (
    <div className="home">
      <header className="hero">
        <div className="logo-blob">
          <span>🏺</span>
        </div>
        <h1 className="title">
          Sfida <span className="accent">DAS</span>
        </h1>
        <p className="subtitle">
          Ciao <b className="accent">{user?.name}</b>! Una reference, un timer, fino a {config?.max_players ?? 8} scultori.
        </p>
      </header>

      <section className="card pop">
        <h2 className="card-title">
          <Swords size={22} /> Nuova sfida
        </h2>
        {s && (
          <>
            <div className="field">
              <span>Chi giudica</span>
              <div className="seg">
                {JUDGES.map((j) => (
                  <button
                    key={j.id}
                    type="button"
                    className={`seg-btn ${s.judge === j.id ? "on" : ""}`}
                    disabled={j.id !== "voto" && !aiOk}
                    onClick={() => upd({ judge: j.id })}
                    title={j.hint}
                  >
                    {j.id === "voto" ? <Users size={16} /> : <Sparkles size={16} />} {j.label}
                  </button>
                ))}
              </div>
              {!aiOk && <small className="muted">Il giudice AI non è configurato sul server: si vota a vicenda.</small>}
            </div>

            <div className="field">
              <span>
                <Timer size={16} /> Timer
              </span>
              <div className="seg">
                {TIMERS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`seg-btn ${s.timer === t.id ? "on" : ""}`}
                    onClick={() => upd({ timer: t.id })}
                    title={t.hint}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <small className="muted">{TIMERS.find((t) => t.id === s.timer)?.hint}</small>
            </div>

            <Toggle
              on={s.colors}
              onChange={(v) => upd({ colors: v })}
              icon={<Palette size={18} />}
              title="Avete paste colorate?"
              hint={
                s.colors
                  ? "Sì: reference anche colorate, e il giudice tiene conto dei colori"
                  : "No, solo DAS bianco: reference bianche e il giudice guarda solo la forma"
              }
            />

            <div className="row2">
              <div className="field">
                <span>Round</span>
                <div className="stepper">
                  <button type="button" aria-label="Un round in meno" onClick={() => upd({ rounds: Math.max(1, s.rounds - 1) })}>−</button>
                  <b>{s.rounds}</b>
                  <button type="button" aria-label="Un round in più" onClick={() => upd({ rounds: Math.min(10, s.rounds + 1) })}>+</button>
                </div>
              </div>
              <label className="field">
                <span>Tema</span>
                <select value={s.theme} onChange={(e) => upd({ theme: e.target.value })}>
                  {Object.entries(config!.themes).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <button type="button" className="link-btn" onClick={() => setOpen((o) => !o)}>
              {open ? "Nascondi" : "Mostra"} regole avanzate
            </button>

            {open && (
              <div className="advanced">
                {s.timer !== "nessuno" && (
                <div className="field">
                  <span>Minuti per difficoltà</span>
                  <div className="minutes">
                    {(Object.keys(DIFF_LABEL) as Difficulty[]).map((d) => (
                      <label key={d} className={`min-box diff-${d}`}>
                        <small>
                          {DIFF_LABEL[d]} ×{config!.multipliers[d]}
                        </small>
                        <input
                          type="number"
                          inputMode="numeric"
                          min={1}
                          max={180}
                          value={s.minutes[d]}
                          onChange={(e) => upd({ minutes: { ...s.minutes, [d]: Number(e.target.value) || 1 } })}
                        />
                      </label>
                    ))}
                  </div>
                </div>
                )}
                <Toggle
                  on={s.rush}
                  onChange={(v) => upd({ rush: v })}
                  icon={<Hourglass size={18} />}
                  title="Gli ultimi rincorrono"
                  hint={`Quando ${s.rush_after} hanno consegnato, chi manca ha ${s.rush_minutes} minuti (poi si chiude)`}
                />
                {s.rush && (
                  <div className="row2 rush-opts">
                    <label className="field">
                      <span>Dopo quante consegne</span>
                      <input
                        type="number"
                        inputMode="numeric"
                        min={1}
                        max={(config?.max_players ?? 8) - 1}
                        value={s.rush_after}
                        onChange={(e) => upd({ rush_after: Math.max(1, Math.min(7, Number(e.target.value) || 1)) })}
                      />
                    </label>
                    <label className="field">
                      <span>Minuti per finire</span>
                      <input
                        type="number"
                        inputMode="numeric"
                        min={1}
                        max={60}
                        value={s.rush_minutes}
                        onChange={(e) => upd({ rush_minutes: Math.max(1, Math.min(60, Number(e.target.value) || 1)) })}
                      />
                    </label>
                  </div>
                )}
                <Toggle on={s.powerups} onChange={(v) => upd({ powerups: v })} icon={<Zap size={18} />} title="Power-up" hint={s.timer === "nessuno" ? "Senza tempo resta solo il cambio reference" : "+2 min, −1 min a un avversario, cambio reference: uno a testa"} />
                <Toggle on={s.memory} onChange={(v) => upd({ memory: v })} icon={<Brain size={18} />} title="Round a memoria" hint="Ogni tanto la reference sparisce dopo 30 secondi" />
                <div className="field">
                  <span>
                    <Dices size={16} /> Handicap
                  </span>
                  <div className="seg">
                    {(
                      [
                        ["off", "Spenti"],
                        ["leader", "A chi è in testa"],
                        ["random", "A sorpresa"],
                      ] as const
                    ).map(([id, label]) => (
                      <button key={id} type="button" className={`seg-btn ${s.handicap === id ? "on" : ""}`} onClick={() => upd({ handicap: id })}>
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        <button className="btn btn-big btn-yellow" disabled={busy || !s} onClick={create}>
          {busy ? "Creo la sfida…" : "Crea la sfida"}
        </button>
      </section>

      <section className="card">
        <h2 className="card-title">
          <Shuffle size={22} /> Hai un codice?
        </h2>
        <div className="join-row">
          <input
            className="code-input"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))}
            placeholder="ABCD"
            maxLength={6}
            onKeyDown={(e) => e.key === "Enter" && join()}
          />
          <button className="btn btn-pink" onClick={join}>
            Entra
          </button>
        </div>
      </section>

      <Link to="/galleria" className="card gallery-link">
        <Images size={26} />
        <div>
          <b>Galleria e storico</b>
          <small>Le tue sfide passate e chi è in vantaggio</small>
        </div>
      </Link>

      <p className="whoami">
        Sei dentro come {user?.email} ·{" "}
        <button
          className="link-inline"
          onClick={async () => {
            const n = window.prompt("Il tuo nuovo nome", user?.name || "");
            if (!n?.trim()) return;
            try {
              setUser((await api.setName(n.trim())).user);
            } catch (e: any) {
              toast(e.message, "error");
            }
          }}
        >
          cambia nome
        </button>{" "}
        ·{" "}
        <button
          className="link-inline"
          onClick={async () => {
            await api.logout().catch(() => {});
            setUser(null);
          }}
        >
          esci
        </button>
      </p>
    </div>
  );
}

function Toggle(props: { on: boolean; onChange: (v: boolean) => void; icon: React.ReactNode; title: string; hint: string }) {
  return (
    <button type="button" className={`toggle ${props.on ? "on" : ""}`} onClick={() => props.onChange(!props.on)}>
      <span className="toggle-icon">{props.icon}</span>
      <span className="toggle-text">
        <b>{props.title}</b>
        <small>{props.hint}</small>
      </span>
      <span className="switch" aria-hidden>
        <span />
      </span>
    </button>
  );
}
