from fastapi.testclient import TestClient

from app.main import app, reset_demo_store


client = TestClient(app)


def test_share_link_grants_access_to_only_one_project() -> None:
    reset_demo_store()

    project = client.post(
        "/projects",
        json={"title": "Shared Review", "description": "Phase 3 demo"},
    ).json()

    share_response = client.post(f"/projects/{project['id']}/share-link")
    assert share_response.status_code == 200
    share_payload = share_response.json()
    assert share_payload["share_token"]
    assert share_payload["share_link"].endswith(share_payload["share_token"])

    public_response = client.get(f"/share/{share_payload['share_token']}")
    assert public_response.status_code == 200
    assert public_response.json()["id"] == project["id"]

    invalid_response = client.get("/share/not-a-real-token")
    assert invalid_response.status_code == 404


def test_project_review_requires_matching_share_token() -> None:
    reset_demo_store()

    first_project = client.post(
        "/projects",
        json={"title": "First Project", "description": "Accessible share"},
    ).json()
    second_project = client.post(
        "/projects",
        json={"title": "Second Project", "description": "Should stay private"},
    ).json()

    first_share = client.post(f"/projects/{first_project['id']}/share-link").json()

    wrong_project_response = client.get(
        f"/projects/{second_project['id']}/review",
        params={"share_token": first_share["share_token"]},
    )
    assert wrong_project_response.status_code == 403

    right_project_response = client.get(
        f"/projects/{first_project['id']}/review",
        params={"share_token": first_share["share_token"]},
    )
    assert right_project_response.status_code == 200
    assert right_project_response.json()["id"] == first_project["id"]


def test_project_status_can_be_updated_for_review() -> None:
    reset_demo_store()

    project = client.post(
        "/projects",
        json={"title": "Approval Flow", "description": "Ready for review"},
    ).json()

    update_response = client.post(
        f"/projects/{project['id']}/status",
        json={"status": "ready_for_review"},
    )
    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["status"] == "ready_for_review"

    detail_response = client.get(f"/projects/{project['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "ready_for_review"
