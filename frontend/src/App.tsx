import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { api } from "./api";
import type { AppConfig, User } from "./types";
import Home from "./pages/Home";
import MatchPage from "./pages/Match";
import GalleryPage from "./pages/Gallery";
import Login from "./pages/Login";

type ToastKind = "info" | "error" | "good" | "bad";
interface Ctx {
  config: AppConfig | null;
  user: User | null;
  setUser: (u: User | null) => void;
  toast: (msg: string, kind?: ToastKind) => void;
}
const AppCtx = createContext<Ctx>({ config: null, user: null, setUser: () => {}, toast: () => {} });
export const useApp = () => useContext(AppCtx);

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  // undefined = non so ancora; null = non collegato
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [toasts, setToasts] = useState<{ id: number; msg: string; kind: ToastKind }[]>([]);

  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
    api
      .me()
      .then((r) => setUser(r.user))
      .catch(() => setUser(null));
  }, []);

  const toast = useCallback((msg: string, kind: ToastKind = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, kind }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);

  return (
    <AppCtx.Provider value={{ config, user: user ?? null, setUser, toast }}>
      <div className="bg-blobs" aria-hidden />
      <div className="shell">
        {user === undefined ? (
          <div className="card center">
            <div className="spinner" /> Un attimo…
          </div>
        ) : !user || !user.name ? (
          <Login user={user} onDone={setUser} />
        ) : (
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/p/:code" element={<MatchPage />} />
          <Route path="/galleria" element={<GalleryPage />} />
          <Route
            path="*"
            element={
              <div className="card center">
                <h2>Pagina non trovata</h2>
                <Link className="btn" to="/">
                  Torna all'inizio
                </Link>
              </div>
            }
          />
        </Routes>
        )}
      </div>
      <div className="toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            {t.msg}
          </div>
        ))}
      </div>
    </AppCtx.Provider>
  );
}
