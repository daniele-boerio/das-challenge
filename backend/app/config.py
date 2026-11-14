"""Tutte le variabili d'ambiente si leggono da qui."""

import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
MEDIA_DIR = DATA_DIR / "media"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'das.db'}")

# Se impostato, serve per creare una partita e per vedere la galleria.
# Chi entra dal link di una partita non ne ha bisogno.
ACCESS_CODE = os.getenv("ACCESS_CODE", "").strip()

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
