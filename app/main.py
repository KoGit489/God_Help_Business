from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

load_dotenv()

app = FastAPI(
    title="God_Help_Business API",
    version="0.1.0",
    description="Backend scaffold for a construction field capture MVP.",
)


class HealthResponse(BaseModel):
    status: str
    service: str


class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None


class ProjectResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    pin_count: int
    status: str = "draft"


class ProjectStatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1)


class PinCreateRequest(BaseModel):
    latitude: float
    longitude: float
    heading: float
    captured_on: str
    photo_key: str | None = None


class PinResponse(BaseModel):
    id: str
    project_id: str
    latitude: float
    longitude: float
    heading: float
    captured_on: str
    photo_key: str | None = None


class ProjectDetailResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    pin_count: int
    status: str = "draft"
    pins: list[PinResponse]


class UploadResponse(BaseModel):
    id: str
    photo_key: str


class ShareLinkResponse(BaseModel):
    project_id: str
    share_token: str
    share_link: str


class AuthUserResponse(BaseModel):
    id: str
    email: str
    name: str


projects: dict[str, dict[str, Any]] = {}
pins_by_project: dict[str, list[dict[str, Any]]] = {}
pins_by_id: dict[str, dict[str, Any]] = {}
project_share_tokens: dict[str, str] = {}
share_token_to_project: dict[str, str] = {}


def reset_demo_store() -> None:
    projects.clear()
    pins_by_project.clear()
    pins_by_id.clear()
    project_share_tokens.clear()
    share_token_to_project.clear()


def seed_demo_data() -> None:
    if projects:
        return

    demo_project_id = str(uuid4())
    demo_project = {
        "id": demo_project_id,
        "title": "North Ridge Inspection",
        "description": "Demo project with evidence captured for a review-ready walkthrough.",
    }
    projects[demo_project_id] = demo_project
    pins_by_project[demo_project_id] = [
        {
            "id": str(uuid4()),
            "project_id": demo_project_id,
            "latitude": 5.6037,
            "longitude": -0.1870,
            "heading": 34.0,
            "captured_on": "2026-08-08",
            "photo_key": "uploads/demo/roof.jpg",
        },
        {
            "id": str(uuid4()),
            "project_id": demo_project_id,
            "latitude": 5.6041,
            "longitude": -0.1880,
            "heading": 118.0,
            "captured_on": "2026-08-08",
            "photo_key": "uploads/demo/beam.jpg",
        },
    ]
    pins_by_id.update({pin["id"]: pin for pin in pins_by_project[demo_project_id]})


seed_demo_data()


def build_project_detail(project_id: str) -> ProjectDetailResponse:
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    pin_items = [PinResponse(**pin) for pin in pins_by_project.get(project_id, [])]
    return ProjectDetailResponse(
        id=project["id"],
        title=project["title"],
        description=project.get("description"),
        pin_count=len(pin_items),
        status=project.get("status", "draft"),
        pins=pin_items,
    )


def ensure_project_access(project_id: str, share_token: str | None = None) -> ProjectDetailResponse:
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if share_token is not None:
        expected_token = project_share_tokens.get(project_id)
        if not expected_token or expected_token != share_token:
            raise HTTPException(status_code=403, detail="Invalid share token for this project")

    return build_project_detail(project_id)


@app.get("/", tags=["core"])
def read_root() -> dict[str, str]:
    return {"message": "God_Help_Business API is ready", "docs": "/docs"}


@app.get("/health", response_model=HealthResponse, tags=["core"])
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="god-help-business")


@app.get("/auth/me", response_model=AuthUserResponse, tags=["auth"])
def get_current_user() -> AuthUserResponse:
    return AuthUserResponse(
        id="demo-user",
        email="demo@God_Help_Business.local",
        name="Demo Builder",
    )


@app.post("/projects", response_model=ProjectResponse, status_code=201, tags=["projects"])
def create_project(payload: ProjectCreateRequest) -> ProjectResponse:
    project_id = str(uuid4())
    project = {
        "id": project_id,
        "title": payload.title,
        "description": payload.description,
        "status": "draft",
    }
    projects[project_id] = project
    pins_by_project[project_id] = []
    return ProjectResponse(id=project_id, title=project["title"], description=project["description"], pin_count=0)


@app.get("/projects", response_model=list[ProjectResponse], tags=["projects"])
def list_projects() -> list[ProjectResponse]:
    return [
        ProjectResponse(
            id=project["id"],
            title=project["title"],
            description=project.get("description"),
            pin_count=len(pins_by_project.get(project["id"], [])),
            status=project.get("status", "draft"),
        )
        for project in projects.values()
    ]


@app.get("/projects/{project_id}", response_model=ProjectDetailResponse, tags=["projects"])
def get_project(project_id: str) -> ProjectDetailResponse:
    return build_project_detail(project_id)


@app.get("/projects/{project_id}/review", response_model=ProjectDetailResponse, tags=["projects"])
def get_project_review(project_id: str, share_token: str | None = Query(default=None)) -> ProjectDetailResponse:
    return ensure_project_access(project_id, share_token)


@app.post("/projects/{project_id}/share-link", response_model=ShareLinkResponse, tags=["projects"])
def create_share_link(project_id: str) -> ShareLinkResponse:
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    share_token = project_share_tokens.get(project_id)
    if not share_token:
        share_token = str(uuid4())
        project_share_tokens[project_id] = share_token
        share_token_to_project[share_token] = project_id

    return ShareLinkResponse(
        project_id=project_id,
        share_token=share_token,
        share_link=f"http://127.0.0.1:8000/share/{share_token}",
    )


@app.get("/share/{share_token}", response_model=ProjectDetailResponse, tags=["projects"])
def open_shared_project(share_token: str) -> ProjectDetailResponse:
    project_id = share_token_to_project.get(share_token)
    if not project_id:
        raise HTTPException(status_code=404, detail="Share link not found")

    return build_project_detail(project_id)


@app.post("/projects/{project_id}/status", response_model=ProjectResponse, tags=["projects"])
def update_project_status(project_id: str, payload: ProjectStatusUpdateRequest) -> ProjectResponse:
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    projects[project_id]["status"] = payload.status
    return ProjectResponse(
        id=projects[project_id]["id"],
        title=projects[project_id]["title"],
        description=projects[project_id].get("description"),
        pin_count=len(pins_by_project.get(project_id, [])),
        status=projects[project_id]["status"],
    )


@app.post("/projects/{project_id}/pins", response_model=PinResponse, status_code=201, tags=["pins"])
def create_pin(project_id: str, payload: PinCreateRequest) -> PinResponse:
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    pin_id = str(uuid4())
    pin = {
        "id": pin_id,
        "project_id": project_id,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "heading": payload.heading,
        "captured_on": payload.captured_on,
        "photo_key": payload.photo_key,
    }
    pins_by_project[project_id].append(pin)
    pins_by_id[pin_id] = pin
    return PinResponse(**pin)


@app.get("/projects/{project_id}/pins", response_model=list[PinResponse], tags=["pins"])
def list_pins(project_id: str) -> list[PinResponse]:
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    return [PinResponse(**pin) for pin in pins_by_project.get(project_id, [])]


@app.get("/projects/{project_id}/pins/{pin_id}", response_model=PinResponse, tags=["pins"])
def get_pin(project_id: str, pin_id: str) -> PinResponse:
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    pin = pins_by_id.get(pin_id)
    if not pin or pin["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Pin not found")

    return PinResponse(**pin)


@app.post("/projects/{project_id}/pins/{pin_id}/upload", response_model=UploadResponse, tags=["pins"])
def upload_pin_photo(project_id: str, pin_id: str, file: UploadFile = File(...)) -> UploadResponse:
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    pin = pins_by_id.get(pin_id)
    if not pin or pin["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Pin not found")

    if file.filename is None:
        raise HTTPException(status_code=400, detail="A filename is required")

    photo_key = f"uploads/{project_id}/{pin_id}/{Path(file.filename).name}"
    pin["photo_key"] = photo_key
    return UploadResponse(id=pin_id, photo_key=photo_key)
