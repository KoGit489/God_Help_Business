from __future__ import annotations

import getpass
import os
import secrets
import sys
import tempfile
import uuid


def main() -> int:
    database_url = os.getenv("STAGING_DATABASE_URL", "").strip()
    if not database_url:
        database_url = getpass.getpass("Staging runtime database connection string: ")
    if not database_url:
        print("Staging database connection string is required.")
        return 2

    os.environ["APP_PERSISTENCE"] = "database"
    os.environ["DATABASE_URL"] = database_url
    os.environ["DATABASE_REQUIRE_RLS"] = "true"
    os.environ["APP_ENV"] = "development"
    os.environ["AUTH_REQUIRED"] = "true"
    os.environ["SESSION_COOKIE_SECURE"] = "false"
    os.environ["ALLOW_ACCOUNT_REGISTRATION"] = "false"
    os.environ["SEED_DEMO_DATA"] = "false"
    os.environ["STORAGE_BACKEND"] = "local"

    temp_dir = tempfile.TemporaryDirectory(prefix="casai-staging-rls-")
    os.environ["UPLOAD_DIR"] = temp_dir.name

    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app import main as app_main
    from app.models import AuthSessionRecord, EmailVerificationRecord, MfaCredentialRecord, MfaRecoveryCodeRecord, PasswordResetRecord, PinRecord, ProjectRecord, ShareLinkRecord, UserRecord
    from app.rls import set_share_token, set_user_id

    owner_a = f"staging-owner-a-{uuid.uuid4().hex[:12]}"
    owner_b = f"staging-owner-b-{uuid.uuid4().hex[:12]}"
    email_a = f"{owner_a}@staging.invalid"
    email_b = f"{owner_b}@staging.invalid"
    password_a = secrets.token_urlsafe(24)
    password_b = secrets.token_urlsafe(24)

    project_id = ""
    pin_id = ""
    share_token = ""

    try:
        with app_main.SessionLocal() as db:
            db.execute(text("SELECT set_config(:setting, :value, false)"), {"setting": "casai.user_id", "value": ""})
            db.execute(text("SELECT set_config(:setting, :value, false)"), {"setting": "casai.share_token", "value": ""})
            db.add_all([
                UserRecord(id=owner_a, email=email_a, name="Staging Owner A", password_hash=app_main.password_hasher.hash(password_a), is_admin=False, is_active=True, email_verified=True),
                UserRecord(id=owner_b, email=email_b, name="Staging Owner B", password_hash=app_main.password_hasher.hash(password_b), is_admin=False, is_active=True, email_verified=True),
            ])
            db.commit()

        origin = {"Origin": "http://127.0.0.1"}
        with TestClient(app_main.app) as client:
            login_a = client.post("/auth/login", headers=origin, json={"email": email_a, "password": password_a})
            if login_a.status_code != 200:
                raise RuntimeError(f"Owner A login failed: {login_a.status_code}")

            created = client.post("/projects", headers=origin, json={"title": "Staging RLS project", "description": "Temporary isolation test"})
            if created.status_code != 201:
                raise RuntimeError(f"Owner A project creation failed: {created.status_code}")
            project_id = created.json()["id"]

            pin = client.post(
                f"/projects/{project_id}/pins",
                headers=origin,
                json={"latitude": 0, "longitude": 0, "heading": 0, "captured_on": "2026-01-01"},
            )
            if pin.status_code != 201:
                raise RuntimeError(f"Owner A pin creation failed: {pin.status_code}")
            pin_id = pin.json()["id"]

            link = client.post(f"/projects/{project_id}/share-link", headers=origin, json={"expires_in_days": 1})
            if link.status_code != 200:
                raise RuntimeError(f"Owner A share link failed: {link.status_code}")
            share_token = link.json()["share_token"]

            client.post("/auth/logout", headers=origin)
            login_b = client.post("/auth/login", headers=origin, json={"email": email_b, "password": password_b})
            if login_b.status_code != 200:
                raise RuntimeError(f"Owner B login failed: {login_b.status_code}")

            forbidden = (
                client.get(f"/projects/{project_id}", headers=origin).status_code,
                client.get(f"/projects/{project_id}/pins", headers=origin).status_code,
                client.get(f"/projects/{project_id}/pins/{pin_id}", headers=origin).status_code,
                client.patch(f"/projects/{project_id}/pins/{pin_id}", headers=origin, json={"heading": 180}).status_code,
                client.delete(f"/projects/{project_id}/pins/{pin_id}", headers=origin).status_code,
                client.post(f"/projects/{project_id}/annotations", headers=origin, json={"body": "Not allowed", "floor_plan_x": 0.5, "floor_plan_y": 0.5}).status_code,
                client.post(f"/projects/{project_id}/share-link", headers=origin).status_code,
            )
            if forbidden != (403, 403, 403, 403, 403, 403, 403):
                raise RuntimeError(f"Owner B cross-owner checks failed: {forbidden}")

            client.post("/auth/logout", headers=origin)
            guest = client.get(f"/share/{share_token}")
            if guest.status_code != 200:
                raise RuntimeError(f"Valid guest share failed: {guest.status_code}")

        print("Staging app RLS check passed:")
        print("- owner A created the project and pin")
        print("- owner B was denied project, pin, annotation and share operations")
        print("- the valid share token opened read-only project detail")
        return 0
    except Exception as error:
        print(f"Staging app RLS check failed: {type(error).__name__}")
        return 1
    finally:
        set_user_id(owner_a)
        set_share_token("")
        with app_main.SessionLocal() as db:
            db.execute(text("SELECT set_config(:setting, :value, false)"), {"setting": "casai.user_id", "value": owner_a})
            db.execute(text("SELECT set_config(:setting, :value, false)"), {"setting": "casai.share_token", "value": ""})
            if project_id:
                db.execute(text("DELETE FROM public.share_links WHERE project_id = :id"), {"id": project_id})
                db.execute(text("DELETE FROM public.annotations WHERE project_id = :id"), {"id": project_id})
                db.execute(text("DELETE FROM public.pins WHERE project_id = :id"), {"id": project_id})
                db.execute(text("DELETE FROM public.projects WHERE id = :id"), {"id": project_id})
            for table, column in (
                (AuthSessionRecord, "user_id"),
                (PasswordResetRecord, "user_id"),
                (EmailVerificationRecord, "user_id"),
                (MfaRecoveryCodeRecord, "user_id"),
                (MfaCredentialRecord, "user_id"),
            ):
                db.query(table).filter(getattr(table, column).in_([owner_a, owner_b])).delete(synchronize_session=False)
            db.query(UserRecord).filter(UserRecord.id.in_([owner_a, owner_b])).delete(synchronize_session=False)
            db.commit()
        temp_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
