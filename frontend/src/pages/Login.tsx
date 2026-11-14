import { useState } from "react";
import { ArrowLeft, Mail } from "lucide-react";
import { api } from "../api";
import { useApp } from "../App";
import type { User } from "../types";

/** Accesso: mail → codice a 6 cifre → (la prima volta) nome. Poi si resta dentro. */
export default function Login({ user, onDone }: { user: User | null; onDone: (u: User) => void }) {
  const { toast } = useApp();
  const [step, setStep] = useState<"email" | "code" | "name">(user && !user.name ? "name" : "email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const invited = location.pathname.startsWith("/p/");

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  const sendCode = () =>
    run(async () => {
      if (!email.trim()) throw new Error("Scrivi la tua mail");
      await api.requestCode(email.trim());
      setStep("code");
      toast("📬 Codice inviato: guarda la mail (anche nello spam)", "good");
    });

  const verify = (c = code) =>
    run(async () => {
      const r = await api.verify(email.trim(), c);
      if (r.user.name) onDone(r.user);
      else setStep("name");
    });

  const saveName = () =>
    run(async () => {
      const r = await api.setName(name.trim());
      onDone(r.user);
    });

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
          {invited ? "Ti hanno sfidato! Entra per accettare." : "Una reference, un timer, due scultori. Chi ci va più vicino?"}
        </p>
      </header>

      <section className="card pop">
        {step === "email" && (
          <>
            <h2 className="card-title">
              <Mail size={22} /> Entra
            </h2>
            <p className="muted">Ti mando un codice per mail. Niente password, e resti dentro per sempre.</p>
            <label className="field">
              <span>La tua mail</span>
              <input
                type="email"
                inputMode="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && sendCode()}
                placeholder="nome@esempio.it"
                autoFocus
              />
            </label>
            <button className="btn btn-big btn-yellow" disabled={busy} onClick={sendCode}>
              {busy ? "Invio…" : "Mandami il codice"}
            </button>
          </>
        )}

        {step === "code" && (
          <>
            <button className="link-btn back" onClick={() => setStep("email")}>
              <ArrowLeft size={16} /> {email}
            </button>
            <h2 className="card-title">Scrivi il codice</h2>
            <p className="muted">Sono 6 cifre, valgono 10 minuti.</p>
            <input
              className="code-input otp"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => {
                const v = e.target.value.replace(/\D/g, "").slice(0, 6);
                setCode(v);
                if (v.length === 6) verify(v);
              }}
              placeholder="••••••"
              autoFocus
            />
            <button className="btn btn-big btn-yellow" disabled={busy || code.length < 6} onClick={() => verify()}>
              {busy ? "Controllo…" : "Entra"}
            </button>
            <button className="link-btn" disabled={busy} onClick={sendCode}>
              Non è arrivato? Mandamene un altro
            </button>
          </>
        )}

        {step === "name" && (
          <>
            <h2 className="card-title">Come ti chiami?</h2>
            <p className="muted">È il nome che vedrà il tuo avversario.</p>
            <label className="field">
              <span>Il tuo nome</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && saveName()}
                maxLength={40}
                placeholder="Es. Daniele"
                autoFocus
              />
            </label>
            <button className="btn btn-big btn-pink" disabled={busy || !name.trim()} onClick={saveName}>
              Iniziamo!
            </button>
          </>
        )}
      </section>
    </div>
  );
}
