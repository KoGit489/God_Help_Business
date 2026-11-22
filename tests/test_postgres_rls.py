import os
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.rls import assert_postgres_rls, set_user_id


DATABASE_URL = os.getenv("TEST_POSTGRES_RLS_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Set TEST_POSTGRES_RLS_URL to a disposable PostgreSQL database")


@pytest.fixture
def rls_database():
    role = f"casai_rls_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
        admin.execute("DROP SCHEMA IF EXISTS casai_security CASCADE")
        admin.execute("DROP TABLE IF EXISTS annotations, pins, share_links, projects CASCADE")
        admin.execute("CREATE TABLE projects (id text PRIMARY KEY, owner_id text NOT NULL)")
        admin.execute("CREATE TABLE pins (id text PRIMARY KEY, project_id text NOT NULL)")
        admin.execute("CREATE TABLE annotations (id text PRIMARY KEY, project_id text NOT NULL)")
        admin.execute("CREATE TABLE share_links (token text PRIMARY KEY, project_id text NOT NULL, revoked_at timestamptz, expires_at timestamptz NOT NULL)")
        admin.execute("INSERT INTO projects VALUES ('project-a', 'owner-a'), ('project-b', 'owner-b')")
        admin.execute("INSERT INTO pins VALUES ('pin-a', 'project-a'), ('pin-b', 'project-b')")
        admin.execute("INSERT INTO annotations VALUES ('note-a', 'project-a'), ('note-b', 'project-b')")
        admin.execute("INSERT INTO share_links VALUES ('share-a', 'project-a', NULL, now() + interval '1 day')")
        admin.execute("INSERT INTO share_links VALUES ('share-expired', 'project-b', NULL, now() - interval '1 day')")
        admin.execute(Path(__file__).resolve().parents[1].joinpath("deploy", "project-rls.sql").read_text(encoding="utf-8"))
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
        admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public, casai_security TO {}").format(sql.Identifier(role)))
        admin.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON projects, pins, annotations, share_links TO {}").format(sql.Identifier(role)))
        admin.execute(sql.SQL("GRANT EXECUTE ON FUNCTION casai_security.can_read_shared_project(text, text) TO {}").format(sql.Identifier(role)))
    try:
        yield role
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
            admin.execute("DROP SCHEMA IF EXISTS casai_security CASCADE")
            admin.execute("DROP TABLE IF EXISTS annotations, pins, share_links, projects CASCADE")


def test_postgres_rls_enforces_tenant_writes_and_scoped_public_shares(rls_database) -> None:
    role = rls_database
    sqlalchemy_url = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(sqlalchemy_url, connect_args={"client_encoding": "utf8"})
    with engine.connect() as admin:
        admin.execute(text(f'SET ROLE "{role}"'))
        assert_postgres_rls(admin)
        admin.rollback()
    engine.dispose()

    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("SET client_encoding TO 'UTF8'")
        connection.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
        connection.execute("SELECT set_config('casai.user_id', 'owner-a', true)")
        assert connection.execute("SELECT id FROM projects ORDER BY id").fetchall() == [("project-a",)]
        assert connection.execute("SELECT id FROM pins ORDER BY id").fetchall() == [("pin-a",)]
        assert connection.execute("UPDATE projects SET owner_id = 'owner-a' WHERE id = 'project-b' RETURNING id").fetchall() == []
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("INSERT INTO pins VALUES ('forged-pin', 'project-b')")
        connection.rollback()

    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("SET client_encoding TO 'UTF8'")
        connection.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
        connection.execute("SELECT set_config('casai.share_token', 'share-a', true)")
        assert connection.execute("SELECT id FROM projects ORDER BY id").fetchall() == [("project-a",)]
        assert connection.execute("SELECT id FROM pins ORDER BY id").fetchall() == [("pin-a",)]
        assert connection.execute("SELECT token FROM share_links").fetchall() == [("share-a",)]

    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("SET client_encoding TO 'UTF8'")
        connection.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
        connection.execute("SELECT set_config('casai.share_token', 'share-expired', true)")
        assert connection.execute("SELECT id FROM projects").fetchall() == []

    app_engine = create_engine(sqlalchemy_url, connect_args={"client_encoding": "utf8"})
    set_user_id("owner-b")
    with Session(app_engine) as session:
        session.execute(text(f'SET LOCAL ROLE "{role}"'))
        assert session.execute(text("SELECT id FROM projects ORDER BY id")).scalars().all() == ["project-b"]
    set_user_id(None)
    app_engine.dispose()


def test_rls_readiness_rejects_truncate_and_extra_permissive_policy(rls_database) -> None:
    role = rls_database
    sqlalchemy_url = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(sqlalchemy_url, connect_args={"client_encoding": "utf8"})
    with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
        admin.execute(sql.SQL("GRANT TRUNCATE ON projects TO {}").format(sql.Identifier(role)))
    with engine.connect() as connection:
        connection.execute(text(f'SET ROLE "{role}"'))
        with pytest.raises(RuntimeError, match="truncate"):
            assert_postgres_rls(connection)
    with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
        admin.execute(sql.SQL("REVOKE TRUNCATE ON projects FROM {}").format(sql.Identifier(role)))
        admin.execute("CREATE POLICY overly_broad ON projects FOR SELECT USING (true)")
    with engine.connect() as connection:
        connection.execute(text(f'SET ROLE "{role}"'))
        with pytest.raises(RuntimeError, match="only the expected"):
            assert_postgres_rls(connection)
    engine.dispose()


def test_account_deletion_cannot_orphan_projects_under_rls(monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker

    from app import main
    from app.models import Base, ProjectRecord, UserRecord

    role = f"casai_account_{uuid.uuid4().hex[:12]}"
    sqlalchemy_url = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    admin_engine = create_engine(sqlalchemy_url, connect_args={"client_encoding": "utf8"})
    Base.metadata.create_all(admin_engine)
    try:
        with Session(admin_engine) as db:
            db.add(UserRecord(id="rls-owner", email="rls-owner@example.com", name="Owner", password_hash=main.password_hasher.hash("secure account deletion password"), is_admin=False, is_active=True))
            db.add(ProjectRecord(id="owned-project", owner_id="rls-owner", title="Owned", status="draft"))
            db.commit()
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute(Path(__file__).resolve().parents[1].joinpath("deploy", "project-rls.sql").read_text(encoding="utf-8"))
            admin.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public, casai_security TO {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("GRANT EXECUTE ON FUNCTION casai_security.can_read_shared_project(text, text) TO {}").format(sql.Identifier(role)))
        runtime_engine = create_engine(make_url(sqlalchemy_url).set(username=role), connect_args={"client_encoding": "utf8"})
        monkeypatch.setattr(main, "PERSISTENCE_MODE", "database")
        monkeypatch.setattr(main, "AUTH_REQUIRED", True)
        monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
        monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=runtime_engine))
        test_client = TestClient(main.app)
        headers = {"Origin": "http://localhost:8000"}
        assert test_client.post("/auth/login", headers=headers, json={"email": "rls-owner@example.com", "password": "secure account deletion password"}).status_code == 200
        response = test_client.request("DELETE", "/auth/me", headers=headers, json={"password": "secure account deletion password"})
        assert response.status_code == 409
        assert "owns projects" in response.json()["error"]["message"]
        runtime_engine.dispose()
    finally:
        admin_engine.dispose()
        with psycopg.connect(DATABASE_URL, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
            admin.execute("DROP SCHEMA IF EXISTS casai_security CASCADE")
            admin.execute("DROP TABLE IF EXISTS analytics_daily, mfa_recovery_codes, mfa_credentials, email_verifications, password_resets, user_sessions, annotations, pins, share_links, projects, users CASCADE")