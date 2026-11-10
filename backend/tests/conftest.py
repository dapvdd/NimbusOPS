"""Shared test fixtures: isolated DB per test, settings overrides."""

import os
import tempfile
import pathlib

import pytest
from fastapi.testclient import TestClient

# Ensure a clean environment for each test session.
_tmpdir = tempfile.mkdtemp(prefix="nimbusops-test-")
os.environ["NIMBUSOPS_ENROLLMENT_TOKEN"] = "test-enroll-token"
os.environ["NIMBUSOPS_DATABASE_URL"] = f"sqlite:///{pathlib.Path(_tmpdir) / 'test.db'}"
os.environ["NIMBUSOPS_CORS_ORIGINS"] = "http://localhost:5173"
os.environ["NIMBUSOPS_STALE_THRESHOLD_SECONDS"] = "90"
os.environ["NIMBUSOPS_OFFLINE_THRESHOLD_SECONDS"] = "600"

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.core.db import create_all, engine  # noqa: E402
from backend.app.main import app  # noqa: E402


@pytest.fixture()
def client():
    create_all()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    # Truncate tables between tests.
    from backend.app.models import Base

    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture()
def enroll_token() -> str:
    return get_settings().enrollment_token


@pytest.fixture()
def enrolled_host(client, enroll_token):
    """Enroll a host and return (host_id, agent_token)."""
    resp = client.post(
        "/api/v1/agents/enroll",
        json={
            "hostname": "test-host-1",
            "enrollment_token": enroll_token,
            "agent_version": "0.1.0",
            "platform": "Linux",
            "platform_release": "6.8.0-45-generic",
            "cpu_cores": 4,
            "total_memory_bytes": 8_000_000_000,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["host_id"], body["agent_token"]


@pytest.fixture()
def db_session():
    """Direct DB session for seeding/inspection (separate from TestClient requests)."""
    from backend.app.core.db import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def online_host(client, enroll_token):
    """Enroll a host and make it ONLINE via a heartbeat."""
    resp = client.post(
        "/api/v1/agents/enroll",
        json={"hostname": "deploy-host", "enrollment_token": enroll_token},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    hb = client.post(
        "/api/v1/agents/heartbeat",
        json={"agent_version": "0.2.0"},
        headers=auth_headers(body["host_id"], body["agent_token"]),
    )
    assert hb.status_code == 200, hb.text
    return body["host_id"], body["agent_token"]


def auth_headers(host_id: str, token: str) -> dict:
    """Plain helper (NOT a fixture): legacy tests import and call this directly."""
    return {"X-Host-Id": host_id, "Authorization": f"Bearer {token}"}
