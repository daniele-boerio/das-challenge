from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# I tempi sono epoch in secondi (float): il client fa lo stesso conto col suo
# scarto dall'orologio del server, e i confronti restano banali.


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    created_at: Mapped[float] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    # lobby (manca l'avversario) → ready (fra un round e l'altro) → playing → finished
    status: Mapped[str] = mapped_column(String(16), default="lobby")
    settings: Mapped[dict] = mapped_column(JSON)

    host_name: Mapped[str] = mapped_column(String(40))
    host_token: Mapped[str] = mapped_column(String(64))
    guest_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    guest_token: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # {"host": {"extra": true, "sabotage": true, "reroll": true}, "guest": {...}}
    powerups: Mapped[dict] = mapped_column(JSON, default=dict)
    rematch_code: Mapped[str | None] = mapped_column(String(8), nullable=True)

    rounds: Mapped[list["Round"]] = relationship(
        back_populates="match", order_by="Round.number", cascade="all, delete-orphan"
    )


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
    host_delta_s: Mapped[int] = mapped_column(Integer, default=0)
    guest_delta_s: Mapped[int] = mapped_column(Integer, default=0)

    # sculpting → judging → done
    status: Mapped[str] = mapped_column(String(16), default="sculpting")
    host_photo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    guest_photo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    host_finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    guest_finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    host_handicap: Mapped[str | None] = mapped_column(String(120), nullable=True)
    guest_handicap: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # power-up usati in questo round: [{"by": "host", "kind": "sabotage", "at": ...}]
    events: Mapped[list] = mapped_column(JSON, default=list)

    # Il voto che host dà alla creazione di guest, e viceversa.
    host_vote: Mapped[float | None] = mapped_column(Float, nullable=True)
    guest_vote: Mapped[float | None] = mapped_column(Float, nullable=True)

    # none | pending | done | failed
    ai_status: Mapped[str] = mapped_column(String(10), default="none")
    ai_started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    host_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    guest_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    host_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    guest_points: Mapped[float | None] = mapped_column(Float, nullable=True)

    match: Mapped[Match] = relationship(back_populates="rounds")
