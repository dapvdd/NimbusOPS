"""Explicit local-only classroom setup; never accepts a password in argv."""
import argparse
import getpass

from sqlalchemy import select
from backend.app.core.db import session_scope
from backend.app.models import Operator
from backend.scripts.create_operator import create_operator


def create_viewer(password: str) -> str:
    if not 8 <= len(password) <= 128:
        raise ValueError('classroom password must be 8-128 characters')
    with session_scope() as db:
        if db.scalar(select(Operator).where(Operator.role == 'ADMIN')) is None:
            raise ValueError('create the ADMIN first')
    return create_operator('viewer', password, 'VIEWER')


def main() -> None:
    parser = argparse.ArgumentParser(description='Create the single read-only classroom viewer in the explicitly selected private database.')
    parser.add_argument('--classroom-only', required=True, action='store_true')
    parser.parse_args()
    password = getpass.getpass('Classroom viewer password: ')
    if password != getpass.getpass('Confirm password: '):
        raise SystemExit('passwords do not match')
    create_viewer(password)
    print('Created classroom VIEWER; password not displayed.')


if __name__ == '__main__':
    main()
