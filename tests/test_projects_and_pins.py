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


def test_project_ownership_is_enforced_by_user_id() -> None:
    reset_demo_store()

    created = client.post(
        "/projects",
        json={"title": "Owned Site", "description": "Private field record"},
        headers={"X-User-Id": "user-alpha"},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    forbidden = client.get(
        f"/projects/{project_id}",
        headers={"X-User-Id": "user-beta"},
    )
    assert forbidden.status_code == 403

    allowed = client.get(
        f"/projects/{project_id}",
        headers={"X-User-Id": "user-alpha"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["title"] == "Owned Site"


def test_pin_accepts_360_native_media_metadata() -> None:
    reset_demo_store()

    project = client.post(
        "/projects",
        json={"title": "360 Site", "description": "Native camera capture"},
        headers={"X-User-Id": "user-alpha"},
    ).json()

    pin = client.post(
        f"/projects/{project['id']}/pins",
        json={
            "latitude": 5.6037,
            "longitude": -0.1870,
            "heading": 180.0,
            "captured_on": "2026-08-11",
            "photo_key": "photos/360.jpg",
            "media_type": "insta360",
            "native_file_key": "raw/360/clip.insp",
            "thumbnail_key": "thumbs/360/clip.jpg",
        },
        headers={"X-User-Id": "user-alpha"},
    )
    assert pin.status_code == 201
    payload = pin.json()
    assert payload["media_type"] == "insta360"
    assert payload["native_file_key"] == "raw/360/clip.insp"
    assert payload["thumbnail_key"] == "thumbs/360/clip.jpg"


def test_manual_insta360_native_upload_is_supported() -> None:
    reset_demo_store()

    project = client.post(
        "/projects",
        json={"title": "Manual Upload Site", "description": "360 upload workflow"},
        headers={"X-User-Id": "user-alpha"},
    ).json()

    pin = client.post(
        f"/projects/{project['id']}/pins",
        json={
            "latitude": 5.6134,
            "longitude": -0.1821,
            "heading": 220.0,
            "captured_on": "2026-08-11",
            "photo_key": "photos/manual.jpg",
            "media_type": "insta360",
        },
        headers={"X-User-Id": "user-alpha"},
    ).json()

    upload_response = client.post(
        f"/projects/{project['id']}/pins/{pin['id']}/native-upload",
        files={"file": ("capture.insp", b"fake-insta360-file", "application/octet-stream")},
        headers={"X-User-Id": "user-alpha"},
    )

    assert upload_response.status_code == 200
    payload = upload_response.json()
    assert payload["native_file_key"].endswith("capture.insp")


def test_camera_status_exposes_browser_ready_mode() -> None:
    reset_demo_store()

    response = client.get("/camera/insta360/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] in {"manual_upload", "sdk"}
    assert payload["supports_web_browser"] is True
    assert payload["supports_native_app"] in {True, False}


def test_camera_adapter_reports_sdk_wiring_readiness() -> None:
    reset_demo_store()

    response = client.get("/camera/insta360/adapter")
    assert response.status_code == 200
    payload = response.json()
    assert "mode" in payload
    assert "supports_direct_sdk" in payload
    assert "recommended_action" in payload
    assert "real_time_feed_supported" in payload


def test_browser_frontend_and_cors_are_available() -> None:
    reset_demo_store()

    index_response = client.get("/index.html")
    assert index_response.status_code == 200
    assert "CASAI MVP" in index_response.text

    preflight = client.options(
        "/projects",
        headers={
            "Origin": "http://192.168.1.10:8000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") in {"*", "http://192.168.1.10:8000"}


def test_floor_plan_upload_and_pin_position_are_available() -> None:
    reset_demo_store()

    project = client.post("/projects", json={"title": "Plan Demo"}).json()
    upload = client.post(
        f"/projects/{project['id']}/floor-plan-upload",
        files={"file": ("plan.png", b"fake-plan", "image/png")},
    )
    assert upload.status_code == 200
    assert upload.json()["media_url"].endswith(f"/media/floorplans/{project['id']}/plan.png")
    media_response = client.get(upload.json()["media_url"])
    assert media_response.status_code == 200
    assert media_response.content == b"fake-plan"

    floorplan_page = client.get("/floorplan.html")
    assert floorplan_page.status_code == 200
    assert "Floor plan walkthrough" in floorplan_page.text

    pin = client.post(
        f"/projects/{project['id']}/pins",
        json={
            "latitude": 5.56,
            "longitude": -0.24,
            "heading": 90,
            "position_x": 0.25,
            "position_y": 0.75,
            "captured_on": "2026-08-20",
            "media_type": "insta360",
        },
    )
    assert pin.status_code == 201
    assert pin.json()["position_x"] == 0.25
    assert pin.json()["position_y"] == 0.75


def test_capture_processing_boundary_accepts_telemetry_metadata() -> None:
    reset_demo_store()

    project = client.post("/projects", json={"title": "Telemetry Demo"}).json()
    pin = client.post(
        f"/projects/{project['id']}/pins",
        json={
            "latitude": 5.56,
            "longitude": -0.24,
            "heading": 90,
            "captured_on": "2026-08-20",
            "telemetry": {"source": "future_insp_parser", "gyro": {"x": 0.1}},
        },
    )
    assert pin.status_code == 201
    assert pin.json()["telemetry"]["source"] == "future_insp_parser"
    assert pin.json()["processing_status"] == "metadata_received"

    status = client.get("/capture-processing/status")
    assert status.status_code == 200
    assert status.json()["status"] == "ready"
    assert "calibrated_dead_reckoning" in status.json()["capabilities"]

    processed = client.post(f"/projects/{project['id']}/pins/{pin.json()['id']}/process")
    assert processed.status_code == 200
    assert processed.json()["telemetry_received"] is True


def test_insp_parser_extracts_timestamped_route_and_motion_metrics() -> None:
    reset_demo_store()

    from app.capture_processing import CaptureProcessor

    sample = b"""
    <Insta360>
      <FileType>INSP</FileType>
      <Device>ONE X2</Device>
      <Session>
        <StartTime>2026-08-20T09:15:00Z</StartTime>
        <Track>
          <Point time="2026-08-20T09:15:00Z" x="0.0" y="0.0" z="0.0" yaw="30.0" pitch="5.0" roll="2.0" speed="0.45" />
          <Point time="2026-08-20T09:15:05Z" x="1.2" y="0.8" z="0.1" yaw="35.0" pitch="6.0" roll="1.5" speed="0.50" />
          <Point time="2026-08-20T09:15:10Z" x="2.5" y="1.6" z="0.2" yaw="42.0" pitch="7.0" roll="1.0" speed="0.52" />
        </Track>
      </Session>
    </Insta360>
    """

    telemetry = CaptureProcessor().parse_insp_payload(sample)
    assert telemetry["source"] == "insp_parser"
    assert telemetry["device"] == "ONE X2"
    assert len(telemetry["route"]) == 3
    assert telemetry["route"][0]["time"] == "2026-08-20T09:15:00Z"
    assert telemetry["motion"]["average_speed_mps"] > 0
    assert telemetry["confidence"] >= 0.5


def test_route_estimator_normalizes_telemetry_into_floorplan_waypoints() -> None:
    reset_demo_store()

    from app.capture_processing import CaptureProcessor

    sample_telemetry = {
        "source": "insp_parser",
        "device": "ONE X2",
        "file_type": "INSP",
        "start_time": "2026-08-20T09:15:00Z",
        "route": [
            {"time": "2026-08-20T09:15:00Z", "x": 0.0, "y": 0.0, "z": 0.0, "yaw": 30.0, "pitch": 5.0, "roll": 2.0, "speed_mps": 0.45},
            {"time": "2026-08-20T09:15:05Z", "x": 1.2, "y": 0.8, "z": 0.1, "yaw": 35.0, "pitch": 6.0, "roll": 1.5, "speed_mps": 0.50},
            {"time": "2026-08-20T09:15:10Z", "x": 2.5, "y": 1.6, "z": 0.2, "yaw": 42.0, "pitch": 7.0, "roll": 1.0, "speed_mps": 0.52},
        ],
        "motion": {"samples": 3, "average_speed_mps": 0.4917, "max_speed_mps": 0.52},
        "confidence": 0.72,
    }

    processor = CaptureProcessor()
    waypoint_result = processor.estimate_route_waypoints(sample_telemetry)

    assert waypoint_result["waypoints"] is not None
    assert len(waypoint_result["waypoints"]) == 3

    for wp in waypoint_result["waypoints"]:
        assert 0.0 <= wp["position_x"] <= 1.0
        assert 0.0 <= wp["position_y"] <= 1.0
        assert wp["heading"] is not None
        assert wp["confidence"] > 0

    assert waypoint_result["bounds"] is not None
    assert "min_x" in waypoint_result["bounds"]
    assert "max_x" in waypoint_result["bounds"]
    assert waypoint_result["route_confidence"] > 0


def test_capture_processing_stores_waypoints_on_pin_when_telemetry_is_processed() -> None:
    reset_demo_store()

    project = client.post("/projects", json={"title": "Route Demo"}).json()
    pin = client.post(
        f"/projects/{project['id']}/pins",
        json={
            "latitude": 5.56,
            "longitude": -0.24,
            "heading": 90,
            "captured_on": "2026-08-20",
            "telemetry": {
                "source": "insp_parser",
                "device": "ONE X2",
                "route": [
                    {"time": "2026-08-20T09:15:00Z", "x": 0.0, "y": 0.0, "z": 0.0, "yaw": 30.0, "pitch": 5.0, "roll": 2.0, "speed_mps": 0.45},
                    {"time": "2026-08-20T09:15:05Z", "x": 1.2, "y": 0.8, "z": 0.1, "yaw": 35.0, "pitch": 6.0, "roll": 1.5, "speed_mps": 0.50},
                    {"time": "2026-08-20T09:15:10Z", "x": 2.5, "y": 1.6, "z": 0.2, "yaw": 42.0, "pitch": 7.0, "roll": 1.0, "speed_mps": 0.52},
                ],
                "motion": {"samples": 3, "average_speed_mps": 0.4917, "max_speed_mps": 0.52},
                "confidence": 0.72,
            },
        },
    ).json()

    processed = client.post(f"/projects/{project['id']}/pins/{pin['id']}/process")
    assert processed.status_code == 200
    assert processed.json()["telemetry_received"] is True

    updated_pin = client.get(f"/projects/{project['id']}/pins/{pin['id']}")
    assert updated_pin.status_code == 200
    pin_data = updated_pin.json()
    assert pin_data["waypoints"] is not None
    assert len(pin_data["waypoints"]) == 3
    assert pin_data["waypoints"][0]["position_x"] is not None
    assert pin_data["waypoints"][0]["position_y"] is not None
