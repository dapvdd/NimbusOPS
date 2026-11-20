"""RC2 F05/F06: label ownership proof and honest verification.

F05: before any lifecycle mutation the agent inspects the target container and
requires both the managed label and the exact deployment label. Missing,
mismatched, or unverifiable ownership fails closed. A name collision with an
unmanaged container is never mutated.

F06: a failed or empty inspection must never be reported as SUCCEEDED/STOPPED.
UNKNOWN is distinct from STOPPED, and HTTP health is reported separately from
process/container state.
"""

import json

from agent.nimbusops_agent.docker_exec import DockerExecutor, ManagedResourceError, parse_container_state

NAME = "nimbusops-nginx-demo-abc12345"
DEP = "dep-1"
TEMPLATE = {
    "key": "nginx-demo",
    "image": "nginx:1.27-alpine",
    "container_port": 80,
    "host_port": 8080,
    "container_name": NAME,
}


class Runner:
    """Small argv-aware fake Docker CLI (no real Engine)."""

    def __init__(
        self,
        *,
        labels=None,
        inspect_rc=0,
        inspect_err="",
        ps_rc=0,
        ps_out="Up 1 second",
        mutate_rc=0,
    ):
        self.labels = labels
        self.inspect_rc = inspect_rc
        self.inspect_err = inspect_err
        self.ps_rc = ps_rc
        self.ps_out = ps_out
        self.mutate_rc = mutate_rc
        self.calls: list[list[str]] = []

    def __call__(self, argv, timeout):
        self.calls.append(list(argv))
        if argv[:2] == ["docker", "version"]:
            return 0, "27.0", ""
        if argv[:2] == ["docker", "inspect"]:
            if self.inspect_rc != 0:
                return self.inspect_rc, "", self.inspect_err
            return 0, json.dumps(self.labels if self.labels is not None else {}), ""
        if argv[:2] == ["docker", "ps"]:
            return self.ps_rc, self.ps_out, ""
        if argv[:2] in (["docker", "start"], ["docker", "stop"], ["docker", "restart"], ["docker", "pull"], ["docker", "run"]):
            return self.mutate_rc, "", ""
        return 0, "", ""

    def mutations(self):
        return [c for c in self.calls if c[:2] in (["docker", "start"], ["docker", "stop"], ["docker", "restart"], ["docker", "run"])]


OWNED = {"nimbusops.managed": "true", "nimbusops.deployment": DEP}


# ------------------------------------------------------------------ F05 start

def test_start_rejects_missing_managed_label():
    r = Runner(labels={"nimbusops.deployment": DEP})
    out = DockerExecutor(runner=r).execute(
        {"op_type": "START", "deployment_id": DEP, "template": {"container_name": NAME}}
    )
    assert out["status"] == "FAILED"
    assert out["error_code"] == "UNAPPROVED_OPERATION"
    assert r.mutations() == []


def test_start_rejects_wrong_deployment_label():
    r = Runner(labels={"nimbusops.managed": "true", "nimbusops.deployment": "someone-else"})
    out = DockerExecutor(runner=r).execute(
        {"op_type": "START", "deployment_id": DEP, "template": {"container_name": NAME}}
    )
    assert out["status"] == "FAILED"
    assert out["error_code"] == "UNAPPROVED_OPERATION"
    assert r.mutations() == []


def test_start_rejects_missing_container():
    r = Runner(inspect_rc=1, inspect_err=f"Error: No such object: {NAME}")
    out = DockerExecutor(runner=r).execute(
        {"op_type": "START", "deployment_id": DEP, "template": {"container_name": NAME}}
    )
    assert out["status"] == "FAILED"
    assert r.mutations() == []


def test_start_fails_closed_when_inspection_fails():
    r = Runner(inspect_rc=1, inspect_err="permission denied")
    out = DockerExecutor(runner=r).execute(
        {"op_type": "START", "deployment_id": DEP, "template": {"container_name": NAME}}
    )
    assert out["status"] == "UNKNOWN"
    assert out["error_code"] == "VERIFY_FAILED"
    assert r.mutations() == []


def test_start_owned_container_succeeds_and_verifies():
    r = Runner(labels=OWNED, ps_out="Up 2 seconds")
    out = DockerExecutor(runner=r).execute(
        {"op_type": "START", "deployment_id": DEP, "template": {"container_name": NAME}}
    )
    assert out["status"] == "SUCCEEDED", out
    assert any(c[:2] == ["docker", "start"] for c in r.mutations())


def test_stop_and_restart_reject_ownership_mismatch():
    for op in ("STOP", "RESTART"):
        r = Runner(labels={"nimbusops.managed": "true", "nimbusops.deployment": "other"})
        out = DockerExecutor(runner=r).execute(
            {"op_type": op, "deployment_id": DEP, "template": {"container_name": NAME}}
        )
        assert out["status"] == "FAILED", op
        assert r.mutations() == [], op


# ----------------------------------------------------------------- F05 deploy

def test_deploy_refuses_unmanaged_name_collision():
    r = Runner(labels={"nimbusops.managed": "false"})
    out = DockerExecutor(runner=r).execute(
        {"op_type": "DEPLOY", "deployment_id": DEP, "template": TEMPLATE}
    )
    assert out["status"] == "FAILED"
    assert out["error_code"] == "UNAPPROVED_OPERATION"
    assert r.mutations() == []


def test_deploy_refuses_to_recreate_an_existing_owned_container():
    r = Runner(labels=OWNED)
    out = DockerExecutor(runner=r).execute(
        {"op_type": "DEPLOY", "deployment_id": DEP, "template": TEMPLATE}
    )
    assert out["status"] == "FAILED"
    assert out["error_code"] == "CONTAINER_EXISTS"
    assert r.mutations() == []


# ------------------------------------------------------------------ F06 stop

def test_stop_inspection_failure_is_unknown_not_success():
    r = Runner(labels=OWNED, ps_rc=1, ps_out="")
    out = DockerExecutor(runner=r).execute(
        {"op_type": "STOP", "deployment_id": DEP, "template": {"container_name": NAME}}
    )
    assert out["status"] == "UNKNOWN"
    assert out["error_code"] == "VERIFY_FAILED"
    assert "EXITED" not in json.dumps(out)


def test_stop_empty_inspection_output_is_unknown_not_stopped():
    r = Runner(labels=OWNED, ps_out="")
    out = DockerExecutor(runner=r).execute(
        {"op_type": "STOP", "deployment_id": DEP, "template": {"container_name": NAME}}
    )
    assert out["status"] == "UNKNOWN"
    assert out["error_code"] == "VERIFY_FAILED"
    assert "EXITED" not in json.dumps(out)


def test_stop_confirmed_exited_succeeds():
    r = Runner(labels=OWNED, ps_out="Exited (0) 1 second ago")
    out = DockerExecutor(runner=r).execute(
        {"op_type": "STOP", "deployment_id": DEP, "template": {"container_name": NAME}}
    )
    assert out["status"] == "SUCCEEDED"
    assert out["result"]["container_state"] == "EXITED"


# ------------------------------------------------------- state parsing / health

def test_paused_container_is_not_running():
    assert parse_container_state("Up 3 hours (Paused)") == "PAUSED"


def test_running_state_and_http_health_are_distinct(monkeypatch):
    r = Runner(labels=OWNED, ps_out="Up 5 seconds")

    def probe_false(self, port, timeout=5.0):
        return False

    monkeypatch.setattr(DockerExecutor, "probe_http", probe_false)
    out = DockerExecutor(runner=r).execute(
        {"op_type": "START", "deployment_id": DEP, "template": {"container_name": NAME, "host_port": 8080}}
    )
    assert out["status"] == "SUCCEEDED"
    assert out["result"]["container_state"] == "RUNNING"
    assert out["result"]["http_ok"] is False
