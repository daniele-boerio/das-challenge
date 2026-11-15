"""Trovare la foto di riferimento di un soggetto: una scultura in pasta da modellare.

La reference non è il soggetto vero (un fungo nel bosco) ma una creazione fatta a
mano con DAS, pongo, polymer clay o plastilina: è quella che si può rifare al tavolo.

Prima Openverse (immagini Creative Commons, API pubblica senza chiave), poi
Wikimedia Commons, con più ricerche («polymer clay owl», «clay owl»…). Si tengono
solo i risultati che nel titolo, nei tag o nelle categorie dicono di essere di
pasta da modellare; se c'è la chiave OpenRouter, un modello guarda le miniature e
sceglie quella che è davvero una scultura del soggetto, fatta bene e ben visibile.

La foto si scarica e si salva in locale: così tutti vedono la stessa immagine, la
galleria non dipende da link esterni che spariscono, e l'attribuzione richiesta
dalla licenza resta accanto all'immagine.
"""

import base64
import io
import json
import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor

import httpx

from . import ai_models, config, media

log = logging.getLogger(__name__)

OPENVERSE = "https://api.openverse.org/v1/images/"
COMMONS = "https://commons.wikimedia.org/w/api.php"
MAX_BYTES = 12 * 1024 * 1024
WANTED = 8          # candidati buoni dopo cui si smette di cercare
AI_CANDIDATES = 6   # miniature mandate al modello

# Le parole che dicono «è fatto di pasta da modellare».
CLAY_WORDS = re.compile(
    r"\b(clay|polymer|fimo|sculpey|plasticine|plastilina|plastilin|play-?doh|playdough|"
    r"pongo|modell?ing (?:clay|paste)|air[- ]dry|cold porcelain|fondant|sugarpaste|gum ?paste)\b",
    re.I,
)


def queries(subject: str, colors: bool = False) -> list[str]:
    if colors:
        return [f"polymer clay {subject}", f"clay {subject}", f"plasticine {subject}", f"{subject} clay sculpture"]
    # Col DAS bianco senza colori, prima le sculture bianche: sono quelle che si possono rifare.
    return [f"white clay {subject}", f"polymer clay {subject}", f"clay {subject}", f"{subject} clay sculpture"]


def is_clay(text: str) -> bool:
    return bool(CLAY_WORDS.search(text or ""))


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=config.REFERENCE_TIMEOUT_S,
        headers={"User-Agent": config.USER_AGENT},
        follow_redirects=True,
    )


def _openverse(c: httpx.Client, query: str) -> list[dict]:
    r = c.get(OPENVERSE, params={"q": query, "page_size": 20, "mature": "false"})
    r.raise_for_status()
    out = []
    for it in r.json().get("results", []):
        if not it.get("url"):
            continue
        lic = (it.get("license") or "").upper()
        ver = it.get("license_version") or ""
        tags = " ".join(t.get("name", "") for t in it.get("tags") or [] if isinstance(t, dict))
        out.append(
            {
                "image": it["url"],
                "thumb": it.get("thumbnail") or it["url"],
                "text": f"{it.get('title') or ''} {tags}",
                "title": it.get("title") or "",
                "creator": it.get("creator") or "",
                "license": f"CC {lic} {ver}".strip() if lic not in ("PDM", "CC0") else lic,
                "license_url": it.get("license_url") or "",
                "source_url": it.get("foreign_landing_url") or "",
                "provider": "Openverse",
            }
        )
    return out


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _commons(c: httpx.Client, query: str) -> list[dict]:
    r = c.get(
        COMMONS,
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrnamespace": 6,
            "gsrlimit": 20,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 1280,
        },
    )
    r.raise_for_status()
    out = []
    for page in (r.json().get("query", {}).get("pages") or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        img = info.get("thumburl") or info.get("url")
        if not img:
            continue
        title = page.get("title", "").removeprefix("File:")
        desc = _strip_html(meta.get("ImageDescription", {}).get("value", ""))
        cats = meta.get("Categories", {}).get("value", "")
        out.append(
            {
                "image": img,
                "thumb": img,
                "text": f"{title} {desc} {cats}",
                "title": title,
                "creator": _strip_html(meta.get("Artist", {}).get("value", "")),
                "license": meta.get("LicenseShortName", {}).get("value", ""),
                "license_url": meta.get("LicenseUrl", {}).get("value", ""),
                "source_url": info.get("descriptionurl", ""),
                "provider": "Wikimedia Commons",
            }
        )
    return out


def _download(c: httpx.Client, url: str) -> bytes:
    with c.stream("GET", url) as r:
        r.raise_for_status()
        buf = bytearray()
        for chunk in r.iter_bytes():
            buf.extend(chunk)
            if len(buf) > MAX_BYTES:
                raise ValueError("immagine troppo grande")
        return bytes(buf)


def candidates(c: httpx.Client, subject: str, colors: bool = False) -> list[dict]:
    """I risultati che si dichiarano di pasta da modellare, senza doppioni."""
    found: list[dict] = []
    seen: set[str] = set()
    for source in (_openverse, _commons):
        for q in queries(subject, colors):
            try:
                results = source(c, q)
            except Exception as exc:
                log.warning("ricerca reference %s «%s» fallita: %s", source.__name__, q, exc)
                break  # la fonte non risponde: inutile insistere con le altre ricerche
            for cand in results:
                if cand["image"] in seen or not is_clay(cand["text"]):
                    continue
                seen.add(cand["image"])
                found.append(cand)
            if len(found) >= WANTED:
                return found
    return found


# ── la scelta del modello ─────────────────────────────────────────────────────

PICK_SYSTEM = """Scegli la foto di riferimento per una sfida di scultura con il DAS \
(pasta da modellare che si asciuga all'aria). Ti mostro delle foto numerate. Serve una \
foto di una SCULTURA FATTA A MANO in pasta da modellare (DAS, pongo, polymer clay, \
plastilina, fimo, ceramica fatta a mano) che rappresenta il soggetto indicato: un \
oggetto singolo, ben visibile, che due persone possano provare a rifare in un tempo \
limitato. {colors} Scarta anche: il soggetto vero (animali, cibo, oggetti reali), disegni, tutorial \
con tante foto, collage, gioielli minuscoli, foto sfocate o dove la scultura è piccola.
Rispondi solo con il JSON richiesto: `best` è il numero della foto migliore, oppure \
null se nessuna va bene."""

PICK_WHITE = """I giocatori hanno solo DAS bianco e nessun colore: preferisci sculture \
bianche, grigie o di un solo colore, e quelle che si riconoscono dalla forma; scarta quelle \
che senza i colori non si capirebbero più (dettagli solo dipinti, motivi colorati, \
tanti pezzi di colori diversi)."""

PICK_COLORS = """I giocatori hanno paste colorate: vanno bene anche sculture a più colori."""

PICK_SCHEMA = {
    "type": "object",
    "properties": {"best": {"type": ["integer", "null"]}, "reason": {"type": "string"}},
    "required": ["best", "reason"],
    "additionalProperties": False,
}


def _small_jpeg(data: bytes, side: int = 512) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _ai_pick(
    c: httpx.Client, subject_it: str, subject_en: str, cands: list[dict], colors: bool = False
) -> dict | None:
    """Il candidato scelto dal modello; None se nessuno va bene. Solleva se la
    chiamata fallisce (chi chiama ripiega sulla scelta a caso)."""
    def thumb_of(cand):
        try:
            return _small_jpeg(_download(c, cand["thumb"]), 384)
        except Exception as exc:
            log.info("miniatura scartata: %s", exc)
            return None

    # Le miniature si scaricano tutte insieme: una dopo l'altra erano secondi persi.
    pool = cands[:AI_CANDIDATES]
    with ThreadPoolExecutor(len(pool) or 1) as ex:
        thumbs = list(ex.map(thumb_of, pool))
    shown: list[dict] = []
    content: list[dict] = []
    for cand, thumb in zip(pool, thumbs):
        if thumb is None:
            continue
        shown.append(cand)
        content += [
            {"type": "text", "text": f"Foto {len(shown)}:"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(thumb).decode()}},
        ]
    if not shown:
        return None
    content.append({"type": "text", "text": f"Soggetto: {subject_it} ({subject_en})."})
    r = httpx.post(
        f"{config.AI_BASE_URL}/chat/completions",
        timeout=config.AI_TIMEOUT_S,
        headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}", "X-Title": "DAS Challenge"},
        json={
            "model": ai_models.resolve(config.REFERENCE_MODEL) if config.REFERENCE_MODEL else ai_models.fast(),
            "max_tokens": 400,
            "messages": [{"role": "system", "content": PICK_SYSTEM.replace("{colors}", PICK_COLORS if colors else PICK_WHITE)}, {"role": "user", "content": content}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "scelta", "strict": True, "schema": PICK_SCHEMA},
            },
        },
    )
    if r.status_code >= 400:
        raise RuntimeError(f"OpenRouter {r.status_code}: {r.text[:200]}")
    text = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    m = re.search(r"\{.*\}", text, re.S)
    best = json.loads(m.group(0) if m else text).get("best")
    if isinstance(best, int) and 1 <= best <= len(shown):
        return shown[best - 1]
    return None


def fetch(
    query: str, rng: random.Random | None = None, subject: str | None = None, colors: bool = False,
    ai: bool = True,
) -> tuple[str | None, dict | None]:
    """(nome del file salvato, attribuzione), oppure (None, None) se non si trova
    nessuna scultura: il round parte lo stesso, col solo nome del soggetto."""
    rng = rng or random
    try:
        with _client() as c:
            cands = candidates(c, query, colors)
            rng.shuffle(cands)
            order = cands
            if cands and ai and config.REFERENCE_AI and config.OPENROUTER_API_KEY:
                try:
                    chosen = _ai_pick(c, subject or query, query, cands, colors)
                    if chosen is None:
                        log.info("il modello non ha trovato una scultura di «%s» fra %d foto", query, len(cands))
                        order = []
                    else:
                        order = [chosen]
                except Exception as exc:
                    log.warning("scelta della reference col modello fallita: %s", exc)
            for cand in order[:4]:
                try:
                    name = media.save_image(_download(c, cand["image"]), "ref")
                    return name, {k: cand[k] for k in ("title", "creator", "license", "license_url", "source_url", "provider")}
                except Exception as exc:
                    log.info("reference scartata: %s", exc)
    except Exception as exc:  # pragma: no cover - rete giù
        log.warning("reference non disponibile: %s", exc)
    return None, None
