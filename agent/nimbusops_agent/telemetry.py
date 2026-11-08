"""Real telemetry collection via psutil. No simulated values."""

from __future__ import annotations

import platform
from datetime import datetime, timezone

import psutil

from . import __version__


def collect_telemetry() -> dict:
    """Collect genuine CPU/RAM/disk metrics of the local host.

    - cpu_percent uses a real sampling window (interval=0.2s) for a
      meaningful reading rather than a since-boot average.
    - Percentages are floats in [0, 100].
    - Timestamps are UTC.
    """
    cpu_percent = psutil.cpu_percent(interval=0.2)
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    boot = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    now = datetime.now(timezone.utc)

    memory_used = vm.total - vm.available
    disk_used = du.used

    return {
        "recorded_at": now,
        "cpu_percent": float(cpu_percent),
        "memory_used_bytes": int(memory_used),
        "memory_total_bytes": int(vm.total),
        "disk_used_bytes": int(disk_used),
        "disk_total_bytes": int(du.total),
        "memory_used_percent": float(vm.percent),
        "disk_used_percent": float(du.percent),
        "_boot_time": boot,
    }


def host_info_snapshot() -> dict:
    """Host metadata reported with heartbeat/enrollment."""
    vm = psutil.virtual_memory()
    return {
        "agent_version": __version__,
        "platform": platform.system(),
        "platform_release": platform.release(),
        "cpu_cores": psutil.cpu_count(logical=True),
        "total_memory_bytes": int(vm.total),
    }
