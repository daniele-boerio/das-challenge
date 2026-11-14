"""Accesso con mail e codice a 6 cifre. Niente password.

La sessione non scade mai (è un gioco: lo ha chiesto il padrone di casa). Il
token sta in un cookie httpOnly, nel DB solo il suo hash.
"""

import hashlib
import logging
import re
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage

from fastapi import HTTPException, Request, Response, WebSocket
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import config
from .game import GameError, clean_name
from .models import LoginCode, Session, User

log = logging.getLogger(__name__)

COOKIE = "das_session"
COOKIE_MAX_AGE = 10 * 365 * 24 * 3600  # «non ti slogga mai»
CODE_TTL_S = 10 * 60
RESEND_S = 30
MAX_ATTEMPTS = 5
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def clean_email(email: str | None) -> str:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise GameError("Scrivi una mail valida")
    if config.ALLOWED_EMAILS and email not in config.ALLOWED_EMAILS:
        raise GameError("Questa mail non è abilitata a giocare", 403)
    return email


def send_code_mail(email: str, code: str):
    if not config.SMTP_HOST:
        log.warning("SMTP non configurato: codice di accesso per %s = %s", email, code)
        return
    msg = EmailMessage()
    msg["Subject"] = f"{code} è il tuo codice per Sfida DAS"
    msg["From"] = config.SMTP_FROM
    msg["To"] = email
    msg.set_content(
        f"Ciao!\n\nIl tuo codice per entrare in Sfida DAS è:\n\n    {code}\n\n"
        "Vale 10 minuti. Se non l'hai chiesto tu, ignora questa mail.\n"
    )
    msg.add_alternative(
        f"""<div style="font-family:system-ui,sans-serif;max-width:420px;margin:auto;padding:24px;
background:#fff8ec;border:3px solid #1a0f33;border-radius:20px;color:#1a0f33">
<h2 style="margin:0 0 8px">🏺 Sfida DAS</h2>
<p>Il tuo codice per entrare:</p>
<p style="font-size:34px;font-weight:800;letter-spacing:8px;background:#ffd23f;border:3px solid #1a0f33;
border-radius:14px;text-align:center;padding:10px">{code}</p>
<p style="color:#5b4d7a;font-size:14px">Vale 10 minuti. Se non l'hai chiesto tu, ignora questa mail.</p></div>""",
        subtype="html",
    )
    ctx = ssl.create_default_context()
    if config.SMTP_SSL:
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=ctx, timeout=20) as s:
            if config.SMTP_USER:
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
            s.send_message(msg)
    else:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
            s.starttls(context=ctx)
            if config.SMTP_USER:
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
            s.send_message(msg)


def request_code(db: DbSession, email: str) -> str:
    """Crea un codice nuovo e lo restituisce (lo spedisce il chiamante)."""
    email = clean_email(email)
    now = time.time()
    last = db.scalar(
        select(LoginCode).where(LoginCode.email == email).order_by(LoginCode.created_at.desc()).limit(1)
    )
    if last and now - last.created_at < RESEND_S:
        raise GameError(f"Aspetta {int(RESEND_S - (now - last.created_at)) + 1} secondi prima di chiederne un altro", 429)
    # I codici vecchi di questa mail non valgono più.
    for old in db.scalars(select(LoginCode).where(LoginCode.email == email, LoginCode.used.is_(False))):
        old.used = True
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(LoginCode(email=email, code_hash=_hash(f"{email}:{code}"), created_at=now, expires_at=now + CODE_TTL_S))
    db.flush()
    return code


def verify_code(db: DbSession, email: str, code: str) -> User:
    email = clean_email(email)
    code = re.sub(r"\D", "", code or "")
    lc = db.scalar(
        select(LoginCode)
        .where(LoginCode.email == email, LoginCode.used.is_(False))
        .order_by(LoginCode.created_at.desc())
        .limit(1)
    )
    if not lc or lc.expires_at < time.time():
        raise GameError("Il codice è scaduto: chiedine un altro")
    lc.attempts += 1
    if lc.attempts > MAX_ATTEMPTS:
        lc.used = True
        raise GameError("Troppi tentativi: chiedi un codice nuovo")
    if not secrets.compare_digest(lc.code_hash, _hash(f"{email}:{code}")):
        left = MAX_ATTEMPTS - lc.attempts
        raise GameError(f"Codice sbagliato ({left} tentativi rimasti)" if left else "Codice sbagliato: chiedine un altro")
    lc.used = True
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(email=email, created_at=time.time())
        db.add(user)
        db.flush()
    return user


def start_session(db: DbSession, user: User, response: Response):
    token = secrets.token_urlsafe(32)
    now = time.time()
    db.add(Session(token_hash=_hash(token), user_id=user.id, created_at=now, last_seen_at=now))
    response.set_cookie(
        COOKIE,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,
        path="/",
    )


def end_session(db: DbSession, token: str | None, response: Response):
    if token:
        s = db.scalar(select(Session).where(Session.token_hash == _hash(token)))
        if s:
            db.delete(s)
    response.delete_cookie(COOKIE, path="/")


def user_from_token(db: DbSession, token: str | None) -> User | None:
    if not token:
        return None
    s = db.scalar(select(Session).where(Session.token_hash == _hash(token)))
    if not s:
        return None
    now = time.time()
    if now - s.last_seen_at > 3600:
        s.last_seen_at = now
    return db.get(User, s.user_id)


def token_of(conn: Request | WebSocket) -> str | None:
    return conn.cookies.get(COOKIE)


def require_named(user: User | None) -> User:
    if not user:
        raise HTTPException(401, "Devi accedere")
    if not user.name:
        raise GameError("Prima scegli il tuo nome", 409)
    return user


def set_name(user: User, name: str):
    user.name = clean_name(name)
