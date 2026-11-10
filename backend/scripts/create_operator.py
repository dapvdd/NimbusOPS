"""Create the first ADMIN operator (out-of-band, never via the unauthenticated API).

Usage (from the repository root):
    backend\\.venv\\Scripts\\python -m backend.scripts.create_operator --username admin

The script prompts for the password (hidden input), hashes it with PBKDF2-SHA256
(240k iterations, core.security), and inserts the operator row. Idempotent per
username: an existing username is rejected with a non-zero exit.

Phase 3B Task 2 (docs/PHASE3B_IMPLEMENTATION_PLAN.md Step 4): the bootstrap
ADMIN is created by an operator with shell access to the server, not over HTTP.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.core.db import session_scope
from backend.app.core.security import hash_operator_password
from backend.app.models import Operator


def create_operator(username: str, password: str, role: str = "ADMIN") -> str:
    """Insert an operator row; returns the operator id. Raises on duplicates."""
    if role not in ("ADMIN", "VIEWER"):
        raise ValueError(f"invalid role {role!r}: must be ADMIN or VIEWER")
    with session_scope() as db:
        existing = db.scalar(select(Operator).where(Operator.username == username))
        if existing is not None:
            raise SystemExit(f"operator {username!r} already exists (id={existing.id})")
        op = Operator(
            username=username,
            password_hash=hash_operator_password(password),
            role=role,
        )
        db.add(op)
        db.flush()
        return op.id


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a NimbusOps operator account.")
    parser.add_argument("--username", required=True, help="operator username (1-64 chars)")
    parser.add_argument("--role", default="ADMIN", choices=["ADMIN", "VIEWER"])
    args = parser.parse_args()

    if not (1 <= len(args.username) <= 64):
        print("error: username must be 1-64 characters", file=sys.stderr)
        return 2

    password = getpass.getpass("password: ")
    confirm = getpass.getpass("confirm password: ")
    if password != confirm:
        print("error: passwords do not match", file=sys.stderr)
        return 2
    if len(password) < 12:
        print("error: password must be at least 12 characters", file=sys.stderr)
        return 2

    # Ensure settings are loaded (same env resolution as the server).
    get_settings()
    operator_id = create_operator(args.username, password, args.role)
    print(f"created {args.role} operator {args.username!r} (id={operator_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
