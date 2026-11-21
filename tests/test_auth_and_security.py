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


def test_streamed_requests_without_known_length_are_rejected() -> None:
    reset_demo_store()
    streamed_upload = client.post(
        "/projects/test/pins/test/upload", content=iter([b"chunk"]),
        headers={"Content-Type": "multipart/form-data; boundary=test"},
    )
    assert streamed_upload.status_code == 411
    streamed_json = client.post(
        "/projects", content=iter([b'{"title":"streamed"}']),
        headers={"Content-Type": "application/json"},
    )
    assert streamed_json.status_code == 411
    oversized_json = client.post(
        "/projects", headers={"Content-Length": str(1024 * 1024 + 1)},
    )
    assert oversized_json.status_code == 413


def test_upload_auth_and_ownership_are_checked_before_multipart_parsing(monkeypatch) -> None:
    reset_demo_store()
    client.cookies.clear()
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    user = {
        "id": "upload-user", "email": "upload@example.com", "name": "Upload User",
        "password_hash": main.password_hasher.hash("an upload test passphrase 2026"),
        "is_admin": False, "is_active": True,
    }
    main.users_by_id[user["id"]] = user
    main.users_by_email[user["email"]] = user
    main.projects["other-project"] = {"id": "other-project", "owner_id": "other-user", "title": "Private"}
    route = "/projects/other-project/pins/some-pin/native-upload"
    malformed_body = {"content": b"not multipart", "headers": {**same_origin, "Content-Type": "multipart/form-data; boundary=broken"}}
    assert client.post(route, **malformed_body).status_code == 401
    assert client.post(
        "/auth/login", headers=same_origin,
        json={"email": user["email"], "password": "an upload test passphrase 2026"},
    ).status_code == 200
    assert client.post(route, **malformed_body).status_code == 403


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


@pytest.mark.parametrize("foreign_key", [
    "uploads/other-project/other-pin/native/private.insv",
    "uploads/{project}/{pin}/native/../../private.insv",
    "uploads/{project}/{pin}/native/..\\private.insv",
])
def test_processing_rejects_foreign_or_traversal_media_keys(monkeypatch, foreign_key) -> None:
    reset_demo_store()
    project_id = client.post("/projects", json={"title": "Private capture"}).json()["id"]
    pin_id = client.post(
        f"/projects/{project_id}/pins",
        json={"latitude": 0, "longitude": 0, "heading": 0, "captured_on": "2026-01-01"},
    ).json()["id"]
    main.pins_by_id[pin_id]["native_file_key"] = foreign_key.format(project=project_id, pin=pin_id)
    monkeypatch.setattr(main, "STORAGE_BACKEND", "s3")
    monkeypatch.setattr(main, "_s3_client", lambda: pytest.fail("Foreign object must not be accessed"))
    response = client.post(f"/projects/{project_id}/pins/{pin_id}/process")
    assert response.status_code == 403


def test_sql_metacharacters_in_project_titles_are_stored_as_data(monkeypatch, tmp_path) -> None:
    from urllib.parse import quote

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'sql-injection.sqlite'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(main, "PERSISTENCE_MODE", "database")
    monkeypatch.setattr(main, "SEED_DEMO_DATA", False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
    payload = "Site'); DROP TABLE projects; --"
    try:
        with TestClient(app) as database_client:
            created = database_client.post("/projects", json={"title": payload})
            assert created.status_code == 201
            assert created.json()["title"] == payload
            assert database_client.get(f"/projects/{created.json()['id']}").json()["title"] == payload
            injected_id = quote("missing' OR 1=1 --", safe="")
            assert database_client.get(f"/projects/{injected_id}").status_code == 404
            assert any(item["title"] == payload for item in database_client.get("/projects").json())
    finally:
        engine.dispose()


def test_spaces_media_ignores_untrusted_content_type(monkeypatch) -> None:
    import io
    from unittest.mock import Mock

    reset_demo_store()
    project_id = client.post("/projects", json={"title": "Media MIME"}).json()["id"]
    storage = Mock()
    storage.get_object.side_effect = lambda **kwargs: {
        "Body": io.BytesIO(b"test media"), "ContentType": "text/html", "ContentLength": 10,
    }
    monkeypatch.setattr(main, "STORAGE_BACKEND", "s3")
    monkeypatch.setattr(main, "_s3_client", lambda: storage)
    monkeypatch.setenv("S3_BUCKET", "test-private-bucket")
    image = client.get(f"/media/uploads/{project_id}/pin/photo.jpg")
    assert image.headers["content-type"] == "image/jpeg"
    assert image.headers["x-content-type-options"] == "nosniff"
    native = client.get(f"/media/uploads/{project_id}/pin/native/raw.insv")
    assert native.headers["content-type"] == "application/octet-stream"
    assert native.headers["content-disposition"] == "attachment"


def test_production_security_configuration_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(main, "AUTH_REQUIRED", False)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", True)
    monkeypatch.setattr(main, "ALLOWED_CORS_ORIGINS", ["https://example.com"])
    with pytest.raises(RuntimeError, match="authentication"):
        main._validate_production_security()

    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    with pytest.raises(RuntimeError, match="secure session cookies"):
        main._validate_production_security()

    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", True)
    monkeypatch.setenv("MEDIA_WORKER_SOCKET", "/run/media-worker/worker.sock")
    for origins in ([], ["http://example.com"], ["https://example.com/path"], ["https://user@example.com"]):
        monkeypatch.setattr(main, "ALLOWED_CORS_ORIGINS", origins)
        with pytest.raises(RuntimeError, match="origin"):
            main._validate_production_security()
    monkeypatch.setattr(main, "ALLOWED_CORS_ORIGINS", ["https://example.com"])
    monkeypatch.delenv("MEDIA_WORKER_SOCKET", raising=False)
    with pytest.raises(RuntimeError, match="media worker"):
        main._validate_production_security()
    monkeypatch.setenv("MEDIA_WORKER_SOCKET", "/run/media-worker/worker.sock")
    main._validate_production_security()


@pytest.mark.parametrize("path", ["/not-a-page", "/missing/deep/page"])
def test_missing_browser_pages_render_404_but_api_clients_receive_json(path) -> None:
    browser = client.get(path, headers={"Accept": "text/html"})
    assert browser.status_code == 404
    assert "text/html" in browser.headers["content-type"]
    assert "Page not found" in browser.text
    api = client.get(path, headers={"Accept": "application/json"})
    assert api.status_code == 404
    assert api.json()["error"]["type"] == "http_error"


@pytest.mark.parametrize("title,description", [("   ", ""), ("x" * 256, ""), ("Valid", "x" * 1001)])
def test_project_validation_rejects_blank_or_oversized_input(title, description) -> None:
    response = client.post("/projects", json={"title": title, "description": description})
    assert response.status_code == 422
    assert response.json()["error"]["type"] == "validation_error"
    assert response.json()["error"]["message"].startswith(("title:", "description:"))


def test_validation_errors_do_not_echo_passwords() -> None:
    password = "sensitive-password-" * 20
    response = client.post("/auth/login", headers=same_origin, json={"email": "person@example.com", "password": password})
    assert response.status_code == 422
    assert password not in response.text
    assert "password:" in response.json()["error"]["message"]
    assert all("input" not in detail and "ctx" not in detail for detail in response.json()["error"]["details"])


@pytest.mark.parametrize("path", ["/privacy.html", "/terms.html"])
def test_legal_pages_are_clearly_marked_unpublished(path) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert "not yet published" in response.text.lower()


def test_login_rate_limit_is_applied_to_known_and_unknown_accounts(monkeypatch) -> None:
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter

    reset_demo_store()
    client.cookies.clear()
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "login_limiter", MovingWindowRateLimiter(MemoryStorage()))
    for _ in range(10):
        response = client.post("/auth/login", headers=same_origin, json={"email": "unknown@example.com", "password": "wrong"})
        assert response.status_code == 401
    limited = client.post("/auth/login", headers=same_origin, json={"email": "unknown@example.com", "password": "wrong"})
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert client.post("/auth/login", headers=same_origin, json={"email": "another@example.com", "password": "wrong"}).status_code == 401


def test_login_global_rate_limit_applies_across_accounts(monkeypatch) -> None:
    from limits import RateLimitItemPerMinute
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter

    reset_demo_store()
    client.cookies.clear()
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "login_limiter", MovingWindowRateLimiter(MemoryStorage()))
    monkeypatch.setattr(main, "LOGIN_GLOBAL_LIMIT", RateLimitItemPerMinute(3))
    for index in range(3):
        response = client.post("/auth/login", headers=same_origin, json={"email": f"user{index}@example.com", "password": "wrong"})
        assert response.status_code == 401
    assert client.post("/auth/login", headers=same_origin, json={"email": "another@example.com", "password": "wrong"}).status_code == 429


def test_startup_fails_when_rate_limit_storage_is_unavailable(monkeypatch) -> None:
    from unittest.mock import Mock

    limiter = Mock()
    limiter.storage.check.return_value = False
    monkeypatch.setattr(main, "login_limiter", limiter)
    with pytest.raises(RuntimeError, match="rate-limit storage"):
        with TestClient(app):
            pass


def test_error_tracking_is_opt_in_and_scrubs_sensitive_event_fields() -> None:
    import json
    from unittest.mock import patch

    from app.monitoring import configure_error_tracking, sanitize_error_event

    assert configure_error_tracking("", "test") is False
    event = {
        "event_id": "event-1", "level": "error", "request": {"url": "https://example.com/share/secret-token", "headers": {"Authorization": "secret-token"}},
        "user": {"email": "secret@example.com"}, "breadcrumbs": {"values": [{"message": "secret-token"}]},
        "exception": {"values": [{"type": "ValueError", "value": "secret-token", "stacktrace": {"frames": [{"filename": "app/main.py", "function": "process", "lineno": 1, "vars": {"password": "secret-token"}}]}}]},
    }
    sanitized = sanitize_error_event(event, {})
    assert sanitized is not None
    assert "secret-token" not in json.dumps(sanitized)
    assert "secret@example.com" not in json.dumps(sanitized)
    assert sanitized["exception"]["values"][0]["type"] == "ValueError"
    assert sanitized["exception"]["values"][0]["stacktrace"]["frames"][0]["function"] == "process"
    assert sanitize_error_event({"message": "sensitive event"}, {}) is None
    with patch("sentry_sdk.init") as initialize:
        assert configure_error_tracking("https://public@example.invalid/1", "test") is True
        options = initialize.call_args.kwargs
        assert options["before_send"] is sanitize_error_event
        assert options["send_default_pii"] is False
        assert options["include_local_variables"] is False
        assert options["traces_sample_rate"] == 0.0


def test_delete_account_requires_password_and_revokes_all_sessions(monkeypatch) -> None:
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter

    reset_demo_store()
    client.cookies.clear()
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(main, "login_limiter", MovingWindowRateLimiter(MemoryStorage()))
    user = {
        "id": "delete-user", "email": "delete@example.com", "name": "User",
        "password_hash": main.password_hasher.hash("a secure deletion passphrase 2026"),
        "is_admin": False, "is_active": True,
    }
    main.users_by_id[user["id"]] = user
    main.users_by_email[user["email"]] = user
    credentials = {"email": user["email"], "password": "a secure deletion passphrase 2026"}
    assert client.post("/auth/login", headers=same_origin, json=credentials).status_code == 200
    first_token = client.cookies.get(main.SESSION_COOKIE_NAME)
    assert client.post("/auth/login", headers=same_origin, json=credentials).status_code == 200
    assert client.request("DELETE", "/auth/me", headers=same_origin, json={"password": "wrong"}).status_code == 401
    assert client.get("/auth/me").status_code == 200
    assert client.request("DELETE", "/auth/me", headers=same_origin, json={"password": credentials["password"]}).status_code == 204
    assert client.get("/auth/me").status_code == 401
    client.cookies.set(main.SESSION_COOKIE_NAME, first_token)
    assert client.get("/auth/me").status_code == 401
    assert user["id"] not in main.users_by_id
    assert user["email"] not in main.users_by_email


@pytest.mark.parametrize("case", ["owned_project", "last_admin"])
def test_delete_account_blocks_project_owners_and_last_admin(monkeypatch, case) -> None:
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter

    reset_demo_store()
    client.cookies.clear()
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(main, "login_limiter", MovingWindowRateLimiter(MemoryStorage()))
    user = {
        "id": "protected-user", "email": "protected@example.com", "name": "User",
        "password_hash": main.password_hasher.hash("a protected passphrase 2026"),
        "is_admin": case == "last_admin", "is_active": True,
    }
    main.users_by_id[user["id"]] = user
    main.users_by_email[user["email"]] = user
    assert client.post("/auth/login", headers=same_origin, json={"email": user["email"], "password": "a protected passphrase 2026"}).status_code == 200
    if case == "owned_project":
        assert client.post("/projects", headers=same_origin, json={"title": "Protected project"}).status_code == 201
    response = client.request("DELETE", "/auth/me", headers=same_origin, json={"password": "a protected passphrase 2026"})
    assert response.status_code == 409
    assert client.get("/auth/me").status_code == 200
    assert user["id"] in main.users_by_id


def test_database_account_deletion_preserves_projects_and_revokes_sessions(monkeypatch, tmp_path) -> None:
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'accounts.sqlite'}", connect_args={"check_same_thread": False})
    main.Base.metadata.create_all(engine)
    local_session = sessionmaker(bind=engine)
    with local_session() as db:
        db.add_all([
            main.UserRecord(id="admin", email="admin-delete@example.com", name="Admin", password_hash=main.password_hasher.hash("an admin deletion passphrase 2026"), is_admin=True, is_active=True),
            main.UserRecord(id="member", email="member-delete@example.com", name="Member", password_hash=main.password_hasher.hash("a member deletion passphrase 2026"), is_admin=False, is_active=True),
        ])
        db.commit()
    monkeypatch.setattr(main, "PERSISTENCE_MODE", "database")
    monkeypatch.setattr(main, "SEED_DEMO_DATA", False)
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", local_session)
    monkeypatch.setattr(main, "login_limiter", MovingWindowRateLimiter(MemoryStorage()))
    try:
        with TestClient(app) as database_client:
            assert database_client.post("/auth/login", headers=same_origin, json={"email": "member-delete@example.com", "password": "a member deletion passphrase 2026"}).status_code == 200
            old_token = database_client.cookies.get(main.SESSION_COOKIE_NAME)
            assert database_client.request("DELETE", "/auth/me", headers=same_origin, json={"password": "a member deletion passphrase 2026"}).status_code == 204
            database_client.cookies.set(main.SESSION_COOKIE_NAME, old_token)
            assert database_client.get("/auth/me").status_code == 401
            with local_session() as db:
                assert db.get(main.UserRecord, "member") is None
                assert db.query(main.AuthSessionRecord).filter_by(user_id="member").count() == 0
            database_client.cookies.clear()
            assert database_client.post("/auth/login", headers=same_origin, json={"email": "admin-delete@example.com", "password": "an admin deletion passphrase 2026"}).status_code == 200
            assert database_client.request("DELETE", "/auth/me", headers=same_origin, json={"password": "an admin deletion passphrase 2026"}).status_code == 409
    finally:
        engine.dispose()


def test_password_reset_is_single_use_expires_and_revokes_sessions(monkeypatch) -> None:
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter

    reset_demo_store()
    client.cookies.clear()
    monkeypatch.setattr(main, "PERSISTENCE_MODE", "memory")
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(main, "login_limiter", MovingWindowRateLimiter(MemoryStorage()))
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.test")
    monkeypatch.setenv("PUBLIC_APP_ORIGIN", "https://example.test")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    deliveries = []
    monkeypatch.setattr(main, "_send_password_reset_email", lambda settings, recipient, token: deliveries.append((recipient, token)))
    user = {
        "id": "reset-user", "email": "reset@example.com", "name": "User",
        "password_hash": main.password_hasher.hash("old secure passphrase 2026"),
        "is_admin": False, "is_active": True,
    }
    main.users_by_id[user["id"]] = user
    main.users_by_email[user["email"]] = user
    assert client.post("/auth/login", headers=same_origin, json={"email": user["email"], "password": "old secure passphrase 2026"}).status_code == 200
    unknown = client.post("/auth/password-reset/request", headers=same_origin, json={"email": "unknown@example.com"})
    known = client.post("/auth/password-reset/request", headers=same_origin, json={"email": user["email"]})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(deliveries) == 1
    raw_token = deliveries[-1][1]
    assert raw_token not in main.password_resets_by_token_hash
    assert main._session_token_hash(raw_token) in main.password_resets_by_token_hash
    assert client.post("/auth/password-reset/confirm", headers=same_origin, json={"token": raw_token, "password": "new secure passphrase 2026"}).status_code == 204
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/password-reset/confirm", headers=same_origin, json={"token": raw_token, "password": "new secure passphrase 2026"}).status_code == 400
    client.cookies.clear()
    assert client.post("/auth/login", headers=same_origin, json={"email": user["email"], "password": "old secure passphrase 2026"}).status_code == 401
    assert client.post("/auth/login", headers=same_origin, json={"email": user["email"], "password": "new secure passphrase 2026"}).status_code == 200
    assert client.post("/auth/password-reset/request", headers=same_origin, json={"email": user["email"]}).status_code == 202
    expired_token = deliveries[-1][1]
    main.password_resets_by_token_hash[main._session_token_hash(expired_token)]["expires_at"] = main._utc_now() - timedelta(seconds=1)
    assert client.post("/auth/password-reset/confirm", headers=same_origin, json={"token": expired_token, "password": "another secure passphrase 2026"}).status_code == 400


def test_password_recovery_fails_closed_without_smtp(monkeypatch) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)
    response = client.post("/auth/password-reset/request", headers=same_origin, json={"email": "person@example.com"})
    assert response.status_code == 503
    assert "not configured" in response.json()["error"]["message"]


def test_reset_email_uses_starttls_and_fragment_link(monkeypatch) -> None:
    from unittest.mock import MagicMock

    connection = MagicMock()
    smtp = MagicMock()
    smtp.return_value.__enter__.return_value = connection
    monkeypatch.setattr(main.smtplib, "SMTP", smtp)
    settings = {
        "host": "smtp.example.test", "port": 587, "sender": "noreply@example.test",
        "username": "mailer", "password": "smtp-test-secret", "origin": "https://example.test",
    }
    main._send_password_reset_email(settings, "person@example.test", "reset-token")
    smtp.assert_called_once_with("smtp.example.test", 587, timeout=10)
    connection.starttls.assert_called_once()
    connection.login.assert_called_once_with("mailer", "smtp-test-secret")
    message = connection.send_message.call_args.args[0]
    assert message["To"] == "person@example.test"
    assert "https://example.test/reset-password.html#token=reset-token" in message.get_content()


def test_database_password_reset_revokes_sessions_and_token(monkeypatch, tmp_path) -> None:
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'reset.sqlite'}", connect_args={"check_same_thread": False})
    main.Base.metadata.create_all(engine)
    local_session = sessionmaker(bind=engine)
    with local_session() as db:
        db.add(main.UserRecord(id="reset-db", email="reset-db@example.com", name="Reset", password_hash=main.password_hasher.hash("old database passphrase 2026"), is_admin=True, is_active=True))
        db.commit()
    monkeypatch.setattr(main, "PERSISTENCE_MODE", "database")
    monkeypatch.setattr(main, "SEED_DEMO_DATA", False)
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", local_session)
    monkeypatch.setattr(main, "login_limiter", MovingWindowRateLimiter(MemoryStorage()))
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.test")
    monkeypatch.setenv("PUBLIC_APP_ORIGIN", "https://example.test")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    deliveries = []
    monkeypatch.setattr(main, "_send_password_reset_email", lambda settings, recipient, token: deliveries.append(token))
    try:
        with TestClient(app) as database_client:
            assert database_client.post("/auth/login", headers=same_origin, json={"email": "reset-db@example.com", "password": "old database passphrase 2026"}).status_code == 200
            assert database_client.post("/auth/password-reset/request", headers=same_origin, json={"email": "reset-db@example.com"}).status_code == 202
            with local_session() as db:
                assert db.get(main.PasswordResetRecord, main._session_token_hash(deliveries[0])) is not None
                assert db.get(main.PasswordResetRecord, deliveries[0]) is None
            assert database_client.post("/auth/password-reset/confirm", headers=same_origin, json={"token": deliveries[0], "password": "new database passphrase 2026"}).status_code == 204
            assert database_client.get("/auth/me").status_code == 401
            assert database_client.post("/auth/password-reset/confirm", headers=same_origin, json={"token": deliveries[0], "password": "new database passphrase 2026"}).status_code == 400
            database_client.cookies.clear()
            assert database_client.post("/auth/login", headers=same_origin, json={"email": "reset-db@example.com", "password": "new database passphrase 2026"}).status_code == 200
    finally:
        engine.dispose()


def test_email_verification_blocks_sign_in_until_single_use_link_is_confirmed(monkeypatch) -> None:
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter

    reset_demo_store()
    client.cookies.clear()
    monkeypatch.setattr(main, "PERSISTENCE_MODE", "memory")
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "EMAIL_VERIFICATION_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(main, "login_limiter", MovingWindowRateLimiter(MemoryStorage()))
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.test")
    monkeypatch.setenv("PUBLIC_APP_ORIGIN", "https://example.test")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    deliveries = []
    monkeypatch.setattr(main, "_send_verification_email", lambda settings, recipient, token: deliveries.append((recipient, token)))
    admin = {
        "id": "verify-admin", "email": "verify-admin@example.com", "name": "Admin",
        "password_hash": main.password_hasher.hash("verified admin passphrase 2026"),
        "is_admin": True, "is_active": True, "email_verified": True,
    }
    main.users_by_id[admin["id"]] = admin
    main.users_by_email[admin["email"]] = admin
    assert client.post("/auth/login", headers=same_origin, json={"email": admin["email"], "password": "verified admin passphrase 2026"}).status_code == 200
    created = client.post("/auth/users", headers=same_origin, json={"email": "unverified@example.com", "name": "Member", "password": "member secure passphrase 2026"})
    assert created.status_code == 201
    assert created.json()["email_verified"] is False
    assert len(deliveries) == 1
    first_token = deliveries[-1][1]
    assert first_token not in main.email_verifications_by_token_hash
    assert main._session_token_hash(first_token) in main.email_verifications_by_token_hash
    assert client.post("/auth/logout", headers=same_origin).status_code == 204
    credentials = {"email": "unverified@example.com", "password": "member secure passphrase 2026"}
    assert client.post("/auth/login", headers=same_origin, json=credentials).status_code == 403
    main.email_verifications_by_token_hash[main._session_token_hash(first_token)]["expires_at"] = main._utc_now() - timedelta(seconds=1)
    assert client.post("/auth/email-verification/confirm", headers=same_origin, json={"token": first_token}).status_code == 400
    unknown = client.post("/auth/email-verification/request", headers=same_origin, json={"email": "unknown@example.com"})
    known = client.post("/auth/email-verification/request", headers=same_origin, json={"email": "unverified@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    token = deliveries[-1][1]
    assert client.post("/auth/email-verification/confirm", headers=same_origin, json={"token": token}).status_code == 204
    assert client.post("/auth/email-verification/confirm", headers=same_origin, json={"token": token}).status_code == 400
    assert client.post("/auth/login", headers=same_origin, json=credentials).status_code == 200
    assert client.get("/auth/me").json()["email_verified"] is True


def test_email_verification_requires_mail_configuration_at_startup(monkeypatch) -> None:
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "EMAIL_VERIFICATION_REQUIRED", True)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with pytest.raises(RuntimeError, match="requires valid SMTP"):
        with TestClient(app):
            pass


def test_database_email_verification_confirms_a_new_user(monkeypatch, tmp_path) -> None:
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'verify.sqlite'}", connect_args={"check_same_thread": False})
    main.Base.metadata.create_all(engine)
    local_session = sessionmaker(bind=engine)
    with local_session() as db:
        db.add(main.UserRecord(id="verify-db", email="verify-db@example.com", name="Member", password_hash=main.password_hasher.hash("database verify passphrase 2026"), is_admin=True, is_active=True, email_verified=False))
        db.commit()
    monkeypatch.setattr(main, "PERSISTENCE_MODE", "database")
    monkeypatch.setattr(main, "SEED_DEMO_DATA", False)
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "EMAIL_VERIFICATION_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", local_session)
    monkeypatch.setattr(main, "login_limiter", MovingWindowRateLimiter(MemoryStorage()))
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.test")
    monkeypatch.setenv("PUBLIC_APP_ORIGIN", "https://example.test")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    deliveries = []
    monkeypatch.setattr(main, "_send_verification_email", lambda settings, recipient, token: deliveries.append(token))
    try:
        with TestClient(app) as database_client:
            credentials = {"email": "verify-db@example.com", "password": "database verify passphrase 2026"}
            assert database_client.post("/auth/login", headers=same_origin, json=credentials).status_code == 403
            assert database_client.post("/auth/email-verification/request", headers=same_origin, json={"email": credentials["email"]}).status_code == 202
            with local_session() as db:
                assert db.get(main.EmailVerificationRecord, main._session_token_hash(deliveries[0])) is not None
            assert database_client.post("/auth/email-verification/confirm", headers=same_origin, json={"token": deliveries[0]}).status_code == 204
            assert database_client.post("/auth/email-verification/confirm", headers=same_origin, json={"token": deliveries[0]}).status_code == 400
            assert database_client.post("/auth/login", headers=same_origin, json=credentials).status_code == 200
            with local_session() as db:
                assert db.get(main.UserRecord, "verify-db").email_verified is True
                assert db.query(main.EmailVerificationRecord).count() == 0
            created = database_client.post(
                "/auth/users", headers=same_origin,
                json={"email": "created-db@example.com", "name": "Created", "password": "created account passphrase 2026"},
            )
            assert created.status_code == 201
            assert created.json()["email_verified"] is False
            assert len(deliveries) == 2
            with local_session() as db:
                assert db.get(main.EmailVerificationRecord, main._session_token_hash(deliveries[1])).user_id == created.json()["id"]
    finally:
        engine.dispose()


def test_legacy_user_is_migrated_without_lockout(monkeypatch, tmp_path) -> None:
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-user.sqlite'}", connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE users (id VARCHAR(64) PRIMARY KEY, email VARCHAR(254) NOT NULL UNIQUE, "
            "name VARCHAR(128) NOT NULL, password_hash VARCHAR(512) NOT NULL, "
            "is_admin BOOLEAN NOT NULL, is_active BOOLEAN NOT NULL, created_at DATETIME NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO users (id, email, name, password_hash, is_admin, is_active, created_at) "
            "VALUES (:id, :email, :name, :password_hash, :is_admin, :is_active, :created_at)"
        ), {"id": "legacy-admin", "email": "legacy@example.com", "name": "Legacy", "password_hash": main.password_hasher.hash("legacy admin passphrase 2026"), "is_admin": True, "is_active": True, "created_at": main._utc_now()})
    local_session = sessionmaker(bind=engine)
    monkeypatch.setattr(main, "PERSISTENCE_MODE", "database")
    monkeypatch.setattr(main, "SEED_DEMO_DATA", False)
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "EMAIL_VERIFICATION_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", local_session)
    monkeypatch.setattr(main, "login_limiter", MovingWindowRateLimiter(MemoryStorage()))
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.test")
    monkeypatch.setenv("PUBLIC_APP_ORIGIN", "https://example.test")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    try:
        with TestClient(app) as database_client:
            response = database_client.post("/auth/login", headers=same_origin, json={"email": "legacy@example.com", "password": "legacy admin passphrase 2026"})
            assert response.status_code == 200
            assert response.json()["email_verified"] is True
    finally:
        engine.dispose()


def test_mfa_enrollment_replay_and_recovery_codes(monkeypatch) -> None:
    from datetime import datetime, timezone

    import pyotp
    from cryptography.fernet import Fernet
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter

    reset_demo_store()
    client.cookies.clear()
    now = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(main, "_utc_now", lambda: now)
    monkeypatch.setattr(main, "PERSISTENCE_MODE", "memory")
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "EMAIL_VERIFICATION_REQUIRED", False)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(main, "login_limiter", MovingWindowRateLimiter(MemoryStorage()))
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    user = {
        "id": "mfa-user", "email": "mfa@example.com", "name": "MFA User",
        "password_hash": main.password_hasher.hash("an MFA test passphrase 2026"),
        "is_admin": False, "is_active": True,
    }
    main.users_by_id[user["id"]] = user
    main.users_by_email[user["email"]] = user
    credentials = {"email": user["email"], "password": "an MFA test passphrase 2026"}
    assert client.post("/auth/login", headers=same_origin, json=credentials).status_code == 200
    old_token = client.cookies.get(main.SESSION_COOKIE_NAME)
    assert client.post("/auth/login", headers=same_origin, json=credentials).status_code == 200
    assert client.get("/auth/mfa").json() == {"enabled": False, "available": True}
    assert client.post("/auth/mfa/setup", headers=same_origin, json={"password": "wrong"}).status_code == 401
    setup = client.post("/auth/mfa/setup", headers=same_origin, json={"password": credentials["password"]})
    assert setup.status_code == 200
    assert setup.headers["cache-control"] == "no-store"
    secret = setup.json()["secret"]
    assert secret not in main.mfa_credentials_by_user[user["id"]]["encrypted_secret"]
    code = pyotp.TOTP(secret).at(now.timestamp())
    assert client.post("/auth/mfa/enable", headers=same_origin, json={"code": "not-six"}).status_code == 401
    enabled = client.post("/auth/mfa/enable", headers=same_origin, json={"code": code})
    assert enabled.status_code == 200
    recovery_codes = enabled.json()["recovery_codes"]
    assert len(set(recovery_codes)) == 10
    assert all(code not in main.mfa_recovery_codes_by_hash for code in recovery_codes)
    old_client = TestClient(app)
    old_client.cookies.set(main.SESSION_COOKIE_NAME, old_token)
    assert old_client.get("/auth/me").status_code == 401
    assert client.get("/auth/mfa").json()["enabled"] is True
    assert client.post("/auth/logout", headers=same_origin).status_code == 204
    assert client.post("/auth/login", headers=same_origin, json=credentials).status_code == 401
    assert client.post("/auth/login", headers=same_origin, json={**credentials, "mfa_code": code}).status_code == 401
    now += timedelta(seconds=30)
    next_code = pyotp.TOTP(secret).at(now.timestamp())
    assert client.post("/auth/login", headers=same_origin, json={**credentials, "mfa_code": next_code}).status_code == 200
    assert client.post("/auth/logout", headers=same_origin).status_code == 204
    assert client.post("/auth/login", headers=same_origin, json={**credentials, "mfa_code": next_code}).status_code == 401
    assert client.post("/auth/login", headers=same_origin, json={**credentials, "mfa_code": recovery_codes[0]}).status_code == 200
    assert client.post("/auth/logout", headers=same_origin).status_code == 204
    assert client.post("/auth/login", headers=same_origin, json={**credentials, "mfa_code": recovery_codes[0]}).status_code == 401
    monkeypatch.delenv("MFA_ENCRYPTION_KEY")
    assert client.post("/auth/login", headers=same_origin, json={**credentials, "mfa_code": recovery_codes[1]}).status_code == 200
    assert client.get("/auth/mfa").json() == {"enabled": True, "available": False}
    assert client.post("/auth/mfa/disable", headers=same_origin, json={"password": credentials["password"], "mfa_code": recovery_codes[2]}).status_code == 204
    assert client.post("/auth/logout", headers=same_origin).status_code == 204
    assert client.post("/auth/login", headers=same_origin, json=credentials).status_code == 200


def test_mfa_setup_fails_closed_without_key(monkeypatch) -> None:
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter

    reset_demo_store()
    client.cookies.clear()
    monkeypatch.setattr(main, "PERSISTENCE_MODE", "memory")
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(main, "login_limiter", MovingWindowRateLimiter(MemoryStorage()))
    monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
    user = {"id": "no-key", "email": "no-key@example.com", "name": "User", "password_hash": main.password_hasher.hash("a no key passphrase 2026"), "is_admin": False, "is_active": True}
    main.users_by_id[user["id"]] = user
    main.users_by_email[user["email"]] = user
    assert client.post("/auth/login", headers=same_origin, json={"email": user["email"], "password": "a no key passphrase 2026"}).status_code == 200
    assert client.get("/auth/mfa").json() == {"enabled": False, "available": False}
    assert client.post("/auth/mfa/setup", headers=same_origin, json={"password": "a no key passphrase 2026"}).status_code == 503
    assert user["id"] not in main.mfa_credentials_by_user


def test_database_mfa_login_and_account_deletion_require_second_factor(monkeypatch, tmp_path) -> None:
    from datetime import datetime, timezone

    import pyotp
    from cryptography.fernet import Fernet
    from limits.storage import MemoryStorage
    from limits.strategies import MovingWindowRateLimiter
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'mfa.sqlite'}", connect_args={"check_same_thread": False})
    main.Base.metadata.create_all(engine)
    local_session = sessionmaker(bind=engine)
    with local_session() as db:
        db.add_all([
            main.UserRecord(id="mfa-admin", email="mfa-admin@example.com", name="Admin", password_hash=main.password_hasher.hash("an MFA admin passphrase 2026"), is_admin=True, is_active=True),
            main.UserRecord(id="mfa-member", email="mfa-member@example.com", name="Member", password_hash=main.password_hasher.hash("an MFA member passphrase 2026"), is_admin=False, is_active=True),
        ])
        db.commit()
    now = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(main, "_utc_now", lambda: now)
    monkeypatch.setattr(main, "PERSISTENCE_MODE", "database")
    monkeypatch.setattr(main, "SEED_DEMO_DATA", False)
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "EMAIL_VERIFICATION_REQUIRED", False)
    monkeypatch.setattr(main, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", local_session)
    monkeypatch.setattr(main, "login_limiter", MovingWindowRateLimiter(MemoryStorage()))
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.test")
    monkeypatch.setenv("PUBLIC_APP_ORIGIN", "https://example.test")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    deliveries = []
    monkeypatch.setattr(main, "_send_password_reset_email", lambda settings, recipient, token: deliveries.append(token))
    try:
        with TestClient(app) as database_client:
            credentials = {"email": "mfa-member@example.com", "password": "an MFA member passphrase 2026"}
            assert database_client.post("/auth/login", headers=same_origin, json=credentials).status_code == 200
            setup = database_client.post("/auth/mfa/setup", headers=same_origin, json={"password": credentials["password"]}).json()
            secret = setup["secret"]
            enabled = database_client.post("/auth/mfa/enable", headers=same_origin, json={"code": pyotp.TOTP(secret).at(now.timestamp())})
            assert enabled.status_code == 200
            recovery_codes = enabled.json()["recovery_codes"]
            with local_session() as db:
                assert secret not in db.get(main.MfaCredentialRecord, "mfa-member").encrypted_secret
                assert db.get(main.MfaRecoveryCodeRecord, recovery_codes[0]) is None
                assert db.get(main.MfaRecoveryCodeRecord, main._session_token_hash(recovery_codes[0])) is not None
            assert database_client.post("/auth/password-reset/request", headers=same_origin, json={"email": credentials["email"]}).status_code == 202
            assert database_client.post("/auth/password-reset/confirm", headers=same_origin, json={"token": deliveries[0], "password": "new MFA member passphrase 2026"}).status_code == 204
            assert database_client.get("/auth/me").status_code == 401
            database_client.cookies.clear()
            assert database_client.post("/auth/login", headers=same_origin, json=credentials).status_code == 401
            credentials["password"] = "new MFA member passphrase 2026"
            assert database_client.post("/auth/login", headers=same_origin, json=credentials).status_code == 401
            now += timedelta(seconds=30)
            assert database_client.post("/auth/login", headers=same_origin, json={**credentials, "mfa_code": pyotp.TOTP(secret).at(now.timestamp())}).status_code == 200
            assert database_client.request("DELETE", "/auth/me", headers=same_origin, json={"password": credentials["password"]}).status_code == 401
            assert database_client.request("DELETE", "/auth/me", headers=same_origin, json={"password": credentials["password"], "mfa_code": recovery_codes[0]}).status_code == 204
            with local_session() as db:
                assert db.get(main.UserRecord, "mfa-member") is None
                assert db.get(main.MfaCredentialRecord, "mfa-member") is None
                assert db.query(main.MfaRecoveryCodeRecord).filter_by(user_id="mfa-member").count() == 0
    finally:
        engine.dispose()
