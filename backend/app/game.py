"""Le regole della sfida: partite, round, power-up, voti, punteggi.

Ogni giocatore ha un posto (`seat`): 0 è chi ha creato la partita, poi 1, 2…
fino a 7. Le funzioni che cambiano lo stato vanno chiamate con `LOCK` preso (lo
fanno le rotte e il giro del ticker): i clic dei giocatori arrivano in parallelo,
e due upload contemporanei non devono far partire due volte il giudice.
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
from .models import Entry, Match, Player, Round
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
MAX_PLAYERS = 8
COUNTDOWN_S = 5          # il «3, 2, 1» prima che la reference si veda
MEMORY_VISIBLE_S = 30    # nel round a memoria la reference sparisce dopo
MEMORY_CHANCE = 0.25
REROLL_WINDOW_S = 120
EXTRA_S = 120
SABOTAGE_S = 60
GRACE_S = 60             # a scadenza rigida, il tempo per fotografare e consegnare
JUDGE_MODES = ("voto", "ai", "entrambi")
HANDICAP_MODES = ("off", "leader", "random")
# libero: allo scadere si può continuare · rigido: poi le consegne si chiudono ·
# nessuno: niente timer, il round finisce quando hanno consegnato tutti
TIMER_MODES = ("libero", "rigido", "nessuno")
POWERUPS = ("extra", "sabotage", "reroll")


class GameError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def now() -> float:
    return time.time()


# ── impostazioni ──────────────────────────────────────────────────────────────


def default_settings() -> dict:
    return {
        "rounds": 3,
        "judge": "ai" if judge.available() else "voto",
        "theme": "misto",
        "minutes": dict(DEFAULT_MINUTES),
        "timer": "libero",
        "rush": False,
        "rush_after": 2,
        "rush_minutes": 3,
        "powerups": True,
        "handicap": "leader",
        "memory": True,
    }


def _int(raw: dict, k: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(raw.get(k, default))))
    except (TypeError, ValueError):
        return default


def clean_settings(raw: dict | None) -> dict:
    s = default_settings()
    raw = raw or {}
    s["rounds"] = _int(raw, "rounds", s["rounds"], 1, 10)
    if raw.get("judge") in JUDGE_MODES:
        s["judge"] = raw["judge"]
    if s["judge"] != "voto" and not judge.available():
        s["judge"] = "voto"
    if raw.get("theme") in THEMES:
        s["theme"] = raw["theme"]
    minutes = raw.get("minutes") or {}
    for d in DIFFICULTIES:
        s["minutes"][d] = _int(minutes, d, s["minutes"][d], 1, 180)
    if raw.get("timer") in TIMER_MODES:
        s["timer"] = raw["timer"]
    for flag in ("rush", "powerups", "memory"):
        if flag in raw:
            s[flag] = bool(raw[flag])
    s["rush_after"] = _int(raw, "rush_after", s["rush_after"], 1, MAX_PLAYERS - 1)
    s["rush_minutes"] = _int(raw, "rush_minutes", s["rush_minutes"], 1, 60)
    if raw.get("handicap") in HANDICAP_MODES:
        s["handicap"] = raw["handicap"]
    return s


def settings_of(m: Match) -> dict:
    """Le impostazioni con i valori nuovi riempiti: le partite di prima non li hanno."""
    return {**default_settings(), "judge": m.settings.get("judge", "voto"), **m.settings}


def timed(m: Match) -> bool:
    return settings_of(m)["timer"] != "nessuno"


def clean_name(name: str | None) -> str:
    name = " ".join((name or "").split())[:40]
    if not name:
        raise GameError("Scrivi il tuo nome")
    return name


# ── partita e giocatori ───────────────────────────────────────────────────────


def _new_code(db: Session) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # niente I e O: si confondono con 1 e 0
    for _ in range(50):
        code = "".join(secrets.choice(alphabet) for _ in range(4))
        if not db.scalar(select(Match.id).where(Match.code == code)):
            return code
    return "".join(secrets.choice(alphabet + string.digits) for _ in range(6))


def _fresh_powerups() -> dict:
    return {p: True for p in POWERUPS}


def create_match(db: Session, host, settings: dict | None) -> Match:
    """`host` è lo User che crea la partita: si siede al posto 0."""
    name = clean_name(host.name)
    m = Match(
        code=_new_code(db),
        created_at=now(),
        status="lobby",
        settings=clean_settings(settings),
        host_user_id=host.id,
        host_name=name,
        host_token="",
        powerups={},
    )
    m.players.append(Player(user_id=host.id, seat=0, name=name, joined_at=now(), powerups=_fresh_powerups()))
    db.add(m)
    db.flush()
    return m


def get_match(db: Session, code: str) -> Match:
    m = db.scalar(select(Match).where(Match.code == code.upper()))
    if not m:
        raise GameError("Partita non trovata", 404)
    return m


def seat_of(m: Match, user_id: int | None) -> int | None:
    if user_id is None:
        return None
    for p in m.players:
        if p.user_id == user_id:
            return p.seat
    return None


def require_seat(m: Match, user_id: int | None) -> int:
    seat = seat_of(m, user_id)
    if seat is None:
        raise GameError("Non fai parte di questa partita", 403)
    return seat


def player(m: Match, seat: int) -> Player:
    for p in m.players:
        if p.seat == seat:
            return p
    raise GameError("Giocatore non trovato", 404)


def joinable(m: Match) -> bool:
    """Si entra solo dalla sala d'attesa: col primo round la partita si chiude."""
    return m.status == "lobby" and len(m.players) < MAX_PLAYERS


def check_can_view(m: Match, seat: int | None):
    """La partita la vedono solo i giocatori. Gli altri la vedono solo finché ci
    si può entrare dal link."""
    if seat is None and not joinable(m):
        raise GameError("Questa partita non è tua: la vedono solo i giocatori", 403)


def join(db: Session, m: Match, user) -> int:
    if seat_of(m, user.id) is not None:
        if m.host_user_id == user.id:
            raise GameError("Non puoi sfidare te stesso: manda il link agli avversari")
        raise GameError("Sei già in questa partita")
    if m.status != "lobby":
        raise GameError("La partita è già cominciata", 409)
    if len(m.players) >= MAX_PLAYERS:
        raise GameError(f"La partita è al completo ({MAX_PLAYERS} giocatori)", 409)
    base = clean_name(user.name)
    taken = {p.name.casefold() for p in m.players}
    name, n = base, 2
    while name.casefold() in taken:
        name, n = f"{base} ({n})", n + 1
    seat = max(p.seat for p in m.players) + 1
    m.players.append(Player(user_id=user.id, seat=seat, name=name, joined_at=now(), powerups=_fresh_powerups()))
    db.flush()
    return seat


def current_round(m: Match) -> Round | None:
    return m.rounds[-1] if m.rounds and m.rounds[-1].status != "done" else None


def totals(m: Match) -> dict[int, float]:
    t = {p.seat: 0.0 for p in m.players}
    for r in m.rounds:
        for e in r.entries:
            if e.seat in t:
                t[e.seat] += e.points or 0
    return {k: round(v, 1) for k, v in t.items()}


def winners(m: Match) -> list[int] | None:
    """I posti col totale più alto (più d'uno se a pari merito); None se non è finita."""
    if m.status != "finished":
        return None
    t = totals(m)
    if not t:
        return []
    best = max(t.values())
    return sorted(s for s, v in t.items() if v == best)


# ── round ─────────────────────────────────────────────────────────────────────


def suggested_difficulty(m: Match) -> str:
    """Difficoltà crescente lungo la partita: facile → media → difficile."""
    n, total = len(m.rounds), m.settings["rounds"]
    if total <= 1:
        return "media"
    idx = min(2, int(n * 3 / total))
    return DIFFICULTIES[idx]


def check_can_start(m: Match, seat: int):
    if seat != 0:
        raise GameError("Il round lo fa partire chi ha creato la partita", 403)
    if len(m.players) < 2:
        raise GameError("Aspetta che entri almeno un avversario")
    if m.status == "finished":
        raise GameError("La partita è finita")
    if current_round(m):
        raise GameError("C'è già un round in corso", 409)


def choose_subject(m: Match, difficulty: str, also_exclude: set[str] | None = None):
    if difficulty not in DIFFICULTIES:
        difficulty = random.choice(DIFFICULTIES)
    used = {r.subject_key for r in m.rounds} | (also_exclude or set())
    return difficulty, pick(difficulty, m.settings["theme"], used)


def _handicaps(m: Match) -> dict[int, str | None]:
    mode = m.settings.get("handicap", "off")
    seats = [p.seat for p in m.players]
    out: dict[int, str | None] = {s: None for s in seats}
    if mode == "random":
        for s in seats:
            if random.random() < 0.4:
                out[s] = random.choice(HANDICAPS)
    elif mode == "leader":
        t = totals(m)
        best = max(t.values()) if t else 0
        leaders = [s for s, v in t.items() if v == best]
        if best > 0 and len(leaders) < len(seats):
            for s in leaders:
                out[s] = random.choice(HANDICAPS)
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
        events=[],
        votes={},
    )
    for p in m.players:
        r.entries.append(Entry(seat=p.seat, handicap=hc[p.seat]))
    db.add(r)
    m.status = "playing"
    db.flush()
    return r


def entry(r: Round, seat: int) -> Entry:
    for e in r.entries:
        if e.seat == seat:
            return e
    raise GameError("Non giochi questo round", 403)


def end_at(m: Match, r: Round, e: Entry) -> float | None:
    """Quando finisce il tempo di quel giocatore (None se si gioca senza tempo)."""
    if not timed(m):
        return None
    return r.starts_at + r.duration_s + e.delta_s


def close_at(m: Match, r: Round, e: Entry) -> float | None:
    """Dopo questo istante quel giocatore non può più consegnare (None = mai).
    Lo decidono il timer rigido e la regola «gli ultimi rincorrono», con un
    minuto in più per scattare la foto."""
    limits = []
    if settings_of(m)["timer"] == "rigido":
        limits.append(end_at(m, r, e))
    if r.rush_end_at:
        limits.append(r.rush_end_at)
    return min(limits) + GRACE_S if limits else None


def deadline(m: Match, r: Round, e: Entry) -> float | None:
    """Il tempo da mostrare sul timer: la fine del proprio tempo o della rincorsa."""
    ts = [t for t in (end_at(m, r, e), r.rush_end_at) if t]
    return min(ts) if ts else None


def delivered(r: Round) -> list[Entry]:
    return [e for e in r.entries if e.photo]


# ── power-up ──────────────────────────────────────────────────────────────────


def check_powerup(m: Match, seat: int, kind: str, target: int | None = None) -> tuple[Round, int | None]:
    """Controlla che il power-up si possa usare; per il sabotaggio restituisce anche il bersaglio."""
    if not m.settings.get("powerups"):
        raise GameError("In questa partita i power-up sono spenti")
    if kind not in POWERUPS:
        raise GameError("Power-up sconosciuto")
    if not player(m, seat).powerups.get(kind):
        raise GameError("Hai già usato questo power-up")
    r = current_round(m)
    if not r or r.status != "sculpting":
        raise GameError("I power-up si usano durante un round")
    t = now()
    if t < r.starts_at:
        raise GameError("Aspetta che il round cominci")
    if kind in ("extra", "sabotage") and not timed(m):
        raise GameError("Senza tempo questo power-up non serve")
    if kind == "extra":
        e = entry(r, seat)
        if e.photo or t >= end_at(m, r, e):
            raise GameError("Il tuo tempo è già finito")
    elif kind == "sabotage":
        others = [x.seat for x in r.entries if x.seat != seat]
        if target is None and len(others) == 1:
            target = others[0]
        if target not in others:
            raise GameError("Scegli chi sabotare")
        e = entry(r, target)
        if e.photo or t >= end_at(m, r, e):
            raise GameError(f"{player(m, target).name} ha già finito")
    elif kind == "reroll":
        if t - r.starts_at > REROLL_WINDOW_S:
            raise GameError("Il cambio reference vale solo nei primi 2 minuti")
        if delivered(r):
            raise GameError("Qualcuno ha già consegnato")
    return r, target


def _spend(m: Match, seat: int, kind: str):
    p = player(m, seat)
    p.powerups = {**p.powerups, kind: False}


def apply_timer_powerup(m: Match, r: Round, seat: int, kind: str, target: int | None):
    t = now()
    if kind == "extra":
        entry(r, seat).delta_s += EXTRA_S
        r.events = [*r.events, {"by": seat, "kind": kind, "at": t}]
    else:
        e = entry(r, target)
        # Non si scende sotto i 30 secondi rimasti: un sabotaggio, non una squalifica.
        cut = min(SABOTAGE_S, max(0, int(end_at(m, r, e) - t - 30)))
        e.delta_s -= cut
        r.events = [*r.events, {"by": seat, "kind": kind, "target": target, "at": t}]
    _spend(m, seat, kind)


def apply_reroll(m: Match, r: Round, seat: int, subject: tuple, image: str | None, attribution: dict | None):
    """Nuovo soggetto della stessa difficoltà; il round riparte da capo per tutti."""
    name, _q, theme = subject
    old_image = r.image_file
    r.subject, r.theme, r.subject_key = name, theme, key(r.difficulty, name)
    r.image_file, r.attribution = image, attribution
    r.starts_at = now() + COUNTDOWN_S
    r.rush_end_at = None
    for e in r.entries:
        e.delta_s = 0
    r.events = [{"by": seat, "kind": "reroll", "at": now()}]
    _spend(m, seat, "reroll")
    if old_image:
        try:
            media.path_of(old_image).unlink(missing_ok=True)
        except Exception:
            pass


# ── consegna ──────────────────────────────────────────────────────────────────


def get_round(m: Match, number: int) -> Round:
    for r in m.rounds:
        if r.number == number:
            return r
    raise GameError("Round non trovato", 404)


def check_upload(m: Match, r: Round, seat: int):
    if r.status != "sculpting":
        raise GameError("Le consegne di questo round sono chiuse")
    if now() < r.starts_at:
        raise GameError("Il round non è ancora cominciato")
    c = close_at(m, r, entry(r, seat))
    if c is not None and now() > c:
        raise GameError("Tempo scaduto: le consegne sono chiuse")


def set_photo(m: Match, r: Round, seat: int, name: str) -> str | None:
    e = entry(r, seat)
    old = e.photo
    e.photo, e.finished_at = name, now()
    s = settings_of(m)
    n = len(delivered(r))
    if s["rush"] and r.rush_end_at is None and s["rush_after"] <= n < len(r.entries):
        r.rush_end_at = now() + s["rush_minutes"] * 60
    return old


def judge_mode(m: Match) -> str:
    return m.settings.get("judge", "voto")


def advance(m: Match, r: Round) -> bool:
    """Chiude le consegne quando hanno consegnato tutti, o quando chi manca non può
    più farlo. True se va avviato il giudice AI."""
    if r.status != "sculpting":
        return False
    t = now()
    for e in r.entries:
        if e.photo:
            continue
        c = close_at(m, r, e)
        if c is None or t <= c:
            return False
    r.status = "judging"
    if not delivered(r):
        maybe_finalize(m, r)
        return False
    if judge_mode(m) in ("ai", "entrambi"):
        if judge.available():
            r.ai_status, r.ai_started_at = "pending", now()
            return True
        r.ai_status, r.ai_error = "failed", "Il giudice AI non è configurato: votate voi"
    maybe_finalize(m, r)
    return False


# ── voti e punteggi ───────────────────────────────────────────────────────────


def needs_votes(m: Match, r: Round) -> bool:
    return judge_mode(m) in ("voto", "entrambi") or r.ai_status == "failed"


def needs_ai(m: Match, r: Round) -> bool:
    return judge_mode(m) in ("ai", "entrambi") and r.ai_status != "failed"


def vote_targets(r: Round, seat: int) -> list[int]:
    """Chi deve votare quel giocatore: le creazioni consegnate da tutti gli altri."""
    return [e.seat for e in delivered(r) if e.seat != seat]


def has_voted(r: Round, seat: int) -> bool:
    mine = (r.votes or {}).get(str(seat)) or {}
    return all(str(t) in mine for t in vote_targets(r, seat))


def votes_closed(r: Round) -> bool:
    return bool((r.votes or {}).get("closed"))


def _clean_vote(value) -> float:
    try:
        v = round(float(value) * 2) / 2
    except (TypeError, ValueError):
        raise GameError("Voto non valido")
    if not 0 <= v <= 10:
        raise GameError("Il voto va da 0 a 10")
    return v


def vote(m: Match, r: Round, seat: int, values: dict) -> None:
    """`values` = {posto: voto} per tutte le creazioni degli altri, in un colpo solo."""
    if r.status != "judging":
        raise GameError("Ora non si vota")
    if not needs_votes(m, r):
        raise GameError("In questa partita giudica l'AI")
    if votes_closed(r):
        raise GameError("La votazione è chiusa")
    targets = vote_targets(r, seat)
    if not targets:
        raise GameError("Non c'è nessuna creazione da votare")
    values = {str(k): v for k, v in (values or {}).items()}
    missing = [t for t in targets if str(t) not in values]
    if missing:
        raise GameError(f"Manca il voto per {player(m, missing[0]).name}")
    mine = {str(t): _clean_vote(values[str(t)]) for t in targets}
    r.votes = {**(r.votes or {}), str(seat): mine}
    maybe_finalize(m, r)


def close_votes(m: Match, r: Round, seat: int):
    """Chi ha creato la partita chiude il voto senza aspettare chi è sparito."""
    if seat != 0:
        raise GameError("Solo chi ha creato la partita può chiudere il voto", 403)
    if r.status != "judging" or not needs_votes(m, r):
        raise GameError("Ora non c'è un voto da chiudere")
    r.votes = {**(r.votes or {}), "closed": True}
    maybe_finalize(m, r)


def received_votes(r: Round, seat: int) -> list[float]:
    out = []
    for voter, given in (r.votes or {}).items():
        if voter != "closed" and isinstance(given, dict) and str(seat) in given:
            out.append(given[str(seat)])
    return out


def maybe_finalize(m: Match, r: Round) -> bool:
    if r.status != "judging":
        return False
    if needs_ai(m, r) and r.ai_status != "done":
        return False
    use_votes = needs_votes(m, r)
    if use_votes and not votes_closed(r):
        if not all(has_voted(r, p.seat) for p in m.players):
            return False

    ai = (r.ai_result or {}).get("entries", {}) if r.ai_status == "done" and judge_mode(m) != "voto" else {}
    mult = MULTIPLIER[r.difficulty]
    for e in r.entries:
        if not e.photo:
            e.score, e.points = 0.0, 0.0
            continue
        parts = []
        if use_votes:
            got = received_votes(r, e.seat)
            if got:
                parts.append(sum(got) / len(got))
        if str(e.seat) in ai:
            parts.append(ai[str(e.seat)]["score"])
        e.score = round(sum(parts) / len(parts), 1) if parts else 0.0
        e.points = round(e.score * mult, 1)
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


def tick(m: Match) -> tuple[bool, bool]:
    """Il giro periodico: chiude le consegne scadute e sblocca un giudice appeso.
    Restituisce (cambiato qualcosa, va avviato il giudice)."""
    r = current_round(m)
    if not r:
        return False, False
    if r.status == "sculpting":
        launch = advance(m, r)
        return r.status != "sculpting", launch
    return heal(m), False


def finish(m: Match, seat: int):
    if seat != 0:
        raise GameError("Solo chi ha creato la partita può chiuderla", 403)
    if current_round(m):
        raise GameError("Finite prima il round in corso")
    if not m.rounds:
        raise GameError("Non avete ancora giocato nessun round")
    m.status, m.finished_at = "finished", now()


# ── cosa vede ciascuno ────────────────────────────────────────────────────────


def _round_view(m: Match, r: Round, seat: int | None) -> dict:
    revealed = r.status != "sculpting"
    done = r.status == "done"
    t = now()

    entries = []
    for e in r.entries:
        entries.append(
            {
                "seat": e.seat,
                "end_at": end_at(m, r, e),
                "deadline": deadline(m, r, e),
                "close_at": close_at(m, r, e),
                "finished_at": e.finished_at,
                "delivered": bool(e.photo),
                "photo": media.url(e.photo) if (e.seat == seat or revealed) else None,
                "handicap": e.handicap,
                "score": e.score if done else None,
                "points": e.points if done else None,
                "votes_received": received_votes(r, e.seat) if done else None,
            }
        )

    voting = needs_votes(m, r) if revealed else judge_mode(m) in ("voto", "entrambi")
    votes: dict = {
        "needed": voting,
        "voted": [p.seat for p in m.players if revealed and has_voted(r, p.seat)],
        "closed": votes_closed(r),
        "targets": vote_targets(r, seat) if seat is not None and revealed else [],
        "mine": (r.votes or {}).get(str(seat)) if seat is not None else None,
    }

    # Soggetto e foto partono già col countdown: lo stato arriva una volta sola e
    # il client li tiene coperti finché il «3, 2, 1» non è finito.
    hide_ref = r.memory and t > r.starts_at + MEMORY_VISIBLE_S and not revealed
    ai_result = None
    if done and r.ai_result:
        ai_result = r.ai_result
    return {
        "number": r.number,
        "difficulty": r.difficulty,
        "multiplier": MULTIPLIER[r.difficulty],
        "theme": r.theme,
        "subject": r.subject,
        "image": media.url(r.image_file) if not hide_ref else None,
        "attribution": r.attribution,
        "memory": r.memory,
        "memory_hide_at": r.starts_at + MEMORY_VISIBLE_S if r.memory else None,
        "status": r.status,
        "starts_at": r.starts_at,
        "duration_s": r.duration_s,
        "timed": timed(m),
        "rush_end_at": r.rush_end_at,
        "entries": entries,
        "events": r.events or [],
        "votes": votes,
        "ai": {"status": r.ai_status, "error": r.ai_error, "result": ai_result},
    }


def view(m: Match, seat: int | None, online: set[int] | None = None) -> dict:
    online = online or set()
    t = totals(m)
    pu_on = bool(m.settings.get("powerups"))
    return {
        "code": m.code,
        "status": m.status,
        "you": seat,
        "max_players": MAX_PLAYERS,
        "server_now": now(),
        "created_at": m.created_at,
        "finished_at": m.finished_at,
        "settings": settings_of(m),
        "grace_s": GRACE_S,
        "players": [
            {
                "seat": p.seat,
                "name": p.name,
                "total": t.get(p.seat, 0.0),
                "online": p.seat in online,
                "powerups": p.powerups if pu_on else {},
            }
            for p in m.players
        ],
        "rounds": [_round_view(m, r, seat) for r in m.rounds],
        "suggested_difficulty": suggested_difficulty(m) if m.status in ("lobby", "ready") else None,
        "winners": winners(m),
        "rematch_code": m.rematch_code,
    }
