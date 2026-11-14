import base64
import io

import httpx
from PIL import Image

from app import ai_models, config, imagegen, main, media, references


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (240, 240, 240)).save(buf, "PNG")
    return buf.getvalue()


class Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def _ok(url, **kw):
    data = "data:image/png;base64," + base64.b64encode(_png()).decode()
    _ok.sent = kw["json"]
    return Resp(200, {"choices": [{"message": {"images": [{"type": "image_url", "image_url": {"url": data}}]}}], "usage": {"cost": 0.014}})


def test_generata_e_salvata(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(httpx, "post", _ok)
    imagegen.forget()
    name, attr = imagegen.generate("Gufo", "owl", "facile", colors=False)
    assert name and media.path_of(name).exists()
    assert attr["provider"] == config.IMAGE_MODEL
    assert _ok.sent["modalities"] == ["image"]
    p = _ok.sent["messages"][0]["content"]
    assert "owl" in p and "white air-dry clay" in p and "not the real thing" in p


def test_colori_e_difficolta_nel_prompt():
    p = imagegen.prompt("owl", "difficile", colors=True)
    assert "polymer clay" in p and "white" not in p and "detailed" in p


def test_modello_dal_listino(monkeypatch):
    cat = [
        {"id": "anthropic/claude-sonnet-5", "architecture": {"output_modalities": ["text"]}},
        {"id": "google/gemini-3.1-flash-lite-image", "architecture": {"output_modalities": ["image", "text"]}},
    ]
    monkeypatch.setattr(ai_models, "_catalog", lambda: cat)
    monkeypatch.setattr(config, "IMAGE_MODEL", "nonesiste/foo")
    imagegen.forget()
    assert imagegen.model() == ("google/gemini-3.1-flash-lite-image", ["image", "text"])
    imagegen.forget()


def test_errore_ripiega_sulla_ricerca(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: Resp(500, {"error": "giù"}))
    imagegen.forget()
    assert imagegen.generate("Gufo", "owl") == (None, None)
    monkeypatch.setattr(references, "fetch", lambda q, **kw: ("cercata.jpg", {"provider": "Test"}))
    name, attr = main._fetch_reference(("Gufo", "owl", "animali"), False, "facile")
    assert name == "cercata.jpg" and attr["provider"] == "Test"


def test_risposta_senza_immagine(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: Resp(200, {"choices": [{"message": {"content": "non posso"}}]}))
    imagegen.forget()
    assert imagegen.generate("Gufo", "owl") == (None, None)


def test_main_preferisce_la_generata(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(httpx, "post", _ok)
    imagegen.forget()
    name, attr = main._fetch_reference(("Gufo", "owl", "animali"), False, "media")
    assert attr["creator"] == "" and attr["title"] == "Foto generata con l'AI"
