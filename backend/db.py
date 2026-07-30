"""SQLAlchemy models, engine setup, and request-scoped database sessions."""

from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Declarative model base."""


class TTSUsage(Base):
    """Persist local ElevenLabs character usage by UTC calendar month."""

    __tablename__ = "tts_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[str] = mapped_column(String(7), unique=True, index=True)
    characters_used: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


engine_options: dict[str, object] = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def init_db(*, drop_existing: bool = False) -> None:
    """Create the local TTS usage schema."""

    if drop_existing:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that always closes the session."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
