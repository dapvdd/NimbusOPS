"""ORM models: hosts, latest telemetry, and telemetry history."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Host(Base):
    __tablename__ = "hosts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    hostname: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    agent_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Agent-reported metadata (heartbeat-refreshed).
    agent_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform_release: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cpu_cores: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_memory_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    boot_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Connectivity
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_telemetry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        Index("ix_telemetry_host_recorded", "host_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    cpu_percent: Mapped[float] = mapped_column(Float, nullable=False)
    memory_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memory_total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disk_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disk_total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memory_used_percent: Mapped[float] = mapped_column(Float, nullable=False)
    disk_used_percent: Mapped[float] = mapped_column(Float, nullable=False)


class EnrollmentAudit(Base):
    """Append-only audit of enrollment attempts (no tokens stored)."""

    __tablename__ = "enrollment_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)  # ENROLLED | DENIED | DISABLED
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
