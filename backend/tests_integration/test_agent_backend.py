"""Integration: real agent code path against the real backend over HTTP.

NOT an Ubuntu verification: this runs on the local development OS
(Windows here). It exercises genuine psutil telemetry, genuine HTTP
transport, real persistence, and real status computation end to end.
"""

import json
import os
import pathlib
import tempfile

import pytest

os.environ["NIMBUSOPS_ENROLLMENT_TOKEN"] = "int-enroll-token"
os.environ["NIMBUSOPS_DATABASE_URL"] = f"sqlite:///{pathlib.Path(tempfile.mkdtemp(prefix='nops-int-')) / 'int.db'}"

import httpx  # noqa: E402

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.core.db import create_all, engine  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.models import Telemetry  # noqa: E402

# Agent imports (real agent code, not mocks)
from nimbusops_agent.telemetry import collect_telemetry, host_info_snapshot  # noqa: E402
from nimbusops_agent import client as agent_client  # noqa: E402


def _enroll_token() -> str:
    """Use the token the loaded settings actually hold (import-order safe)."""
    from backend.app.core.config import get_settings

    return get_settings().enrollment_token


@pytest.fixture(scope="module")
def server_url():
    """Run a real uvicorn server on a loopback port for the integration tests."""
    create_all()
    import threading
    import time as _time

    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=8991, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Wait for readiness.
    for _ in range(50):
        try:
            import httpx as _h

            if _h.get("http://127.0.0.1:8991/api/v1/health").status_code == 200:
                break
        except Exception:
            _time.sleep(0.1)
    yield "http://127.0.0.1:8991", None
    server.should_exit = True
    thread.join(timeout=5)


def _agent_sender(server_url, transport, host_id="", token=""):
    s = agent_client.Sender(server_url=server_url, host_id=host_id, agent_token=token)
    return s


def test_full_agent_to_backend_flow(server_url):
    server, transport = server_url

    # 1. Agent enrolls with the real enrollment payload.
    sender = _agent_sender(server, transport)
    ok, result = sender.enroll(
        hostname="integration-host",
        enrollment_token=_enroll_token(),
        info=host_info_snapshot(),
    )
    assert ok, result
    host_id, agent_token = result["host_id"], result["agent_token"]

    # 2. Real psutil telemetry is collected and accepted.
    sender = _agent_sender(server, transport, host_id, agent_token)
    telemetry = collect_telemetry()
    ok, detail = sender.send_telemetry(telemetry)
    assert ok, detail

    # 3. Backend actually persisted it (DB query, not API echo).
    with engine.connect() as conn:
        rows = conn.execute(
            Telemetry.__table__.select().where(Telemetry.host_id == host_id)
        ).mappings().all()
    assert len(rows) == 1
    row = rows[0]
    assert row["cpu_percent"] == pytest.approx(telemetry["cpu_percent"])
    assert row["memory_total_bytes"] == telemetry["memory_total_bytes"]
    assert row["disk_total_bytes"] == telemetry["disk_total_bytes"]

    # 4. Public API exposes it with honest status.
    public = httpx.Client(base_url=server)
    host = public.get(f"/api/v1/hosts/{host_id}").json()
    assert host["status"] == "ONLINE"
    assert host["latest_metrics"]["cpu_percent"] == pytest.approx(telemetry["cpu_percent"])
    assert host["last_telemetry_at"] is not None

    # 5. Heartbeat keeps it online.
    ok, detail = sender.send_heartbeat(host_info_snapshot())
    assert ok, detail

    # 6. Wrong credential is rejected on the same path the real agent uses.
    bad = _agent_sender(server, transport, host_id, "not-the-token")
    with pytest.raises(agent_client.AuthError):
        bad.send_telemetry({**{k: v for k, v in telemetry.items() if not k.startswith("_")}})


def test_tampered_telemetry_rejected(server_url):
    server, transport = server_url
    sender = _agent_sender(server, transport)
    ok, result = sender.enroll("tamper-host", _enroll_token(), host_info_snapshot())
    assert ok
    host_id, token = result["host_id"], result["agent_token"]
    sender = _agent_sender(server, transport, host_id, token)
    telemetry = collect_telemetry()
    telemetry["cpu_percent"] = 150.0  # Out of physical bounds.
    ok, detail = sender.send_telemetry(telemetry)
    assert not ok
    assert "422" in detail
