from __future__ import annotations

import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, PinRecord, ProjectRecord, ShareLinkRecord

load_dotenv()

logger = logging.getLogger("god_help_business.api")
logging.basicConfig(level=logging.INFO)

PERSISTENCE_MODE = os.getenv("APP_PERSISTENCE", "memory").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./god_help_business.db")
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").strip().lower()
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploaded_files"))
PUBLIC_SHARE_BASE_URL = os.getenv("PUBLIC_SHARE_BASE_URL", "http://127.0.0.1:5500/frontend/share.html")
SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "true").strip().lower() in {"1", "true", "yes"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    if PERSISTENCE_MODE == "database":
        try:
            Base.metadata.create_all(bind=engine)
        except SQLAlchemyError as exc:
            logger.exception("Database startup failed")
            raise RuntimeError("Database initialization failed") from exc
    _seed_demo_data()
    yield


app = FastAPI(
    title="God_Help_Business API",
    version="0.2.0",
    description="Backend scaffold for a construction field capture MVP.",
    lifespan=lifespan,
)


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadinessResponse(BaseModel):
    status: str
    persistence_mode: str
    storage_backend: str


class ErrorEnvelope(BaseModel):
    error: dict[str, Any]


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
    media_type: str | None = None
    native_file_key: str | None = None
    thumbnail_key: str | None = None


class PinResponse(BaseModel):
    id: str
    project_id: str
    latitude: float
    longitude: float
    heading: float
    captured_on: str
    photo_key: str | None = None
    media_type: str | None = None
    native_file_key: str | None = None
    thumbnail_key: str | None = None


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


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

projects: dict[str, dict[str, Any]] = {}
pins_by_project: dict[str, list[dict[str, Any]]] = {}
pins_by_id: dict[str, dict[str, Any]] = {}
project_share_tokens: dict[str, str] = {}
share_token_to_project: dict[str, str] = {}


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "type": "validation_error",
                "message": "Request validation failed",
                "request_id": request.state.request_id,
                "details": exc.errors(),
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": "http_error",
                "message": exc.detail,
                "request_id": request.state.request_id,
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception for request %s", request.state.request_id)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "type": "internal_error",
                "message": "An unexpected error occurred",
                "request_id": request.state.request_id,
            }
        },
    )


def reset_demo_store() -> None:
    projects.clear()
    pins_by_project.clear()
    pins_by_id.clear()
    project_share_tokens.clear()
    share_token_to_project.clear()

    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            db.query(ShareLinkRecord).delete()
            db.query(PinRecord).delete()
            db.query(ProjectRecord).delete()
            db.commit()


def _create_share_url(token: str) -> str:
    base = PUBLIC_SHARE_BASE_URL.rstrip("/")
    if base.endswith("share.html"):
        return f"{base}?token={token}"
    return f"{base}/share/{token}"


def _store_photo(project_id: str, pin_id: str, upload: UploadFile) -> str:
    filename = Path(upload.filename or "upload.bin").name
    photo_key = f"uploads/{project_id}/{pin_id}/{filename}"

    if STORAGE_BACKEND == "s3":
        try:
            import boto3
        except ImportError as exc:
            raise HTTPException(status_code=500, detail="boto3 is required for S3 storage backend") from exc

        bucket = os.getenv("S3_BUCKET")
        region = os.getenv("S3_REGION")
        endpoint_url = os.getenv("S3_ENDPOINT_URL")
        if not bucket:
            raise HTTPException(status_code=500, detail="S3_BUCKET is required for S3 storage backend")

        s3_client = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)
        upload.file.seek(0)
        s3_client.upload_fileobj(upload.file, bucket, photo_key)
        return photo_key

    destination = UPLOAD_DIR / project_id / pin_id
    destination.mkdir(parents=True, exist_ok=True)
    output_file = destination / filename
    upload.file.seek(0)
    with output_file.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)

    return photo_key


def _pin_response_from_record(record: PinRecord) -> PinResponse:
    return PinResponse(
        id=record.id,
        project_id=record.project_id,
        latitude=record.latitude,
        longitude=record.longitude,
        heading=record.heading,
        captured_on=record.captured_on,
        photo_key=record.photo_key,
        media_type=record.media_type,
        native_file_key=record.native_file_key,
        thumbnail_key=record.thumbnail_key,
    )


def _project_response_from_record(db: Session, record: ProjectRecord) -> ProjectResponse:
    pin_count = db.query(PinRecord).filter(PinRecord.project_id == record.id).count()
    return ProjectResponse(
        id=record.id,
        title=record.title,
        description=record.description,
        pin_count=pin_count,
        status=record.status,
    )


def _project_detail_from_record(db: Session, record: ProjectRecord) -> ProjectDetailResponse:
    pins = db.query(PinRecord).filter(PinRecord.project_id == record.id).all()
    pin_items = [_pin_response_from_record(pin) for pin in pins]
    return ProjectDetailResponse(
        id=record.id,
        title=record.title,
        description=record.description,
        pin_count=len(pin_items),
        status=record.status,
        pins=pin_items,
    )


def _build_project_detail_memory(project_id: str) -> ProjectDetailResponse:
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


def _build_project_detail(project_id: str) -> ProjectDetailResponse:
    if PERSISTENCE_MODE != "database":
        return _build_project_detail_memory(project_id)

    with SessionLocal() as db:
        project = db.get(ProjectRecord, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return _project_detail_from_record(db, project)


def _get_user_id(request: Request) -> str:
    user_id = request.headers.get("x-user-id")
    return user_id or "demo"


def _ensure_project_ownership(project_id: str, user_id: str) -> None:
    if user_id in {"demo", "demo-user"}:
        return

    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            project = db.get(ProjectRecord, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            if project.owner_id != user_id:
                raise HTTPException(status_code=403, detail="Project does not belong to this user")
        return

    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.get("owner_id") != user_id:
        raise HTTPException(status_code=403, detail="Project does not belong to this user")


def _ensure_project_access(project_id: str, share_token: str | None = None, user_id: str | None = None) -> ProjectDetailResponse:
    if PERSISTENCE_MODE != "database":
        project = projects.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if user_id and project.get("owner_id") and project.get("owner_id") != user_id and user_id not in {"demo", "demo-user"}:
            raise HTTPException(status_code=403, detail="Project does not belong to this user")

        if share_token is not None:
            expected_token = project_share_tokens.get(project_id)
            if not expected_token or expected_token != share_token:
                raise HTTPException(status_code=403, detail="Invalid share token for this project")
        return _build_project_detail_memory(project_id)

    with SessionLocal() as db:
        project = db.get(ProjectRecord, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if user_id and user_id not in {"demo", "demo-user"} and project.owner_id != user_id:
            raise HTTPException(status_code=403, detail="Project does not belong to this user")

        if share_token is not None:
            link = db.scalar(select(ShareLinkRecord).where(ShareLinkRecord.project_id == project_id))
            if not link or link.token != share_token:
                raise HTTPException(status_code=403, detail="Invalid share token for this project")

        return _project_detail_from_record(db, project)


def _seed_demo_data() -> None:
    if not SEED_DEMO_DATA:
        return

    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            existing = db.query(ProjectRecord).first()
            if existing:
                return

            project_id = str(uuid4())
            project = ProjectRecord(
                id=project_id,
                owner_id="demo-user",
                title="North Ridge Inspection",
                description="Demo project with evidence captured for a review-ready walkthrough.",
                status="ready_for_review",
            )
            pin_a = PinRecord(
                id=str(uuid4()),
                project_id=project_id,
                latitude=5.6037,
                longitude=-0.1870,
                heading=34.0,
                captured_on="2026-08-08",
                photo_key="uploads/demo/roof.jpg",
                media_type="photo",
                native_file_key=None,
                thumbnail_key=None,
            )
            pin_b = PinRecord(
                id=str(uuid4()),
                project_id=project_id,
                latitude=5.6041,
                longitude=-0.1880,
                heading=118.0,
                captured_on="2026-08-08",
                photo_key="uploads/demo/beam.jpg",
                media_type="photo",
                native_file_key=None,
                thumbnail_key=None,
            )
            db.add_all([project, pin_a, pin_b])
            db.commit()
            return

    if projects:
        return

    demo_project_id = str(uuid4())
    demo_project = {
        "id": demo_project_id,
        "owner_id": "demo-user",
        "title": "North Ridge Inspection",
        "description": "Demo project with evidence captured for a review-ready walkthrough.",
        "status": "ready_for_review",
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
            "media_type": "photo",
            "native_file_key": None,
            "thumbnail_key": None,
        },
        {
            "id": str(uuid4()),
            "project_id": demo_project_id,
            "latitude": 5.6041,
            "longitude": -0.1880,
            "heading": 118.0,
            "captured_on": "2026-08-08",
            "photo_key": "uploads/demo/beam.jpg",
            "media_type": "photo",
            "native_file_key": None,
            "thumbnail_key": None,
        },
    ]
    pins_by_id.update({pin["id"]: pin for pin in pins_by_project[demo_project_id]})


@app.get("/", tags=["core"])
def read_root() -> dict[str, str]:
    return {"message": "God_Help_Business API is ready", "docs": "/docs"}


@app.get("/health", response_model=HealthResponse, tags=["core"])
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="god-help-business")


@app.get("/health/ready", response_model=ReadinessResponse, tags=["core"])
def readiness_check() -> ReadinessResponse:
    if PERSISTENCE_MODE == "database":
        try:
            with SessionLocal() as db:
                db.execute(select(ProjectRecord.id).limit(1))
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database is not reachable") from exc

    if STORAGE_BACKEND == "local":
        try:
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=503, detail="Local storage path is not writable") from exc

    return ReadinessResponse(status="ready", persistence_mode=PERSISTENCE_MODE, storage_backend=STORAGE_BACKEND)


@app.get("/auth/me", response_model=AuthUserResponse, tags=["auth"])
def get_current_user(request: Request) -> AuthUserResponse:
    user_id = _get_user_id(request)
    return AuthUserResponse(
        id="demo-user",
        email="demo@God_Help_Business.local",
        name="Demo Builder",
    )


@app.post("/projects", response_model=ProjectResponse, status_code=201, tags=["projects"])
def create_project(payload: ProjectCreateRequest, request: Request) -> ProjectResponse:
    user_id = _get_user_id(request)
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            project = ProjectRecord(
                id=str(uuid4()),
                owner_id=user_id,
                title=payload.title,
                description=payload.description,
                status="draft",
            )
            db.add(project)
            db.commit()
            return ProjectResponse(
                id=project.id,
                title=project.title,
                description=project.description,
                pin_count=0,
                status=project.status,
            )

    project_id = str(uuid4())
    project = {
        "id": project_id,
        "owner_id": user_id,
        "title": payload.title,
        "description": payload.description,
        "status": "draft",
    }
    projects[project_id] = project
    pins_by_project[project_id] = []
    return ProjectResponse(id=project_id, title=project["title"], description=project["description"], pin_count=0, status="draft")


@app.get("/projects", response_model=list[ProjectResponse], tags=["projects"])
def list_projects(request: Request) -> list[ProjectResponse]:
    user_id = _get_user_id(request)
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            items = db.query(ProjectRecord).filter(ProjectRecord.owner_id == user_id).all()
            return [_project_response_from_record(db, project) for project in items]

    return [
        ProjectResponse(
            id=project["id"],
            title=project["title"],
            description=project.get("description"),
            pin_count=len(pins_by_project.get(project["id"], [])),
            status=project.get("status", "draft"),
        )
        for project in projects.values()
        if project.get("owner_id") == user_id or user_id == "demo-user"
    ]


@app.get("/projects/{project_id}", response_model=ProjectDetailResponse, tags=["projects"])
def get_project(project_id: str, request: Request) -> ProjectDetailResponse:
    _ensure_project_ownership(project_id, _get_user_id(request))
    return _build_project_detail(project_id)


@app.get("/projects/{project_id}/review", response_model=ProjectDetailResponse, tags=["projects"])
def get_project_review(project_id: str, request: Request, share_token: str | None = Query(default=None)) -> ProjectDetailResponse:
    return _ensure_project_access(project_id, share_token, _get_user_id(request))


@app.post("/projects/{project_id}/status", response_model=ProjectResponse, tags=["projects"])
def update_project_status(project_id: str, payload: ProjectStatusUpdateRequest, request: Request) -> ProjectResponse:
    user_id = _get_user_id(request)
    _ensure_project_ownership(project_id, user_id)
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            project = db.get(ProjectRecord, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            project.status = payload.status
            db.commit()
            return _project_response_from_record(db, project)

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


@app.post("/projects/{project_id}/share-link", response_model=ShareLinkResponse, tags=["projects"])
def create_share_link(project_id: str, request: Request) -> ShareLinkResponse:
    user_id = _get_user_id(request)
    _ensure_project_ownership(project_id, user_id)
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            project = db.get(ProjectRecord, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            share_link = db.scalar(select(ShareLinkRecord).where(ShareLinkRecord.project_id == project_id))
            if not share_link:
                share_link = ShareLinkRecord(token=str(uuid4()), project_id=project_id)
                db.add(share_link)
                db.commit()

            return ShareLinkResponse(
                project_id=project_id,
                share_token=share_link.token,
                share_link=_create_share_url(share_link.token),
            )

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
        share_link=_create_share_url(share_token),
    )


@app.get("/share/{share_token}", response_model=ProjectDetailResponse, tags=["projects"])
def open_shared_project(share_token: str) -> ProjectDetailResponse:
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            link = db.get(ShareLinkRecord, share_token)
            if not link:
                raise HTTPException(status_code=404, detail="Share link not found")

            project = db.get(ProjectRecord, link.project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            return _project_detail_from_record(db, project)

    project_id = share_token_to_project.get(share_token)
    if not project_id:
        raise HTTPException(status_code=404, detail="Share link not found")

    return _build_project_detail_memory(project_id)


@app.post("/projects/{project_id}/pins", response_model=PinResponse, status_code=201, tags=["pins"])
def create_pin(project_id: str, payload: PinCreateRequest, request: Request) -> PinResponse:
    user_id = _get_user_id(request)
    _ensure_project_ownership(project_id, user_id)
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            project = db.get(ProjectRecord, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            pin = PinRecord(
                id=str(uuid4()),
                project_id=project_id,
                latitude=payload.latitude,
                longitude=payload.longitude,
                heading=payload.heading,
                captured_on=payload.captured_on,
                photo_key=payload.photo_key,
                media_type=payload.media_type or "photo",
                native_file_key=payload.native_file_key,
                thumbnail_key=payload.thumbnail_key,
            )
            db.add(pin)
            db.commit()
            return _pin_response_from_record(pin)

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
        "media_type": payload.media_type or "photo",
        "native_file_key": payload.native_file_key,
        "thumbnail_key": payload.thumbnail_key,
    }
    pins_by_project[project_id].append(pin)
    pins_by_id[pin_id] = pin
    return PinResponse(**pin)


@app.get("/projects/{project_id}/pins", response_model=list[PinResponse], tags=["pins"])
def list_pins(project_id: str, request: Request) -> list[PinResponse]:
    user_id = _get_user_id(request)
    _ensure_project_ownership(project_id, user_id)
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            project = db.get(ProjectRecord, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            pins = db.query(PinRecord).filter(PinRecord.project_id == project_id).all()
            return [_pin_response_from_record(pin) for pin in pins]

    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    return [PinResponse(**pin) for pin in pins_by_project.get(project_id, [])]


@app.get("/projects/{project_id}/pins/{pin_id}", response_model=PinResponse, tags=["pins"])
def get_pin(project_id: str, pin_id: str, request: Request) -> PinResponse:
    user_id = _get_user_id(request)
    _ensure_project_ownership(project_id, user_id)
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            project = db.get(ProjectRecord, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            pin = db.get(PinRecord, pin_id)
            if not pin or pin.project_id != project_id:
                raise HTTPException(status_code=404, detail="Pin not found")

            return _pin_response_from_record(pin)

    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    pin = pins_by_id.get(pin_id)
    if not pin or pin["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Pin not found")

    return PinResponse(**pin)


@app.post("/projects/{project_id}/pins/{pin_id}/upload", response_model=UploadResponse, tags=["pins"])
def upload_pin_photo(project_id: str, pin_id: str, request: Request, file: UploadFile = File(...)) -> UploadResponse:
    if file.filename is None:
        raise HTTPException(status_code=400, detail="A filename is required")

    user_id = _get_user_id(request)
    _ensure_project_ownership(project_id, user_id)

    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            project = db.get(ProjectRecord, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            pin = db.get(PinRecord, pin_id)
            if not pin or pin.project_id != project_id:
                raise HTTPException(status_code=404, detail="Pin not found")

            photo_key = _store_photo(project_id, pin_id, file)
            pin.photo_key = photo_key
            db.commit()
            return UploadResponse(id=pin_id, photo_key=photo_key)

    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    pin = pins_by_id.get(pin_id)
    if not pin or pin["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Pin not found")

    photo_key = _store_photo(project_id, pin_id, file)
    pin["photo_key"] = photo_key
    return UploadResponse(id=pin_id, photo_key=photo_key)
