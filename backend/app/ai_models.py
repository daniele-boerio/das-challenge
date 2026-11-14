"""Quale modello chiedere davvero a OpenRouter.

Lo slug in `AI_MODEL` si scrive a mano e sbagliarlo è facile (`claude-opus-4-8`
senza fornitore davanti, trattini al posto dei punti, un modello ritirato): la
prima volta lo si scopriva con un 400 a metà partita. Qui lo si confronta col
listino pubblico di OpenRouter e, se non c'è, si prende la variante giusta o il
Claude Opus più recente che vede le immagini.
"""

import logging
import re
import threading
import time

import httpx

from . import config

log = logging.getLogger(__name__)

_TTL = 6 * 3600
_lock = threading.Lock()
_cache: dict[str, tuple[float, str]] = {}


def _catalog() -> list[dict]:
    r = httpx.get(f"{config.AI_BASE_URL}/models", timeout=15)
    r.raise_for_status()
    return [m for m in r.json().get("data") or [] if m.get("id")]


def _sees_images(m: dict) -> bool:
    mods = (m.get("architecture") or {}).get("input_modalities")
    return mods is None or "image" in mods


def pick(wanted: str, models: list[dict]) -> str:
    """Lo slug da usare: quello chiesto se esiste, altrimenti la sua variante
    (fornitore davanti, punti al posto dei trattini), altrimenti il Claude Opus
    più recente che accetta immagini, altrimenti quello chiesto così com'è."""
    ids = {m["id"] for m in models}
    w = wanted.strip()
    tail = w.split("/", 1)[-1]
    dotted = re.sub(r"(\d)-(\d)", r"\1.\2", tail)
    for cand in (w, f"anthropic/{tail}", f"anthropic/{dotted}", dotted):
        if cand in ids:
            return cand
    opus = [m for m in models if m["id"].startswith("anthropic/claude-opus") and _sees_images(m)]
    claude = [m for m in models if m["id"].startswith("anthropic/claude") and _sees_images(m)]
    for pool in (opus, claude):
        if pool:
            return max(pool, key=lambda m: m.get("created") or 0)["id"]
    return w


def resolve(wanted: str | None = None) -> str:
    wanted = wanted or config.AI_MODEL
    now = time.time()
    with _lock:
        hit = _cache.get(wanted)
        if hit and hit[0] > now:
            return hit[1]
    try:
        slug = pick(wanted, _catalog())
    except Exception as exc:
        log.warning("listino di OpenRouter non disponibile, uso %s così com'è: %s", wanted, exc)
        return wanted
    if slug != wanted:
        log.warning("il modello %s non esiste su OpenRouter: uso %s", wanted, slug)
    with _lock:
        _cache[wanted] = (now + _TTL, slug)
    return slug


def forget():
    """Dopo un 400 sul modello si rilegge il listino alla prossima chiamata."""
    with _lock:
        _cache.clear()
