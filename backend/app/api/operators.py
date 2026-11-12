"""Operator auth: login/logout/me + require_operator dependency (O1 accepted).

Session tokens are 256-bit random, shown/held by the client, stored hashed.
Verification resolves the operator and enforces expiry + revocation + role.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.codes import ErrorCode
from ..core.config import get_settings
from ..core.db import get_db
from ..core.errors import ApiError
from ..core.security import generate_agent_token, hash_session_token, verify_operator_password
from ..models import Operator, OperatorSession
from ..schemas import (
    LoginRequest,
    LoginResponse,
    MeResponse,
)

router = APIRouter(prefix="/api/v1/operators")


# -------------------------------------------------------------------------
# Phase 6: login rate limiting — per-username sliding window (in-memory).
#
# Single-process control plane (uvicorn, one worker) makes in-memory state
# sufficient; a multi-worker deployment would need shared state (documented
# limitation in the release notes). Bounded memory: at most one deque per
# username seen, pruned on access.
# -------------------------------------------------------------------------
from collections import deque  # noqa: E402
from threading import Lock  # noqa: E402

# Bounded: at most _MAX_TRACKED_USERNAMES usernames tracked at once (the
# window deques are small). Prevents unbounded memory growth from attackers
# rotating unique usernames (review finding, Phase 6).
_MAX_TRACKED_USERNAMES = 10_000
_login_attempts: dict[str, deque[datetime]] = {}
_login_lock = Lock()


def _check_login_rate(username: str) -> None:
    """Raise 429 RATE_LIMITED when the username exceeded its attempt budget."""
    settings = get_settings()
    now = _now()
    window = timedelta(seconds=settings.login_rate_limit_window_seconds)
    with _login_lock:
        if (
            username not in _login_attempts
            and len(_login_attempts) >= _MAX_TRACKED_USERNAMES
        ):
            # Evict expired entries wholesale; if still full, drop the oldest.
            for key in list(_login_attempts.keys()):
                dq = _login_attempts[key]
                if not dq or now - dq[-1] > window:
                    del _login_attempts[key]
            while len(_login_attempts) >= _MAX_TRACKED_USERNAMES:
                _login_attempts.pop(next(iter(_login_attempts)))
        attempts = _login_attempts.setdefault(username, deque())
        while attempts and now - attempts[0] > window:
            attempts.popleft()
        if len(attempts) >= settings.login_rate_limit_attempts:
            # Generic body: identical for known/unknown usernames so the limit
            # response is not a username-existence oracle (review finding).
            raise ApiError(429, ErrorCode.RATE_LIMITED,
                           "too many login attempts; retry later")
        attempts.append(now)


def _reset_login_rate(username: str) -> None:
    """Clear the failure window after a successful login."""
    with _login_lock:
        _login_attempts.pop(username, None)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    """Normalize DB-provided (possibly naive) datetimes to aware UTC (SQLite)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _resolve_session(db: Session, token: str | None) -> tuple[Operator, OperatorSession]:
    """Validate a bearer session token; return (operator, session)."""
    if not token or not token.startswith("Bearer "):
        raise ApiError(401, ErrorCode.OPERATOR_AUTH_REQUIRED, "operator authentication required")
    token = token.removeprefix("Bearer ").strip()
    if not token:
        raise ApiError(401, ErrorCode.OPERATOR_AUTH_REQUIRED, "operator authentication required")
    sess = db.scalar(select(OperatorSession).where(OperatorSession.token_hash == hash_session_token(token)))
    if sess is None:
        raise ApiError(401, ErrorCode.OPERATOR_AUTH_REQUIRED, "invalid or expired operator session")
    now = _now()
    if sess.revoked_at is not None or _as_utc(sess.expires_at) <= now:
        raise ApiError(401, ErrorCode.OPERATOR_AUTH_REQUIRED, "invalid or expired operator session")
    op = db.get(Operator, sess.operator_id)
    if op is None:
        raise ApiError(401, ErrorCode.OPERATOR_AUTH_REQUIRED, "invalid or expired operator session")
    return op, sess


def require_operator(role: str | None = None):
    """FastAPI dependency factory: operator auth, optionally role-gated (O1)."""

    def _dep(
        authorization: str | None = Header(default=None),
        db: Session = Depends(get_db),
    ) -> Operator:
        op, _sess = _resolve_session(db, authorization)
        if role is not None and op.role != role:
            raise ApiError(403, ErrorCode.OPERATOR_FORBIDDEN, f"operator role {op.role!r} may not perform this action")
        return op

    return _dep


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    # Phase 6: per-username sliding window BEFORE any credential work, so the
    # limit applies to unknown usernames too (no enumeration, no brute force).
    _check_login_rate(req.username)
    op = db.scalar(select(Operator).where(Operator.username == req.username))
    # Same generic message for unknown user and wrong password (no enumeration).
    if op is None or not verify_operator_password(req.password, op.password_hash):
        raise ApiError(401, ErrorCode.UNAUTHORIZED, "invalid credentials")
    _reset_login_rate(req.username)
    settings = get_settings()
    token = generate_agent_token()  # 256-bit, url-safe (same entropy standard)
    now = _now()
    expires = now + timedelta(seconds=settings.operator_session_ttl_seconds)
    sess = OperatorSession(operator_id=op.id, token_hash=hash_session_token(token), created_at=now, expires_at=expires)
    db.add(sess)
    db.commit()
    return LoginResponse(session_token=token, operator_id=op.id, role=op.role, expires_at=expires)


@router.post("/logout")
def logout(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Invalidate the presented session. Idempotent: unknown/already-revoked → 200."""
    if authorization:
        token = authorization.removeprefix("Bearer ").strip()
        sess = db.scalar(select(OperatorSession).where(OperatorSession.token_hash == hash_session_token(token)))
        if sess is not None and sess.revoked_at is None:
            sess.revoked_at = _now()
            db.commit()
    return {"status": "ok"}


@router.get("/me", response_model=MeResponse)
def me(op: Operator = Depends(require_operator())) -> MeResponse:
    return MeResponse(operator_id=op.id, username=op.username, role=op.role)
