import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from app.models import Base


ADMIN_URL = os.getenv("TEST_STAGING_CHECKER_ADMIN_URL")
TEST_CA = os.getenv("TEST_STAGING_CHECKER_CA")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def checker_database():
    if not ADMIN_URL or not TEST_CA:
        pytest.skip("Requires a disposable PostgreSQL admin URL and TLS CA")
    suffix = uuid.uuid4().hex[:12]
    database = f"checker_{suffix}"
    role = f"checker_{suffix}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD 'test-only-password'").format(sql.Identifier(role)))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    admin_url = make_url(ADMIN_URL).set(database=database)
    engine = create_engine(admin_url.set(drivername="postgresql+psycopg"))
    try:
        Base.metadata.create_all(engine)
        with psycopg.connect(admin_url.render_as_string(hide_password=False), autocommit=True) as admin:
            admin.execute((ROOT / "deploy" / "project-rls.sql").read_text(encoding="utf-8"))
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public, casai_security TO {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("GRANT EXECUTE ON FUNCTION casai_security.can_read_shared_project(text, text) TO {}").format(sql.Identifier(role)))
        yield admin_url, role
    finally:
        engine.dispose()
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


@pytest.mark.parametrize("staging_url,live_url", [
    ("not-a-url", "postgresql://live:secret@production.invalid/live"),
    ("postgresql://user:secret@production.invalid/live", "postgresql://live:secret@production.invalid/live"),
    ("postgresql://wrong:secret@rls-backup-do-user-45793368-0.f.db.ondigitalocean.com/db", "postgresql://live:secret@production.invalid/live"),
    ("postgresql://casai_staging_runtime:secret@rls-backup-do-user-45793368-0.f.db.ondigitalocean.com/db?host=production.invalid", "postgresql://live:secret@production.invalid/live"),
    ("postgresql://casai_staging_runtime:secret@rls-backup-do-user-45793368-0.f.db.ondigitalocean.com/db", "postgresql://live:secret@rls-backup-do-user-45793368-0.f.db.ondigitalocean.com/db"),
    ("postgresql://casai_staging_runtime:secret@rls-backup-do-user-45793368-0.f.db.ondigitalocean.com/db", "not-a-url"),
])
def test_checker_rejects_unsafe_targets(staging_url, live_url, tmp_path):
    ca_file = tmp_path / "ca.crt"
    ca_file.write_text("test only", encoding="utf-8")
    environment = os.environ.copy()
    environment.update({"STAGING_DATABASE_URL": staging_url, "DATABASE_URL": live_url, "CHECKER_TEST_CA": str(ca_file)})
    script = """
import os
import socket
from tools import run_staging_rls_app_check as checker
checker.STAGING_CA = os.environ['CHECKER_TEST_CA']
def deny_connect(*args, **kwargs):
    raise AssertionError('preflight attempted a network connection')
socket.socket.connect = deny_connect
raise SystemExit(checker.main())
"""
    completed = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=environment, capture_output=True, text=True, timeout=15)
    assert completed.returncode == 2
    assert "preflight failed" in completed.stdout
    assert "secret" not in completed.stdout + completed.stderr


def test_checker_refuses_noninteractive_prompt():
    environment = os.environ.copy()
    environment.pop("STAGING_DATABASE_URL", None)
    completed = subprocess.run([sys.executable, str(ROOT / "tools" / "run_staging_rls_app_check.py")], cwd=ROOT, env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
    assert completed.returncode == 2
    assert "terminal is required" in completed.stdout


@pytest.mark.parametrize("mode", ["success", "fail_pin", "not_ready", "cleanup_failure"])
def test_checker_isolated_workflow_and_cleanup(checker_database, mode):
    admin_url, role = checker_database
    if mode in {"not_ready", "cleanup_failure"}:
        with psycopg.connect(admin_url.render_as_string(hide_password=False), autocommit=True) as admin:
            if mode == "not_ready":
                admin.execute("CREATE POLICY checker_unexpected ON projects FOR SELECT USING (true)")
            else:
                admin.execute(sql.SQL("REVOKE DELETE ON projects FROM {}").format(sql.Identifier(role)))
    runtime_url = admin_url.set(username=role, password="test-only-password")
    environment = os.environ.copy()
    environment.update({
        "DATABASE_URL": "postgresql://live:secret@production.invalid/live",
        "STAGING_DATABASE_URL": runtime_url.render_as_string(hide_password=False),
        "CHECKER_TEST_HOST": runtime_url.host,
        "CHECKER_TEST_USER": role,
        "CHECKER_TEST_CA": TEST_CA,
        "CHECKER_TEST_FAIL_PIN": str(int(mode == "fail_pin")),
        "APP_DOMAIN": "casaifield.com",
        "CORS_ALLOWED_ORIGINS": "https://casaifield.com",
        "RATE_LIMIT_STORAGE_URI": "redis://127.0.0.1:1",
        "SENTRY_DSN": "https://example@127.0.0.1/1",
        "EMAIL_VERIFICATION_REQUIRED": "true",
        "BOOTSTRAP_ADMIN_EMAIL": "unwanted@staging.invalid",
        "BOOTSTRAP_ADMIN_PASSWORD": "this-must-not-be-used",
        "STORAGE_BACKEND": "s3",
    })
    script = """
import os
from tools import run_staging_rls_app_check as checker
checker.STAGING_HOST = os.environ['CHECKER_TEST_HOST']
checker.STAGING_USER = os.environ['CHECKER_TEST_USER']
checker.STAGING_CA = os.environ['CHECKER_TEST_CA']
if os.environ['CHECKER_TEST_FAIL_PIN'] == '1':
    from fastapi.testclient import TestClient
    original_post = TestClient.post
    def reject_pin(self, url, **kwargs):
        if url.endswith('/pins'):
            kwargs['headers'] = {'Origin': 'http://rejected.invalid'}
        return original_post(self, url, **kwargs)
    TestClient.post = reject_pin
raise SystemExit(checker.main())
"""
    completed = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=environment, capture_output=True, text=True, timeout=90)
    assert completed.returncode == int(mode != "success"), completed.stdout + completed.stderr
    if mode == "fail_pin":
        assert "pin creation failed: 403" in completed.stdout
    elif mode == "success":
        assert "Staging app RLS check passed" in completed.stdout
    elif mode == "not_ready":
        assert "Staging app RLS check failed" in completed.stdout
    else:
        assert "Cleanup failed; temporary user IDs:" in completed.stdout
    with psycopg.connect(admin_url.render_as_string(hide_password=False)) as admin:
        for table in ("users", "projects", "pins", "annotations", "share_links", "user_sessions"):
            count = admin.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0]
            if mode == "cleanup_failure" and table in {"users", "projects"}:
                assert count > 0
            elif mode != "cleanup_failure":
                assert count == 0