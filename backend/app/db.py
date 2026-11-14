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
    """Crea engine e tabelle. Lo schema è piccolo e per ora `create_all` basta:
    il giorno che una colonna cambia, si passa ad Alembic."""
    global engine
    url = url or config.DATABASE_URL
    if url.startswith("sqlite:///") and ":memory:" not in url:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine = _make_engine(url)
    SessionLocal.configure(bind=engine)
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)
    return engine


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
