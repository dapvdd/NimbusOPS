"""Single source of truth for the server version/build identity.

RC2 F15: the health payload previously reported a fixed literal, so a running
server could not be traced to a release artifact. ``VERSION`` is the release
identity and ``build_id()`` is the immutable build marker injected at deploy
time (``NIMBUSOPS_BUILD_SHA``); "unknown" is reported honestly when the
deployment did not supply one.
"""

from __future__ import annotations

import os

VERSION = "1.0.0-rc2"


def build_id() -> str:
    """Immutable build identifier for this server process (never fabricated)."""
    return os.environ.get("NIMBUSOPS_BUILD_SHA", "unknown").strip() or "unknown"
