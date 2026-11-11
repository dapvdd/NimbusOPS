"""Application configuration.

Values come from environment variables (optionally via a local .env file).
No secret has a default: an empty enrollment token disables enrollment
outright rather than silently permitting unauthenticated registration.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NIMBUSOPS_", extra="ignore")

    # Shared secret presented by operators when enrolling a new agent.
    # Empty/absent => enrollment endpoint returns 503 (enrollment disabled).
    enrollment_token: str = ""

    # SQLite database URL. Relative paths resolve against the backend/ dir.
    database_url: str = "sqlite:///./nimbusops.db"

    # Host status thresholds in seconds.
    stale_threshold_seconds: int = 90
    offline_threshold_seconds: int = 600

    # Telemetry rows retained per host (bounded retention).
    telemetry_retention_rows: int = 1440

    # Comma-separated browser origins allowed by CORS. "*" is rejected.
    cors_origins: str = "http://localhost:5173"

    # Optional extra pepper mixed into stored agent-token hashes. If unset,
    # the enrollment token is used as pepper (see core/security.py).
    token_pepper: str = ""

    # Phase 3B (O1 accepted): operator session TTL in seconds (default 12h).
    operator_session_ttl_seconds: int = 43200

    # Phase 3B (O4 accepted): grace period for rotated agent credentials.
    credential_rotation_grace_seconds: int = 300

    # Phase 3B: claim timeout for RUNNING operations (threat I4).
    op_claim_timeout_seconds: int = 600

    # Phase 3B: default TTL for operator-issued bootstrap tokens (max 3600).
    bootstrap_token_ttl_seconds: int = 600


@lru_cache
def get_settings() -> Settings:
    return Settings()
