"""Diagnostics use isolated DB fixtures and mocked installation, never SSH."""

import json

import pytest
from sqlalchemy import select

from backend.app.models import Operator
from backend.app.models.provisioning import ProvisioningEvent
from backend.app.provisioning import worker
from backend.app.provisioning.ssh import InstallOutcomeUnknown, Target
from backend.app.services.provisioning import confirm_plan, save_plan


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "[]",
        "null",
        "true",
        '{"transport_exit_status": true}',
        '{"transport_exit_status": "73"}',
        '{"transport_exit_status": 1.5}',
        '{"transport_exit_status": 256}',
        '{"transport_exit_status": -256}',
    ],
)
def test_diagnostic_allowlist_rejects_invalid_details(raw):
    from backend.app.api.provisioning import safe_event_detail

    assert (
        safe_event_detail(
            ProvisioningEvent(code="INSTALL_TRANSPORT_FAILED", safe_detail_json=raw)
        )
        == {}
    )


def test_other_event_codes_cannot_expose_transport_details():
    from backend.app.api.provisioning import safe_event_detail

    assert (
        safe_event_detail(
            ProvisioningEvent(
                code="OTHER", safe_detail_json='{"transport_exit_status":73}'
            )
        )
        == {}
    )


@pytest.mark.parametrize("code", [
    "INSTALL_COMPLETED", "INSTALL_TIMED_OUT", "INSTALL_CANCELLED",
    "INSTALL_TRANSPORT_FAILED",
])
def test_terminal_diagnostics_expose_only_bounded_exit_facts(code):
    from backend.app.api.provisioning import safe_event_detail

    assert safe_event_detail(ProvisioningEvent(code=code, safe_detail_json=json.dumps({
        "installer_exit_status": 0, "transport_exit_status": 255,
        "stdout": "never-expose", "phase": "untrusted",
    }))) == {"installer_exit_status": 0, "transport_exit_status": 255}


@pytest.mark.parametrize("status", [True, False, "0", 1.5, -1, 256, None])
def test_installer_status_rejects_non_protocol_values(status):
    from backend.app.api.provisioning import safe_event_detail

    assert safe_event_detail(ProvisioningEvent(
        code="INSTALL_COMPLETED", safe_detail_json=json.dumps({
            "installer_exit_status": status, "transport_exit_status": 0,
        }),
    )) == {"transport_exit_status": 0}


@pytest.mark.parametrize("code", ["OTHER", "INSTALL_PHASE_INSTALLER_STARTED", "INSTALL_PHASE_SECRET", "INSTALL_COMPLETED_EXTRA"])
def test_non_outcome_events_do_not_expose_exit_details(code):
    from backend.app.api.provisioning import safe_event_detail

    assert safe_event_detail(ProvisioningEvent(code=code, safe_detail_json=
        '{"installer_exit_status":0,"transport_exit_status":0}')) == {}


def test_legacy_negative_transport_status_is_preserved():
    from backend.app.api.provisioning import safe_event_detail

    assert safe_event_detail(ProvisioningEvent(code="INSTALL_TRANSPORT_FAILED",
        safe_detail_json='{"transport_exit_status":-255}')) == {"transport_exit_status": -255}


def test_numeric_exit_is_recorded_without_changing_reconciliation(
    db_session, monkeypatch
):
    op = Operator(username="diagnostic-admin", password_hash="unused", role="ADMIN")
    db_session.add(op)
    db_session.commit()
    target = Target("test", "192.0.2.1", "installer", "vm", "/key", "/known", "a" * 32)
    facts = {"hostname": "vm"}
    plan = save_plan(db_session, op.id, target, facts)
    job = confirm_plan(db_session, op.id, target, plan.id, plan.plan_hash)
    monkeypatch.setattr(worker, "preflight", lambda _: facts)

    def fail(*args):
        raise InstallOutcomeUnknown(73)

    monkeypatch.setattr(worker, "install", fail)
    worker.run_once(db_session, {"test": target}, "https://demo.example")
    db_session.refresh(job)
    assert job.state == "VERIFYING"
    assert job.reconciliation_required
    assert job.reason_code == "RECONCILIATION_REQUIRED"
    events = db_session.scalars(
        select(ProvisioningEvent).where(ProvisioningEvent.job_id == job.id)
    ).all()
    diagnostic = next(e for e in events if e.code == "INSTALL_TRANSPORT_FAILED")
    assert json.loads(diagnostic.safe_detail_json) == {"transport_exit_status": 73}
    from backend.app.api.provisioning import job_status

    diagnostic.safe_detail_json = json.dumps(
        {"transport_exit_status": 73, "secret": "never-expose"}
    )
    db_session.commit()
    payload = job_status(job.id, op, db_session)
    exposed = next(
        e for e in payload["events"] if e["code"] == "INSTALL_TRANSPORT_FAILED"
    )
    assert exposed["safe_detail"] == {"transport_exit_status": 73}
    assert "never-expose" not in str(payload)
