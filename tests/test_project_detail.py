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
