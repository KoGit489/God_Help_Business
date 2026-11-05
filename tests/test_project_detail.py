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
    sample_file.write_bytes(b"fake-image")

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
    monkeypatch.setattr(api.capture_processor, "provider", "slam")
    monkeypatch.setattr(
        api.capture_processor,
        "extract_insp_preview",
        lambda path: {"preview_available": True, "preview_data": b"preview", "preview_format": "jpeg"},
    )

    def fake_slam_pipeline(*, video_path):
        assert video_path.is_file()
        return {
            "available": True,
            "poses": [
                {"x": 0.0, "y": 0.0, "heading": 0.0, "confidence": 0.8},
                {"x": 2.0, "y": 1.0, "heading": 30.0, "confidence": 0.8},
            ],
            "pose_count": 2,
            "loop_closures": [],
            "optimized": False,
            "confidence": 0.8,
            "message": "Fixture SLAM completed.",
        }

    monkeypatch.setattr(api.capture_processor, "run_slam_pipeline", fake_slam_pipeline)
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
            native_upload_response = database_client.post(
                f"{pin_route}/native-upload", headers=headers,
                files={"file": ("audit.insp", image.getvalue(), "application/octet-stream")},
            )
            assert native_upload_response.status_code == 200
            assert native_upload_response.json()["native_file_key"].endswith("audit.insp")
            assert database_client.get(pin_route, headers=headers).json()["native_file_key"].endswith("audit.insp")
            preview_process_response = database_client.post(f"{pin_route}/process", headers=headers)
            assert preview_process_response.status_code == 200
            preview = database_client.get(pin_route, headers=headers).json()["preview_url"]
            assert preview, preview_process_response.json().get("preview_error") or preview_process_response.json()
            assert database_client.get(preview).status_code == 200

            slam_pin_response = database_client.post(
                f"{project_route}/pins", headers=headers,
                json={
                    "latitude": 5.51, "longitude": -0.19, "heading": 90,
                    "position_x": 0.5, "position_y": 0.6,
                    "captured_on": "2026-11-01", "media_type": "insta360",
                },
            )
            slam_pin_id = slam_pin_response.json()["id"]
            slam_pin_route = f"{project_route}/pins/{slam_pin_id}"
            assert database_client.post(
                f"{slam_pin_route}/native-upload", headers=headers,
                files={"file": ("route.insv", image.getvalue(), "application/octet-stream")},
            ).status_code == 200
            slam_response = database_client.post(f"{slam_pin_route}/process", headers=headers)
            assert slam_response.status_code == 200
            assert slam_response.json()["slam"]["pose_count"] == 2
            with api.SessionLocal() as db:
                slam_record = db.get(api.PinRecord, slam_pin_id)
                assert slam_record is not None
                assert len(slam_record.waypoints_json)
                assert slam_record.auto_position_x is not None
                assert slam_record.auto_position_y is not None

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
            remaining_pins = database_client.get(f"{project_route}/pins", headers=headers).json()
            assert [pin["id"] for pin in remaining_pins] == [slam_pin_id]
            assert database_client.delete(slam_pin_route, headers=headers).status_code == 200
            assert database_client.get(f"{project_route}/pins", headers=headers).json() == []
    finally:
        engine.dispose()
