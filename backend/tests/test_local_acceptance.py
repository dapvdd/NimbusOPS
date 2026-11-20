"""Local acceptance only: separate processes and synthetic SQLite preservation."""

import multiprocessing
import sqlite3


def _claim_contender(url, start, queue):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.app.provisioning.worker import claim_job

    engine = create_engine(url, connect_args={"timeout": 15})
    try:
        assert start.wait(timeout=30)
        with Session(engine) as db:
            queue.put(claim_job(db))
    finally:
        engine.dispose()


def test_overlapping_processes_admit_one_job_once(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.app.models import Base, Operator
    from backend.app.provisioning.ssh import Target
    from backend.app.services.provisioning import save_plan, confirm_plan

    url = f"sqlite:///{(tmp_path / 'claims.db').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        actor = Operator(
            username="synthetic-admin", password_hash="unused", role="ADMIN"
        )
        db.add(actor)
        db.commit()
        target = Target(
            "synthetic",
            "192.0.2.10",
            "installer",
            "synthetic-vm",
            "/run/key",
            "/etc/known",
            "a" * 32,
        )
        plan = save_plan(db, actor.id, target, {"hostname": target.hostname})
        job_id = confirm_plan(db, actor.id, target, plan.id, plan.plan_hash).id
    engine.dispose()
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    queue = context.Queue()
    children = [
        context.Process(target=_claim_contender, args=(url, start, queue))
        for _ in range(4)
    ]
    try:
        for child in children:
            child.start()
        start.set()
        results = [queue.get(timeout=45) for _ in children]
        for child in children:
            child.join(timeout=30)
            assert child.exitcode == 0
        assert results.count(job_id) == 1
        assert results.count(None) == 3
        with sqlite3.connect(tmp_path / "claims.db") as db:
            assert db.execute(
                "SELECT state, reconciliation_required FROM provisioning_jobs"
            ).fetchall() == [("RUNNING", 1)]
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join()
        queue.close()


def _lock_contender(database, queue):
    from backend.app.provisioning.worker import worker_lock

    with worker_lock(database) as acquired:
        queue.put(acquired)


def test_worker_lock_excludes_an_independent_process_and_recovers(tmp_path):
    from backend.app.provisioning.worker import worker_lock

    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    database = str(tmp_path / "isolated.db")
    with worker_lock(database) as acquired:
        assert acquired
        child = context.Process(target=_lock_contender, args=(database, queue))
        child.start()
        try:
            assert queue.get(timeout=30) is False
            child.join(timeout=30)
            assert child.exitcode == 0
        finally:
            if child.is_alive():
                child.terminate()
                child.join()
    child = context.Process(target=_lock_contender, args=(database, queue))
    child.start()
    try:
        assert queue.get(timeout=30) is True
        child.join(timeout=30)
        assert child.exitcode == 0
    finally:
        if child.is_alive():
            child.terminate()
            child.join()
        queue.close()


def test_synthetic_online_backup_migration_preserves_identity_and_telemetry(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.app.models import Base, Host, Telemetry
    from backend.app.core.migrations import upgrade_phase3b
    from datetime import datetime, timezone

    source = tmp_path / "synthetic.db"
    copy = tmp_path / "rehearsal.db"
    engine = create_engine(f"sqlite:///{source.as_posix()}")
    Base.metadata.create_all(engine)
    stamp = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(
            Host(
                id="synthetic-preserved-id",
                hostname="synthetic-only",
                agent_token_hash="a" * 64,
                enrolled_at=stamp,
                enrollment_status="ENROLLED",
                credential_version=7,
                docker_enabled=False,
                is_revoked=False,
            )
        )
        db.commit()
        db.add(
            Telemetry(
                host_id="synthetic-preserved-id",
                recorded_at=stamp,
                cpu_percent=1,
                memory_used_bytes=1,
                memory_total_bytes=2,
                disk_used_bytes=1,
                disk_total_bytes=2,
                memory_used_percent=50,
                disk_used_percent=50,
            )
        )
        db.commit()
    engine.dispose()
    with sqlite3.connect(source) as original, sqlite3.connect(copy) as rehearsal:
        original.backup(rehearsal)
        before = {
            table: original.execute(f"SELECT * FROM {table}").fetchall()
            for table in ("hosts", "telemetry")
        }
    url = f"sqlite:///{copy.as_posix()}"
    upgrade_phase3b(url)
    with sqlite3.connect(copy) as db:
        schema = db.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    upgrade_phase3b(url)
    with sqlite3.connect(copy) as db:
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            db.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
            == schema
        )
        for table, rows in before.items():
            assert db.execute(f"SELECT * FROM {table}").fetchall() == rows
        assert db.execute(
            "SELECT id, credential_version, docker_enabled FROM hosts"
        ).fetchall() == [("synthetic-preserved-id", 7, 0)]
