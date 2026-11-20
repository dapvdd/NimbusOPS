"""Sprint 5 zero-touch provisioning ORM models (design §4, §15.1-15.3).

Column contracts are normative in
docs/superpowers/specs/2026-11-17-sprint5-full-design.md §4. Conventions:
UUID text PKs, integer millisecond UTC timestamps, bounded text enums with
CHECK, booleans 0/1, hashes fixed 64 hex, JSON as canonical text. All
provisioning FKs use RESTRICT; provisioning records are never cascade-deleted
with hosts. `provisioning_validations.consumed_by_job_id` is a logical
reference (verified transactionally in D2) to avoid a circular insertion
dependency — it is NOT a database FK.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from . import Base, new_uuid

# Bounded enum value sets (§3/§4/§15).
JOB_STATES = ("PENDING", "VALIDATING", "RUNNING", "VERIFYING", "SUCCEEDED", "FAILED", "CANCELLED")
JOB_OPERATIONS = ("INSTALL", "REENROLL", "ROTATE", "RESTART", "DIAGNOSE", "UPGRADE")
ATTEMPT_STATUSES = ("INTENT", "ACCEPTED", "COMPLETED", "NOT_SUBMITTED", "UNKNOWN")
ADMISSION_STATES = ("OPEN", "ADMITTED", "CLOSED")
DISPOSITIONS = ("HELD", "RECONCILING", "RELEASED")
RECEIPT_KINDS = ("HEARTBEAT", "TELEMETRY")
MATCHED_SLOTS = ("CURRENT", "GRACE")
PROVIDERS = ("AZURE_VM", "GENERIC_LINUX", "LOCAL_WINDOWS")
MAPPING_STATUSES = ("UNMAPPED", "PENDING_MAPPING", "MAPPED", "IDENTITY_MAPPING_REQUIRED")


def _check(name: str, col: str, values: tuple[str, ...]) -> CheckConstraint:
    quoted = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{col} IN ({quoted})", name=name)


def _restrict(target: str, **kw) -> ForeignKey:
    """§4: provisioning FKs never cascade with hosts/parents.

    DEFERRABLE INITIALLY DEFERRED: RESTRICT semantics apply at COMMIT (a
    committed write can never leave a dangling reference), while within a
    transaction parent rows may be written in any order — the durable
    write-ahead journal requires inserting child intent rows before the
    parent's final state exists in the same transaction.
    """
    return ForeignKey(target, ondelete="RESTRICT", deferrable=True, initially="DEFERRED", **kw)


class ProvisioningMachine(Base):
    """§15.3: global machine/installation ownership root."""

    __tablename__ = "provisioning_machines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    machine_binding_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    installation_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    binding_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ProvisioningConnection(Base):
    """§4: provider connection configuration mirror (nonsecret metadata only)."""

    __tablename__ = "provisioning_connections"
    __table_args__ = (_check("ck_prov_conn_provider", "provider", PROVIDERS),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ProvisioningTarget(Base):
    """§4: discovered provider target; mapping to host/machine is explicit."""

    __tablename__ = "provisioning_targets"
    __table_args__ = (
        Index("ux_prov_targets_conn_canonical", "connection_id", "canonical_key", unique=True),
        _check("ck_prov_targets_mapping_status", "mapping_status", MAPPING_STATUSES),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    connection_id: Mapped[str] = mapped_column(_restrict("provisioning_connections.id"), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    observed_identity_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    host_id: Mapped[str | None] = mapped_column(_restrict("hosts.id"), unique=True, nullable=True)
    machine_id: Mapped[str | None] = mapped_column(_restrict("provisioning_machines.id"), nullable=True)
    mapping_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mapping_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNMAPPED")
    discovered_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProvisioningValidation(Base):
    """§4: reviewed plan fingerprint; consumable exactly once by one job.

    `consumed_by_job_id` is a logical reference (no DB FK) to avoid the
    circular jobs↔validations insertion dependency; D2 verifies it
    transactionally.
    """

    __tablename__ = "provisioning_validations"
    __table_args__ = (
        CheckConstraint("expected_revocation_revision >= 0", name="ck_prov_validations_revocation_min"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    target_id: Mapped[str] = mapped_column(_restrict("provisioning_targets.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(_restrict("operators.id"), nullable=False)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)  # <=32KiB, service-enforced
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    config_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    consumed_by_job_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    expected_revocation_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProvisioningJob(Base):
    """§4: durable seven-state job (§3). Terminal iff completed_at is set."""

    __tablename__ = "provisioning_jobs"
    __table_args__ = (
        _check("ck_prov_jobs_state", "state", JOB_STATES),
        _check("ck_prov_jobs_operation", "operation", JOB_OPERATIONS),
        CheckConstraint("revision >= 0", name="ck_prov_jobs_revision_min"),
        CheckConstraint("lease_generation >= 0", name="ck_prov_jobs_lease_generation_min"),
        Index("ix_jobs_dispatch", "state", "next_check_at", "lease_until"),
        Index("ix_jobs_target_created", "target_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    target_id: Mapped[str] = mapped_column(_restrict("provisioning_targets.id"), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    expected_host_id: Mapped[str | None] = mapped_column(_restrict("hosts.id"), nullable=True)
    validation_id: Mapped[str] = mapped_column(_restrict("provisioning_validations.id"), unique=True, nullable=False)
    requester_id: Mapped[str] = mapped_column(_restrict("operators.id"), nullable=False)
    approval_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approval_expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)  # <=32KiB, service-enforced
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    step: Mapped[str] = mapped_column(String(64), nullable=False, default="REVALIDATE")
    deadline_at: Mapped[int] = mapped_column(Integer, nullable=False)
    cancel_requested_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reconciliation_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dispatch_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_check_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_until: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_of_job_id: Mapped[str | None] = mapped_column(_restrict("provisioning_jobs.id"), nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ProvisioningRequest(Base):
    """§4: idempotency reservation; retained as long as the job."""

    __tablename__ = "provisioning_requests"

    actor_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    route_scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    job_id: Mapped[str] = mapped_column(_restrict("provisioning_jobs.id"), nullable=False)


class ProvisioningOwnership(Base):
    """§4: target ownership; row and generation survive release (§5)."""

    __tablename__ = "provisioning_ownership"
    __table_args__ = (
        _check("ck_prov_ownership_disposition", "disposition", DISPOSITIONS),
        CheckConstraint("generation >= 1", name="ck_prov_ownership_generation_min"),
    )

    target_id: Mapped[str] = mapped_column(_restrict("provisioning_targets.id"), primary_key=True)
    host_id: Mapped[str | None] = mapped_column(_restrict("hosts.id"), unique=True, nullable=True)
    owner_job_id: Mapped[str] = mapped_column(_restrict("provisioning_jobs.id"), unique=True, nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    disposition: Mapped[str] = mapped_column(String(16), nullable=False, default="HELD")
    acquired_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    released_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


# ---------------------------------------------------------------------- §4 §15.1


class ProvisioningAttempt(Base):
    """§4 §15.1: per-step attempt; ordinal 1..3; admission gate for irrevocable steps."""

    __tablename__ = "provisioning_attempts"
    __table_args__ = (
        _check("ck_prov_attempts_ordinal", "ordinal", (1, 2, 3)),
        _check("ck_prov_attempts_admission_state", "admission_state", ADMISSION_STATES),
        Index("ix_attempts_job_status", "job_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(_restrict("provisioning_jobs.id"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    dispatch_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    ownership_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    intent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="INTENT")
    provider_handle: Mapped[str | None] = mapped_column(String(512), nullable=True)
    provider_receipt_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deadline_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finished_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # §15.1: irrevocable-closure gate.
    admission_state: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    closed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    closure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProvisioningEvent(Base):
    """§4: append-only job audit log; (job_id, sequence) is the natural PK."""

    __tablename__ = "provisioning_events"
    __table_args__ = (Index("ix_events_job_sequence", "job_id", "sequence"),)

    job_id: Mapped[str] = mapped_column(_restrict("provisioning_jobs.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------- §4 §15.2


class ProvisioningGrant(Base):
    """§15.2: one-time provisioning token; consumed at agent handshake."""

    __tablename__ = "provisioning_grants"
    __table_args__ = (
        CheckConstraint("expected_revocation_revision >= 0", name="ck_prov_grants_revocation_min"),
        Index("ix_grants_job_expires", "job_id", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(_restrict("provisioning_jobs.id"), nullable=False)
    dispatch_id: Mapped[str] = mapped_column(_restrict("provisioning_jobs.id"), nullable=False)
    target_id: Mapped[str] = mapped_column(_restrict("provisioning_targets.id"), nullable=False)
    expected_host_id: Mapped[str | None] = mapped_column(_restrict("hosts.id"), nullable=True)
    intent: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    consumed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_host_id: Mapped[str | None] = mapped_column(_restrict("hosts.id"), nullable=True)
    result_credential_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revoked_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_revocation_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProvisioningCredentialCommit(Base):
    """§15.2: durable credential version record; survives agent restarts."""

    __tablename__ = "provisioning_credential_commits"
    __table_args__ = (
        CheckConstraint("expected_revocation_revision >= 0", name="ck_prov_credcommits_revocation_min"),
        CheckConstraint("committed_version >= 1", name="ck_prov_credcommits_version_min"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(_restrict("provisioning_jobs.id"), nullable=False)
    grant_id: Mapped[str] = mapped_column(_restrict("provisioning_grants.id"), unique=True, nullable=False)
    host_id: Mapped[str] = mapped_column(_restrict("hosts.id"), nullable=False)
    previous_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    committed_version: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    committed_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_revocation_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# ---------------------------------------------------------------------- §4 §15.3


class ProvisioningChallenge(Base):
    """§15.3: per-attempt challenge; nonce consumed on first valid response."""

    __tablename__ = "provisioning_challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(_restrict("provisioning_jobs.id"), nullable=False)
    host_id: Mapped[str] = mapped_column(_restrict("hosts.id"), nullable=False)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_instance_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    nonce_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    activation_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    consumed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ProvisioningReceipt(Base):
    """§15.3: agent identity proof; composite (job, kind, instance, sequence) is unique."""

    __tablename__ = "provisioning_receipts"
    __table_args__ = (
        Index(
            "ix_receipts_job_id",
            "job_id", "kind", "runtime_instance_id", "sample_sequence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(_restrict("provisioning_jobs.id"), nullable=False)
    host_id: Mapped[str] = mapped_column(_restrict("hosts.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_slot: Mapped[str] = mapped_column(String(16), nullable=False)
    runtime_instance_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    challenge_id: Mapped[str] = mapped_column(_restrict("provisioning_challenges.id"), nullable=False)
    sample_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


