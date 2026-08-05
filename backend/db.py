"""SQLAlchemy models, engine setup, and request-scoped database sessions."""

from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, Uuid, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from .config import settings


class Base(DeclarativeBase):
    """Declarative model base."""


RUNTIME_SCHEMA = (
    settings.assistant_database_schema
    if settings.database_url.startswith(("postgresql", "postgres"))
    else None
)
TABLE_ARGS = {"schema": RUNTIME_SCHEMA} if RUNTIME_SCHEMA else {}


class TTSUsage(Base):
    """Persist local ElevenLabs character usage by UTC calendar month."""

    __tablename__ = "tts_usage"
    __table_args__ = TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[str] = mapped_column(String(7), unique=True, index=True)
    characters_used: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Conversation(Base):
    """A user-scoped persistent chat and its bounded context state."""

    __tablename__ = "conversations"
    __table_args__ = TABLE_ARGS

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(120), index=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )


class ConversationMessage(Base):
    """One persisted user or assistant turn with privacy-safe metadata."""

    __tablename__ = "messages"
    __table_args__ = TABLE_ARGS

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            f"{RUNTIME_SCHEMA + '.' if RUNTIME_SCHEMA else ''}conversations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_content: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    query_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


engine_options: dict[str, object] = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def init_db(*, drop_existing: bool = False) -> None:
    """Create writable runtime tables; DoraDB remains a separate read-only engine."""

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
