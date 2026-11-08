"""Phase 2 agent tests: Docker executor (MOCKED subprocess), poll loop, results.

All Docker interaction here is MOCKED — no real Docker Engine is required or
used. Real-Docker verification is a separate live gate (see
docs/PHASE2_VERIFICATION.md; BLOCKED on this machine).
"""

import pytest

from agent.nimbusops_agent.docker_exec import (
    DockerExecutor,
    DockerUnavailable,
    ManagedResourceError,
    parse_container_state,
)


NGINX_TEMPLATE = {
    "key": "nginx-demo",
    "image": "nginx:1.27-alpine",
    "container_port": 80,
    "host_port": 8080,
    "container_name": "nimbusops-nginx-demo-abc12345",
}


class FakeRunner:
    """Records argv, returns canned (returncode, stdout, stderr)."""

    def __init__(self, results=None):
        self.calls: list[list[str]] = []
        self.results = results or []

    def __call__(self, argv, timeout):
        self.calls.append(list(argv))
        if callable(self.results):
            return self.results(len(self.calls), argv)
        if self.results:
            return self.results.pop(0)
        return 0, "", ""


# ------------------------------------------------------------ availability


def test_docker_unavailable_raises(monkeypatch):
    calls = []

    def runner(argv, timeout):
        calls.append(argv)
        raise FileNotFoundError("docker not found")

    ex = DockerExecutor(runner=runner)
    with pytest.raises(DockerUnavailable):
        ex.ensure_available()
    assert calls, "availability probe should invoke docker CLI"


def test_docker_unavailable_error_is_typed(monkeypatch):
    def runner(argv, timeout):
        return 1, "", "Cannot connect to the Docker daemon"

    ex = DockerExecutor(runner=runner)
    with pytest.raises(DockerUnavailable):
        ex.ensure_available()


# ---------------------------------------------------------------- deploy


def test_deploy_uses_constrained_argv_with_labels():
    runner = FakeRunner(
        results=[
            (0, "24.0.7", ""),  # ensure_available
            (0, "", ""),  # pull
            (0, "", ""),  # run
            (0, "Up 2 minutes", ""),  # ps filter (state verify)
        ]
    )
    recorded = []
    ex = DockerExecutor(runner=lambda argv, timeout: (recorded.append(argv), runner(argv, timeout))[1])

    outcome = ex.deploy(NGINX_TEMPLATE, deployment_id="dep-1")
    assert outcome["status"] == "SUCCEEDED"
    # run argv: no shell string, explicit label, no privileged, no mounts
    run_argv = next(a for a in recorded if "run" in a)
    assert "-d" in run_argv
    assert "--label" in run_argv
    assert "nimbusops.managed=true" in run_argv
    assert "nimbusops.deployment=dep-1" in run_argv
    assert "--name" in run_argv
    assert not any(arg.startswith("--privileged") for arg in run_argv)
    assert "-v" not in run_argv  # no host mounts in Phase 2 nginx template


def test_deploy_failure_maps_to_DOCKER_FAILURE():
    runner = FakeRunner(
        results=[
            (0, "available", ""),
            (0, "", ""),
            (1, "", "OCI runtime create failed: something broke"),  # run fails
        ]
    )
    ex = DockerExecutor(runner=runner)
    outcome = ex.deploy(NGINX_TEMPLATE, deployment_id="dep-1")
    assert outcome["status"] == "FAILED"
    assert outcome["error_code"] == "DOCKER_FAILURE"
    assert "OCI runtime create failed" in outcome["error_message"]


def test_deploy_verifies_container_actually_running():
    """SUCCEEDED requires ps output showing the container running."""

    def results(n, argv):
        if "version" in argv:
            return 0, "24.0.7", ""
        if "ps" in argv:
            return 0, "", ""  # empty: container NOT running
        return 0, "", ""

    runner = FakeRunner(results=results)
    ex = DockerExecutor(runner=runner)
    outcome = ex.deploy(NGINX_TEMPLATE, deployment_id="dep-1")
    assert outcome["status"] == "UNKNOWN"
    assert outcome["error_code"] == "VERIFY_FAILED"


def test_deploy_timeout_maps_to_TIMEOUT():
    def runner(argv, timeout):
        raise TimeoutError()

    ex = DockerExecutor(runner=runner)
    outcome = ex.execute(
        {"op_type": "DEPLOY", "template": NGINX_TEMPLATE, "deployment_id": "dep-1", "operation_id": "op-1"}
    )
    assert outcome["status"] == "UNKNOWN"
    assert outcome["error_code"] == "TIMEOUT"


# ---------------------------------------------------------- state parsing


def test_parse_container_state_from_ps_format():
    assert parse_container_state("Up 2 minutes") == "RUNNING"
    assert parse_container_state("Exited (0) 5 seconds ago") == "EXITED"
    assert parse_container_state("") is None


# ---------------------------------------------------------- start / stop


def test_start_stop_only_touches_labeled_managed_container():
    recorded = []
    runner = FakeRunner(
        results=[
            (0, "24.0.7", ""),  # ensure_available (start)
            (0, "", ""),  # start
            (0, "Up 1 second", ""),  # verify
        ]
    )
    ex = DockerExecutor(runner=lambda argv, timeout: (recorded.append(argv), runner(argv, timeout))[1])

    outcome = ex.start("nimbusops-nginx-demo-abc12345", deployment_id="dep-1", host_port=None)
    assert outcome["status"] == "SUCCEEDED"
    start_argv = next(a for a in recorded if "start" in a)
    # Container name is constrained to the nimbusops prefix.
    assert start_argv[-1] == "nimbusops-nginx-demo-abc12345"


def test_start_rejects_non_nimbusops_container_name():
    ex = DockerExecutor(runner=FakeRunner())
    with pytest.raises(ManagedResourceError):
        ex.start("evil-container", deployment_id="dep-1")


def test_stop_rejects_non_nimbusops_container_name():
    ex = DockerExecutor(runner=FakeRunner())
    with pytest.raises(ManagedResourceError):
        ex.stop("my-important-db", deployment_id="dep-1")


def test_stop_succeeds_and_verifies():
    runner = FakeRunner(
        results=[
            (0, "available", ""),
            (0, "", ""),  # stop
            (0, "Exited (0)", ""),  # verify
        ]
    )
    ex = DockerExecutor(runner=runner)
    outcome = ex.stop("nimbusops-nginx-demo-abc12345", deployment_id="dep-1")
    assert outcome["status"] == "SUCCEEDED"
    assert outcome["result"]["container_state"] == "EXITED"


# ------------------------------------------------------------ HTTP probe


def test_http_probe_reports_ok(monkeypatch):
    from agent.nimbusops_agent import docker_exec

    class FakeResp:
        status_code = 200

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def get(self, url, **kwargs):
            return FakeResp()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(docker_exec.httpx, "Client", FakeClient)
    ex = DockerExecutor(runner=FakeRunner())
    ok = ex.probe_http(8080)
    assert ok is True


def test_http_probe_failure_is_false_not_error():
    ex = DockerExecutor(runner=FakeRunner())
    # Port 1 should be closed; probe must return False (explicit, no raise).
    ok = ex.probe_http(1, timeout=0.3)
    assert ok is False


# ------------------------------------------------- invalid command rejection


def test_unknown_template_rejected():
    ex = DockerExecutor(runner=FakeRunner())
    with pytest.raises(ManagedResourceError):
        ex.deploy({"key": "crypto-miner", "image": "bad/image"}, deployment_id="dep-9")


def test_unknown_op_type_rejected():
    ex = DockerExecutor(runner=FakeRunner())
    outcome = ex.execute(
        {"op_type": "EXEC", "template": NGINX_TEMPLATE, "deployment_id": "dep-1", "operation_id": "op-1"}
    )
    assert outcome["status"] == "FAILED"
    assert outcome["error_code"] == "UNAPPROVED_OPERATION"
