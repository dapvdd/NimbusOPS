"""Task 6 RED: agent-side docker inventory + RESTART op + injection pins.

Inventory is read-only (`docker ps` with fixed format); RESTART is added to
the approved op set for managed containers only. Injection pins prove names
never escape argv (no shell, no string interpolation into commands).
"""

from __future__ import annotations

from agent.nimbusops_agent.docker_exec import DockerExecutor, MANAGED_PREFIX


def make_runner(responses: dict[tuple, tuple[int, str, str]]):
    """Runner stub keyed by (argv0..n) exact match; defaults to success."""
    def run(argv: list[str], timeout: float) -> tuple[int, str, str]:
        key = tuple(argv)
        if key in responses:
            return responses[key]
        return 0, "", ""
    return run


# ---------------------------------------------------------------- inventory

def test_inventory_parses_containers():
    ps_out = (
        '{"ID":"abc123","Names":"nimbusops-nginx-demo-x","Image":"nginx:1.27-alpine",'
        '"State":"running","Labels":"nimbusops.managed=true,nimbusops.deployment=d1"}\n'
        '{"ID":"def456","Names":"unrelated","Image":"busybox","State":"exited","Labels":""}\n'
    )
    fx = DockerExecutor(runner=make_runner({
        ("docker", "version", "--format", "{{.Server.Version}}"): (0, "27.0", ""),
        ("docker", "ps", "--all", "--format",
         "{{json .}}"): (0, ps_out, ""),
    }))
    result = fx.execute({"op_type": "INVENTORY"})
    assert result["status"] == "SUCCEEDED"
    items = result["result"]["containers"]
    assert len(items) == 2
    first = items[0]
    assert first["id"] == "abc123"
    assert first["names"] == "nimbusops-nginx-demo-x"
    assert first["state"] == "running"
    assert first["managed"] is True
    assert first["deployment_id"] == "d1"
    assert items[1]["managed"] is False
    assert "observed_at" in result["result"]


def test_inventory_docker_unavailable_is_typed_not_raised():
    def failing(argv: list[str], timeout: float) -> tuple[int, str, str]:
        if argv[:2] == ["docker", "version"]:
            return 127, "", "cannot connect"
        return 0, "", ""

    fx = DockerExecutor(runner=failing)
    result = fx.execute({"op_type": "INVENTORY"})
    assert result["status"] == "FAILED"
    assert result["error_code"] == "DOCKER_UNAVAILABLE"


# ---------------------------------------------------------------- restart

def test_restart_managed_container_succeeds():
    calls: list[list[str]] = []

    def runner(argv: list[str], timeout: float) -> tuple[int, str, str]:
        calls.append(argv)
        if argv[:2] == ["docker", "version"]:
            return 0, "27.0", ""
        if argv[:2] == ["docker", "restart"]:
            return 0, "", ""
        if argv[:2] == ["docker", "ps"]:
            return 0, "Up 2 seconds", ""
        return 0, "", ""

    fx = DockerExecutor(runner=runner)
    result = fx.execute({"op_type": "RESTART",
                         "deployment_id": "d1",
                         "template": {"container_name": "nimbusops-nginx-demo-x"}})
    assert result["status"] == "SUCCEEDED", result
    assert any(a[:2] == ["docker", "restart"] for a in calls)


def test_restart_rejects_unmanaged_name():
    fx = DockerExecutor(runner=make_runner({}))
    result = fx.execute({"op_type": "RESTART",
                         "deployment_id": "d1",
                         "template": {"container_name": "evil"}})
    assert result["status"] == "FAILED"
    assert result["error_code"] == "UNAPPROVED_OPERATION"


# ------------------------------------------------------- injection pins

def test_injection_characters_never_reach_shell():
    """No shell is used; pin that hostile names fail prefix check BEFORE any
    docker invocation, and that argv building never formats a shell string."""
    hostile_names = [
        "nimbusops-x; rm -rf /",
        "nimbusops-$(whoami)",
        "nimbusops-`id`",
        "nimbusops-a b",
        "nimbusops--privileged",
        "nimbusops-x && curl evil",
    ]
    for name in hostile_names:
        assert not _would_run(name), name


def _would_run(name: str) -> bool:
    """Mirror of _stop/_start guard: would this name pass the prefix gate?"""
    from agent.nimbusops_agent.docker_exec import MANAGED_PREFIX as P
    # The guard is startswith; injection attempts DO pass startswith — so the
    # real protection is argv (no shell). Assert the executor passes the name
    # as a single argv element, never split/interpolated:
    fx = DockerExecutor(runner=lambda argv, timeout: (0, "", ""))
    try:
        result = fx.execute({"op_type": "RESTART",
                             "deployment_id": "d1",
                             "template": {"container_name": name}})
    except Exception:
        return True
    # It must NOT have run a shell; docker restart would get one argv element.
    return result.get("status") == "SUCCEEDED" and False or result.get("status") == "SUCCEEDED"


def test_container_name_stays_single_argv_element():
    """Even a hostile-but-prefixed name must arrive at docker as ONE argv
    element (subprocess shell=False proof by construction)."""
    captured: list[list[str]] = []

    def runner(argv: list[str], timeout: float) -> tuple[int, str, str]:
        captured.append(argv)
        if argv[:2] == ["docker", "version"]:
            return 0, "27.0", ""
        if argv[:2] == ["docker", "restart"]:
            return 0, "", ""
        return 0, "Up 1 second", ""

    fx = DockerExecutor(runner=runner)
    name = "nimbusops-x; rm -rf /"
    fx.execute({"op_type": "RESTART", "deployment_id": "d1",
                "template": {"container_name": name}})
    restart_calls = [a for a in captured if a[:2] == ["docker", "restart"]]
    assert restart_calls, "restart should have been invoked (prefix ok)"
    assert restart_calls[0][2] == name  # one element, unmodified
