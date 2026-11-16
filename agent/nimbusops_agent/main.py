"""Agent main loop: enroll (once), then heartbeat + telemetry cycles.

Graceful shutdown on SIGINT/SIGTERM. No inbound ports. Normal mode executes
approved Docker operations; telemetry-only mode disables all Docker paths.
"""

from __future__ import annotations

import logging
import pathlib
import signal
import socket
import sys
import time

from . import __version__
from .client import AuthError, Sender
from .config import (
    DEFAULT_INTERVAL,
    DEFAULT_SERVER_URL,
    Config,
    ConfigError,
    collect_host_info,
    load_identity,
    save_identity,
    Identity,
)
from .telemetry import collect_telemetry, host_info_snapshot
from .worker import CommandWorker, SenderCommandAdapter

logger = logging.getLogger("nimbusops.agent")

_stop = {"requested": False}


def request_stop(_signum, _frame) -> None:
    _stop["requested"] = True


def install_signal_handlers() -> None:
    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)


def ensure_enrolled(cfg: Config) -> tuple[Identity, bool]:
    """Return (identity, created_now). Enrolls when no stored identity exists."""
    identity = load_identity(cfg.state_file)
    if identity is not None:
        return identity, False

    sender = Sender(
        server_url=cfg.server_url,
        host_id="pending-enrollment",
        agent_token=cfg.enrollment_token,
    )
    try:
        ok, result = sender.enroll(
            hostname=socket.gethostname(),
            enrollment_token=cfg.enrollment_token,
            bootstrap_token=cfg.bootstrap_token or None,
            info=collect_host_info(),
        )
    finally:
        sender.close()
    if not ok:
        raise RuntimeError(f"enrollment failed: {result}")
    identity = Identity(host_id=result["host_id"], agent_token=result["agent_token"])
    save_identity(cfg.state_file, identity)
    logger.info("enrolled as host_id=%s (identity saved to %s)", identity.host_id, cfg.state_file)
    return identity, True


def run_cycle(
    sender: Sender, worker: CommandWorker | None = None, *, telemetry_only: bool = False
) -> tuple[bool, str]:
    """One heartbeat + telemetry (+ command poll) cycle. Returns (ok, detail)."""
    info = host_info_snapshot()
    # Phase 5 (FR-03): attach a read-only docker inventory snapshot when Docker
    # is available; heartbeat stays inventory-less when it is not (additive).
    if not telemetry_only:
        try:
            from .docker_exec import DockerExecutor
            inv = DockerExecutor().inventory()
            if inv.get("status") == "SUCCEEDED":
                info["inventory"] = inv["result"]
        except Exception as exc:  # inventory never breaks the monitoring loop
            logger.debug("inventory unavailable: %s", exc)
    ok_hb, detail_hb = sender.send_heartbeat(info)
    telemetry = collect_telemetry()
    ok_t, detail_t = sender.send_telemetry(telemetry)

    detail = f"heartbeat: {detail_hb}; telemetry: {detail_t}"
    if worker is not None and not telemetry_only:
        try:
            outcome = worker.poll_once()
            detail += f"; commands: {outcome.value}"
        except AuthError:
            raise
        except Exception as exc:  # command failures never kill monitoring
            detail += f"; commands: {type(exc).__name__}: {exc}"
    return ok_hb and ok_t, detail


def run(cfg: Config) -> int:
    install_signal_handlers()
    try:
        identity, created = ensure_enrolled(cfg)
    except AuthError as exc:
        logger.error("enrollment rejected: %s", exc)
        return 2
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 2

    if created:
        pass  # Freshly enrolled; continue into main loop.

    sender = Sender(server_url=cfg.server_url, host_id=identity.host_id, agent_token=identity.agent_token)
    # Docker integration is optional: monitoring runs whether or not Docker works.
    worker = None
    if not cfg.telemetry_only:
        from .docker_exec import DockerExecutor

        worker = CommandWorker(http=SenderCommandAdapter(sender), executor=DockerExecutor())
    logger.info(
        "agent %s started: server=%s interval=%.1fs state=%s",
        __version__, cfg.server_url, cfg.interval, cfg.state_file,
    )
    exit_code = 0
    try:
        while not _stop["requested"]:
            started = time.monotonic()
            try:
                ok, detail = run_cycle(sender, worker, telemetry_only=cfg.telemetry_only)
                if not ok:
                    logger.warning("cycle incomplete: %s", detail)
            except AuthError as exc:
                logger.error("credentials rejected, stopping: %s", exc)
                exit_code = 3
                break
            if cfg.once:
                exit_code = 0 if ok else 1
                break
            elapsed = time.monotonic() - started
            wait = max(0.0, cfg.interval - elapsed)
            deadline = time.monotonic() + wait
            while not _stop["requested"] and time.monotonic() < deadline:
                time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
    finally:
        sender.close()
        logger.info("agent stopped (exit=%d)", exit_code)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="nimbusops-agent", description="NimbusOps host agent")
    parser.add_argument("--server-url", default=None, help="Control server base URL")
    parser.add_argument("--enrollment-token", default=None, help="Legacy shared token for initial enrollment")
    parser.add_argument(
        "--bootstrap-token-file",
        default=None,
        help="Path to a file containing a single-use bootstrap enrollment token (preferred)",
    )
    parser.add_argument("--interval", type=float, default=None, help="Sampling interval seconds")
    parser.add_argument("--state-file", default=None, help="Path for identity storage")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit (testing)")
    parser.add_argument("--telemetry-only", action="store_true", help="Disable Docker inventory and operation execution/polling")
    args = parser.parse_args(argv)

    import os

    # RC2 F01: the bootstrap token is a high-value single-use secret. Read it
    # from the environment or a file, never from argv (process arguments are
    # world-readable on common POSIX systems and appear in process listings).
    bootstrap_token = os.environ.get("NIMBUSOPS_AGENT_BOOTSTRAP_TOKEN", "").strip()
    if args.bootstrap_token_file:
        if bootstrap_token:
            print(
                "nimbusops-agent: invalid configuration: set only one of "
                "NIMBUSOPS_AGENT_BOOTSTRAP_TOKEN or --bootstrap-token-file",
                file=sys.stderr,
            )
            return 2
        try:
            bootstrap_token = pathlib.Path(args.bootstrap_token_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            print(
                f"nimbusops-agent: invalid configuration: cannot read bootstrap token file: {type(exc).__name__}",
                file=sys.stderr,
            )
            return 2
        if not bootstrap_token:
            print("nimbusops-agent: invalid configuration: bootstrap token file is empty", file=sys.stderr)
            return 2

    try:
        cfg = Config(
            server_url=args.server_url or os.environ.get("NIMBUSOPS_AGENT_SERVER_URL", DEFAULT_SERVER_URL),
            enrollment_token=args.enrollment_token or os.environ.get("NIMBUSOPS_AGENT_ENROLLMENT_TOKEN", ""),
            bootstrap_token=bootstrap_token,
            interval=float(args.interval or os.environ.get("NIMBUSOPS_AGENT_INTERVAL", DEFAULT_INTERVAL)),
            state_file=pathlib.Path(
                args.state_file or os.environ.get("NIMBUSOPS_AGENT_STATE_FILE", str(pathlib.Path.home() / ".nimbusops" / "agent.json"))
            ),
            once=args.once,
            telemetry_only=args.telemetry_only,
        )
    except ConfigError as exc:
        print(f"nimbusops-agent: invalid configuration: {exc}", file=sys.stderr)
        return 2
    return run(cfg)


if __name__ == "__main__":
    sys.exit(main())
