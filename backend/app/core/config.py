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


@lru_cache
def get_settings() -> Settings:
    return Settings()
