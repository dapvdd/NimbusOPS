import pytest
from sqlalchemy import select
from backend.app.models import Operator
from backend.scripts.create_operator import create_operator


def test_classroom_viewer_requires_explicit_local_setup(client, db_session):
    from backend.scripts.create_classroom_viewer import create_viewer
    with pytest.raises(ValueError, match='ADMIN'):
        create_viewer('example-short')
    create_operator('setup-admin', 'test-admin-password')
    create_viewer('example-short')
    viewer=db_session.scalar(select(Operator).where(Operator.username=='viewer'))
    assert viewer.role=='VIEWER'
    assert viewer.password_hash.startswith('$argon2id$')
    with pytest.raises(SystemExit):
        create_viewer('different-password')
