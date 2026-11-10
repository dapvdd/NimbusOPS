"""Tests for the create_operator CLI script (Task 2 Step 4)."""

import pytest

from backend.scripts.create_operator import create_operator


def test_create_operator_inserts_hashed_admin(client, db_session):
    op_id = create_operator("cli-admin", "a-long-secret-password-123", "ADMIN")
    from sqlalchemy import select

    from backend.app.models import Operator

    op = db_session.scalar(select(Operator).where(Operator.username == "cli-admin"))
    assert op is not None
    assert op.id == op_id
    assert op.role == "ADMIN"
    assert op.password_hash.startswith("pbkdf2$")
    assert "a-long-secret-password-123" not in op.password_hash


def test_create_operator_rejects_duplicate_username(client, db_session):
    create_operator("dup", "a-long-secret-password-123", "VIEWER")
    with pytest.raises(SystemExit):
        create_operator("dup", "another-long-secret-password", "VIEWER")


def test_create_operator_rejects_bad_role(client, db_session):
    with pytest.raises(ValueError):
        create_operator("badrole", "a-long-secret-password-123", "SUPERUSER")
