"""Trovare la foto di riferimento di un soggetto.

Prima Openverse (immagini Creative Commons, API pubblica senza chiave), poi
Wikimedia Commons. La foto si scarica e si salva in locale: così entrambi vedono
la stessa immagine, la galleria non dipende da link esterni che spariscono, e
l'attribuzione richiesta dalla licenza resta accanto all'immagine.
"""

import logging
import random
import re

import httpx

from . import config, media

log = logging.getLogger(__name__)

OPENVERSE = "https://api.openverse.org/v1/images/"
COMMONS = "https://commons.wikimedia.org/w/api.php"
MAX_BYTES = 12 * 1024 * 1024


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
        out.append(
            {
                "image": it["url"],
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
        out.append(
            {
                "image": img,
                "title": page.get("title", "").removeprefix("File:"),
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


def fetch(query: str, rng: random.Random | None = None) -> tuple[str | None, dict | None]:
    """(nome del file salvato, attribuzione), oppure (None, None) se non si trova
    niente: il round parte lo stesso, col solo nome del soggetto."""
    rng = rng or random
    try:
        with _client() as c:
            for source in (_openverse, _commons):
                try:
                    candidates = source(c, query)
                except Exception as exc:
                    log.warning("ricerca reference %s fallita: %s", source.__name__, exc)
                    continue
                rng.shuffle(candidates)
                for cand in candidates[:4]:
                    try:
                        name = media.save_image(_download(c, cand.pop("image")), "ref")
                        return name, cand
                    except Exception as exc:
                        log.info("reference scartata: %s", exc)
    except Exception as exc:  # pragma: no cover - rete giù
        log.warning("reference non disponibile: %s", exc)
    return None, None
