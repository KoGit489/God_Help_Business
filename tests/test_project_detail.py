from fastapi.testclient import TestClient

from app.main import app, reset_demo_store


client = TestClient(app)


def test_project_detail_includes_pins() -> None:
    reset_demo_store()

    created_project = client.post(
        "/projects",
        json={"title": "Detail Site", "description": "Show project details"},
    ).json()

    client.post(
        f"/projects/{created_project['id']}/pins",
        json={
            "latitude": 5.6,
            "longitude": -0.2,
            "heading": 12.0,
            "captured_on": "2026-08-09",
            "photo_key": "photos/003.jpg",
        },
    )

    response = client.get(f"/projects/{created_project['id']}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Detail Site"
    assert payload["pin_count"] == 1
    assert len(payload["pins"]) == 1
    assert payload["pins"][0]["photo_key"] == "photos/003.jpg"


def test_upload_photo_for_pin(tmp_path) -> None:
    reset_demo_store()
    import io
    from PIL import Image

    created_project = client.post(
        "/projects",
        json={"title": "Upload Site", "description": "Photo workflow"},
    ).json()

    created_pin = client.post(
        f"/projects/{created_project['id']}/pins",
        json={
            "latitude": 5.7,
            "longitude": -0.3,
            "heading": 90.0,
            "captured_on": "2026-08-10",
            "photo_key": None,
        },
    ).json()

    sample_file = tmp_path / "sample.jpg"
    image = io.BytesIO()
    Image.new("RGB", (1, 1), (20, 40, 60)).save(image, format="JPEG")
    sample_file.write_bytes(image.getvalue())

    with sample_file.open("rb") as handle:
        response = client.post(
            f"/projects/{created_project['id']}/pins/{created_pin['id']}/upload",
            files={"file": ("sample.jpg", handle, "image/jpeg")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["photo_key"].endswith("sample.jpg")


def test_database_workflows_preserve_capture_review_and_sharing(monkeypatch, tmp_path) -> None:
    import io

    from PIL import Image
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    from sqlalchemy.orm import sessionmaker

    from app import main as api

    engine = create_engine(
        URL.create("sqlite", database=str(tmp_path / "audit.sqlite")),
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(api, "PERSISTENCE_MODE", "database")
    monkeypatch.setattr(api, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(api, "UPLOAD_DIR", tmp_path / "media")
    monkeypatch.setattr(api, "SEED_DEMO_DATA", False)
    monkeypatch.setattr(api, "engine", engine)
    monkeypatch.setattr(api, "SessionLocal", sessionmaker(bind=engine))
    image = io.BytesIO()
    Image.new("RGB", (128, 64), (70, 160, 90)).save(image, format="JPEG")
    headers = {"x-user-id": "demo"}
    try:
        with TestClient(app) as database_client:
            response = database_client.post("/projects", headers=headers, json={"title": "Database audit"})
            assert response.status_code == 201
            project_id = response.json()["id"]
            project_route = f"/projects/{project_id}"
            response = database_client.post(
                f"{project_route}/pins",
                headers=headers,
                json={
                    "latitude": 5.5, "longitude": -0.2, "heading": 90,
                    "position_x": 0.4, "position_y": 0.5,
                    "captured_on": "2026-11-01", "media_type": "insta360",
                },
            )
            assert response.status_code == 201
            pin_id = response.json()["id"]
            pin_route = f"{project_route}/pins/{pin_id}"
            assert database_client.post(
                f"{pin_route}/native-upload", headers=headers,
                files={"file": ("audit.insp", image.getvalue(), "application/octet-stream")},
            ).status_code == 200
            assert database_client.post(f"{pin_route}/process", headers=headers).status_code == 200
            preview = database_client.get(pin_route, headers=headers).json()["preview_url"]
            assert preview
            assert database_client.get(preview).status_code == 200
            for upload_route in [f"{pin_route}/upload", f"{project_route}/floor-plan-upload"]:
                assert database_client.post(
                    upload_route, headers=headers,
                    files={"file": ("photo.jpg", image.getvalue(), "image/jpeg")},
                ).status_code == 200
            assert database_client.patch(
                f"{pin_route}/calibration", headers=headers,
                json={"position_x": 0.3, "position_y": 0.6, "note": "Database audit"},
            ).status_code == 200
            assert database_client.patch(pin_route, headers=headers, json={"heading": 180}).status_code == 200
            assert database_client.post(
                f"{project_route}/annotations", headers=headers,
                json={"body": "Audit note", "floor_plan_x": 0.3, "floor_plan_y": 0.6, "pin_id": pin_id},
            ).status_code == 201
            assert len(database_client.get(f"{project_route}/annotations", headers=headers).json()) == 1
            assert database_client.post(
                f"{project_route}/status", headers=headers, json={"status": "ready_for_review"},
            ).status_code == 200
            token = database_client.post(f"{project_route}/share-link", headers=headers).json()["share_token"]
            assert database_client.get(f"/share/{token}").status_code == 200
            assert database_client.get(f"{project_route}/review", headers={"x-user-id": "other"}).status_code == 403
            assert database_client.get("/health/ready").status_code == 200
            assert database_client.delete(pin_route, headers=headers).status_code == 200
            assert database_client.get(f"{project_route}/pins", headers=headers).json() == []
        with TestClient(app) as reopened_client:
            detail = reopened_client.get(project_route, headers=headers).json()
            assert detail["floor_plan"]["filename"] == "photo.jpg"
            assert reopened_client.get(detail["floor_plan"]["media_url"], headers=headers).status_code == 200
        with engine.begin() as connection:
            from sqlalchemy import text

            connection.execute(text("UPDATE projects SET floor_plan_json = NULL"))
        with TestClient(app) as legacy_client:
            recovered = legacy_client.get(project_route, headers=headers).json()["floor_plan"]
            assert recovered["filename"] == "photo.jpg"
            with api.SessionLocal() as db:
                assert db.get(api.ProjectRecord, project_id).floor_plan_json is not None
    finally:
        engine.dispose()


def test_existing_project_table_gets_floor_plan_column(monkeypatch, tmp_path) -> None:
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import sessionmaker

    from app import main as api

    engine = create_engine(
        f"sqlite:///{tmp_path / 'legacy.sqlite'}", connect_args={"check_same_thread": False},
    )
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE projects (id VARCHAR(64) PRIMARY KEY, owner_id VARCHAR(128) NOT NULL, "
            "title VARCHAR(255) NOT NULL, description VARCHAR(1000), status VARCHAR(64) NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO projects VALUES ('legacy', 'demo', 'Existing project', NULL, 'draft')"
        ))
    monkeypatch.setattr(api, "PERSISTENCE_MODE", "database")
    monkeypatch.setattr(api, "engine", engine)
    monkeypatch.setattr(api, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(api, "SEED_DEMO_DATA", False)
    try:
        with TestClient(app) as migrated_client:
            response = migrated_client.get("/projects/legacy")
            assert response.status_code == 200
            assert response.json()["title"] == "Existing project"
            assert response.json()["floor_plan"] is None
            assert "floor_plan_json" in {column["name"] for column in inspect(engine).get_columns("projects")}
    finally:
        engine.dispose()


def test_legacy_spaces_plan_is_recovered_once_from_project_scoped_pages(monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone
    from unittest.mock import Mock

    from app import main as api

    reset_demo_store()
    project_id = client.post("/projects", json={"title": "Legacy Spaces plan"}).json()["id"]
    prefix = f"floorplans/{project_id}/"
    now = datetime.now(timezone.utc)
    storage = Mock()
    paginator = storage.get_paginator.return_value
    paginator.paginate.return_value = [
        {"Contents": [{"Key": f"{prefix}older.pdf", "LastModified": now - timedelta(days=1), "Size": 10}]},
        {"Contents": [
            {"Key": f"{prefix}latest.png", "LastModified": now, "Size": 20},
            {"Key": "floorplans/other/private.png", "LastModified": now + timedelta(days=1), "Size": 20},
            {"Key": f"{prefix}unrelated.txt", "LastModified": now + timedelta(days=1), "Size": 20},
        ]},
    ]
    monkeypatch.setattr(api, "STORAGE_BACKEND", "s3")
    monkeypatch.setattr(api, "_s3_client", lambda: storage)
    monkeypatch.setenv("S3_BUCKET", "test-private-bucket")
    for _ in range(2):
        detail = client.get(f"/projects/{project_id}").json()
        assert detail["floor_plan"]["media_key"] == f"{prefix}latest.png"
        assert detail["floor_plan"]["content_type"] == "image/png"
    paginator.paginate.assert_called_once_with(Bucket="test-private-bucket", Prefix=prefix)


def test_legacy_plan_storage_failure_does_not_hide_project(monkeypatch) -> None:
    from app import main as api

    reset_demo_store()
    project_id = client.post("/projects", json={"title": "Still accessible"}).json()["id"]
    monkeypatch.setattr(api, "STORAGE_BACKEND", "s3")

    def unavailable_storage():
        raise RuntimeError("Storage unavailable")

    monkeypatch.setattr(api, "_s3_client", unavailable_storage)
    response = client.get(f"/projects/{project_id}")
    assert response.status_code == 200
    assert response.json()["floor_plan"] is None
