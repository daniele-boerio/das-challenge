"""Le regole della sfida: partite, round, power-up, voti, punteggi.

Le funzioni che cambiano lo stato vanno chiamate con `LOCK` preso (lo fanno le
rotte): i giocatori sono due, ma i loro clic arrivano in parallelo, e due upload
contemporanei non devono far partire due volte il giudice.
"""

import logging
import random
import secrets
import string
import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, judge, media
from .models import Match, Round
from .subjects import (
    DEFAULT_MINUTES,
    DIFFICULTIES,
    HANDICAPS,
    MULTIPLIER,
    THEMES,
    key,
    pick,
)

log = logging.getLogger(__name__)

LOCK = threading.RLock()
COUNTDOWN_S = 5          # il «3, 2, 1» prima che la reference si veda
MEMORY_VISIBLE_S = 30    # nel round a memoria la reference sparisce dopo
MEMORY_CHANCE = 0.25
REROLL_WINDOW_S = 120
EXTRA_S = 120
SABOTAGE_S = 60
JUDGE_MODES = ("voto", "ai", "entrambi")
HANDICAP_MODES = ("off", "leader", "random")
POWERUPS = ("extra", "sabotage", "reroll")
ROLES = ("host", "guest")


class GameError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def now() -> float:
    return time.time()


def other(role: str) -> str:
    return "guest" if role == "host" else "host"


# ── impostazioni ──────────────────────────────────────────────────────────────


def default_settings() -> dict:
    return {
        "rounds": 3,
        "judge": "ai" if judge.available() else "voto",
        "theme": "misto",
        "minutes": dict(DEFAULT_MINUTES),
        "powerups": True,
        "handicap": "leader",
        "memory": True,
    }


def clean_settings(raw: dict | None) -> dict:
    s = default_settings()
    raw = raw or {}
    try:
        s["rounds"] = max(1, min(10, int(raw.get("rounds", s["rounds"]))))
    except (TypeError, ValueError):
        pass
    if raw.get("judge") in JUDGE_MODES:
        s["judge"] = raw["judge"]
    if s["judge"] != "voto" and not judge.available():
        s["judge"] = "voto"
    if raw.get("theme") in THEMES:
        s["theme"] = raw["theme"]
    minutes = raw.get("minutes") or {}
    for d in DIFFICULTIES:
        try:
            s["minutes"][d] = max(1, min(180, int(minutes.get(d, s["minutes"][d]))))
        except (TypeError, ValueError):
            pass
    if "powerups" in raw:
        s["powerups"] = bool(raw["powerups"])
    if raw.get("handicap") in HANDICAP_MODES:
        s["handicap"] = raw["handicap"]
    if "memory" in raw:
        s["memory"] = bool(raw["memory"])
    return s


def clean_name(name: str | None) -> str:
    name = " ".join((name or "").split())[:40]
    if not name:
        raise GameError("Scrivi il tuo nome")
    return name


# ── partita ───────────────────────────────────────────────────────────────────


def _new_code(db: Session) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # niente I e O: si confondono con 1 e 0
    for _ in range(50):
        code = "".join(secrets.choice(alphabet) for _ in range(4))
        if not db.scalar(select(Match.id).where(Match.code == code)):
            return code
    return "".join(secrets.choice(alphabet + string.digits) for _ in range(6))


def create_match(db: Session, host, settings: dict | None) -> Match:
    """`host` è lo User che crea la partita."""
    m = Match(
        code=_new_code(db),
        created_at=now(),
        status="lobby",
        settings=clean_settings(settings),
        host_user_id=host.id,
        host_name=clean_name(host.name),
        host_token=secrets.token_urlsafe(24),
        powerups={r: {p: True for p in POWERUPS} for r in ROLES},
    )
    db.add(m)
    db.flush()
    return m


def get_match(db: Session, code: str) -> Match:
    m = db.scalar(select(Match).where(Match.code == code.upper()))
    if not m:
        raise GameError("Partita non trovata", 404)
    return m


def role_of(m: Match, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    if m.host_user_id == user_id:
        return "host"
    if m.guest_user_id is not None and m.guest_user_id == user_id:
        return "guest"
    return None


def require_role(m: Match, user_id: int | None) -> str:
    role = role_of(m, user_id)
    if not role:
        raise GameError("Non fai parte di questa partita", 403)
    return role


def has_guest(m: Match) -> bool:
    return m.guest_user_id is not None


def check_can_view(m: Match, role: str | None):
    """La partita la vedono solo i due giocatori. Gli altri la vedono solo finché
    il posto dell'avversario è libero, per poterci entrare dal link."""
    if role is None and has_guest(m):
        raise GameError("Questa partita non è tua: la vedono solo i due giocatori", 403)


def join(db: Session, m: Match, user) -> None:
    if m.host_user_id == user.id:
        raise GameError("Non puoi sfidare te stesso: manda il link all'avversario")
    if has_guest(m):
        raise GameError("La partita ha già due giocatori", 409)
    name = clean_name(user.name)
    if name.casefold() == m.host_name.casefold():
        name = f"{name} (2)"
    m.guest_user_id = user.id
    m.guest_name = name
    m.guest_token = secrets.token_urlsafe(24)
    if m.status == "lobby":
        m.status = "ready"


def name_of(m: Match, role: str) -> str:
    return m.host_name if role == "host" else (m.guest_name or "")


def current_round(m: Match) -> Round | None:
    return m.rounds[-1] if m.rounds and m.rounds[-1].status != "done" else None


def totals(m: Match) -> dict[str, float]:
    t = {"host": 0.0, "guest": 0.0}
    for r in m.rounds:
        t["host"] += r.host_points or 0
        t["guest"] += r.guest_points or 0
    return {k: round(v, 1) for k, v in t.items()}


def winner(m: Match) -> str | None:
    """'host', 'guest', 'pari', oppure None se la partita non è finita."""
    if m.status != "finished":
        return None
    t = totals(m)
    if t["host"] == t["guest"]:
        return "pari"
    return "host" if t["host"] > t["guest"] else "guest"


# ── round ─────────────────────────────────────────────────────────────────────


def suggested_difficulty(m: Match) -> str:
    """Difficoltà crescente lungo la partita: facile → media → difficile."""
    n, total = len(m.rounds), m.settings["rounds"]
    if total <= 1:
        return "media"
    idx = min(2, int(n * 3 / total))
    return DIFFICULTIES[idx]


def check_can_start(m: Match, role: str):
    if role != "host":
        raise GameError("Il round lo fa partire chi ha creato la partita", 403)
    if not has_guest(m):
        raise GameError("Aspetta che l'avversario entri")
    if m.status == "finished":
        raise GameError("La partita è finita")
    if current_round(m):
        raise GameError("C'è già un round in corso", 409)


def choose_subject(m: Match, difficulty: str, exclude_current: bool = False):
    if difficulty not in DIFFICULTIES:
        difficulty = random.choice(DIFFICULTIES)
    used = {r.subject_key for r in m.rounds}
    return difficulty, pick(difficulty, m.settings["theme"], used)


def _handicaps(m: Match) -> dict[str, str | None]:
    mode = m.settings.get("handicap", "off")
    out: dict[str, str | None] = {"host": None, "guest": None}
    if mode == "random":
        for r in ROLES:
            if random.random() < 0.4:
                out[r] = random.choice(HANDICAPS)
    elif mode == "leader":
        t = totals(m)
        if t["host"] != t["guest"]:
            leader = "host" if t["host"] > t["guest"] else "guest"
            out[leader] = random.choice(HANDICAPS)
    return out


def create_round(
    db: Session, m: Match, difficulty: str, subject: tuple, image: str | None, attribution: dict | None
) -> Round:
    name, _query, theme = subject
    memory = bool(m.settings.get("memory")) and len(m.rounds) >= 1 and random.random() < MEMORY_CHANCE
    hc = _handicaps(m)
    r = Round(
        match=m,
        number=len(m.rounds) + 1,
        difficulty=difficulty,
        theme=theme,
        subject=name,
        subject_key=key(difficulty, name),
        image_file=image,
        attribution=attribution,
        memory=memory,
        starts_at=now() + COUNTDOWN_S,
        duration_s=m.settings["minutes"][difficulty] * 60,
        status="sculpting",
        host_handicap=hc["host"],
        guest_handicap=hc["guest"],
        events=[],
    )
    db.add(r)
    m.status = "playing"
    db.flush()
    return r


def end_at(r: Round, role: str) -> float:
    delta = r.host_delta_s if role == "host" else r.guest_delta_s
    return r.starts_at + r.duration_s + delta


def finished_at(r: Round, role: str) -> float | None:
    return r.host_finished_at if role == "host" else r.guest_finished_at


def photo_of(r: Round, role: str) -> str | None:
    return r.host_photo if role == "host" else r.guest_photo


# ── power-up ──────────────────────────────────────────────────────────────────


def check_powerup(m: Match, role: str, kind: str) -> Round:
    if not m.settings.get("powerups"):
        raise GameError("In questa partita i power-up sono spenti")
    if kind not in POWERUPS:
        raise GameError("Power-up sconosciuto")
    if not m.powerups.get(role, {}).get(kind):
        raise GameError("Hai già usato questo power-up")
    r = current_round(m)
    if not r or r.status != "sculpting":
        raise GameError("I power-up si usano durante un round")
    t = now()
    if t < r.starts_at:
        raise GameError("Aspetta che il round cominci")
    if kind == "extra":
        if finished_at(r, role) or t >= end_at(r, role):
            raise GameError("Il tuo tempo è già finito")
    elif kind == "sabotage":
        o = other(role)
        if finished_at(r, o) or t >= end_at(r, o):
            raise GameError("L'avversario ha già finito")
    elif kind == "reroll":
        if t - r.starts_at > REROLL_WINDOW_S:
            raise GameError("Il cambio reference vale solo nei primi 2 minuti")
        if r.host_finished_at or r.guest_finished_at:
            raise GameError("Qualcuno ha già consegnato")
    return r


def _spend(m: Match, role: str, kind: str):
    pu = {k: dict(v) for k, v in m.powerups.items()}
    pu[role][kind] = False
    m.powerups = pu


def apply_timer_powerup(m: Match, r: Round, role: str, kind: str):
    t = now()
    if kind == "extra":
        if role == "host":
            r.host_delta_s += EXTRA_S
        else:
            r.guest_delta_s += EXTRA_S
    else:
        o = other(role)
        # Non si scende sotto i 30 secondi rimasti: un sabotaggio, non una squalifica.
        cut = min(SABOTAGE_S, max(0, int(end_at(r, o) - t - 30)))
        if o == "host":
            r.host_delta_s -= cut
        else:
            r.guest_delta_s -= cut
    r.events = [*r.events, {"by": role, "kind": kind, "at": t}]
    _spend(m, role, kind)


def apply_reroll(m: Match, r: Round, role: str, subject: tuple, image: str | None, attribution: dict | None):
    """Nuovo soggetto della stessa difficoltà; il round riparte da capo per tutti e due."""
    name, _q, theme = subject
    old_image = r.image_file
    r.subject, r.theme, r.subject_key = name, theme, key(r.difficulty, name)
    r.image_file, r.attribution = image, attribution
    r.starts_at = now() + COUNTDOWN_S
    r.host_delta_s = r.guest_delta_s = 0
    r.events = [{"by": role, "kind": "reroll", "at": now()}]
    _spend(m, role, "reroll")
    if old_image:
        try:
            media.path_of(old_image).unlink(missing_ok=True)
        except Exception:
            pass


# ── consegna, voti, punteggi ──────────────────────────────────────────────────


def get_round(m: Match, number: int) -> Round:
    for r in m.rounds:
        if r.number == number:
            return r
    raise GameError("Round non trovato", 404)


def check_upload(m: Match, r: Round):
    if r.status != "sculpting":
        raise GameError("Le foto di questo round sono già state consegnate")
    if now() < r.starts_at:
        raise GameError("Il round non è ancora cominciato")


def set_photo(r: Round, role: str, name: str) -> str | None:
    old = photo_of(r, role)
    if role == "host":
        r.host_photo, r.host_finished_at = name, now()
    else:
        r.guest_photo, r.guest_finished_at = name, now()
    return old


def judge_mode(m: Match) -> str:
    return m.settings.get("judge", "voto")


def needs_votes(m: Match, r: Round) -> bool:
    return judge_mode(m) in ("voto", "entrambi") or r.ai_status == "failed"


def needs_ai(m: Match, r: Round) -> bool:
    return judge_mode(m) in ("ai", "entrambi") and r.ai_status != "failed"


def after_upload(m: Match, r: Round) -> bool:
    """Se ora ci sono entrambe le foto si passa al giudizio. True se va avviato il giudice AI."""
    if not (r.host_photo and r.guest_photo):
        return False
    r.status = "judging"
    if judge_mode(m) in ("ai", "entrambi"):
        if judge.available():
            r.ai_status, r.ai_started_at = "pending", now()
            return True
        r.ai_status, r.ai_error = "failed", "Il giudice AI non è configurato: votate voi"
    maybe_finalize(m, r)
    return False


def vote(m: Match, r: Round, role: str, value) -> None:
    if r.status != "judging":
        raise GameError("Ora non si vota")
    if not needs_votes(m, r):
        raise GameError("In questa partita giudica l'AI")
    try:
        v = round(float(value) * 2) / 2
    except (TypeError, ValueError):
        raise GameError("Voto non valido")
    if not 0 <= v <= 10:
        raise GameError("Il voto va da 0 a 10")
    if role == "host":
        r.host_vote = v
    else:
        r.guest_vote = v
    maybe_finalize(m, r)


def maybe_finalize(m: Match, r: Round) -> bool:
    if r.status != "judging":
        return False
    if needs_ai(m, r) and r.ai_status != "done":
        return False
    use_votes = needs_votes(m, r)
    if use_votes and (r.host_vote is None or r.guest_vote is None):
        return False

    def score(role: str) -> float:
        parts = []
        if use_votes:
            # il voto per host lo dà guest, e viceversa
            parts.append(r.guest_vote if role == "host" else r.host_vote)
        if r.ai_status == "done" and judge_mode(m) != "voto":
            parts.append(r.ai_result[role]["score"])
        return round(sum(parts) / len(parts), 1)

    mult = MULTIPLIER[r.difficulty]
    r.host_score, r.guest_score = score("host"), score("guest")
    r.host_points = round(r.host_score * mult, 1)
    r.guest_points = round(r.guest_score * mult, 1)
    r.status = "done"
    if r.number >= m.settings["rounds"]:
        m.status, m.finished_at = "finished", now()
    else:
        m.status = "ready"
    return True


def ai_failed(m: Match, r: Round, message: str):
    r.ai_status, r.ai_error = "failed", message[:500]
    maybe_finalize(m, r)


def heal(m: Match) -> bool:
    """Un giudice rimasto «in corso» troppo a lungo (processo riavviato, rete
    appesa) non deve bloccare la partita: si passa al voto."""
    r = current_round(m)
    limit = config.AI_TIMEOUT_S * 3 + 30
    if r and r.ai_status == "pending" and r.ai_started_at and now() - r.ai_started_at > limit:
        ai_failed(m, r, "Il giudice AI non ha risposto in tempo: votate voi")
        return True
    return False


def finish(m: Match, role: str):
    if role != "host":
        raise GameError("Solo chi ha creato la partita può chiuderla", 403)
    if current_round(m):
        raise GameError("Finite prima il round in corso")
    m.status, m.finished_at = "finished", now()


# ── cosa vede ciascuno ────────────────────────────────────────────────────────


def _round_view(m: Match, r: Round, role: str | None) -> dict:
    revealed = r.status != "sculpting"
    done = r.status == "done"
    t = now()

    def photo(who: str):
        if who == role or revealed:
            return media.url(photo_of(r, who))
        return None

    votes: dict = {
        "needed": needs_votes(m, r) if r.status != "sculpting" else judge_mode(m) in ("voto", "entrambi"),
        "host_voted": r.host_vote is not None,
        "guest_voted": r.guest_vote is not None,
    }
    if done:
        votes.update({"host": r.host_vote, "guest": r.guest_vote})
    elif role:
        votes["mine"] = r.host_vote if role == "host" else r.guest_vote

    # Soggetto e foto partono già col countdown: lo stato arriva una volta sola e
    # il client li tiene coperti finché il «3, 2, 1» non è finito.
    hide_ref = r.memory and t > r.starts_at + MEMORY_VISIBLE_S and not revealed
    show_ref = True
    return {
        "number": r.number,
        "difficulty": r.difficulty,
        "multiplier": MULTIPLIER[r.difficulty],
        "theme": r.theme,
        "subject": r.subject if show_ref else None,
        "image": media.url(r.image_file) if show_ref and not hide_ref else None,
        "attribution": r.attribution if show_ref else None,
        "memory": r.memory,
        "memory_hide_at": r.starts_at + MEMORY_VISIBLE_S if r.memory else None,
        "status": r.status,
        "starts_at": r.starts_at,
        "duration_s": r.duration_s,
        "end_at": {who: end_at(r, who) for who in ROLES},
        "finished_at": {who: finished_at(r, who) for who in ROLES},
        "delivered": {who: bool(photo_of(r, who)) for who in ROLES},
        "photos": {who: photo(who) for who in ROLES},
        "handicaps": {"host": r.host_handicap, "guest": r.guest_handicap},
        "events": r.events or [],
        "votes": votes,
        "ai": {
            "status": r.ai_status,
            "error": r.ai_error,
            "result": r.ai_result if done else None,
        },
        "scores": {"host": r.host_score, "guest": r.guest_score} if done else None,
        "points": {"host": r.host_points, "guest": r.guest_points} if done else None,
    }


def view(m: Match, role: str | None, online: set[str] | None = None) -> dict:
    online = online or set()
    t = totals(m)
    players = {}
    for who in ROLES:
        if who == "guest" and not has_guest(m):
            players[who] = None
            continue
        players[who] = {
            "name": name_of(m, who),
            "total": t[who],
            "online": who in online,
            "powerups": m.powerups.get(who, {}) if m.settings.get("powerups") else {},
        }
    return {
        "code": m.code,
        "status": m.status,
        "you": role,
        "server_now": now(),
        "created_at": m.created_at,
        "finished_at": m.finished_at,
        "settings": m.settings,
        "players": players,
        "rounds": [_round_view(m, r, role) for r in m.rounds],
        "suggested_difficulty": suggested_difficulty(m) if m.status in ("lobby", "ready") else None,
        "winner": winner(m),
        "rematch_code": m.rematch_code,
    }
