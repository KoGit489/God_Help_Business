from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app, reset_demo_store


client = TestClient(app)
same_origin = {"Origin": "http://localhost:8000"}


def test_individual_login_ignores_spoofed_user_header_and_logout_revokes_session(monkeypatch) -> None:
    reset_demo_store()
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    user = {
        "id": "account-1",
        "email": "owner@example.com",
        "name": "Project Owner",
        "password_hash": main.password_hasher.hash("correct horse battery staple 2026"),
        "is_admin": True,
        "is_active": True,
    }
    main.users_by_id[user["id"]] = user
    main.users_by_email[user["email"]] = user

    spoofed = client.get("/projects", headers={"x-user-id": user["id"]})
    assert spoofed.status_code == 401

    login = client.post("/auth/login", headers=same_origin, json={"email": user["email"], "password": "correct horse battery staple 2026"})
    assert login.status_code == 200
    assert login.json()["id"] == user["id"]
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie

    project = client.post("/projects", headers={**same_origin, "x-user-id": "attacker"}, json={"title": "Private project"})
    assert project.status_code == 201
    assert project.json()["id"] in {item["id"] for item in client.get("/projects").json()}

    logout = client.post("/auth/logout", headers=same_origin)
    assert logout.status_code == 204
    assert client.get("/projects").status_code == 401


def test_admin_can_create_a_separate_individual_account(monkeypatch) -> None:
    reset_demo_store()
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    admin = {
        "id": "admin-1", "email": "admin@example.com", "name": "Admin",
        "password_hash": main.password_hasher.hash("a secure admin passphrase 2026"),
        "is_admin": True, "is_active": True,
    }
    member = {
        "id": "member-1", "email": "member@example.com", "name": "Member",
        "password_hash": main.password_hasher.hash("a secure member passphrase 2026"),
        "is_admin": False, "is_active": True,
    }
    main.users_by_id[admin["id"]] = admin
    main.users_by_email[admin["email"]] = admin
    main.users_by_id[member["id"]] = member
    main.users_by_email[member["email"]] = member

    assert client.post("/auth/login", headers=same_origin, json={"email": admin["email"], "password": "a secure admin passphrase 2026"}).status_code == 200
    created = client.post("/auth/users", headers=same_origin, json={"email": "new@example.com", "name": "New Technician", "password": "a secure new passphrase 2026"})
    assert created.status_code == 201
    assert created.json()["is_admin"] is False
    assert client.post("/auth/logout", headers=same_origin).status_code == 204
    assert client.post("/auth/login", headers=same_origin, json={"email": member["email"], "password": "a secure member passphrase 2026"}).status_code == 200
    forbidden = client.post("/auth/users", headers=same_origin, json={"email": "other@example.com", "name": "Other", "password": "a secure other passphrase 2026"})
    assert forbidden.status_code == 403


def test_cookie_authenticated_writes_reject_missing_and_foreign_origins(monkeypatch) -> None:
    reset_demo_store()
    client.cookies.clear()
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    user = {
        "id": "origin-user", "email": "origin@example.com", "name": "Origin User",
        "password_hash": main.password_hasher.hash("a secure origin passphrase 2026"),
        "is_admin": False, "is_active": True,
    }
    main.users_by_id[user["id"]] = user
    main.users_by_email[user["email"]] = user
    assert client.post(
        "/auth/login", headers=same_origin,
        json={"email": user["email"], "password": "a secure origin passphrase 2026"},
    ).status_code == 200

    missing_origin = client.post("/projects", json={"title": "No origin"})
    foreign_origin = client.post(
        "/projects", headers={"Origin": "https://attacker.example"}, json={"title": "Foreign origin"},
    )
    assert missing_origin.status_code == 403
    assert foreign_origin.status_code == 403
    assert client.post("/projects", headers=same_origin, json={"title": "Allowed origin"}).status_code == 201


def test_image_upload_rejects_spoofed_content_and_oversize_files(monkeypatch) -> None:
    import io

    from PIL import Image

    reset_demo_store()
    project = client.post("/projects", json={"title": "Upload validation"}).json()
    pin = client.post(
        f"/projects/{project['id']}/pins",
        json={"latitude": 0, "longitude": 0, "heading": 0, "captured_on": "2026-01-01"},
    ).json()
    route = f"/projects/{project['id']}/pins/{pin['id']}/upload"

    spoofed = client.post(route, files={"file": ("photo.jpg", b"not an image", "image/jpeg")})
    assert spoofed.status_code == 415

    image = io.BytesIO()
    Image.new("RGB", (2, 2), (10, 20, 30)).save(image, format="JPEG")
    monkeypatch.setattr(main, "MAX_IMAGE_UPLOAD_BYTES", 8)
    oversized = client.post(route, files={"file": ("photo.jpg", image.getvalue(), "image/jpeg")})
    assert oversized.status_code == 413

    middleware_limited = client.post(
        route,
        headers={"Content-Length": str(8 + 1024 * 1024 + 1)},
    )
    assert middleware_limited.status_code == 413


def test_memory_startup_requires_and_uses_bootstrap_admin(monkeypatch) -> None:
    reset_demo_store()
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "PERSISTENCE_MODE", "memory")
    monkeypatch.delenv("BOOTSTRAP_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="BOOTSTRAP_ADMIN_EMAIL"):
        main._bootstrap_first_admin()

    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "a secure bootstrap passphrase 2026")
    main._bootstrap_first_admin()
    admin = main.users_by_email["owner@example.com"]
    main._seed_demo_data()
    assert next(iter(main.projects.values()))["owner_id"] == admin["id"]


def test_uploaded_media_is_private_to_the_project_owner(monkeypatch, tmp_path) -> None:
    import io

    from PIL import Image

    reset_demo_store()
    client.cookies.clear()
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)
    owner = {
        "id": "media-owner", "email": "media-owner@example.com", "name": "Media Owner",
        "password_hash": main.password_hasher.hash("a secure media owner passphrase 2026"),
        "is_admin": False, "is_active": True,
    }
    other = {
        "id": "media-other", "email": "media-other@example.com", "name": "Other User",
        "password_hash": main.password_hasher.hash("a secure media other passphrase 2026"),
        "is_admin": False, "is_active": True,
    }
    for user in (owner, other):
        main.users_by_id[user["id"]] = user
        main.users_by_email[user["email"]] = user

    assert client.post(
        "/auth/login", headers=same_origin,
        json={"email": owner["email"], "password": "a secure media owner passphrase 2026"},
    ).status_code == 200
    project = client.post("/projects", headers=same_origin, json={"title": "Private media"}).json()
    pin = client.post(
        f"/projects/{project['id']}/pins", headers=same_origin,
        json={"latitude": 0, "longitude": 0, "heading": 0, "captured_on": "2026-01-01"},
    ).json()
    image = io.BytesIO()
    Image.new("RGB", (1, 1), (12, 34, 56)).save(image, format="JPEG")
    upload = client.post(
        f"/projects/{project['id']}/pins/{pin['id']}/upload", headers=same_origin,
        files={"file": ("private.jpg", image.getvalue(), "image/jpeg")},
    )
    media_url = f"/media/{upload.json()['photo_key']}"
    assert upload.status_code == 200
    assert client.get(media_url).status_code == 200

    client.cookies.clear()
    assert client.get(media_url).status_code == 401
    assert client.post(
        "/auth/login", headers=same_origin,
        json={"email": other["email"], "password": "a secure media other passphrase 2026"},
    ).status_code == 200
    assert client.get(media_url).status_code == 403


def test_share_links_expire_and_can_be_revoked() -> None:
    reset_demo_store()
    project = client.post("/projects", json={"title": "Expiring review"}).json()
    project_id = project["id"]
    link = client.post(f"/projects/{project_id}/share-link", json={"expires_in_days": 2})
    assert link.status_code == 200
    payload = link.json()
    assert payload["expires_at"]
    assert client.get(f"/share/{payload['share_token']}").status_code == 200

    assert client.delete(f"/projects/{project_id}/share-link").status_code == 204
    assert client.get(f"/share/{payload['share_token']}").status_code == 404

    replacement = client.post(f"/projects/{project_id}/share-link").json()
    main.share_links_by_project[project_id]["expires_at"] = main._utc_now() - timedelta(seconds=1)
    assert client.get(f"/share/{replacement['share_token']}").status_code == 404
