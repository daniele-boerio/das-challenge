"""Il giudice AI (un modello via OpenRouter) guarda la reference e le due creazioni e dà i voti.

Le due foto arrivano come «A» e «B» in ordine casuale: l'ordine non deve dire chi
ha creato la partita. I nomi servono solo perché commenti e verdetto suonino naturali.
"""

import base64
import json
import random
import re

import httpx

from . import config, media

SCHEMA = {
    "type": "object",
    "properties": {
        "A": {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "comment": {"type": "string"},
            },
            "required": ["score", "comment"],
            "additionalProperties": False,
        },
        "B": {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "comment": {"type": "string"},
            },
            "required": ["score", "comment"],
            "additionalProperties": False,
        },
        "verdict": {"type": "string"},
    },
    "required": ["A", "B", "verdict"],
    "additionalProperties": False,
}

SYSTEM = """Sei il giudice di una sfida di scultura fra due persone che usano il DAS, \
una pasta da modellare che si asciuga all'aria. Ricevi la foto di riferimento e le foto \
delle due creazioni, A e B. Devi dire quanto ciascuna si avvicina al soggetto della reference.

Come giudicare:
- Conta la forma: silhouette, proporzioni, posa, volumi e i dettagli riconoscibili.
- Il DAS di solito è bianco o grigio e non è dipinto: ignora il colore, a meno che la \
creazione sia stata dipinta, e in quel caso un colore giusto è un piccolo bonus.
- Ignora sfondo, luce e qualità della foto. Se una foto non mostra una scultura, dalle 0 \
e dillo.
- Tieni conto della difficoltà: su un soggetto difficile anche un risultato approssimativo \
merita un voto discreto, se si riconosce.
- Voti da 0 a 10 con al massimo un decimale. Usa tutta la scala e non dare lo stesso voto \
alle due creazioni, a meno che siano davvero equivalenti.

Scrivi in italiano. Per ciascuna creazione un commento di una o due frasi, concreto \
(cosa è riuscito, cosa manca) e simpatico, mai cattivo. Il verdetto è una frase sola, \
da presentatore di gara, che dice chi vince il round e perché."""


def available() -> bool:
    return bool(config.OPENROUTER_API_KEY)


def _image_part(name: str) -> dict:
    data = base64.standard_b64encode(media.for_model(name)).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}


def _parse(text: str) -> dict:
    """Il JSON della risposta. Con `response_format` arriva pulito; se il modello
    lo avvolge in un blocco di codice o in una frase, si prende la prima graffa."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError("Il giudice AI non ha risposto con dei voti")
        return json.loads(m.group(0))


def judge(
    subject: str,
    difficulty: str,
    reference: str | None,
    host_photo: str,
    guest_photo: str,
    host_name: str = "A",
    guest_name: str = "B",
    rng: random.Random | None = None,
) -> dict:
    """{"host": {"score", "comment"}, "guest": {...}, "verdict"}. Solleva in caso di errore."""
    rng = rng or random
    host_is_a = rng.random() < 0.5
    a, b = (host_photo, guest_photo) if host_is_a else (guest_photo, host_photo)
    na, nb = (host_name, guest_name) if host_is_a else (guest_name, host_name)

    content: list[dict] = []
    if reference:
        content += [{"type": "text", "text": "Foto di riferimento:"}, _image_part(reference)]
    content += [
        {"type": "text", "text": f"Creazione A, di {na}:"},
        _image_part(a),
        {"type": "text", "text": f"Creazione B, di {nb}:"},
        _image_part(b),
        {
            "type": "text",
            "text": f"Soggetto: {subject}. Difficoltà: {difficulty}. "
            f"Nei commenti e nel verdetto chiama i due per nome ({na} e {nb}), non A e B. "
            "Rispondi solo con il JSON richiesto."
            + ("" if reference else " La foto di riferimento non era disponibile: giudica "
               "quanto ciascuna creazione rappresenta bene il soggetto."),
        },
    ]

    r = httpx.post(
        f"{config.AI_BASE_URL}/chat/completions",
        timeout=config.AI_TIMEOUT_S,
        headers={
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "X-Title": "DAS Challenge",
        },
        json={
            "model": config.AI_MODEL,
            "max_tokens": 2000,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "giudizio", "strict": True, "schema": SCHEMA},
            },
        },
    )
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message") or r.text
        except Exception:
            msg = r.text
        raise RuntimeError(f"OpenRouter {r.status_code}: {msg[:300]}")
    body = r.json()
    choice = (body.get("choices") or [{}])[0]
    data = _parse((choice.get("message") or {}).get("content") or "")

    def clean(x: dict) -> dict:
        score = max(0.0, min(10.0, round(float(x["score"]), 1)))
        return {"score": score, "comment": str(x["comment"]).strip()}

    ra, rb = clean(data["A"]), clean(data["B"])
    host, guest = (ra, rb) if host_is_a else (rb, ra)
    return {"host": host, "guest": guest, "verdict": str(data["verdict"]).strip()}
