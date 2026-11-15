"""DAS Challenge — l'API.

Tutte le rotte stanno sotto /api: nginx le inoltra così come sono.
Le rotte HTTP sono `def` (girano nel threadpool), solo il WebSocket è async.
"""

import logging
import threading
from contextlib import asynccontextmanager

import asyncio
from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, update

from . import auth, config, db, game, judge, imagegen, media, references
from .game import LOCK, GameError
from .models import Match, Player, Round, User
from .realtime import rooms
from .subjects import DEFAULT_MINUTES, MULTIPLIER, THEMES

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("das")


def state_for(code: str, seat: int | None, online: set[int]) -> dict:
    with db.session_scope() as s:
        m = game.get_match(s, code)
        return game.view(m, seat, online)


TICK_S = 2.0
TICKER = True  # nei test è spento: si chiama `tick_all()` a mano


def tick_all():
    """Un giro su tutte le partite in corso: chiude i round scaduti (timer rigido,
    rincorsa) anche se nessuno tocca niente, e sblocca i giudici appesi."""
    changed, launch = [], []
    with LOCK, db.session_scope() as s:
        for m in s.scalars(select(Match).where(Match.status == "playing")):
            ch, la = game.tick(m)
            if ch:
                changed.append(m.code)
            if la:
                launch.append((m.code, game.current_round(m).number))
    for code, number in launch:
        start_judge(code, number)
    # Le reference preparate per partite ormai finite non servono più.
    with _ready_lock:
        codes = {c for c, _ in _ready}
    if codes:
        with db.session_scope() as s:
            done = s.scalars(select(Match.code).where(Match.code.in_(codes), Match.status == "finished")).all()
        for code in done:
            forget_ready(code)
    for code in changed:
        rooms.notify(code)


def _ticker(stop: threading.Event):
    while not stop.wait(TICK_S):
        try:
            tick_all()
        except Exception:
            log.exception("giro del ticker fallito")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if db.engine is None:
        db.init()
    # Un giudice «in corso» all'avvio è di un processo che non c'è più.
    with db.session_scope() as s:
        s.execute(
            update(Round)
            .where(Round.ai_status == "pending")
            .values(ai_status="failed", ai_error="Il server si è riavviato: votate voi")
        )
        for m in s.scalars(select(Match).where(Match.status == "playing")):
            r = game.current_round(m)
            if r and r.ai_status == "failed":
                game.maybe_finalize(m, r)
    rooms.loop = asyncio.get_running_loop()
    rooms.state_for = state_for
    stop = threading.Event()
    if TICKER:
        threading.Thread(target=_ticker, args=(stop,), daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="DAS Challenge", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.exception_handler(GameError)
def _game_error(_: Request, exc: GameError):
    return JSONResponse({"detail": str(exc)}, status_code=exc.status)


# ── dipendenze ────────────────────────────────────────────────────────────────


def viewer(request: Request) -> int | None:
    """L'id dell'utente collegato, se c'è (e ha scelto il nome)."""
    with db.session_scope() as s:
        u = auth.user_from_token(s, auth.token_of(request))
        return u.id if u and u.name else None


def me(request: Request) -> int:
    """Come `viewer`, ma obbligatorio."""
    with db.session_scope() as s:
        return auth.require_named(auth.user_from_token(s, auth.token_of(request))).id


def _user(s, uid: int) -> User:
    return s.get(User, uid)


def _state(s, m: Match, seat: int | None) -> dict:
    s.flush()
    return game.view(m, seat, rooms.online(m.code))


# ── configurazione e salute ───────────────────────────────────────────────────


@app.get("/api/health")
def health():
    with db.session_scope() as s:
        s.execute(select(1))
    return {"ok": True}


@app.get("/api/config")
def get_config(uid: int | None = Depends(viewer)):
    with db.session_scope() as s:
        ai = game.ai_user(s.get(User, uid)) if uid else False
    return {
        # L'AI la accende solo chi è in `AI_EMAILS`: per gli altri il giudice AI non si sceglie.
        "ai_available": ai,
        "themes": THEMES,
        "default_minutes": DEFAULT_MINUTES,
        "multipliers": MULTIPLIER,
        "defaults": game.default_settings(),
        "max_players": game.MAX_PLAYERS,
    }


# ── accesso ───────────────────────────────────────────────────────────────────


class EmailIn(BaseModel):
    email: str = Field(max_length=254)


class VerifyIn(BaseModel):
    email: str = Field(max_length=254)
    code: str = Field(max_length=12)


class NameIn(BaseModel):
    name: str = Field(max_length=60)


def _me_out(u: User | None) -> dict:
    if not u:
        return {"user": None}
    return {"user": {"id": u.id, "email": u.email, "name": u.name}}


@app.get("/api/auth/me")
def auth_me(request: Request):
    with db.session_scope() as s:
        return _me_out(auth.user_from_token(s, auth.token_of(request)))


@app.post("/api/auth/request")
def auth_request(body: EmailIn):
    with db.session_scope() as s:
        code = auth.request_code(s, body.email)
        email = auth.clean_email(body.email)
    try:
        auth.send_code_mail(email, code)
    except Exception as exc:
        log.exception("invio del codice fallito")
        raise GameError("Non riesco a mandare la mail: riprova fra poco", 502) from exc
    return {"ok": True}


@app.post("/api/auth/verify")
def auth_verify(body: VerifyIn, response: Response):
    with db.session_scope() as s:
        u = auth.verify_code(s, body.email, body.code)
        auth.start_session(s, u, response)
        return _me_out(u)


@app.post("/api/auth/name")
def auth_name(body: NameIn, request: Request):
    with db.session_scope() as s:
        u = auth.user_from_token(s, auth.token_of(request))
        if not u:
            raise HTTPException(401, "Devi accedere")
        auth.set_name(u, body.name)
        return _me_out(u)


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    with db.session_scope() as s:
        auth.end_session(s, auth.token_of(request), response)
    return {"ok": True}


# ── partite ───────────────────────────────────────────────────────────────────


class CreateIn(BaseModel):
    settings: dict | None = None


class RoundIn(BaseModel):
    difficulty: str = "casuale"


class PowerupIn(BaseModel):
    kind: str
    target: int | None = None


class VoteIn(BaseModel):
    # {posto: voto} per tutte le creazioni degli altri
    votes: dict[str, float]


@app.post("/api/matches")
def create(body: CreateIn, uid: int = Depends(me)):
    with LOCK, db.session_scope() as s:
        m = game.create_match(s, _user(s, uid), body.settings)
        out = {"code": m.code, "state": _state(s, m, 0)}
    prefetch(out["code"])
    return out


@app.get("/api/matches/{code}")
def get_state(code: str, uid: int | None = Depends(viewer)):
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        seat = game.seat_of(m, uid)
        game.check_can_view(m, seat)
        healed = game.heal(m)
        out = _state(s, m, seat)
    if healed:
        rooms.notify(m.code)
    return out


@app.post("/api/matches/{code}/join")
def join(code: str, uid: int = Depends(me)):
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        before = game.ai_allowed(m)
        seat = game.join(s, m, _user(s, uid))
        changed = game.ai_allowed(m) != before
        out = {"state": _state(s, m, seat)}
    rooms.notify(m.code)
    if changed:  # è entrato chi ha l'AI: le foto già cercate senza si rifanno
        forget_ready(m.code)
        prefetch(m.code)
    return out


def _fetch_reference(subject: tuple, colors: bool = False, difficulty: str = "media", ai: bool = True):
    """Con l'AI, prima la foto generata (c'è sempre, ed è veloce) e se fallisce la
    ricerca con la scelta del modello. Senza, solo la ricerca col filtro sulle parole."""
    if ai:
        image, attribution = imagegen.generate(subject[0], subject[1], difficulty, colors)
        if image:
            return image, attribution
    return references.fetch(subject[1], subject=subject[0], colors=colors, ai=ai)


# ── reference pronte in anticipo ──────────────────────────────────────────────
# Cercare la scultura (ricerche, miniature, modello) richiede decine di secondi:
# troppi da aspettare dopo «Via al round!». Così, appena la partita esiste e poi a
# ogni round, un thread prepara una reference per ciascuna difficoltà; il round
# prende quella pronta e il thread rifà la scorta. Sta in memoria: dopo un
# riavvio si ricomincia a cercare, e nel frattempo si cerca al momento come prima.

PREFETCH = True  # nei test è spento
_ready: dict[tuple[str, str], tuple[tuple, str | None, dict | None, bool]] = {}
_ready_lock = threading.Lock()
_prefetching: set[str] = set()


def _take_ready(code: str, difficulty: str, used: set[str], ai: bool):
    """(soggetto, foto, attribuzione) preparati, se fatti con la stessa AI di adesso:
    una foto cercata prima che entrasse chi ha l'AI (o viceversa) si butta."""
    with _ready_lock:
        item = _ready.pop((code, difficulty), None)
    if not item:
        return None
    if item[3] != ai or subjects_key(difficulty, item[0]) in used:
        if item[1]:
            media.path_of(item[1]).unlink(missing_ok=True)
        return None
    return item[:3]


def subjects_key(difficulty: str, subject: tuple) -> str:
    from .subjects import key

    return key(difficulty, subject[0])


def _prefetch_worker(code: str):
    from .subjects import DIFFICULTIES

    try:
        for d in DIFFICULTIES:
            with _ready_lock:
                if (code, d) in _ready:
                    continue
                taken = {subjects_key(dd, it[0]) for (c, dd), it in _ready.items() if c == code}
            with LOCK, db.session_scope() as s:
                m = game.get_match(s, code)
                if m.status == "finished" or len(m.rounds) >= m.settings["rounds"]:
                    return  # non ci sono altri round da preparare
                _, subject = game.choose_subject(m, d, taken)
                colors = game.settings_of(m)["colors"]
                ai = game.ai_allowed(m)
            image, attribution = _fetch_reference(subject, colors, d, ai)
            with _ready_lock:
                _ready[(code, d)] = (subject, image, attribution, ai)
    except Exception:
        log.exception("preparazione delle reference fallita")
    finally:
        with _ready_lock:
            _prefetching.discard(code)


def prefetch(code: str):
    if not PREFETCH:
        return
    code = code.upper()
    with _ready_lock:
        if code in _prefetching:
            return
        _prefetching.add(code)
    threading.Thread(target=_prefetch_worker, args=(code,), daemon=True).start()


def forget_ready(code: str):
    """Partita finita: le reference preparate e mai usate si buttano, file compresi."""
    with _ready_lock:
        items = [_ready.pop(k) for k in [k for k in _ready if k[0] == code.upper()]]
    for _, image, _, _ in items:
        if image:
            media.path_of(image).unlink(missing_ok=True)


@app.post("/api/matches/{code}/rounds")
def start_round(code: str, body: RoundIn, uid: int = Depends(me)):
    # La foto si cerca fuori dal lock (sono secondi di rete), poi si ricontrolla tutto.
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        seat = game.require_seat(m, uid)
        game.check_can_start(m, seat)
        difficulty, subject = game.choose_subject(m, body.difficulty)
        used = {r.subject_key for r in m.rounds}
        colors = game.settings_of(m)["colors"]
        ai = game.ai_allowed(m)
    ready = _take_ready(code.upper(), difficulty, used, ai)
    if ready:
        subject, image, attribution = ready
    else:
        image, attribution = _fetch_reference(subject, colors, difficulty, ai)
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        game.check_can_start(m, seat)
        game.create_round(s, m, difficulty, subject, image, attribution)
        out = _state(s, m, seat)
    rooms.notify(code.upper())
    prefetch(code)  # la scorta per il round dopo, mentre si scolpisce
    return out


@app.post("/api/matches/{code}/powerups")
def use_powerup(code: str, body: PowerupIn, uid: int = Depends(me)):
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        seat = game.require_seat(m, uid)
        r, target = game.check_powerup(m, seat, body.kind, body.target)
        if body.kind != "reroll":
            game.apply_timer_powerup(m, r, seat, body.kind, target)
            out = _state(s, m, seat)
            rooms.notify(m.code)
            return out
        number = r.number
        difficulty, subject = game.choose_subject(m, r.difficulty)
        used = {x.subject_key for x in m.rounds}
        colors = game.settings_of(m)["colors"]
        ai = game.ai_allowed(m)
    ready = _take_ready(code.upper(), difficulty, used, ai)
    if ready:
        subject, image, attribution = ready
    else:
        image, attribution = _fetch_reference(subject, colors, difficulty, ai)
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        r, _ = game.check_powerup(m, seat, "reroll")
        if r.number != number:
            raise GameError("Il round è cambiato nel frattempo", 409)
        game.apply_reroll(m, r, seat, subject, image, attribution)
        out = _state(s, m, seat)
    rooms.notify(code.upper())
    prefetch(code)
    return out


def _run_judge(code: str, number: int):
    """Il giudice AI gira in un thread suo: chiunque abbia caricato per secondo non
    resta appeso, e il risultato arriva a tutti via WebSocket."""
    with db.session_scope() as s:
        m = game.get_match(s, code)
        r = game.get_round(m, number)
        args = dict(
            subject=r.subject,
            difficulty=r.difficulty,
            reference=r.image_file,
            entries=[
                {"seat": e.seat, "name": game.player(m, e.seat).name, "photo": e.photo}
                for e in game.delivered(r)
            ],
            colors=game.settings_of(m)["colors"],
        )
    try:
        result, error = judge.judge(**args), None
    except Exception as exc:
        log.exception("giudice AI fallito")
        result, error = None, str(exc)
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        r = game.get_round(m, number)
        if r.ai_status != "pending":
            return
        if result:
            r.ai_status, r.ai_result = "done", result
            game.maybe_finalize(m, r)
        else:
            game.ai_failed(m, r, f"Il giudice AI non ce l'ha fatta ({error[:160]}): votate voi")
    rooms.notify(code)


def start_judge(code: str, number: int):
    threading.Thread(target=_run_judge, args=(code, number), daemon=True).start()


@app.post("/api/matches/{code}/rounds/{number}/photo")
def upload_photo(
    code: str,
    number: int,
    photo: UploadFile = File(...),
    uid: int = Depends(me),
):
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        seat = game.require_seat(m, uid)
        game.check_upload(m, game.get_round(m, number), seat)
    data = photo.file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise GameError(f"La foto supera i {config.MAX_UPLOAD_MB} MB")
    try:
        name = media.save_image(data, f"r{number}-p{seat}")
    except media.BadImage as exc:
        raise GameError(str(exc))
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        r = game.get_round(m, number)
        try:
            game.check_upload(m, r, seat)
        except GameError:
            media.path_of(name).unlink(missing_ok=True)
            raise
        old = game.set_photo(m, r, seat, name)
        launch = game.advance(m, r)
        out = _state(s, m, seat)
    if old:
        media.path_of(old).unlink(missing_ok=True)
    if launch:
        start_judge(code.upper(), number)
    rooms.notify(code.upper())
    return out


@app.post("/api/matches/{code}/rounds/{number}/vote")
def vote(code: str, number: int, body: VoteIn, uid: int = Depends(me)):
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        seat = game.require_seat(m, uid)
        game.vote(m, game.get_round(m, number), seat, body.votes)
        out = _state(s, m, seat)
    rooms.notify(code.upper())
    return out


@app.post("/api/matches/{code}/rounds/{number}/close-votes")
def close_votes(code: str, number: int, uid: int = Depends(me)):
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        seat = game.require_seat(m, uid)
        game.close_votes(m, game.get_round(m, number), seat)
        out = _state(s, m, seat)
    rooms.notify(code.upper())
    return out


@app.post("/api/matches/{code}/finish")
def finish(code: str, uid: int = Depends(me)):
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        seat = game.require_seat(m, uid)
        game.finish(m, seat)
        out = _state(s, m, seat)
    forget_ready(code)
    rooms.notify(code.upper())
    return out


@app.post("/api/matches/{code}/rematch")
def rematch(code: str, uid: int = Depends(me)):
    """La rivincita: stesse regole, partita nuova. Chi la chiede la crea (e ne è
    l'host); gli altri la trovano nello stato della vecchia e ci entrano con un tocco."""
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        game.require_seat(m, uid)
        if m.status != "finished":
            raise GameError("La partita non è ancora finita")
        if m.rematch_code:
            raise GameError("La rivincita c'è già", 409)
        new = game.create_match(s, _user(s, uid), m.settings)
        m.rematch_code = new.code
        out = {"code": new.code, "state": _state(s, new, 0)}
    rooms.notify(code.upper())
    forget_ready(code)
    prefetch(out["code"])
    return out


# ── galleria ──────────────────────────────────────────────────────────────────


@app.get("/api/gallery")
def gallery(uid: int = Depends(me)):
    """Solo le partite finite che hai giocato tu. Il testa a testa è per
    avversario: in quante partite giocate insieme hai fatto più punti tu o lui."""
    with db.session_scope() as s:
        matches = s.scalars(
            select(Match)
            .where(Match.status == "finished")
            .where(Match.players.any(Player.user_id == uid))
            .order_by(Match.finished_at.desc())
            .limit(300)
        ).all()
        items, h2h = [], {}
        for m in matches:
            if not m.rounds:
                continue
            t = game.totals(m)
            w = game.winners(m) or []
            mine = game.seat_of(m, uid)
            items.append(
                {
                    "code": m.code,
                    "finished_at": m.finished_at,
                    "players": [{"seat": p.seat, "name": p.name, "total": t.get(p.seat, 0.0)} for p in m.players],
                    "winners": w,
                    "you": mine,
                    "rounds": [
                        {
                            "subject": r.subject,
                            "difficulty": r.difficulty,
                            "image": media.url(r.image_file),
                            "photos": [media.url(e.photo) for e in r.entries if e.photo],
                        }
                        for r in m.rounds
                    ],
                }
            )
            for p in m.players:
                if p.seat == mine:
                    continue
                rec = h2h.setdefault(
                    p.user_id, {"name": p.name, "matches": 0, "wins": 0, "losses": 0, "draws": 0}
                )
                rec["matches"] += 1
                a, b = t.get(mine, 0), t.get(p.seat, 0)
                rec["wins" if a > b else "losses" if a < b else "draws"] += 1
        played = len(items)
        won = sum(1 for it in items if it["you"] in it["winners"] and len(it["winners"]) == 1)
        return {
            "matches": items,
            "head_to_head": sorted(h2h.values(), key=lambda x: -x["matches"]),
            "stats": {"played": played, "won": won},
        }


# ── immagini ──────────────────────────────────────────────────────────────────


@app.get("/api/media/{name}")
def get_media(name: str):
    try:
        p = media.path_of(name)
    except FileNotFoundError:
        raise HTTPException(404)
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"})


# ── tempo reale ───────────────────────────────────────────────────────────────


@app.websocket("/api/ws/{code}")
async def ws(websocket: WebSocket, code: str):
    code = code.upper()
    from starlette.concurrency import run_in_threadpool

    def _seat():
        with db.session_scope() as s:
            u = auth.user_from_token(s, auth.token_of(websocket))
            m = game.get_match(s, code)
            seat = game.seat_of(m, u.id if u else None)
            game.check_can_view(m, seat)
            return seat

    try:
        seat = await run_in_threadpool(_seat)
    except GameError as exc:
        await websocket.close(code=4403 if exc.status == 403 else 4404)
        return
    await websocket.accept()
    await rooms.join(code, websocket, seat)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong", "server_now": game.now()})
    except WebSocketDisconnect:
        pass
    finally:
        await rooms.leave(code, websocket)
