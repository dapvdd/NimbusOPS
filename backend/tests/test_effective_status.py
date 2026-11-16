"""Slice 1 / Task 1.1: effective_status — REVOKED beats connectivity.

The connectivity-only `compute_status` cannot express revocation: a revoked
host with a fresh heartbeat renders ONLINE today. `effective_status` is the
display-truth function: revocation always wins, everything else delegates to
the existing connectivity contract (unchanged semantics, existing callers).
"""

from datetime import datetime, timedelta, timezone

from backend.app.services.hosts import effective_status

NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
FRESH = NOW - timedelta(seconds=30)
MID = NOW - timedelta(minutes=10)
PAST = NOW - timedelta(hours=2)
STALE_S = 300
OFFLINE_S = 3600


def _call(last_seen_at):
    return effective_status(
        is_revoked=False,
        enrollment_status="ENROLLED",
        last_seen_at=last_seen_at,
        now=NOW,
        stale_s=STALE_S,
        offline_s=OFFLINE_S,
    )


def test_revoked_beats_fresh_heartbeat():
    """A revoked host must never render ONLINE, even with a fresh heartbeat."""
    status = effective_status(
        is_revoked=True,
        enrollment_status="ENROLLED",
        last_seen_at=FRESH,
        now=NOW,
        stale_s=STALE_S,
        offline_s=OFFLINE_S,
    )
    assert status == "REVOKED"


def test_enrollment_status_revoked_wins():
    """`enrollment_status == "REVOKED"` alone also forces REVOKED (tombstones)."""
    status = effective_status(
        is_revoked=False,
        enrollment_status="REVOKED",
        last_seen_at=FRESH,
        now=NOW,
        stale_s=STALE_S,
        offline_s=OFFLINE_S,
    )
    assert status == "REVOKED"


def test_revoked_beats_never_seen():
    status = effective_status(
        is_revoked=True,
        enrollment_status="ENROLLED",
        last_seen_at=None,
        now=NOW,
        stale_s=STALE_S,
        offline_s=OFFLINE_S,
    )
    assert status == "REVOKED"


def test_non_revoked_matches_compute_status():
    """Non-revoked hosts keep the exact connectivity contract."""
    assert _call(None) == "OFFLINE"
    assert _call(FRESH) == "ONLINE"
    assert _call(MID) == "STALE"
    assert _call(PAST) == "OFFLINE"
