import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture
def jpeg():
    def make(color=(200, 200, 200)):
        buf = io.BytesIO()
        Image.new("RGB", (64, 48), color).save(buf, "JPEG")
        return buf.getvalue()

    return make


@pytest.fixture
def app_env(tmp_path, monkeypatch, jpeg):
    from app import auth, config, db, game, judge, main, references

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(config, "ALLOWED_EMAILS", set())
    sent_codes: dict[str, str] = {}
    monkeypatch.setattr(auth, "send_code_mail", lambda email, code: sent_codes.__setitem__(email, code))
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    db.init(f"sqlite:///{tmp_path / 'test.db'}")

    # Niente rete: la reference è un'immagine finta salvata davvero.
    def fake_fetch(query, rng=None, subject=None):
        from app import media

        return media.save_image(jpeg((10, 120, 10)), "ref"), {
            "title": query, "creator": "Test", "license": "CC0", "license_url": "",
            "source_url": "", "provider": "Test",
        }

    monkeypatch.setattr(references, "fetch", fake_fetch)
    # Il countdown iniziale non serve nei test.
    monkeypatch.setattr(game, "COUNTDOWN_S", -1)
    # Il giudice AI gira nello stesso thread, così il test vede subito il risultato.
    monkeypatch.setattr(main, "start_judge", lambda code, n: main._run_judge(code, n))
    # Niente ticker in background: i test chiamano main.tick_all() quando serve.
    monkeypatch.setattr(main, "TICKER", False)
    # Niente reference preparate in background: i test le chiedono a mano.
    monkeypatch.setattr(main, "PREFETCH", False)
    with TestClient(main.app) as client:
        client.sent_codes = sent_codes
        yield client, monkeypatch


def login(client, email, name="Giocatore"):
    """Accede con mail + codice e sceglie il nome; il cookie resta nel client."""
    from app import auth

    r = client.post("/api/auth/request", json={"email": email})
    assert r.status_code == 200, r.text
    code = client.sent_codes[email.lower()] if hasattr(client, "sent_codes") else None
    r = client.post("/api/auth/verify", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    if name:
        assert client.post("/api/auth/name", json={"name": name}).status_code == 200
    return client


def new_player(base, email, name):
    """Un secondo dispositivo: client separato (cookie suoi), stessa app."""
    from fastapi.testclient import TestClient
    from app import main

    c = TestClient(main.app)
    c.sent_codes = base.sent_codes
    return login(c, email, name)


@pytest.fixture
def clock(monkeypatch):
    """Un orologio da spostare a mano: clock.advance(secondi)."""
    import time as _time

    from app import game

    class Clock:
        t = _time.time()

        def advance(self, seconds):
            self.t += seconds

    c = Clock()
    monkeypatch.setattr(game, "now", lambda: c.t)
    return c


@pytest.fixture(autouse=True)
def no_model_catalog(monkeypatch):
    """Il listino di OpenRouter non si scarica nei test: lo slug resta quello chiesto."""
    from app import ai_models

    monkeypatch.setattr(ai_models, "_catalog", lambda: [])
    ai_models.forget()
