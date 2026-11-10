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


# ------------------------------------------------------------------ Phase 3B

_OPERATOR_KDF_ITERATIONS = 240_000  # PBKDF2-SHA256; real KDF for human passwords


def hash_operator_password(password: str) -> str:
    """PBKDF2-SHA256 for operator passwords (NOT the fast token hash —
    passwords are human-chosen and need a KDF; docs/SECURITY.md limitation 4)."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _OPERATOR_KDF_ITERATIONS)
    return f"pbkdf2${_OPERATOR_KDF_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_operator_password(password: str, stored: str) -> bool:
    """Constant-time PBKDF2 verification of the stored `pbkdf2$iter$salt$dk` string."""
    try:
        scheme, iterations, salt_hex, dk_hex = stored.split("$", 3)
        if scheme != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return secrets.compare_digest(dk.hex(), dk_hex)
    except (ValueError, TypeError):
        return False


def hash_session_token(token: str) -> str:
    """Session/bootstrap tokens: same keyed-hash scheme as agent tokens
    (256-bit random values, fast keyed hash is appropriate)."""
    return hash_token(token)
