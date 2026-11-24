from __future__ import annotations

import getpass
import os
import secrets
import sys
import tempfile
import uuid
import warnings
from pathlib import Path


STAGING_HOST = "rls-backup-do-user-45793368-0.f.db.ondigitalocean.com"
STAGING_USER = "casai_staging_runtime"
STAGING_CA = "/tmp/casai-staging-ca.crt"


class CheckFailure(Exception):
    pass


repository_root = Path(__file__).resolve().parent.parent
for import_root in (repository_root, Path("/app")):
    if import_root.is_dir() and str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))


def main() -> int:
    database_url = os.getenv("STAGING_DATABASE_URL", "").strip()
    if not database_url:
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            print("A terminal is required for the hidden staging database prompt.")
            return 2
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                database_url = getpass.getpass("Staging runtime database connection string: ")
        except (getpass.GetPassWarning, EOFError):
            print("Unable to read the staging database connection string privately.")
            return 2
    if not database_url:
        print("Staging database connection string is required.")
        return 2

    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ArgumentError

    try:
        staging_url = make_url(database_url)
        live_url = make_url(os.environ["DATABASE_URL"])
        if (
            staging_url.drivername not in {"postgresql", "postgresql+psycopg"}
            or staging_url.host != STAGING_HOST
            or staging_url.username != STAGING_USER
            or not staging_url.database
            or not staging_url.password
            or set(staging_url.query) - {"sslmode", "sslrootcert"}
            or not live_url.host
            or live_url.host.lower() == STAGING_HOST.lower()
            or not Path(STAGING_CA).is_file()
        ):
            raise ValueError("unsafe target")
    except (ArgumentError, KeyError, ValueError, TypeError):
        print("Staging target preflight failed. Check the staging host, runtime user, CA certificate, and separate live DATABASE_URL.")
        return 2
    staging_url = staging_url.set(drivername="postgresql+psycopg", query={"sslmode": "verify-full", "sslrootcert": STAGING_CA})
    database_url = staging_url.render_as_string(hide_password=False)

    system_environment = {key: value for key, value in os.environ.items() if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "LD_LIBRARY_PATH"}}
    os.environ.clear()
    os.environ.update(system_environment)
    os.environ["APP_PERSISTENCE"] = "database"
    os.environ["DATABASE_URL"] = database_url
    os.environ["DATABASE_REQUIRE_RLS"] = "true"
    os.environ["APP_ENV"] = "development"
    os.environ["AUTH_REQUIRED"] = "true"
    os.environ["SESSION_COOKIE_SECURE"] = "false"
    os.environ["ALLOW_ACCOUNT_REGISTRATION"] = "false"
    os.environ["SEED_DEMO_DATA"] = "false"
    os.environ["STORAGE_BACKEND"] = "local"
    os.environ["CORS_ALLOWED_ORIGINS"] = "http://127.0.0.1"

    temp_dir = tempfile.TemporaryDirectory(prefix="casai-staging-rls-")
    os.environ["UPLOAD_DIR"] = temp_dir.name

    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app import main as app_main
    from app.models import AuthSessionRecord, EmailVerificationRecord, MfaCredentialRecord, MfaRecoveryCodeRecord, PasswordResetRecord, UserRecord
    from app.rls import assert_postgres_rls, set_share_token, set_user_id

    owner_a = f"staging-owner-a-{uuid.uuid4().hex}"
    owner_b = f"staging-owner-b-{uuid.uuid4().hex}"
    email_a = f"{owner_a}@staging.invalid"
    email_b = f"{owner_b}@staging.invalid"
    password_a = secrets.token_urlsafe(24)
    password_b = secrets.token_urlsafe(24)

    project_id = ""
    pin_id = ""
    share_token = ""
    users_created = False
    result = 1

    try:
        with app_main.engine.connect() as connection:
            assert_postgres_rls(connection)
        with app_main.SessionLocal() as db:
            db.execute(text("SELECT set_config(:setting, :value, false)"), {"setting": "casai.user_id", "value": ""})
            db.execute(text("SELECT set_config(:setting, :value, false)"), {"setting": "casai.share_token", "value": ""})
            db.add_all([
                UserRecord(id=owner_a, email=email_a, name="Staging Owner A", password_hash=app_main.password_hasher.hash(password_a), is_admin=False, is_active=True, email_verified=True),
                UserRecord(id=owner_b, email=email_b, name="Staging Owner B", password_hash=app_main.password_hasher.hash(password_b), is_admin=False, is_active=True, email_verified=True),
            ])
            db.flush()
            users_created = True
            db.commit()

        origin = {"Origin": "http://127.0.0.1"}
        with TestClient(app_main.app) as client:
            login_a = client.post("/auth/login", headers=origin, json={"email": email_a, "password": password_a})
            if login_a.status_code != 200:
                raise CheckFailure(f"Owner A login failed: {login_a.status_code}")

            created = client.post("/projects", headers=origin, json={"title": "Staging RLS project", "description": "Temporary isolation test"})
            if created.status_code != 201:
                raise CheckFailure(f"Owner A project creation failed: {created.status_code}")
            project_id = created.json()["id"]

            pin = client.post(
                f"/projects/{project_id}/pins",
                headers=origin,
                json={"latitude": 0, "longitude": 0, "heading": 0, "captured_on": "2026-01-01"},
            )
            if pin.status_code != 201:
                raise CheckFailure(f"Owner A pin creation failed: {pin.status_code}")
            pin_id = pin.json()["id"]

            link = client.post(f"/projects/{project_id}/share-link", headers=origin, json={"expires_in_days": 1})
            if link.status_code != 200:
                raise CheckFailure(f"Owner A share link failed: {link.status_code}")
            share_token = link.json()["share_token"]

            client.post("/auth/logout", headers=origin)
            login_b = client.post("/auth/login", headers=origin, json={"email": email_b, "password": password_b})
            if login_b.status_code != 200:
                raise CheckFailure(f"Owner B login failed: {login_b.status_code}")

            forbidden = (
                client.get(f"/projects/{project_id}", headers=origin).status_code,
                client.get(f"/projects/{project_id}/pins", headers=origin).status_code,
                client.get(f"/projects/{project_id}/pins/{pin_id}", headers=origin).status_code,
                client.patch(f"/projects/{project_id}/pins/{pin_id}", headers=origin, json={"heading": 180}).status_code,
                client.delete(f"/projects/{project_id}/pins/{pin_id}", headers=origin).status_code,
                client.post(f"/projects/{project_id}/annotations", headers=origin, json={"body": "Not allowed", "floor_plan_x": 0.5, "floor_plan_y": 0.5}).status_code,
                client.post(f"/projects/{project_id}/share-link", headers=origin).status_code,
            )
            if any(status not in (403, 404) for status in forbidden):
                raise CheckFailure(f"Owner B cross-owner checks failed: {forbidden}")

            client.post("/auth/logout", headers=origin)
            guest = client.get(f"/share/{share_token}")
            if guest.status_code != 200 or guest.json().get("id") != project_id:
                raise CheckFailure(f"Valid guest share failed: {guest.status_code}")
            if client.get(f"/share/{secrets.token_urlsafe(32)}").status_code != 404:
                raise CheckFailure("Invalid guest share was not rejected")
            if client.patch(f"/projects/{project_id}/pins/{pin_id}", headers=origin, json={"heading": 180}).status_code not in (401, 403, 404):
                raise CheckFailure("Guest modification was not rejected")

            set_user_id(owner_a)
            set_share_token(None)
            with app_main.SessionLocal() as db:
                db.execute(text("UPDATE public.share_links SET expires_at = CURRENT_TIMESTAMP - INTERVAL '1 day' WHERE project_id = :id"), {"id": project_id})
                db.commit()
            if client.get(f"/share/{share_token}").status_code != 404:
                raise CheckFailure("Expired guest share was not rejected")
            if client.post("/auth/login", headers=origin, json={"email": email_a, "password": password_a}).status_code != 200:
                raise CheckFailure("Owner A could not log in to revoke the share")
            renewed = client.post(f"/projects/{project_id}/share-link", headers=origin, json={"expires_in_days": 1})
            if renewed.status_code != 200:
                raise CheckFailure("Owner A could not renew the share")
            renewed_token = renewed.json()["share_token"]
            if client.delete(f"/projects/{project_id}/share-link", headers=origin).status_code != 204:
                raise CheckFailure("Owner A could not revoke the share")
            client.post("/auth/logout", headers=origin)
            if client.get(f"/share/{renewed_token}").status_code != 404:
                raise CheckFailure("Revoked guest share was not rejected")

        result = 0
    except Exception as error:
        detail = str(error) if isinstance(error, CheckFailure) else type(error).__name__
        print(f"Staging app RLS check failed: {detail}")
    finally:
        if users_created:
            try:
                set_user_id(owner_a)
                set_share_token("")
                with app_main.SessionLocal() as db:
                    project_ids = db.execute(text("SELECT id FROM public.projects WHERE owner_id = :owner"), {"owner": owner_a}).scalars().all()
                    for cleanup_project_id in project_ids:
                        for table_name in ("share_links", "annotations", "pins"):
                            db.execute(text(f"DELETE FROM public.{table_name} WHERE project_id = :id"), {"id": cleanup_project_id})
                        db.execute(text("DELETE FROM public.projects WHERE id = :id AND owner_id = :owner"), {"id": cleanup_project_id, "owner": owner_a})
                    if db.execute(text("SELECT count(*) FROM public.projects WHERE owner_id = :owner"), {"owner": owner_a}).scalar_one():
                        raise RuntimeError("Temporary project cleanup failed")
                    for table, column in (
                        (AuthSessionRecord, "user_id"),
                        (PasswordResetRecord, "user_id"),
                        (EmailVerificationRecord, "user_id"),
                        (MfaRecoveryCodeRecord, "user_id"),
                        (MfaCredentialRecord, "user_id"),
                    ):
                        db.query(table).filter(getattr(table, column).in_([owner_a, owner_b])).delete(synchronize_session=False)
                    db.query(UserRecord).filter(UserRecord.id.in_([owner_a, owner_b])).delete(synchronize_session=False)
                    if db.query(UserRecord).filter(UserRecord.id.in_([owner_a, owner_b])).count():
                        raise RuntimeError("Temporary user cleanup failed")
                    db.commit()
            except Exception:
                print(f"Cleanup failed; temporary user IDs: {owner_a}, {owner_b}")
                result = 1
        set_user_id(None)
        set_share_token(None)
        app_main.engine.dispose()
        temp_dir.cleanup()
    if result == 0:
        print("Staging app RLS check passed: owner isolation, valid/invalid/expired/revoked shares, and temporary record cleanup.")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
