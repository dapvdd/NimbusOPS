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


# ------------------------------------------------------------------ Phase 2


class DeploymentTemplate(Base):
    """Approved application template. Seeded on startup; operator-safe by construction."""

    __tablename__ = "deployment_templates"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image: Mapped[str] = mapped_column(String(255), nullable=False)
    container_port: Mapped[int] = mapped_column(Integer, nullable=False)
    host_port: Mapped[int] = mapped_column(Integer, nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ManagedDeployment(Base):
    """A deployed application instance on one host (stable identity across redeploys)."""

    __tablename__ = "managed_deployments"
    __table_args__ = (
        Index("ix_managed_deploy_host_template", "host_id", "template_key", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    host_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_key: Mapped[str] = mapped_column(
        String(64), ForeignKey("deployment_templates.key"), nullable=False
    )
    container_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class DeploymentOperation(Base):
    """One durable operation against a managed deployment (deploy/start/stop)."""

    __tablename__ = "deployment_operations"
    __table_args__ = (
        Index("ix_ops_deployment_created", "deployment_id", "created_at"),
        Index("ix_ops_host_status", "host_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("managed_deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    host_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    op_type: Mapped[str] = mapped_column(String(16), nullable=False)  # DEPLOY | START | STOP
    # QUEUED | RUNNING | SUCCEEDED | FAILED | UNKNOWN
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    # Verifiable evidence the agent reported (container id, http probe, etc.).
    result_json: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)


class OperationEvent(Base):
    """Append-only event log for operations (no secrets; sanitized messages)."""

    __tablename__ = "operation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    operation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("deployment_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event: Mapped[str] = mapped_column(String(32), nullable=False)  # CREATED | CLAIMED | RESULT | TIMED_OUT
    detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
