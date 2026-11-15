"""Package entrypoint: ``python -m nimbusops_agent``.

RC2 F09: the release runbook documented this invocation, but no tracked
``__main__`` module existed, so a clean host could not start the agent the way
the runbook said.
"""

from __future__ import annotations

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
