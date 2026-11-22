"""Offline history contracts: synthetic jobs, no confirmation or dispatch."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import hash_session_token
from backend.app.models import Base, Operator, OperatorSession
from backend.app.models.provisioning import (
    ProvisioningConnection,
    ProvisioningEvent,
    ProvisioningJob,
    ProvisioningTarget,
    ProvisioningValidation,
)

PREFIX = "/api/v1/provisioning/jobs"
METADATA_KEYS = {
    "id",
    "target_id",
    "method",
    "operation",
    "created_at",
    "updated_at",
    "state",
    "step",
    "reason_code",
    "reconciliation_required",
}


@pytest.fixture()
def history(client: TestClient, db_session: Session) -> dict[str, dict[str, str]]:
    """Seed complete FK-valid records solely in the scratch test database."""
    headers = {}
    for name, role in (("owner", "ADMIN"), ("other", "ADMIN"), ("viewer", "VIEWER")):
        db_session.add(
            Operator(id=name, username=name, password_hash="unused", role=role)
        )
        db_session.flush()
        db_session.add(
            OperatorSession(
                operator_id=name,
                token_hash=hash_session_token(name + "-token"),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        headers[name] = {"Authorization": "Bearer " + name + "-token"}
    db_session.add(
        ProvisioningConnection(
            id="connection",
            provider="GENERIC_LINUX",
            display_name="Offline",
            policy_hash="c" * 64,
        )
    )
    db_session.flush()
    db_session.add(
        ProvisioningTarget(
            id="target",
            connection_id="connection",
            canonical_key="offline-target",
        )
    )
    db_session.flush()
    for index in range(106):
        owner = "owner" if index < 105 else "other"
        identifier = f"job-{index:03}"
        db_session.add(
            ProvisioningValidation(
                id=identifier,
                target_id="target",
                actor_id=owner,
                plan_json='{"secret":"validation-secret"}',
                plan_hash="a" * 64,
                config_revision=1,
                mapping_revision=0,
                observed_identity_hash="b" * 64,
                expires_at=999999,
            )
        )
        db_session.flush()
        db_session.add(
            ProvisioningJob(
                id=identifier,
                target_id="target",
                operation="INSTALL",
                requester_id=owner,
                validation_id=identifier,
                approval_hash="d" * 64,
                approval_expires_at=999999,
                plan_json='{"token":"plan-secret","provider":"provider-secret"}',
                deadline_at=999999,
                created_at=1000 + index // 2,
                updated_at=2000 + index,
                state="FAILED",
                step="REVALIDATE",
                reason_code="PREFLIGHT_REJECTED",
            )
        )
    db_session.flush()
    for sequence, code, detail in (
        (
            2,
            "INSTALL_TRANSPORT_FAILED",
            '{"transport_exit_status":23,"token":"event-secret"}',
        ),
        (1, "PREFLIGHT_REJECTED", '{"provider":"provider-secret"}'),
        (3, "INSTALL_TRANSPORT_FAILED", '{"transport_exit_status":true}'),
        (4, "INSTALL_TRANSPORT_FAILED", "not-json"),
        (5, "INSTALL_TRANSPORT_FAILED", '{"transport_exit_status":256}'),
    ):
        db_session.add(
            ProvisioningEvent(
                job_id="job-104",
                sequence=sequence,
                at=3000 + sequence,
                actor_kind="WORKER",
                actor_id="offline",
                code=code,
                safe_detail_json=detail,
            )
        )
    db_session.commit()
    return headers


def test_history_default_page_is_owner_scoped_newest_first(
    client: TestClient,
    history: dict[str, dict[str, str]],
) -> None:
    response = client.get(PREFIX, headers=history["owner"])
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"jobs", "total"}
    assert body["total"] == 105
    assert [job["id"] for job in body["jobs"]] == [
        f"job-{i:03}" for i in range(104, 54, -1)
    ]
    assert all(set(job) == METADATA_KEYS for job in body["jobs"])
    assert body["jobs"][0] == {
        "id": "job-104",
        "target_id": "target",
        "method": "Automatic Setup",
        "operation": "INSTALL",
        "created_at": 1052,
        "updated_at": 2104,
        "state": "FAILED",
        "step": "REVALIDATE",
        "reason_code": "PREFLIGHT_REJECTED",
        "reconciliation_required": False,
    }


def test_history_pagination_and_owner_totals(
    client: TestClient,
    history: dict[str, dict[str, str]],
) -> None:
    response = client.get(
        PREFIX, params={"limit": 100, "offset": 3}, headers=history["owner"]
    )
    assert response.status_code == 200
    assert [job["id"] for job in response.json()["jobs"]] == [
        f"job-{i:03}" for i in range(101, 1, -1)
    ]
    assert response.json()["total"] == 105
    assert client.get(
        PREFIX, params={"offset": 105}, headers=history["owner"]
    ).json() == {"jobs": [], "total": 105}
    other = client.get(PREFIX, headers=history["other"]).json()
    assert other["total"] == 1
    assert [job["id"] for job in other["jobs"]] == ["job-105"]
    assert client.get(PREFIX + "/job-105", headers=history["owner"]).status_code == 404
    assert client.get(PREFIX + "/missing", headers=history["owner"]).status_code == 404


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "bad"}]
)
def test_history_rejects_invalid_pagination(
    client: TestClient,
    history: dict[str, dict[str, str]],
    params: dict[str, Any],
) -> None:
    assert (
        client.get(PREFIX, params=params, headers=history["owner"]).status_code == 422
    )


@pytest.mark.parametrize("suffix", ["", "/job-104"])
def test_history_requires_admin(
    client: TestClient,
    history: dict[str, dict[str, str]],
    suffix: str,
) -> None:
    assert client.get(PREFIX + suffix).status_code == 401
    assert client.get(PREFIX + suffix, headers=history["viewer"]).status_code == 403


def test_detail_extends_metadata_preserving_retry_and_safe_events(
    client: TestClient,
    history: dict[str, dict[str, str]],
) -> None:
    response = client.get(PREFIX + "/job-104", headers=history["owner"])
    assert response.status_code == 200
    detail = response.json()
    assert set(detail) == METADATA_KEYS | {"retry_allowed", "events"}
    assert detail["method"] == "Automatic Setup"
    assert detail["target_id"] == "target"
    assert detail["operation"] == "INSTALL"
    assert detail["created_at"] == 1052
    assert detail["updated_at"] == 2104
    assert detail["retry_allowed"] is True
    assert [event["sequence"] for event in detail["events"]] == [1, 2, 3, 4, 5]
    assert [event["safe_detail"] for event in detail["events"]] == [
        {},
        {"transport_exit_status": 23},
        {},
        {},
        {},
    ]
    assert all(
        set(event) == {"sequence", "code", "at", "safe_detail"}
        for event in detail["events"]
    )
    assert "secret" not in response.text


def test_history_and_detail_never_mutate_persisted_records(
    client: TestClient,
    db_session: Session,
    history: dict[str, dict[str, str]],
) -> None:
    def snapshot() -> dict[str, list[dict[str, Any]]]:
        return {
            table.name: [
                dict(row) for row in db_session.execute(select(table)).mappings()
            ]
            for table in Base.metadata.sorted_tables
        }

    before = snapshot()
    assert client.get(PREFIX, headers=history["owner"]).status_code == 200
    assert client.get(PREFIX + "/job-104", headers=history["owner"]).status_code == 200
    db_session.expire_all()
    assert snapshot() == before
