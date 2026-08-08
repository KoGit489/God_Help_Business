from fastapi.testclient import TestClient

from app.main import app, reset_demo_store


client = TestClient(app)


def test_create_project_and_pin_flow() -> None:
    reset_demo_store()
    project_response = client.post(
        "/projects",
        json={"title": "North Site", "description": "Initial field capture"},
    )
    assert project_response.status_code == 201

    project = project_response.json()
    assert project["title"] == "North Site"
    assert project["pin_count"] == 0

    pin_response = client.post(
        f"/projects/{project['id']}/pins",
        json={
            "latitude": 5.6037,
            "longitude": -0.1870,
            "heading": 45.0,
            "captured_on": "2026-08-07",
            "photo_key": "photos/001.jpg",
        },
    )
    assert pin_response.status_code == 201

    pin = pin_response.json()
    assert pin["project_id"] == project["id"]
    assert pin["heading"] == 45.0

    pins_response = client.get(f"/projects/{project['id']}/pins")
    assert pins_response.status_code == 200
    pins = pins_response.json()
    assert len(pins) == 1
    assert pins[0]["photo_key"] == "photos/001.jpg"


def test_list_projects_and_fetch_pin_detail() -> None:
    reset_demo_store()

    created_project = client.post(
        "/projects",
        json={"title": "West Site", "description": "Another capture"},
    ).json()

    created_pin = client.post(
        f"/projects/{created_project['id']}/pins",
        json={
            "latitude": 5.55,
            "longitude": -0.25,
            "heading": 90.0,
            "captured_on": "2026-08-08",
            "photo_key": "photos/002.jpg",
        },
    ).json()

    projects_response = client.get("/projects")
    assert projects_response.status_code == 200
    projects = projects_response.json()
    assert len(projects) == 1
    assert projects[0]["title"] == "West Site"

    detail_response = client.get(f"/projects/{created_project['id']}/pins/{created_pin['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == created_pin["id"]


def test_auth_me_returns_demo_user() -> None:
    reset_demo_store()

    response = client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "demo@God_Help_Business.local"
