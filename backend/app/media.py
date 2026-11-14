"""Le immagini: decodifica (anche HEIC), rotazione EXIF, ridimensionamento, salvataggio.

I file hanno nomi casuali da 128 bit: chi non ha il link non li indovina.
"""

import io
import secrets

from PIL import Image, ImageOps

from . import config

try:  # HEIC è il formato di default dell'iPhone
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # pragma: no cover - opzionale
    pass

MAX_SIDE = 1600


class BadImage(ValueError):
    pass


def _normalize(data: bytes, max_side: int = MAX_SIDE) -> bytes:
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
    except Exception as exc:
        raise BadImage("Il file non è un'immagine leggibile") from exc
    if img.mode not in ("RGB", "L"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


def save_image(data: bytes, prefix: str) -> str:
    """Salva una versione JPEG ridotta e ne restituisce il nome del file."""
    jpeg = _normalize(data)
    name = f"{prefix}-{secrets.token_hex(16)}.jpg"
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    (config.MEDIA_DIR / name).write_bytes(jpeg)
    return name


def read(name: str) -> bytes:
    return (config.MEDIA_DIR / name).read_bytes()


def path_of(name: str):
    p = (config.MEDIA_DIR / name).resolve()
    if p.parent != config.MEDIA_DIR.resolve():
        raise FileNotFoundError(name)
    return p


def url(name: str | None) -> str | None:
    return f"/api/media/{name}" if name else None


def for_model(name: str, max_side: int = 1024) -> bytes:
    """Una copia più piccola da mandare al giudice AI."""
    return _normalize(read(name), max_side)
