from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# I tempi sono epoch in secondi (float): il client fa lo stesso conto col suo
# scarto dall'orologio del server, e i confronti restano banali.


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[float] = mapped_column(Float)


class LoginCode(Base):
    """Il codice a 6 cifre mandato per mail. Si salva solo l'hash."""

    __tablename__ = "login_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float)
    expires_at: Mapped[float] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Session(Base):
    """Una sessione per dispositivo, senza scadenza: è un gioco, si resta dentro.
    Nel cookie c'è il token, qui solo il suo hash."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[float] = mapped_column(Float)
    last_seen_at: Mapped[float] = mapped_column(Float)


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    created_at: Mapped[float] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    # lobby (manca l'avversario) → ready (fra un round e l'altro) → playing → finished
    status: Mapped[str] = mapped_column(String(16), default="lobby")
    settings: Mapped[dict] = mapped_column(JSON)

    # Chi ha creato la partita (è anche il giocatore al posto 0).
    host_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    host_name: Mapped[str] = mapped_column(String(40))
    rematch_code: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Della versione a due giocatori: i dati sono passati in `players`/`entries`
    # (db._migrate_players), le colonne restano solo perché SQLite le ha già.
    guest_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    guest_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    host_token: Mapped[str] = mapped_column(String(64), default="")
    guest_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    powerups: Mapped[dict] = mapped_column(JSON, default=dict)

    players: Mapped[list["Player"]] = relationship(
        back_populates="match", order_by="Player.seat", cascade="all, delete-orphan"
    )
    rounds: Mapped[list["Round"]] = relationship(
        back_populates="match", order_by="Round.number", cascade="all, delete-orphan"
    )


class Player(Base):
    """Un giocatore di una partita, al suo posto (0 = chi l'ha creata, fino a 7)."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    seat: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(40))
    joined_at: Mapped[float] = mapped_column(Float)
    # {"extra": true, "sabotage": true, "reroll": true}: true = ancora da usare
    powerups: Mapped[dict] = mapped_column(JSON, default=dict)

    match: Mapped[Match] = relationship(back_populates="players")


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[str] = mapped_column(String(12))
    theme: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(80))
    subject_key: Mapped[str] = mapped_column(String(80))
    image_file: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attribution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    memory: Mapped[bool] = mapped_column(Boolean, default=False)

    starts_at: Mapped[float] = mapped_column(Float)
    duration_s: Mapped[int] = mapped_column(Integer)
    # «Gli ultimi rincorrono»: quando abbastanza giocatori hanno consegnato, chi
    # manca ha tempo fino a qui (scadenza sempre rigida).
    rush_end_at: Mapped[float | None] = mapped_column(Float, nullable=True)

    # sculpting → judging → done
    status: Mapped[str] = mapped_column(String(16), default="sculpting")
    # power-up usati in questo round: [{"by": 0, "kind": "sabotage", "target": 1, "at": ...}]
    events: Mapped[list] = mapped_column(JSON, default=list)
    # {"<posto di chi vota>": {"<posto votato>": 7.5, ...}, ...}
    votes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # none | pending | done | failed
    ai_status: Mapped[str] = mapped_column(String(10), default="none")
    ai_started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    # {"entries": {"<posto>": {"score", "comment"}}, "verdict": "..."}
    ai_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Della versione a due giocatori (vedi Match): non si usano più.
    host_delta_s: Mapped[int] = mapped_column(Integer, default=0)
    guest_delta_s: Mapped[int] = mapped_column(Integer, default=0)
    host_photo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    guest_photo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    host_finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    guest_finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    host_handicap: Mapped[str | None] = mapped_column(String(120), nullable=True)
    guest_handicap: Mapped[str | None] = mapped_column(String(120), nullable=True)
    host_vote: Mapped[float | None] = mapped_column(Float, nullable=True)
    guest_vote: Mapped[float | None] = mapped_column(Float, nullable=True)
    host_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    guest_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    host_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    guest_points: Mapped[float | None] = mapped_column(Float, nullable=True)

    match: Mapped[Match] = relationship(back_populates="rounds")
    entries: Mapped[list["Entry"]] = relationship(
        back_populates="round", order_by="Entry.seat", cascade="all, delete-orphan"
    )


class Entry(Base):
    """La partecipazione di un giocatore a un round: tempo, handicap, foto, punti."""

    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), index=True)
    seat: Mapped[int] = mapped_column(Integer)
    delta_s: Mapped[int] = mapped_column(Integer, default=0)  # power-up: + e −
    handicap: Mapped[str | None] = mapped_column(String(120), nullable=True)
    photo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    points: Mapped[float | None] = mapped_column(Float, nullable=True)

    round: Mapped[Round] = relationship(back_populates="entries")
