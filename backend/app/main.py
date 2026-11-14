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

from . import auth, config, db, game, judge, media, references
from .game import LOCK, GameError
from .models import Match, Round, User
from .realtime import rooms
from .subjects import DEFAULT_MINUTES, MULTIPLIER, THEMES

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("das")


def state_for(code: str, role: str | None, online: set[str]) -> dict:
    with db.session_scope() as s:
        m = game.get_match(s, code)
        return game.view(m, role, online)


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
    yield


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


def _state(s, m: Match, role: str | None) -> dict:
    s.flush()
    return game.view(m, role, rooms.online(m.code))


# ── configurazione e salute ───────────────────────────────────────────────────


@app.get("/api/health")
def health():
    with db.session_scope() as s:
        s.execute(select(1))
    return {"ok": True}


@app.get("/api/config")
def get_config():
    return {
        "ai_available": judge.available(),
        "themes": THEMES,
        "default_minutes": DEFAULT_MINUTES,
        "multipliers": MULTIPLIER,
        "defaults": game.default_settings(),
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


class VoteIn(BaseModel):
    value: float


@app.post("/api/matches")
def create(body: CreateIn, uid: int = Depends(me)):
    with LOCK, db.session_scope() as s:
        m = game.create_match(s, _user(s, uid), body.settings)
        return {"code": m.code, "state": _state(s, m, "host")}


@app.get("/api/matches/{code}")
def get_state(code: str, uid: int | None = Depends(viewer)):
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        role = game.role_of(m, uid)
        game.check_can_view(m, role)
        healed = game.heal(m)
        out = _state(s, m, role)
    if healed:
        rooms.notify(m.code)
    return out


@app.post("/api/matches/{code}/join")
def join(code: str, uid: int = Depends(me)):
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        game.join(s, m, _user(s, uid))
        out = {"state": _state(s, m, "guest")}
    rooms.notify(m.code)
    return out


def _fetch_reference(subject: tuple):
    return references.fetch(subject[1])


@app.post("/api/matches/{code}/rounds")
def start_round(code: str, body: RoundIn, uid: int = Depends(me)):
    # La foto si cerca fuori dal lock (sono secondi di rete), poi si ricontrolla tutto.
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        role = game.require_role(m, uid)
        game.check_can_start(m, role)
        difficulty, subject = game.choose_subject(m, body.difficulty)
    image, attribution = _fetch_reference(subject)
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        game.check_can_start(m, role)
        game.create_round(s, m, difficulty, subject, image, attribution)
        out = _state(s, m, role)
    rooms.notify(code.upper())
    return out


@app.post("/api/matches/{code}/powerups")
def use_powerup(code: str, body: PowerupIn, uid: int = Depends(me)):
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        role = game.require_role(m, uid)
        r = game.check_powerup(m, role, body.kind)
        if body.kind != "reroll":
            game.apply_timer_powerup(m, r, role, body.kind)
            out = _state(s, m, role)
            rooms.notify(m.code)
            return out
        number = r.number
        difficulty, subject = game.choose_subject(m, r.difficulty)
    image, attribution = _fetch_reference(subject)
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        r = game.check_powerup(m, role, "reroll")
        if r.number != number:
            raise GameError("Il round è cambiato nel frattempo", 409)
        game.apply_reroll(m, r, role, subject, image, attribution)
        out = _state(s, m, role)
    rooms.notify(code.upper())
    return out


def _run_judge(code: str, number: int):
    """Il giudice AI gira in un thread suo: chiunque abbia caricato per secondo non
    resta appeso, e il risultato arriva a entrambi via WebSocket."""
    with db.session_scope() as s:
        m = game.get_match(s, code)
        r = game.get_round(m, number)
        args = dict(
            subject=r.subject,
            difficulty=r.difficulty,
            reference=r.image_file,
            host_photo=r.host_photo,
            guest_photo=r.guest_photo,
            host_name=m.host_name,
            guest_name=m.guest_name or "",
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
        role = game.require_role(m, uid)
        game.check_upload(m, game.get_round(m, number))
    data = photo.file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise GameError(f"La foto supera i {config.MAX_UPLOAD_MB} MB")
    try:
        name = media.save_image(data, f"r{number}-{role}")
    except media.BadImage as exc:
        raise GameError(str(exc))
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        r = game.get_round(m, number)
        game.check_upload(m, r)
        old = game.set_photo(r, role, name)
        launch = game.after_upload(m, r)
        out = _state(s, m, role)
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
        role = game.require_role(m, uid)
        game.vote(m, game.get_round(m, number), role, body.value)
        out = _state(s, m, role)
    rooms.notify(code.upper())
    return out


@app.post("/api/matches/{code}/finish")
def finish(code: str, uid: int = Depends(me)):
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        role = game.require_role(m, uid)
        game.finish(m, role)
        out = _state(s, m, role)
    rooms.notify(code.upper())
    return out


@app.post("/api/matches/{code}/rematch")
def rematch(code: str, uid: int = Depends(me)):
    """La rivincita: stesse regole, partita nuova. Chi la chiede la crea (e ne è
    l'host); l'altro la trova nello stato della vecchia e ci entra con un tocco."""
    with LOCK, db.session_scope() as s:
        m = game.get_match(s, code)
        role = game.require_role(m, uid)
        if m.status != "finished":
            raise GameError("La partita non è ancora finita")
        if m.rematch_code:
            raise GameError("La rivincita c'è già", 409)
        new = game.create_match(s, _user(s, uid), m.settings)
        m.rematch_code = new.code
        out = {"code": new.code, "state": _state(s, new, "host")}
    rooms.notify(code.upper())
    return out


# ── galleria ──────────────────────────────────────────────────────────────────


@app.get("/api/gallery")
def gallery(uid: int = Depends(me)):
    """Solo le partite finite che hai giocato tu, da creatore o da sfidante."""
    with db.session_scope() as s:
        matches = s.scalars(
            select(Match)
            .where(Match.status == "finished")
            .where(or_(Match.host_user_id == uid, Match.guest_user_id == uid))
            .order_by(Match.finished_at.desc())
            .limit(300)
        ).all()
        items, h2h = [], {}
        for m in matches:
            if not m.rounds:
                continue
            t = game.totals(m)
            w = game.winner(m)
            items.append(
                {
                    "code": m.code,
                    "finished_at": m.finished_at,
                    "host": {"name": m.host_name, "total": t["host"]},
                    "guest": {"name": m.guest_name, "total": t["guest"]},
                    "winner": w,
                    "rounds": [
                        {
                            "subject": r.subject,
                            "difficulty": r.difficulty,
                            "image": media.url(r.image_file),
                            "host_photo": media.url(r.host_photo),
                            "guest_photo": media.url(r.guest_photo),
                        }
                        for r in m.rounds
                    ],
                }
            )
            # Testa a testa per coppia di nomi, a prescindere da chi ha creato la partita.
            names = sorted([m.host_name, m.guest_name or "?"], key=str.casefold)
            k = " vs ".join(names)
            rec = h2h.setdefault(k, {"players": names, "wins": {n: 0 for n in names}, "draws": 0, "matches": 0})
            rec["matches"] += 1
            if w == "pari":
                rec["draws"] += 1
            elif w:
                rec["wins"][game.name_of(m, w)] = rec["wins"].get(game.name_of(m, w), 0) + 1
        return {"matches": items, "head_to_head": list(h2h.values())}


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

    def _role():
        with db.session_scope() as s:
            u = auth.user_from_token(s, auth.token_of(websocket))
            m = game.get_match(s, code)
            role = game.role_of(m, u.id if u else None)
            game.check_can_view(m, role)
            return role

    try:
        role = await run_in_threadpool(_role)
    except GameError as exc:
        await websocket.close(code=4403 if exc.status == 403 else 4404)
        return
    await websocket.accept()
    await rooms.join(code, websocket, role)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"type": "pong", "server_now": game.now()})
    except WebSocketDisconnect:
        pass
    finally:
        await rooms.leave(code, websocket)
