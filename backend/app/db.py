from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _pragmas(conn, _):
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    return eng


engine = None
SessionLocal = sessionmaker(expire_on_commit=False)


def init(url: str | None = None):
    """Crea engine e tabelle. Lo schema è piccolo: `create_all` per le tabelle e
    `_add_columns` per le colonne nuove di tabelle già esistenti. Il giorno che una
    colonna esistente cambia tipo, si passa ad Alembic."""
    global engine
    url = url or config.DATABASE_URL
    if url.startswith("sqlite:///") and ":memory:" not in url:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine = _make_engine(url)
    SessionLocal.configure(bind=engine)
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)
    _add_columns(engine)
    _migrate_players(engine)
    return engine


# Colonne aggiunte dopo il primo rilascio: (tabella, colonna, DDL).
_NEW_COLUMNS = [
    ("matches", "host_user_id", "INTEGER REFERENCES users(id)"),
    ("matches", "guest_user_id", "INTEGER REFERENCES users(id)"),
    ("rounds", "rush_end_at", "FLOAT"),
    ("rounds", "votes", "JSON"),
]


def _add_columns(eng):
    from sqlalchemy import inspect, text

    insp = inspect(eng)
    with eng.begin() as conn:
        for table, col, ddl in _NEW_COLUMNS:
            if table in insp.get_table_names() and col not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


def _migrate_players(eng):
    """Le partite della versione a due (colonne host_*/guest_*) passano a
    giocatori e consegne per posto: host = posto 0, guest = posto 1. Si fa una
    volta sola per partita (quelle che hanno già dei `players` si saltano), e
    solo per quelle con un account: le partite di prima degli account non le
    vedeva più nessuno."""
    from sqlalchemy import select

    from .models import Entry, Match, Player

    roles = ("host", "guest")
    with sessionmaker(bind=eng)() as s:
        todo = s.scalars(select(Match).where(Match.host_user_id.is_not(None)).where(~Match.players.any())).all()
        for m in todo:
            users = {"host": m.host_user_id, "guest": m.guest_user_id}
            names = {"host": m.host_name, "guest": m.guest_name}
            for seat, role in enumerate(roles):
                if users[role] is None:
                    continue
                s.add(
                    Player(
                        match=m,
                        user_id=users[role],
                        seat=seat,
                        name=names[role] or "?",
                        joined_at=m.created_at,
                        powerups=dict((m.powerups or {}).get(role) or {"extra": True, "sabotage": True, "reroll": True}),
                    )
                )
            for r in m.rounds:
                for seat, role in enumerate(roles):
                    if users[role] is None:
                        continue
                    s.add(
                        Entry(
                            round=r,
                            seat=seat,
                            delta_s=getattr(r, f"{role}_delta_s") or 0,
                            handicap=getattr(r, f"{role}_handicap"),
                            photo=getattr(r, f"{role}_photo"),
                            finished_at=getattr(r, f"{role}_finished_at"),
                            score=getattr(r, f"{role}_score"),
                            points=getattr(r, f"{role}_points"),
                        )
                    )
                # host_vote è il voto che host ha dato a guest
                votes = {}
                if r.host_vote is not None:
                    votes["0"] = {"1": r.host_vote}
                if r.guest_vote is not None:
                    votes["1"] = {"0": r.guest_vote}
                r.votes = votes
                if r.ai_result and "entries" not in r.ai_result:
                    old = r.ai_result
                    r.ai_result = {
                        "entries": {str(i): old[role] for i, role in enumerate(roles) if role in old},
                        "verdict": old.get("verdict", ""),
                    }
                if r.events:
                    r.events = [
                        {**ev, "by": roles.index(ev["by"]) if ev.get("by") in roles else ev.get("by"),
                         **({"target": 1 - roles.index(ev["by"])} if ev.get("kind") == "sabotage" and ev.get("by") in roles else {})}
                        for ev in r.events
                    ]
        s.commit()


@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
