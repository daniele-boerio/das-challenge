import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { api } from "./api";
import type { AppConfig } from "./types";
import Home from "./pages/Home";
import MatchPage from "./pages/Match";
import GalleryPage from "./pages/Gallery";

type ToastKind = "info" | "error" | "good" | "bad";
interface Ctx {
  config: AppConfig | null;
  toast: (msg: string, kind?: ToastKind) => void;
}
const AppCtx = createContext<Ctx>({ config: null, toast: () => {} });
export const useApp = () => useContext(AppCtx);

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [toasts, setToasts] = useState<{ id: number; msg: string; kind: ToastKind }[]>([]);

  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
  }, []);

  const toast = useCallback((msg: string, kind: ToastKind = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, kind }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);

  return (
    <AppCtx.Provider value={{ config, toast }}>
      <div className="bg-blobs" aria-hidden />
      <div className="shell">
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
