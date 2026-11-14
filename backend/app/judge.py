"""Il giudice AI (un modello via OpenRouter) guarda la reference e le creazioni e dà i voti.

Le foto arrivano come «A», «B», «C»… in ordine casuale: l'ordine non deve dire chi
ha creato la partita né chi ha consegnato prima. I nomi servono solo perché
commenti e verdetto suonino naturali.
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
        "creations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "score": {"type": "number"},
                    "comment": {"type": "string"},
                },
                "required": ["label", "score", "comment"],
                "additionalProperties": False,
            },
        },
        "verdict": {"type": "string"},
    },
    "required": ["creations", "verdict"],
    "additionalProperties": False,
}

LABELS = "ABCDEFGH"

SYSTEM = """Sei il giudice di una sfida di scultura fra amici che usano il DAS, \
una pasta da modellare che si asciuga all'aria. Ricevi la foto di riferimento e le foto \
delle creazioni, indicate con una lettera (A, B, C…). Devi dire quanto ciascuna si \
avvicina al soggetto della reference.

Come giudicare:
- Conta la forma: silhouette, proporzioni, posa, volumi e i dettagli riconoscibili.
- Il DAS di solito è bianco o grigio e non è dipinto: ignora il colore, a meno che la \
creazione sia stata dipinta, e in quel caso un colore giusto è un piccolo bonus.
- Ignora sfondo, luce e qualità della foto. Se una foto non mostra una scultura, dalle 0 \
e dillo.
- Tieni conto della difficoltà: su un soggetto difficile anche un risultato approssimativo \
merita un voto discreto, se si riconosce.
- Voti da 0 a 10 con al massimo un decimale. Usa tutta la scala e non dare lo stesso voto \
a due creazioni, a meno che siano davvero equivalenti.

Scrivi in italiano. Per ciascuna creazione un commento di una o due frasi, concreto \
(cosa è riuscito, cosa manca) e simpatico, mai cattivo. Il verdetto è una frase sola, \
da presentatore di gara, che dice chi vince il round e perché. Nella risposta dai un \
elemento di `creations` per ogni lettera ricevuta, con la sua `label`."""


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
    entries: list[dict],
    rng: random.Random | None = None,
) -> dict:
    """`entries` = [{"seat", "name", "photo"}]. Restituisce
    {"entries": {"<posto>": {"score", "comment"}}, "verdict"}. Solleva in caso di errore."""
    rng = rng or random
    order = list(entries)
    rng.shuffle(order)
    by_label = {LABELS[i]: e for i, e in enumerate(order)}

    content: list[dict] = []
    if reference:
        content += [{"type": "text", "text": "Foto di riferimento:"}, _image_part(reference)]
    for label, e in by_label.items():
        content += [{"type": "text", "text": f"Creazione {label}, di {e['name']}:"}, _image_part(e["photo"])]
    names = ", ".join(f"{e['name']} ({label})" for label, e in by_label.items())
    content.append(
        {
            "type": "text",
            "text": f"Soggetto: {subject}. Difficoltà: {difficulty}. Creazioni: {names}. "
            "Nei commenti e nel verdetto chiama tutti per nome, non per lettera. "
            "Rispondi solo con il JSON richiesto."
            + ("" if reference else " La foto di riferimento non era disponibile: giudica "
               "quanto ciascuna creazione rappresenta bene il soggetto."),
        }
    )

    r = httpx.post(
        f"{config.AI_BASE_URL}/chat/completions",
        timeout=config.AI_TIMEOUT_S,
        headers={
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "X-Title": "DAS Challenge",
        },
        json={
            "model": config.AI_MODEL,
            "max_tokens": 1000 + 400 * len(entries),
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

    out: dict[str, dict] = {}
    for c in data.get("creations") or []:
        e = by_label.get(str(c.get("label", "")).strip().upper()[:1])
        if not e:
            continue
        score = max(0.0, min(10.0, round(float(c["score"]), 1)))
        out[str(e["seat"])] = {"score": score, "comment": str(c.get("comment", "")).strip()}
    missing = [e["name"] for e in entries if str(e["seat"]) not in out]
    if missing:
        raise ValueError(f"Il giudice AI non ha votato {', '.join(missing)}")
    return {"entries": out, "verdict": str(data.get("verdict", "")).strip()}
