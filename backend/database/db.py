"""SQLAlchemy models, engine setup, and request-scoped database sessions."""

from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from ..config import settings


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


class ZaraWorkflow(Base):
    """A saved Zara workflow definition in the writable runtime store."""

    __tablename__ = "zara_workflows"
    __table_args__ = TABLE_ARGS

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Report(Base):
    """A persisted, editable report.

    Reports are first-class objects rather than chat answers: they outlive the
    conversation they were built from, combine evidence from several messages
    and several conversations, and stay reproducible because each source keeps
    an immutable snapshot (see ``ReportSource.evidence``).

    Lives in the writable runtime store beside conversations. DoraDB stays
    read-only; nothing here is ever written there.
    """

    __tablename__ = "reports"
    __table_args__ = TABLE_ARGS

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    # Every query filters on user_id. A report is never reachable by guessing
    # its id alone -- see report_repository.ReportRepository.get.
    user_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    template: Mapped[str] = mapped_column(String(60), nullable=False, default="blank")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    audience: Mapped[str] = mapped_column(String(40), nullable=False, default="delivery_manager")
    tone: Mapped[str] = mapped_column(String(40), nullable=False, default="professional")
    detail_level: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    include_recommendations: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # project / squad / sprint / release / date_from / date_to
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # Non-blocking findings from the last validate/compose run.
    validation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # Oldest evidence retrieval time across sources -- drives staleness.
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sections: Mapped[list["ReportSection"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportSection.position",
    )
    sources: Mapped[list["ReportSource"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportSource.created_at",
    )


class ReportSection(Base):
    """One ordered, individually editable block of a report."""

    __tablename__ = "report_sections"
    __table_args__ = TABLE_ARGS

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    report_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            f"{RUNTIME_SCHEMA + '.' if RUNTIME_SCHEMA else ''}reports.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Chart / table / KPI payloads stay structured rather than flattened into
    # text, so exports can lay them out properly and CSV stays possible.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    content_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="rewrite")
    # observed_fact | interpretation | recommendation | user_authored
    content_classification: Mapped[str] = mapped_column(
        String(30), nullable=False, default="observed_fact"
    )
    manually_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Set when a user edits a section that carried validated numbers: the
    # section can no longer claim to be evidence-verified without revalidation.
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_ids: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    report: Mapped[Report] = relationship(back_populates="sections")


class ReportSource(Base):
    """An immutable snapshot of one piece of evidence used by a report.

    The snapshot is deliberately a copy, not a live reference: archiving the
    conversation, or changing how an answer is presented later, must not alter
    or invalidate a report that was already built from it.
    """

    __tablename__ = "report_sources"
    __table_args__ = TABLE_ARGS

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    report_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            f"{RUNTIME_SCHEMA + '.' if RUNTIME_SCHEMA else ''}reports.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    message_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    selection: Mapped[str] = mapped_column(String(20), nullable=False, default="full")
    # Approved provenance fields only -- never prompts, credentials or SQL.
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    report: Mapped[Report] = relationship(back_populates="sources")


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
