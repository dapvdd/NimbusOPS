"""Deployment resource isolation: fixed argv, hard limits, private binding.

These tests pin the *observable* docker run invocation, not source text. The
fake runner records argv exactly as the executor would pass it to
``subprocess.run(shell=False)``.
"""

from __future__ import annotations

from agent.nimbusops_agent.docker_exec import DockerExecutor

TEMPLATE = {
    "key": "nginx-demo",
    "image": "nginx:1.27-alpine",
    "container_port": 80,
    "host_port": 18080,
    "container_name": "nimbusops-nginx-demo-abc12345",
}


def _run_argv(host_port: int = 18080) -> list[str]:
    calls: list[list[str]] = []

    def runner(argv: list[str], timeout: float) -> tuple[int, str, str]:
        calls.append(list(argv))
        if argv[:2] == ["docker", "version"]:
            return 0, "27.0.0", ""
        if argv[:2] == ["docker", "inspect"]:
            return 1, "", "Error: No such object: " + argv[-1]
        if argv[:2] == ["docker", "ps"]:
            return 0, "Up 2 seconds", ""
        return 0, "", ""

    template = dict(TEMPLATE, host_port=host_port)
    outcome = DockerExecutor(runner=runner).deploy(template, deployment_id="dep-1")
    assert outcome["status"] == "SUCCEEDED", outcome
    return next(argv for argv in calls if argv[:2] == ["docker", "run"])


def test_deploy_run_argv_pins_exact_resource_limits():
    """A run must carry the approved CPU/mem/pid ceilings as fixed argv."""
    argv = _run_argv()
    assert "--cpus=0.25" in argv
    assert "--memory=128m" in argv
    assert "--memory-swap=128m" in argv
    assert "--pids-limit=64" in argv


def test_deploy_run_argv_publishes_only_on_loopback():
    """The published port must never be reachable from a non-loopback IP."""
    argv = _run_argv()
    assert "-p" in argv
    assert argv[argv.index("-p") + 1] == "127.0.0.1:18080:80"


def test_deploy_run_argv_uses_template_port_with_loopback_prefix():
    """Loopback binding is a prefix rule, not a hardcoded 18080."""
    argv = _run_argv(host_port=19090)
    assert argv[argv.index("-p") + 1] == "127.0.0.1:19090:80"


def test_deploy_run_argv_restart_policy_and_no_escape_hatches():
    """No restart daemon, privileged mode, host network, or host mounts."""
    argv = _run_argv()
    assert "--restart" in argv and argv[argv.index("--restart") + 1] == "no"
    assert not any(a.startswith("--privileged") for a in argv)
    assert "--network" not in argv and "--net" not in argv
    assert "-v" not in argv and "--mount" not in argv
    assert "--cpus=0.25" in argv  # limits must accompany the port publish
