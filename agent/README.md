# NimbusOps agent

Host-side agent for NimbusOps: heartbeat, telemetry, Docker inventory, and
approved DEPLOY/START/STOP/RESTART operations.

Install from this directory:

```bash
python3 -m pip install .
```

Run with either entrypoint (identical code path):

```bash
python3 -m nimbusops_agent --help
nimbusops-agent --help
```

Enrollment uses exactly one credential: an operator-issued single-use bootstrap
token (preferred, `--bootstrap-token-file` or
`NIMBUSOPS_AGENT_BOOTSTRAP_TOKEN`), or the legacy shared token
(`NIMBUSOPS_AGENT_ENROLLMENT_TOKEN`) when the server runs
`NIMBUSOPS_ENROLLMENT_MODE=legacy`.
