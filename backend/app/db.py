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
    return engine


# Colonne aggiunte dopo il primo rilascio: (tabella, colonna, DDL).
_NEW_COLUMNS = [
    ("matches", "host_user_id", "INTEGER REFERENCES users(id)"),
    ("matches", "guest_user_id", "INTEGER REFERENCES users(id)"),
]


def _add_columns(eng):
    from sqlalchemy import inspect, text

    insp = inspect(eng)
    with eng.begin() as conn:
        for table, col, ddl in _NEW_COLUMNS:
            if table in insp.get_table_names() and col not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


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
