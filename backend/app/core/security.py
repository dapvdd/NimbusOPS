"""Agent credential generation, hashing, and verification.

Design (brief §6):
- Enrollment requires the operator's enrollment token (env-provided).
- Each enrolled agent receives a random 256-bit token, returned once.
- Only the SHA-256 hash of the agent token is stored; plaintext is never
  persisted and never logged. Agent endpoints require this token.
- Limitation (documented in docs/SECURITY.md): Phase 1 has no rotation or
  revocation workflow; re-enrolling a host issues a new token.
"""

import hashlib
import secrets

from .config import get_settings

_NIMBUS = b"nimbusops-agent-token-v1"


def generate_agent_token() -> str:
    """256 bits of entropy, URL-safe. Returned once at enrollment."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Keyed hash so a leaked DB file alone is not enough to forge tokens.

    Not a password KDF: agent tokens are 256-bit random values, so a fast
    keyed hash is appropriate and keeps per-request verification cheap.
    The pepper (NIMBUSOPS_TOKEN_PEPPER) is optional; default derives from
    the enrollment token if one is set.
    """
    settings = get_settings()
    pepper = settings.token_pepper or settings.enrollment_token
    return hashlib.sha256(_NIMBUS + pepper.encode("utf-8") + b"\x00" + token.encode("utf-8")).hexdigest()


def verify_agent_token(token: str, expected_hash: str) -> bool:
    if not token or not expected_hash:
        return False
    return secrets.compare_digest(hash_token(token), expected_hash)


def verify_enrollment_token(presented: str) -> bool:
    settings = get_settings()
    if not settings.enrollment_token:
        # Enrollment disabled entirely; caller maps this to 503.
        return False
    return secrets.compare_digest(presented, settings.enrollment_token)
