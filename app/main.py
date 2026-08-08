from __future__ import annotations

from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
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
    pins: list[PinResponse]


class AuthUserResponse(BaseModel):
    id: str
    email: str
    name: str


projects: dict[str, dict[str, Any]] = {}
pins_by_project: dict[str, list[dict[str, Any]]] = {}
pins_by_id: dict[str, dict[str, Any]] = {}


def reset_demo_store() -> None:
    projects.clear()
    pins_by_project.clear()
    pins_by_id.clear()


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
        )
        for project in projects.values()
    ]


@app.get("/projects/{project_id}", response_model=ProjectDetailResponse, tags=["projects"])
def get_project(project_id: str) -> ProjectDetailResponse:
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    pin_items = [PinResponse(**pin) for pin in pins_by_project.get(project_id, [])]
    return ProjectDetailResponse(
        id=project["id"],
        title=project["title"],
        description=project.get("description"),
        pin_count=len(pin_items),
        pins=pin_items,
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
