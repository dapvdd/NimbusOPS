"""RC2 F12/F15: dependency-honest health, readiness, and build identity.

F12: a degraded database must never be reported as a fully healthy service,
and readiness must fail (503) so a load balancer stops routing to it.
F15: the health payload must carry the real server version and a build
identifier instead of a fixed placeholder that cannot be traced to a commit.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.core.db import get_db
from backend.app.main import app


class _BrokenSession:
    def execute(self, *_args, **_kwargs):
        raise RuntimeError("database is unavailable")

    def close(self) -> None:
        pass


@pytest.fixture()
def broken_db(client):
    def _override():
        yield _BrokenSession()

    app.dependency_overrides[get_db] = _override
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_health_reports_degraded_database_honestly(broken_db):
    resp = broken_db.get("/api/v1/health")
    assert resp.status_code == 200  # liveness stays up; the body tells the truth
    body = resp.json()
    assert body["database"] == "degraded"
    assert body["status"] == "degraded"


def test_health_ok_when_database_responds(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_readiness_ok_when_database_responds(client):
    resp = client.get("/api/v1/ready")
    assert resp.status_code == 200
    assert resp.json()["ready"] is True


def test_readiness_fails_when_database_is_degraded(broken_db):
    resp = broken_db.get("/api/v1/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ready"] is False
    assert body["database"] == "degraded"


def test_health_version_and_build_identity_are_real(client, monkeypatch):
    """The version must come from the version module, not a literal pin."""
    from backend.app import version as version_module

    monkeypatch.setattr(version_module, "VERSION", "9.9.9-rcX")
    body = client.get("/api/v1/health").json()
    assert body["version"] == "9.9.9-rcX"
    assert isinstance(body["build"], str) and body["build"]
    assert body["build"] != "0.1.0"


def test_health_response_schema_accepts_degraded():
    """Regression pin: the response model must not reject degraded status."""
    from backend.app.schemas import HealthResponse
    from datetime import datetime, timezone

    model = HealthResponse(
        status="degraded",
        service="nimbusops-control-server",
        version="1.0.0-rc2",
        build="abc1234",
        server_time=datetime.now(timezone.utc),
        database="degraded",
    )
    assert model.status == "degraded"
