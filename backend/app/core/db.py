"""SQLAlchemy engine/session wiring and table creation."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import get_settings


def _database_url() -> str:
    url = get_settings().database_url
    if url.startswith("sqlite:///./"):
        # Resolve relative SQLite paths against backend/ regardless of cwd.
        from pathlib import Path

        backend_dir = Path(__file__).resolve().parents[2]
        return f"sqlite:///{(backend_dir / url.removeprefix('sqlite:///./')).as_posix()}"
    return url


engine: Engine = create_engine(
    _database_url(),
    connect_args={"check_same_thread": False} if _database_url().startswith("sqlite") else {},
)

# Enforce FK integrity (off by default in SQLite) and a sane busy timeout.
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_all() -> None:
    from ..models import Base  # noqa: F401  (import registers mappers)

    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """CLI/script session with commit/rollback semantics."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
