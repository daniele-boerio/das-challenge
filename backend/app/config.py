"""Tutte le variabili d'ambiente si leggono da qui."""

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
MEDIA_DIR = DATA_DIR / "media"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'das.db'}")

# Accesso con mail + codice. Se ALLOWED_EMAILS è impostato (separate da virgola),
# entrano solo quelle mail; vuoto = chiunque abbia il link.
ALLOWED_EMAILS = {e.strip().lower() for e in os.getenv("ALLOWED_EMAILS", "").split(",") if e.strip()}
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")

# SMTP per i codici. Senza SMTP_HOST il codice finisce nei log del backend.
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "").strip() or SMTP_USER
SMTP_SSL = os.getenv("SMTP_SSL", "false").lower() in ("1", "true", "yes")

# Giudice AI via OpenRouter (API compatibile OpenAI): senza chiave l'app funziona
# solo col voto reciproco. Il modello è uno slug OpenRouter, col fornitore davanti.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "anthropic/claude-opus-4-8")
AI_TIMEOUT_S = float(os.getenv("AI_TIMEOUT_S", "120"))

# Reference: Openverse (Creative Commons) e, se non trova niente, Wikimedia Commons.
REFERENCE_TIMEOUT_S = float(os.getenv("REFERENCE_TIMEOUT_S", "12"))
USER_AGENT = os.getenv("USER_AGENT", "das-challenge/1.0 (self-hosted game)")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
