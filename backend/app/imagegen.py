"""La foto di riferimento generata da un modello di immagini (via OpenRouter).

Cercarla su Openverse e Commons a volte non trovava nessuna scultura, e il round
partiva col solo nome del soggetto. Generata, la foto c'è sempre, è sempre una
scultura in pasta da modellare (mai il soggetto vero), rispetta il DAS bianco e la
difficoltà, e arriva in pochi secondi. Costa circa mezzo centesimo a foto
con il modello di default (`IMAGE_MODEL`); se la generazione fallisce si torna
alla ricerca.
"""

import base64
import logging
import time

import httpx

from . import ai_models, config, media

log = logging.getLogger(__name__)

# In ordine di preferenza, se `IMAGE_MODEL` non è nel listino: economici e buoni sulle foto.
PREFERRED = (
    "openai/gpt-image-2",
    "black-forest-labs/flux.2-klein-4b",
    "google/gemini-3.1-flash-lite-image",
    "black-forest-labs/flux.2-pro",
    "google/gemini-3.1-flash-image",
)

_TTL = 6 * 3600
_chosen: tuple[float, str, list[str]] | None = None

LEVEL = {
    "facile": "very simple and chunky, a few smooth rounded shapes, almost no small details",
    "media": "moderately simple, a few clear details such as eyes, ears or simple texture",
    "difficile": "more detailed and expressive, with fine modelled details and texture, still a single piece",
}

WHITE = (
    "made entirely of plain unpainted matte white air-dry clay (like DAS), all one white "
    "colour, the shape alone makes the subject recognizable"
)
COLORS = "made of colourful polymer clay / plasticine, with a few bright solid colours"


def prompt(subject_en: str, difficulty: str, colors: bool) -> str:
    return (
        f"A realistic photo of a small handmade sculpture of {subject_en}, "
        f"{COLORS if colors else WHITE}. Hobbyist craft, visibly handmade with slight "
        f"fingerprints and tool marks. Style: {LEVEL.get(difficulty, LEVEL['media'])}. "
        "One single object, centered, fully visible, standing on a plain light table, "
        "plain neutral background, soft natural light, sharp focus, square photo. "
        "It is a clay figurine, not the real thing. No text, no hands, no tools, no other objects."
    )


def _outputs(m: dict) -> list[str]:
    return list((m.get("architecture") or {}).get("output_modalities") or [])


def model() -> tuple[str, list[str]]:
    """(slug, modalità da chiedere). Il modello configurato se esiste nel listino,
    altrimenti il primo disponibile di `PREFERRED`, altrimenti uno qualsiasi che
    produca immagini."""
    global _chosen
    now = time.time()
    if _chosen and _chosen[0] > now:
        return _chosen[1], _chosen[2]
    wanted = config.IMAGE_MODEL
    try:
        cat = {m["id"]: m for m in ai_models._catalog()}
    except Exception as exc:
        log.warning("listino di OpenRouter non disponibile, uso %s: %s", wanted, exc)
        return wanted, _guess_modalities(wanted)
    makes_images = {i: m for i, m in cat.items() if "image" in _outputs(m)}
    slug = next((s for s in (wanted, *PREFERRED) if s in makes_images), None)
    if slug is None and makes_images:
        slug = min(makes_images, key=lambda i: float((makes_images[i].get("pricing") or {}).get("image") or 1))
    if slug is None:
        slug = wanted
    if slug != wanted:
        log.warning("il modello di immagini %s non c'è su OpenRouter: uso %s", wanted, slug)
    mods = ["image", "text"] if "text" in _outputs(cat.get(slug, {})) else ["image"]
    _chosen = (now + _TTL, slug, mods)
    return slug, mods


def _guess_modalities(slug: str) -> list[str]:
    return ["image", "text"] if slug.startswith(("google/", "openai/")) else ["image"]


def forget():
    global _chosen
    _chosen = None


def _image_bytes(message: dict) -> bytes | None:
    urls = [
        (im.get("image_url") or {}).get("url")
        for im in message.get("images") or []
        if isinstance(im, dict)
    ]
    content = message.get("content")
    if isinstance(content, list):  # alcuni modelli mettono l'immagine fra le parti del contenuto
        urls += [(p.get("image_url") or {}).get("url") for p in content if isinstance(p, dict) and p.get("type") == "image_url"]
    for url in filter(None, urls):
        if url.startswith("data:"):
            return base64.b64decode(url.split(",", 1)[1])
        r = httpx.get(url, timeout=config.REFERENCE_TIMEOUT_S, follow_redirects=True)
        if r.status_code < 400:
            return r.content
    return None


def generate(
    subject_it: str, subject_en: str, difficulty: str = "media", colors: bool = False
) -> tuple[str | None, dict | None]:
    """(nome del file salvato, attribuzione), oppure (None, None): niente chiave,
    generazione spenta o fallita. Non solleva mai."""
    if not (config.IMAGE_AI and config.OPENROUTER_API_KEY):
        return None, None
    slug, mods = model()
    t0 = time.monotonic()
    try:
        r = httpx.post(
            f"{config.AI_BASE_URL}/chat/completions",
            timeout=config.IMAGE_TIMEOUT_S,
            headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}", "X-Title": "DAS Challenge"},
            json={
                "model": slug,
                "modalities": mods,
                "messages": [{"role": "user", "content": prompt(subject_en, difficulty, colors)}],
            },
        )
        if r.status_code >= 400:
            if r.status_code in (400, 404):
                forget()
            raise RuntimeError(f"OpenRouter {r.status_code}: {r.text[:200]}")
        body = r.json()
        data = _image_bytes(((body.get("choices") or [{}])[0].get("message")) or {})
        if not data:
            raise RuntimeError("nessuna immagine nella risposta")
        name = media.save_image(data, "ref")
    except Exception as exc:
        log.warning("generazione della reference «%s» fallita: %s", subject_en, exc)
        return None, None
    cost = (body.get("usage") or {}).get("cost")
    log.info("reference «%s» generata con %s in %.1f s (costo %s)", subject_en, slug, time.monotonic() - t0, cost)
    return name, {
        "title": "Foto generata con l'AI",
        "creator": "",
        "license": "",
        "license_url": "",
        "source_url": "",
        "provider": slug,
    }
