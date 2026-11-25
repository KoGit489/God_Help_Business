from __future__ import annotations

import logging
import json
import hashlib
import os
import re
import secrets
import shutil
import smtplib
import ssl
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from threading import RLock
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Body, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from limits import RateLimitItemPerMinute
from limits.storage import storage_from_string
from limits.strategies import MovingWindowRateLimiter
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.analytics import record_event as record_analytics_event, summary as analytics_summary
from app.camera_adapter import Insta360CameraAdapter
from app.capture_processing import CaptureProcessor
from app.media_client import process_media, process_media_path
from app.mfa import decrypt_mfa_secret, match_totp_counter, mfa_cipher
from app.models import AnnotationRecord, AuthSessionRecord, Base, EmailVerificationRecord, MfaCredentialRecord, MfaRecoveryCodeRecord, PasswordResetRecord, PinRecord, ProjectRecord, ShareLinkRecord, UserRecord
from app.monitoring import configure_error_tracking
from app.rls import assert_postgres_rls, set_share_token, set_user_id

load_dotenv()
configure_error_tracking(os.getenv("SENTRY_DSN", "").strip(), os.getenv("APP_ENV", "development"))

logger = logging.getLogger("god_help_business.api")
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

camera_adapter = Insta360CameraAdapter()
capture_processor = CaptureProcessor()

PERSISTENCE_MODE = os.getenv("APP_PERSISTENCE", "memory").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./god_help_business.db")
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").strip().lower()
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploaded_files"))
PUBLIC_SHARE_BASE_URL = os.getenv("PUBLIC_SHARE_BASE_URL", "http://127.0.0.1:5500/frontend/share.html")
SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "true").strip().lower() in {"1", "true", "yes"}
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "true").strip().lower() in {"1", "true", "yes"}
ALLOW_ACCOUNT_REGISTRATION = os.getenv("ALLOW_ACCOUNT_REGISTRATION", "false").strip().lower() in {"1", "true", "yes"}
EMAIL_VERIFICATION_REQUIRED = os.getenv("EMAIL_VERIFICATION_REQUIRED", "false").strip().lower() in {"1", "true", "yes"}
SESSION_COOKIE_NAME = "casai_session"
SESSION_TTL = timedelta(hours=int(os.getenv("SESSION_TTL_HOURS", "12")))
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").strip().lower() in {"1", "true", "yes"}
MAX_IMAGE_UPLOAD_BYTES = int(os.getenv("MAX_IMAGE_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_FLOOR_PLAN_UPLOAD_BYTES = int(os.getenv("MAX_FLOOR_PLAN_UPLOAD_BYTES", str(100 * 1024 * 1024)))
MAX_NATIVE_UPLOAD_BYTES = int(os.getenv("MAX_NATIVE_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))
MAX_REQUEST_BODY_BYTES = MAX_NATIVE_UPLOAD_BYTES + 1024 * 1024
password_hasher = PasswordHasher()
dummy_password_hash = password_hasher.hash(secrets.token_urlsafe(32))
login_limiter = MovingWindowRateLimiter(storage_from_string(os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")))
LOGIN_ACCOUNT_LIMIT = RateLimitItemPerMinute(10)
LOGIN_GLOBAL_LIMIT = RateLimitItemPerMinute(120)
ANALYTICS_GLOBAL_LIMIT = RateLimitItemPerMinute(600)


def _configured_cors_origins() -> list[str]:
    origins = {origin.strip().rstrip("/") for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()}
    domain = os.getenv("APP_DOMAIN", "").strip().rstrip("/")
    if domain:
        origins.add(domain if domain.startswith(("http://", "https://")) else f"https://{domain}")
    elif os.getenv("APP_ENV", "development").lower() != "production":
        origins.update({
            "http://localhost:5500", "http://127.0.0.1:5500",
            "http://localhost:8000", "http://127.0.0.1:8000",
        })
    return sorted(origins)


ALLOWED_CORS_ORIGINS = _configured_cors_origins()


def _validate_production_security() -> None:
    if os.getenv("APP_ENV", "development").strip().lower() != "production":
        return
    if not AUTH_REQUIRED or not SESSION_COOKIE_SECURE:
        raise RuntimeError("Production requires authentication and secure session cookies.")
    if not os.getenv("MEDIA_WORKER_SOCKET", "").strip():
        raise RuntimeError("Production requires an isolated media worker socket.")
    if not ALLOWED_CORS_ORIGINS:
        raise RuntimeError("Production requires at least one configured HTTPS origin.")
    for origin in ALLOWED_CORS_ORIGINS:
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            raise RuntimeError("Production origins must be exact HTTPS origins.")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _migrate_pin_ordering() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("pins")}
    timestamp_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
    now = _utc_now()
    with engine.begin() as connection:
        if "created_at" not in columns:
            connection.execute(text(f"ALTER TABLE pins ADD COLUMN created_at {timestamp_type}"))
        if "route_order" not in columns:
            connection.execute(text("ALTER TABLE pins ADD COLUMN route_order INTEGER"))
        connection.execute(text("UPDATE pins SET created_at = :now WHERE created_at IS NULL"), {"now": now})
        connection.execute(text("UPDATE pins SET route_order = 0 WHERE route_order IS NULL"))
        for project_id, in connection.execute(text("SELECT DISTINCT project_id FROM pins")).all():
            pins = connection.execute(text("SELECT id, route_order FROM pins WHERE project_id = :project_id ORDER BY created_at, id"), {"project_id": project_id}).all()
            next_route_order = max((route_order or 0 for _, route_order in pins), default=0)
            for pin_id, route_order in pins:
                if route_order in (None, 0):
                    next_route_order += 1
                    connection.execute(text("UPDATE pins SET route_order = :route_order WHERE id = :pin_id"), {"route_order": next_route_order, "pin_id": pin_id})
        if engine.dialect.name == "postgresql":
            connection.execute(text("ALTER TABLE pins ALTER COLUMN created_at SET NOT NULL"))
            connection.execute(text("ALTER TABLE pins ALTER COLUMN route_order SET NOT NULL"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_pins_project_route_unique ON pins(project_id, route_order)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_pins_project_route ON pins(project_id, route_order, created_at, id)"))


def _migrate_legacy_share_links() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("share_links")}
    timestamp_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
    additions = {
        "created_at": f"{timestamp_type}",
        "expires_at": f"{timestamp_type}",
        "revoked_at": f"{timestamp_type}",
    }
    now = _utc_now()
    with engine.begin() as connection:
        for column_name, column_type in additions.items():
            if column_name not in columns:
                connection.execute(text(f"ALTER TABLE share_links ADD COLUMN {column_name} {column_type}"))
        connection.execute(text("UPDATE share_links SET created_at = :now WHERE created_at IS NULL"), {"now": now})
        # Legacy tokens had no lifetime; expire them at migration time so they cannot remain permanent.
        connection.execute(text("UPDATE share_links SET expires_at = :now WHERE expires_at IS NULL"), {"now": now})


def _bootstrap_first_admin() -> None:
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    name = os.getenv("BOOTSTRAP_ADMIN_NAME", "Administrator").strip() or "Administrator"
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            bootstrap_admin = db.scalar(select(UserRecord).where(UserRecord.email == email)) if email else None
            if not db.query(UserRecord).count():
                if not email or len(password) < 16:
                    raise RuntimeError("Set BOOTSTRAP_ADMIN_EMAIL and a 16+ character BOOTSTRAP_ADMIN_PASSWORD before first startup.")
                bootstrap_admin = UserRecord(
                    id=str(uuid4()), email=_validate_account_email(email), name=name,
                    password_hash=password_hasher.hash(password), is_admin=True, is_active=True,
                )
                db.add(bootstrap_admin)
                db.flush()
            if bootstrap_admin:
                db.query(ProjectRecord).filter(ProjectRecord.owner_id.in_(["demo", "demo-user"])).update(
                    {ProjectRecord.owner_id: bootstrap_admin.id}, synchronize_session=False
                )
            db.commit()
        return

    if not users_by_email:
        if not email or len(password) < 16:
            raise RuntimeError("Set BOOTSTRAP_ADMIN_EMAIL and a 16+ character BOOTSTRAP_ADMIN_PASSWORD before first startup.")
        email = _validate_account_email(email)
        user = {
            "id": str(uuid4()), "email": email, "name": name,
            "password_hash": password_hasher.hash(password), "is_admin": True, "is_active": True,
        }
        users_by_email[email] = user
        users_by_id[user["id"]] = user


@asynccontextmanager
async def lifespan(_: FastAPI):
    _validate_production_security()
    if not login_limiter.storage.check():
        raise RuntimeError("Login rate-limit storage is unavailable.")
    if EMAIL_VERIFICATION_REQUIRED:
        if not AUTH_REQUIRED:
            raise RuntimeError("Email verification requires authentication.")
        try:
            _password_reset_mail_settings()
        except HTTPException as exc:
            raise RuntimeError("Email verification requires valid SMTP and public-origin settings.") from exc
    if PERSISTENCE_MODE == "database":
        try:
            require_rls = os.getenv("DATABASE_REQUIRE_RLS", "false").strip().lower() in {"1", "true", "yes"}
            if not require_rls:
                Base.metadata.create_all(bind=engine)
                _migrate_legacy_share_links()
                _migrate_pin_ordering()
                project_columns = {column["name"] for column in inspect(engine).get_columns("projects")}
                if "floor_plan_json" not in project_columns:
                    with engine.begin() as connection:
                        connection.execute(text("ALTER TABLE projects ADD COLUMN floor_plan_json TEXT"))
                user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
                if "email_verified" not in user_columns:
                    with engine.begin() as connection:
                        connection.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT TRUE"))
            else:
                with engine.connect() as connection:
                    assert_postgres_rls(connection)
        except (SQLAlchemyError, RuntimeError) as exc:
            logger.exception("Database startup failed")
            raise RuntimeError("Database initialization failed") from exc
    if AUTH_REQUIRED:
        _bootstrap_first_admin()
    _seed_demo_data()
    yield


app = FastAPI(
    title="God_Help_Business API",
    version="0.2.0",
    description="Backend scaffold for a construction field capture MVP.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


class AnalyticsEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal["dashboard_opened", "project_created"]
    consent: Literal[True]


class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class ProjectResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    pin_count: int
    status: str = "draft"


class ProjectStatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1, max_length=64)


class PinCreateRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    heading: float
    position_x: float | None = Field(default=None, ge=0, le=1)
    position_y: float | None = Field(default=None, ge=0, le=1)
    telemetry: dict[str, Any] | None = None
    captured_on: str = Field(min_length=1, max_length=64)
    photo_key: str | None = Field(default=None, max_length=500)
    media_type: str | None = Field(default=None, max_length=64)
    native_file_key: str | None = Field(default=None, max_length=500)
    thumbnail_key: str | None = Field(default=None, max_length=500)


class PinUpdateRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    heading: float | None = None


class PinCalibrationRequest(BaseModel):
    position_x: float = Field(ge=0, le=1)
    position_y: float = Field(ge=0, le=1)
    note: str | None = Field(default=None, max_length=500)


class PinResponse(BaseModel):
    id: str
    project_id: str
    route_order: int = 0
    latitude: float
    longitude: float
    heading: float
    position_x: float | None = None
    position_y: float | None = None
    auto_position_x: float | None = None
    auto_position_y: float | None = None
    alignment_confidence: float = 0.0
    calibration_state: str = "unreviewed"
    calibration_data: dict[str, Any] | None = None
    telemetry: dict[str, Any] | None = None
    waypoints: list[dict[str, Any]] | None = None
    preview_url: str | None = None
    processing_status: str = "not_requested"
    processing_error: str | None = None
    captured_on: str
    photo_key: str | None = None
    media_type: str | None = None
    native_file_key: str | None = None
    thumbnail_key: str | None = None


class AnnotationCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
    floor_plan_x: float = Field(ge=0, le=1)
    floor_plan_y: float = Field(ge=0, le=1)
    pin_id: str | None = None
    status: str = Field(default="open", pattern="^(open|in_progress|resolved)$")
    assigned_to: str | None = Field(default=None, max_length=128)


class AnnotationResponse(BaseModel):
    id: str
    project_id: str
    pin_id: str | None = None
    author_id: str
    body: str
    status: str
    assigned_to: str | None = None
    floor_plan_x: float
    floor_plan_y: float


class ProjectDetailResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    pin_count: int
    status: str = "draft"
    pins: list[PinResponse]
    floor_plan: dict[str, Any] | None = None


class UploadResponse(BaseModel):
    id: str
    photo_key: str


class NativeUploadResponse(BaseModel):
    id: str
    native_file_key: str
    photo_key: str | None = None


class FloorPlanUploadResponse(BaseModel):
    filename: str
    media_key: str
    media_url: str
    content_type: str | None = None


class CameraStatusResponse(BaseModel):
    mode: str
    supports_web_browser: bool = True
    supports_native_app: bool = False
    sdk_available: bool = False
    supports_direct_sdk: bool = False
    browser_upload_supported: bool = True
    recommended_action: str


class ShareLinkResponse(BaseModel):
    project_id: str
    share_token: str
    share_link: str
    expires_at: datetime


class ShareLinkCreateRequest(BaseModel):
    expires_in_days: int = Field(default=7, ge=1, le=30)


class AuthLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)
    mfa_code: str | None = Field(default=None, max_length=128)


class AuthUserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=256)
    is_admin: bool = False


class AuthRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=256)


class AuthPasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    mfa_code: str | None = Field(default=None, max_length=128)


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=128)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=12, max_length=256)


class EmailVerificationConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=128)


class AuthUserResponse(BaseModel):
    id: str
    email: str
    name: str
    is_admin: bool = False
    email_verified: bool = True


engine = create_engine(DATABASE_URL, pool_pre_ping=True, hide_parameters=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

projects: dict[str, dict[str, Any]] = {}
pins_by_project: dict[str, list[dict[str, Any]]] = {}
pins_by_id: dict[str, dict[str, Any]] = {}
annotations_by_project: dict[str, list[dict[str, Any]]] = {}
annotations_by_id: dict[str, dict[str, Any]] = {}
project_share_tokens: dict[str, str] = {}
share_token_to_project: dict[str, str] = {}
share_links_by_project: dict[str, dict[str, Any]] = {}
users_by_id: dict[str, dict[str, Any]] = {}
users_by_email: dict[str, dict[str, Any]] = {}
user_sessions_by_token_hash: dict[str, dict[str, Any]] = {}
password_resets_by_token_hash: dict[str, dict[str, Any]] = {}
email_verifications_by_token_hash: dict[str, dict[str, Any]] = {}
mfa_credentials_by_user: dict[str, dict[str, Any]] = {}
mfa_recovery_codes_by_hash: dict[str, str] = {}
account_mutation_lock = RLock()


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4()))
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", request_id):
        request_id = str(uuid4())
    request.state.request_id = request_id
    if os.getenv("APP_ENV", "development").strip().lower() == "production" and request.url.path in {"/docs", "/docs/", "/docs/oauth2-redirect", "/redoc", "/redoc/", "/openapi.json"}:
        return JSONResponse(status_code=404, content={"error": {"type": "http_error", "message": "Not Found", "request_id": request_id}})
    content_length = request.headers.get("content-length")
    is_upload = request.method == "POST" and request.url.path.endswith(("/floor-plan-upload", "/native-upload", "/upload"))
    if request.method not in {"GET", "HEAD", "OPTIONS"} and (
        request.headers.get("transfer-encoding") or (is_upload and content_length is None)
    ):
        return JSONResponse(status_code=411, content={"error": {"type": "length_required", "message": "A Content-Length is required for streamed requests and uploads.", "request_id": request_id}})
    if content_length:
        request_body_limit = 1024 * 1024
        multipart_overhead = 1024 * 1024
        if request.url.path.endswith("/floor-plan-upload"):
            request_body_limit = MAX_FLOOR_PLAN_UPLOAD_BYTES + multipart_overhead
        elif request.url.path.endswith("/native-upload"):
            request_body_limit = MAX_NATIVE_UPLOAD_BYTES + multipart_overhead
        elif request.url.path.endswith("/upload"):
            request_body_limit = MAX_IMAGE_UPLOAD_BYTES + multipart_overhead
        try:
            length = int(content_length)
            if length < 0:
                raise ValueError("Negative Content-Length")
            if length > request_body_limit:
                return JSONResponse(status_code=413, content={"error": {"type": "request_too_large", "message": "Request body exceeds the configured upload limit.", "request_id": request_id}})
        except ValueError:
            return JSONResponse(status_code=400, content={"error": {"type": "invalid_content_length", "message": "Content-Length must be an integer.", "request_id": request_id}})
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in ALLOWED_CORS_ORIGINS:
            return JSONResponse(status_code=403, content={"error": {"type": "origin_denied", "message": "Request origin is not allowed.", "request_id": request_id}})
        if AUTH_REQUIRED and request.cookies.get(SESSION_COOKIE_NAME) and not origin:
            return JSONResponse(status_code=403, content={"error": {"type": "csrf_check_failed", "message": "Authenticated state-changing requests must include an Origin header.", "request_id": request_id}})
    upload_route = re.fullmatch(r"/projects/([^/]+)/(?:floor-plan-upload|pins/[^/]+/(?:native-upload|upload))", request.url.path)
    if AUTH_REQUIRED and request.method == "POST" and upload_route:
        try:
            _ensure_project_ownership(upload_route.group(1), _get_user_id(request))
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": {"type": "http_error", "message": exc.detail, "request_id": request_id}})
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    if (request.url.path.startswith(("/auth/", "/projects", "/share/", "/media/", "/analytics/"))
            and "no-store" not in response.headers.get("Cache-Control", "").lower()):
        response.headers["Cache-Control"] = "private, no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [{"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors()]
    first_error = details[0] if details else None
    field = ".".join(str(part) for part in first_error["loc"] if part not in {"body", "query", "path"}) if first_error else ""
    message = f"{field}: {first_error['msg']}" if field and first_error else "Request validation failed"
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "type": "validation_error",
                "message": message,
                "request_id": request.state.request_id,
                "details": details,
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    if exc.status_code == 404 and request.method == "GET" and "text/html" in request.headers.get("accept", ""):
        return FileResponse(FRONTEND_DIR / "404.html", status_code=404, headers=exc.headers)
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
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
    annotations_by_project.clear()
    annotations_by_id.clear()
    project_share_tokens.clear()
    share_token_to_project.clear()
    share_links_by_project.clear()
    users_by_id.clear()
    users_by_email.clear()
    user_sessions_by_token_hash.clear()
    password_resets_by_token_hash.clear()
    email_verifications_by_token_hash.clear()
    mfa_credentials_by_user.clear()
    mfa_recovery_codes_by_hash.clear()

    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            db.query(AuthSessionRecord).delete()
            db.query(PasswordResetRecord).delete()
            db.query(EmailVerificationRecord).delete()
            db.query(MfaRecoveryCodeRecord).delete()
            db.query(MfaCredentialRecord).delete()
            db.query(UserRecord).delete()
            db.query(ShareLinkRecord).delete()
            db.query(AnnotationRecord).delete()
            db.query(PinRecord).delete()
            db.query(ProjectRecord).delete()
            db.commit()


def _create_share_url(token: str) -> str:
    base = PUBLIC_SHARE_BASE_URL.rstrip("/")
    if base.endswith("share.html"):
        return f"{base}?token={token}"
    return f"{base}/share/{token}"


def _s3_client():
    try:
        import boto3
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="boto3 is required for S3 storage backend") from exc

    bucket = os.getenv("S3_BUCKET")
    region = os.getenv("S3_REGION")
    endpoint_url = os.getenv("S3_ENDPOINT_URL")
    if not bucket or not region or not endpoint_url:
        raise HTTPException(status_code=500, detail="S3_BUCKET, S3_REGION, and S3_ENDPOINT_URL are required for S3 storage")
    if not os.getenv("AWS_ACCESS_KEY_ID") or not os.getenv("AWS_SECRET_ACCESS_KEY"):
        raise HTTPException(status_code=500, detail="Spaces access key credentials are not configured")
    if os.getenv("APP_ENV", "development").strip().lower() == "production":
        try:
            endpoint = urlsplit(endpoint_url)
            if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
                raise ValueError("Invalid storage endpoint")
        except ValueError as exc:
            raise HTTPException(status_code=500, detail="Production storage requires a valid HTTPS endpoint without embedded credentials.") from exc
    return boto3.client("s3", region_name=region, endpoint_url=endpoint_url)


def _upload_s3_fileobj(file_obj, key: str, content_type: str | None = None) -> None:
    extra_args = {"ContentType": content_type} if content_type else None
    file_obj.seek(0)
    _s3_client().upload_fileobj(file_obj, os.environ["S3_BUCKET"], key, ExtraArgs=extra_args or {})


def _materialized_media_path(media_key: str):
    """Yield a local file path for media processing, downloading from Spaces if needed."""
    from contextlib import contextmanager

    @contextmanager
    def materialize():
        if STORAGE_BACKEND != "s3":
            local_path = UPLOAD_DIR / media_key.removeprefix("uploads/")
            yield local_path
            return

        suffix = Path(media_key).suffix or ".bin"
        handle = tempfile.NamedTemporaryFile(prefix="god-help-", suffix=suffix, delete=False)
        temp_path = Path(handle.name)
        handle.close()
        try:
            _s3_client().download_file(os.environ["S3_BUCKET"], media_key, str(temp_path))
            yield temp_path
        finally:
            temp_path.unlink(missing_ok=True)

    return materialize()


def _validate_capture_media_key(media_key: str, project_id: str, pin_id: str) -> None:
    parts = media_key.split("/")
    if (
        parts[:3] != ["uploads", project_id, pin_id]
        or len(parts) not in {4, 5}
        or (len(parts) == 5 and parts[3] != "native")
        or parts[-1] in {"", ".", ".."}
        or "\\" in parts[-1]
    ):
        raise HTTPException(status_code=403, detail="Capture file does not belong to this waypoint.")


def _validate_upload_file(upload: UploadFile, allowed_suffixes: set[str], max_bytes: int) -> None:
    filename = Path(upload.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in allowed_suffixes:
        raise HTTPException(status_code=415, detail="This file type is not allowed for this upload.")
    upload.file.seek(0, os.SEEK_END)
    size = upload.file.tell()
    upload.file.seek(0)
    if size <= 0:
        raise HTTPException(status_code=400, detail="Uploaded files cannot be empty.")
    if size > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds the {max_bytes}-byte upload limit.")

    prefix = upload.file.read(16)
    upload.file.seek(0)
    signatures = {
        ".jpg": prefix.startswith(b"\xff\xd8\xff"),
        ".jpeg": prefix.startswith(b"\xff\xd8\xff"),
        ".png": prefix.startswith(b"\x89PNG\r\n\x1a\n"),
        ".webp": len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP",
        ".pdf": prefix.startswith(b"%PDF-"),
        ".zip": prefix.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")),
        ".mp4": len(prefix) >= 8 and prefix[4:8] == b"ftyp",
        ".insv": len(prefix) >= 8 and prefix[4:8] == b"ftyp",
    }
    if suffix in signatures and not signatures[suffix]:
        raise HTTPException(status_code=415, detail="The file contents do not match the filename type.")


def _store_photo(project_id: str, pin_id: str, upload: UploadFile) -> str:
    filename = Path(upload.filename or "upload.bin").name
    photo_key = f"uploads/{project_id}/{pin_id}/{filename}"

    if STORAGE_BACKEND == "s3":
        _upload_s3_fileobj(upload.file, photo_key, upload.content_type)
        return photo_key

    destination = UPLOAD_DIR / project_id / pin_id
    destination.mkdir(parents=True, exist_ok=True)
    output_file = destination / filename
    upload.file.seek(0)
    with output_file.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)

    return photo_key


def _store_native_file(project_id: str, pin_id: str, upload: UploadFile) -> str:
    filename = Path(upload.filename or "capture.bin").name
    native_key = f"uploads/{project_id}/{pin_id}/native/{filename}"

    if STORAGE_BACKEND == "s3":
        _upload_s3_fileobj(upload.file, native_key, upload.content_type)
        return native_key

    destination = UPLOAD_DIR / project_id / pin_id / "native"
    destination.mkdir(parents=True, exist_ok=True)
    output_file = destination / filename
    upload.file.seek(0)
    with output_file.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)

    return native_key


def _rasterize_floor_plan(file_data: bytes) -> bytes:
    if os.getenv("MEDIA_WORKER_SOCKET", "").strip():
        return process_media("pdf", BytesIO(file_data), len(file_data), ".pdf")[1]
    import pymupdf

    with pymupdf.open(stream=file_data, filetype="pdf") as document:
        return document.load_page(0).get_pixmap(dpi=150).tobytes("png")


def _store_floor_plan(project_id: str, upload: UploadFile) -> str:
    filename = Path(upload.filename or "floor-plan.bin").name
    destination = UPLOAD_DIR / "floorplans" / project_id
    upload.file.seek(0)
    file_data = upload.file.read()
    content_type = upload.content_type or "application/octet-stream"
    if filename.lower().endswith(".pdf"):
        try:
            file_data = _rasterize_floor_plan(file_data)
            filename = f"{Path(filename).stem}.png"
            content_type = "image/png"
        except Exception as exc:
            if os.getenv("APP_ENV", "development").strip().lower() == "production":
                raise HTTPException(status_code=503, detail="Floor plan processing is unavailable.") from exc
            logger.warning("PDF rasterization failed, keeping original: %s", exc)

    floor_plan_key = f"floorplans/{project_id}/{filename}"
    if STORAGE_BACKEND == "s3":
        from io import BytesIO
        _upload_s3_fileobj(BytesIO(file_data), floor_plan_key, content_type)
        return floor_plan_key

    destination.mkdir(parents=True, exist_ok=True)
    (destination / filename).write_bytes(file_data)
    return floor_plan_key


def _store_preview(project_id: str, pin_id: str, preview_data: bytes) -> str:
    """Store a generated preview image for a pin."""
    preview_key = f"previews/{project_id}/{pin_id}/preview.jpg"
    if STORAGE_BACKEND == "s3":
        from io import BytesIO
        _upload_s3_fileobj(BytesIO(preview_data), preview_key, "image/jpeg")
        return preview_key

    destination = UPLOAD_DIR / "previews" / project_id / pin_id
    destination.mkdir(parents=True, exist_ok=True)
    output_file = destination / "preview.jpg"
    with output_file.open("wb") as handle:
        handle.write(preview_data)

    return preview_key


def _process_capture_telemetry(telemetry: Any) -> dict[str, Any]:
    if not os.getenv("MEDIA_WORKER_SOCKET", "").strip():
        return capture_processor.process(telemetry)
    payload = json.dumps(telemetry, allow_nan=False).encode("utf-8")
    try:
        _, output = process_media("telemetry", BytesIO(payload), len(payload), ".json")
        result = json.loads(output)
        if not isinstance(result, dict):
            raise ValueError("Invalid media worker response.")
        return result
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Capture processing is unavailable.") from exc


def _extract_capture_preview(path: Path) -> dict[str, Any]:
    if not os.getenv("MEDIA_WORKER_SOCKET", "").strip():
        return capture_processor.extract_insp_preview(path)
    metadata, output = process_media_path("preview", path)
    metadata["preview_data"] = output
    return metadata


def _pin_response_from_record(record: PinRecord) -> PinResponse:
    telemetry = json.loads(record.telemetry_json) if record.telemetry_json else None
    waypoints = json.loads(record.waypoints_json) if record.waypoints_json else None
    calibration_data = json.loads(record.calibration_json) if record.calibration_json else None
    preview_url = f"/media/{record.preview_key}" if record.preview_key else None
    return PinResponse(
        id=record.id,
        project_id=record.project_id,
        route_order=record.route_order,
        latitude=record.latitude,
        longitude=record.longitude,
        heading=record.heading,
        position_x=record.position_x,
        position_y=record.position_y,
        auto_position_x=record.auto_position_x,
        auto_position_y=record.auto_position_y,
        alignment_confidence=record.alignment_confidence,
        calibration_state=(calibration_data or {}).get("state", "unreviewed"),
        calibration_data=calibration_data,
        telemetry=telemetry,
        waypoints=waypoints,
        preview_url=preview_url,
        processing_status=record.processing_status,
        processing_error=record.processing_error,
        captured_on=record.captured_on,
        photo_key=record.photo_key,
        media_type=record.media_type,
        native_file_key=record.native_file_key,
        thumbnail_key=record.thumbnail_key,
    )


def _pin_response_from_memory(pin: dict[str, Any]) -> PinResponse:
    """Build a PinResponse from an in-memory pin dictionary."""
    preview_url = f"/media/{pin['preview_key']}" if pin.get('preview_key') else None
    return PinResponse(
        id=pin["id"],
        project_id=pin["project_id"],
        route_order=pin.get("route_order", 0),
        latitude=pin["latitude"],
        longitude=pin["longitude"],
        heading=pin["heading"],
        position_x=pin.get("position_x"),
        position_y=pin.get("position_y"),
        auto_position_x=pin.get("auto_position_x"),
        auto_position_y=pin.get("auto_position_y"),
        alignment_confidence=pin.get("alignment_confidence", 0.0),
        calibration_state=pin.get("calibration_state", "unreviewed"),
        calibration_data=pin.get("calibration_data"),
        telemetry=pin.get("telemetry"),
        waypoints=pin.get("waypoints"),
        preview_url=preview_url,
        processing_status=pin.get("processing_status", "not_requested"),
        processing_error=pin.get("processing_error"),
        captured_on=pin["captured_on"],
        photo_key=pin.get("photo_key"),
        media_type=pin.get("media_type"),
        native_file_key=pin.get("native_file_key"),
        thumbnail_key=pin.get("thumbnail_key"),
    )


def _annotation_response_from_record(record: AnnotationRecord) -> AnnotationResponse:
    return AnnotationResponse(
        id=record.id,
        project_id=record.project_id,
        pin_id=record.pin_id,
        author_id=record.author_id,
        body=record.body,
        status=record.status,
        assigned_to=record.assigned_to,
        floor_plan_x=record.floor_plan_x,
        floor_plan_y=record.floor_plan_y,
    )


def _annotation_response_from_memory(annotation: dict[str, Any]) -> AnnotationResponse:
    return AnnotationResponse(**annotation)


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
    if not record.floor_plan_json:
        recovered_plan = _recover_floor_plan(record.id)
        if recovered_plan:
            record.floor_plan_json = json.dumps(recovered_plan)
            db.commit()
    pins = (db.query(PinRecord).filter(PinRecord.project_id == record.id)
            .order_by(PinRecord.route_order.asc(), PinRecord.created_at.asc(), PinRecord.id.asc()).all())
    pin_items = [_pin_response_from_record(pin) for pin in pins]
    return ProjectDetailResponse(
        id=record.id,
        title=record.title,
        description=record.description,
        pin_count=len(pin_items),
        status=record.status,
        pins=pin_items,
        floor_plan=json.loads(record.floor_plan_json) if record.floor_plan_json else None,
    )


def _build_project_detail_memory(project_id: str) -> ProjectDetailResponse:
    project = projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.get("floor_plan"):
        project["floor_plan"] = _recover_floor_plan(project_id)
    pin_items = [_pin_response_from_memory(pin) for pin in pins_by_project.get(project_id, [])]
    return ProjectDetailResponse(
        id=project["id"],
        title=project["title"],
        description=project.get("description"),
        pin_count=len(pin_items),
        status=project.get("status", "draft"),
        pins=pin_items,
        floor_plan=project.get("floor_plan"),
    )


def _recover_floor_plan(project_id: str) -> dict[str, Any] | None:
    content_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf"}
    prefix = f"floorplans/{project_id}/"
    try:
        if STORAGE_BACKEND == "s3":
            pages = _s3_client().get_paginator("list_objects_v2").paginate(
                Bucket=os.environ["S3_BUCKET"], Prefix=prefix,
            )
            candidates = (
                item for page in pages for item in page.get("Contents", [])
                if item["Key"].startswith(prefix)
                and "/" not in item["Key"][len(prefix):]
                and Path(item["Key"]).suffix.lower() in content_types
                and item.get("Size", 0) > 0
            )
            newest = max(candidates, key=lambda item: item["LastModified"], default=None)
            media_key = newest["Key"] if newest else None
        else:
            folder = UPLOAD_DIR / "floorplans" / project_id
            files = (
                path for path in folder.iterdir()
                if path.is_file() and not path.is_symlink() and path.suffix.lower() in content_types
            ) if folder.is_dir() else ()
            newest_file = max(files, key=lambda path: path.stat().st_mtime_ns, default=None)
            media_key = f"{prefix}{newest_file.name}" if newest_file else None
        if not media_key:
            return None
        return FloorPlanUploadResponse(
            filename=Path(media_key).name,
            media_key=media_key,
            media_url=f"/media/{media_key}",
            content_type=content_types[Path(media_key).suffix.lower()],
        ).model_dump()
    except Exception:
        logger.warning("Could not recover the saved floor plan for project %s", project_id, exc_info=True)
        return None


def _build_project_detail(project_id: str) -> ProjectDetailResponse:
    if PERSISTENCE_MODE != "database":
        return _build_project_detail_memory(project_id)

    with SessionLocal() as db:
        project = db.get(ProjectRecord, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return _project_detail_from_record(db, project)


def _get_user_id(request: Request) -> str:
    if not AUTH_REQUIRED:
        user_id = request.headers.get("x-user-id") or "demo"
        set_user_id(user_id)
        return user_id
    user = _authenticated_user(request)
    set_user_id(user["id"])
    return user["id"]


def _session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _authenticated_user(request: Request) -> dict[str, Any]:
    cached = getattr(request.state, "authenticated_user", None)
    if cached:
        set_user_id(cached["id"])
        return cached
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in is required.")
    token_hash = _session_token_hash(token)
    now = _utc_now()

    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            session = db.get(AuthSessionRecord, token_hash)
            if not session or session.revoked_at is not None or _as_utc(session.expires_at) <= now:
                raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.")
            user = db.get(UserRecord, session.user_id)
            if not user or not user.is_active:
                raise HTTPException(status_code=401, detail="This account is unavailable.")
            if EMAIL_VERIFICATION_REQUIRED and not user.email_verified:
                raise HTTPException(status_code=403, detail="Verify your email address before signing in.")
            user_data = {"id": user.id, "email": user.email, "name": user.name, "is_admin": user.is_admin, "is_active": user.is_active, "email_verified": user.email_verified}
    else:
        session = user_sessions_by_token_hash.get(token_hash)
        if not session or session.get("revoked_at") is not None or _as_utc(session["expires_at"]) <= now:
            raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.")
        user = users_by_id.get(session["user_id"])
        if not user or not user.get("is_active", True):
            raise HTTPException(status_code=401, detail="This account is unavailable.")
        if EMAIL_VERIFICATION_REQUIRED and not user.get("email_verified", True):
            raise HTTPException(status_code=403, detail="Verify your email address before signing in.")
        user_data = user
    request.state.authenticated_user = user_data
    set_user_id(user_data["id"])
    return user_data


def _consume_mfa_database(db: Session, user_id: str, code: str | None) -> None:
    credential = db.scalar(select(MfaCredentialRecord).where(MfaCredentialRecord.user_id == user_id).with_for_update())
    if not credential or not credential.enabled:
        return
    if not code:
        raise HTTPException(status_code=401, detail="Enter an authenticator or recovery code.")
    code = code.strip()
    if code.startswith("recovery-"):
        code_hash = _session_token_hash(code)
        recovery = db.scalar(select(MfaRecoveryCodeRecord).where(MfaRecoveryCodeRecord.code_hash == code_hash, MfaRecoveryCodeRecord.user_id == user_id).with_for_update())
        if not recovery:
            raise HTTPException(status_code=401, detail="Authenticator or recovery code is incorrect or has already been used.")
        db.delete(recovery)
        return
    counter = match_totp_counter(decrypt_mfa_secret(credential.encrypted_secret), code, _utc_now().timestamp(), credential.last_counter)
    if counter is None:
        raise HTTPException(status_code=401, detail="Authenticator or recovery code is incorrect or has already been used.")
    credential.last_counter = counter


def _consume_mfa_memory(user_id: str, code: str | None) -> None:
    credential = mfa_credentials_by_user.get(user_id)
    if not credential or not credential["enabled"]:
        return
    if not code:
        raise HTTPException(status_code=401, detail="Enter an authenticator or recovery code.")
    code = code.strip()
    if code.startswith("recovery-"):
        code_hash = _session_token_hash(code)
        if mfa_recovery_codes_by_hash.get(code_hash) != user_id:
            raise HTTPException(status_code=401, detail="Authenticator or recovery code is incorrect or has already been used.")
        del mfa_recovery_codes_by_hash[code_hash]
        return
    counter = match_totp_counter(decrypt_mfa_secret(credential["encrypted_secret"]), code, _utc_now().timestamp(), credential["last_counter"])
    if counter is None:
        raise HTTPException(status_code=401, detail="Authenticator or recovery code is incorrect or has already been used.")
    credential["last_counter"] = counter


def _set_login_session(response: Response, request: Request, user_id: str, expected_password_hash: str, mfa_code: str | None) -> None:
    raw_token = secrets.token_urlsafe(32)
    now = _utc_now()
    expires_at = now + SESSION_TTL
    token_hash = _session_token_hash(raw_token)
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            user = db.scalar(select(UserRecord).where(UserRecord.id == user_id).with_for_update())
            if not user or not user.is_active or user.password_hash != expected_password_hash:
                raise HTTPException(status_code=401, detail="Email or password is incorrect.")
            if EMAIL_VERIFICATION_REQUIRED and not user.email_verified:
                raise HTTPException(status_code=403, detail="Verify your email address before signing in.")
            _consume_mfa_database(db, user_id, mfa_code)
            db.add(AuthSessionRecord(token_hash=token_hash, user_id=user_id, created_at=now, expires_at=expires_at))
            db.commit()
    else:
        with account_mutation_lock:
            user = users_by_id.get(user_id)
            if not user or not user.get("is_active", True) or user["password_hash"] != expected_password_hash:
                raise HTTPException(status_code=401, detail="Email or password is incorrect.")
            if EMAIL_VERIFICATION_REQUIRED and not user.get("email_verified", True):
                raise HTTPException(status_code=403, detail="Verify your email address before signing in.")
            _consume_mfa_memory(user_id, mfa_code)
            user_sessions_by_token_hash[token_hash] = {
                "user_id": user_id, "created_at": now, "expires_at": expires_at, "revoked_at": None,
            }
    response.set_cookie(
        SESSION_COOKIE_NAME,
        raw_token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=SESSION_COOKIE_SECURE or request.url.scheme == "https",
        samesite="strict",
        path="/",
    )


def _clear_login_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", httponly=True, secure=SESSION_COOKIE_SECURE, samesite="strict")


def _password_matches(password_hash: str, password: str) -> bool:
    try:
        return bool(password_hasher.verify(password_hash, password))
    except (VerifyMismatchError, InvalidHashError):
        return False


def _limit_mfa_action(email: str) -> None:
    account_key = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    if not login_limiter.hit(LOGIN_GLOBAL_LIMIT, "mfa-global") or not login_limiter.hit(LOGIN_ACCOUNT_LIMIT, "mfa-account", account_key):
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait a minute and try again.", headers={"Retry-After": "60"})


def _revoke_other_sessions_database(db: Session, user_id: str, request: Request) -> None:
    current_hash = _session_token_hash(request.cookies.get(SESSION_COOKIE_NAME, ""))
    db.query(AuthSessionRecord).filter(AuthSessionRecord.user_id == user_id, AuthSessionRecord.token_hash != current_hash).delete(synchronize_session=False)


def _revoke_other_sessions_memory(user_id: str, request: Request) -> None:
    current_hash = _session_token_hash(request.cookies.get(SESSION_COOKIE_NAME, ""))
    for token_hash, session in list(user_sessions_by_token_hash.items()):
        if session["user_id"] == user_id and token_hash != current_hash:
            del user_sessions_by_token_hash[token_hash]


def _validate_account_email(email: str) -> str:
    normalized = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return normalized


def _password_reset_mail_settings() -> dict[str, Any]:
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    domain = os.getenv("APP_DOMAIN", "").strip().rstrip("/")
    origin = os.getenv("PUBLIC_APP_ORIGIN", "").strip().rstrip("/") or (f"https://{domain}" if domain else "")
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        parsed = urlsplit(origin)
        valid_origin = parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
        if os.getenv("APP_ENV", "development").strip().lower() == "production":
            valid_origin = valid_origin and parsed.scheme == "https" and origin in ALLOWED_CORS_ORIGINS
        if not host or not sender or "\n" in sender or "\r" in sender or bool(username) != bool(password) or not valid_origin or not 1 <= port <= 65535:
            raise ValueError("Invalid mail configuration")
    except ValueError:
        raise HTTPException(status_code=503, detail="Email delivery is not configured. Contact your administrator.") from None
    return {"host": host, "port": port, "sender": sender, "username": username, "password": password, "origin": origin}


def _send_account_email(settings: dict[str, Any], recipient: str, subject: str, body: str) -> None:
    try:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings["sender"]
        message["To"] = recipient
        message.set_content(body)
        with smtplib.SMTP(settings["host"], settings["port"], timeout=10) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if settings["username"]:
                smtp.login(settings["username"], settings["password"])
            smtp.send_message(message)
    except Exception:
        logger.warning("Account email delivery failed; check the SMTP configuration.")


def _send_password_reset_email(settings: dict[str, Any], recipient: str, token: str) -> None:
    _send_account_email(
        settings, recipient, "CASAI password reset",
        "A password reset was requested for your CASAI account. This link expires in 30 minutes "
        "and can be used once. If you did not request it, you can ignore this message.\n\n"
        f"{settings['origin']}/reset-password.html#token={token}\n",
    )


def _send_verification_email(settings: dict[str, Any], recipient: str, token: str) -> None:
    _send_account_email(
        settings, recipient, "Verify your CASAI email",
        "Please verify your email address for your CASAI account. This link expires in 24 hours "
        "and can be used once. If you did not expect this message, you can ignore it.\n\n"
        f"{settings['origin']}/verify-email.html#token={token}\n",
    )


def _get_user_by_email(email: str) -> dict[str, Any] | None:
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            user = db.scalar(select(UserRecord).where(UserRecord.email == email))
            if not user:
                return None
            return {
                "id": user.id, "email": user.email, "name": user.name,
                "password_hash": user.password_hash, "is_admin": user.is_admin,
                "is_active": user.is_active, "email_verified": user.email_verified,
            }
    return users_by_email.get(email)


def _ensure_project_ownership(project_id: str, user_id: str) -> None:
    if not AUTH_REQUIRED and user_id in {"demo", "demo-user"}:
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

        if user_id and project.get("owner_id") and project.get("owner_id") != user_id and (AUTH_REQUIRED or user_id not in {"demo", "demo-user"}):
            raise HTTPException(status_code=403, detail="Project does not belong to this user")

        if share_token is not None:
            link = share_links_by_project.get(project_id)
            if not link or link["token"] != share_token or link["revoked_at"] is not None or _as_utc(link["expires_at"]) <= _utc_now():
                raise HTTPException(status_code=403, detail="Invalid share token for this project")
        return _build_project_detail_memory(project_id)

    with SessionLocal() as db:
        project = db.get(ProjectRecord, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if user_id and (AUTH_REQUIRED or user_id not in {"demo", "demo-user"}) and project.owner_id != user_id:
            raise HTTPException(status_code=403, detail="Project does not belong to this user")

        if share_token is not None:
            link = db.scalar(select(ShareLinkRecord).where(ShareLinkRecord.project_id == project_id))
            if not link or link.token != share_token or link.revoked_at is not None or _as_utc(link.expires_at) <= _utc_now():
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

            demo_owner_id = "demo-user"
            if AUTH_REQUIRED:
                demo_owner_id = db.scalar(
                    select(UserRecord.id).where(UserRecord.is_admin.is_(True)).order_by(UserRecord.created_at).limit(1)
                ) or demo_owner_id

            project_id = str(uuid4())
            project = ProjectRecord(
                id=project_id,
                owner_id=demo_owner_id,
                title="North Ridge Inspection",
                description="Demo project with evidence captured for a review-ready walkthrough.",
                status="ready_for_review",
            )
            pin_a = PinRecord(
                id=str(uuid4()),
                project_id=project_id,
                route_order=1,
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
                route_order=2,
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

    demo_owner_id = "demo-user"
    if AUTH_REQUIRED:
        demo_owner_id = next(
            (user["id"] for user in users_by_id.values() if user.get("is_admin")),
            demo_owner_id,
        )
    demo_project_id = str(uuid4())
    demo_project = {
        "id": demo_project_id,
        "owner_id": demo_owner_id,
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
            "position_x": None,
            "position_y": None,
            "auto_position_x": None,
            "auto_position_y": None,
            "alignment_confidence": 0.0,
            "calibration_state": "unreviewed",
            "calibration_data": None,
            "telemetry": None,
            "waypoints": None,
            "preview_key": None,
            "processing_status": "not_requested",
            "processing_error": None,
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
            "position_x": None,
            "position_y": None,
            "auto_position_x": None,
            "auto_position_y": None,
            "alignment_confidence": 0.0,
            "calibration_state": "unreviewed",
            "calibration_data": None,
            "telemetry": None,
            "waypoints": None,
            "preview_key": None,
            "processing_status": "not_requested",
            "processing_error": None,
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
    if not AUTH_REQUIRED:
        return AuthUserResponse(id="demo-user", email="demo@God_Help_Business.local", name="Demo Builder", is_admin=True)
    user = _authenticated_user(request)
    return AuthUserResponse(id=user["id"], email=user["email"], name=user["name"], is_admin=user["is_admin"], email_verified=user.get("email_verified", True))


@app.get("/auth/mfa", tags=["auth"])
def get_mfa_status(request: Request, response: Response) -> dict[str, bool]:
    user = _authenticated_user(request)
    try:
        mfa_cipher()
        available = True
    except HTTPException:
        available = False
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            credential = db.get(MfaCredentialRecord, user["id"])
            enabled = bool(credential and credential.enabled)
    else:
        credential = mfa_credentials_by_user.get(user["id"])
        enabled = bool(credential and credential["enabled"])
    response.headers["Cache-Control"] = "no-store"
    return {"enabled": enabled, "available": available}


@app.post("/auth/mfa/setup", tags=["auth"])
def setup_mfa(payload: AuthPasswordRequest, request: Request, response: Response) -> dict[str, str]:
    user = _authenticated_user(request)
    _limit_mfa_action(user["email"])
    cipher = mfa_cipher()
    secret = pyotp.random_base32()
    encrypted_secret = cipher.encrypt(secret.encode("ascii")).decode("ascii")
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            account = db.scalar(select(UserRecord).where(UserRecord.id == user["id"]).with_for_update())
            if not account or not account.is_active or not _password_matches(account.password_hash, payload.password):
                raise HTTPException(status_code=401, detail="Password is incorrect.")
            credential = db.get(MfaCredentialRecord, user["id"])
            if credential and credential.enabled:
                raise HTTPException(status_code=409, detail="Authenticator is already enabled.")
            if not credential:
                credential = MfaCredentialRecord(user_id=user["id"], encrypted_secret=encrypted_secret, enabled=False, last_counter=-1)
                db.add(credential)
            else:
                credential.encrypted_secret = encrypted_secret
                credential.last_counter = -1
            db.commit()
    else:
        with account_mutation_lock:
            account = users_by_id.get(user["id"])
            if not account or not account.get("is_active", True) or not _password_matches(account["password_hash"], payload.password):
                raise HTTPException(status_code=401, detail="Password is incorrect.")
            credential = mfa_credentials_by_user.get(user["id"])
            if credential and credential["enabled"]:
                raise HTTPException(status_code=409, detail="Authenticator is already enabled.")
            mfa_credentials_by_user[user["id"]] = {"encrypted_secret": encrypted_secret, "enabled": False, "last_counter": -1}
    response.headers["Cache-Control"] = "no-store"
    return {"secret": secret, "provisioning_uri": pyotp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name="CASAI")}


@app.post("/auth/mfa/enable", tags=["auth"])
def enable_mfa(payload: MfaCodeRequest, request: Request, response: Response) -> dict[str, list[str]]:
    user = _authenticated_user(request)
    _limit_mfa_action(user["email"])
    recovery_codes = [f"recovery-{secrets.token_urlsafe(16)}" for _ in range(10)]
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            account = db.scalar(select(UserRecord).where(UserRecord.id == user["id"]).with_for_update())
            credential = db.scalar(select(MfaCredentialRecord).where(MfaCredentialRecord.user_id == user["id"]).with_for_update()) if account else None
            if not account or not account.is_active or not credential or credential.enabled:
                raise HTTPException(status_code=409, detail="Start authenticator setup first.")
            counter = match_totp_counter(decrypt_mfa_secret(credential.encrypted_secret), payload.code.strip(), _utc_now().timestamp(), credential.last_counter)
            if counter is None:
                raise HTTPException(status_code=401, detail="Authenticator code is incorrect or has already been used.")
            credential.enabled = True
            credential.last_counter = counter
            db.query(MfaRecoveryCodeRecord).filter(MfaRecoveryCodeRecord.user_id == user["id"]).delete(synchronize_session=False)
            db.add_all([MfaRecoveryCodeRecord(code_hash=_session_token_hash(code), user_id=user["id"]) for code in recovery_codes])
            _revoke_other_sessions_database(db, user["id"], request)
            db.commit()
    else:
        with account_mutation_lock:
            account = users_by_id.get(user["id"])
            credential = mfa_credentials_by_user.get(user["id"])
            if not account or not account.get("is_active", True) or not credential or credential["enabled"]:
                raise HTTPException(status_code=409, detail="Start authenticator setup first.")
            counter = match_totp_counter(decrypt_mfa_secret(credential["encrypted_secret"]), payload.code.strip(), _utc_now().timestamp(), credential["last_counter"])
            if counter is None:
                raise HTTPException(status_code=401, detail="Authenticator code is incorrect or has already been used.")
            credential["enabled"] = True
            credential["last_counter"] = counter
            for code_hash, owner_id in list(mfa_recovery_codes_by_hash.items()):
                if owner_id == user["id"]:
                    del mfa_recovery_codes_by_hash[code_hash]
            for code in recovery_codes:
                mfa_recovery_codes_by_hash[_session_token_hash(code)] = user["id"]
            _revoke_other_sessions_memory(user["id"], request)
    response.headers["Cache-Control"] = "no-store"
    return {"recovery_codes": recovery_codes}


@app.post("/auth/mfa/disable", status_code=204, tags=["auth"])
def disable_mfa(payload: AuthPasswordRequest, request: Request) -> Response:
    user = _authenticated_user(request)
    _limit_mfa_action(user["email"])
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            account = db.scalar(select(UserRecord).where(UserRecord.id == user["id"]).with_for_update())
            credential = db.scalar(select(MfaCredentialRecord).where(MfaCredentialRecord.user_id == user["id"]).with_for_update()) if account else None
            if not account or not account.is_active or not _password_matches(account.password_hash, payload.password):
                raise HTTPException(status_code=401, detail="Password is incorrect.")
            if not credential or not credential.enabled:
                raise HTTPException(status_code=409, detail="Authenticator is not enabled.")
            _consume_mfa_database(db, user["id"], payload.mfa_code)
            db.flush()
            db.query(MfaRecoveryCodeRecord).filter(MfaRecoveryCodeRecord.user_id == user["id"]).delete(synchronize_session=False)
            db.delete(credential)
            _revoke_other_sessions_database(db, user["id"], request)
            db.commit()
    else:
        with account_mutation_lock:
            account = users_by_id.get(user["id"])
            credential = mfa_credentials_by_user.get(user["id"])
            if not account or not account.get("is_active", True) or not _password_matches(account["password_hash"], payload.password):
                raise HTTPException(status_code=401, detail="Password is incorrect.")
            if not credential or not credential["enabled"]:
                raise HTTPException(status_code=409, detail="Authenticator is not enabled.")
            _consume_mfa_memory(user["id"], payload.mfa_code)
            for code_hash, owner_id in list(mfa_recovery_codes_by_hash.items()):
                if owner_id == user["id"]:
                    del mfa_recovery_codes_by_hash[code_hash]
            del mfa_credentials_by_user[user["id"]]
            _revoke_other_sessions_memory(user["id"], request)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@app.post("/auth/email-verification/request", status_code=202, tags=["auth"])
def request_email_verification(payload: PasswordResetRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    settings = _password_reset_mail_settings()
    email = _validate_account_email(payload.email)
    account_key = hashlib.sha256(email.encode("utf-8")).hexdigest()
    if not login_limiter.hit(LOGIN_GLOBAL_LIMIT, "verify-global") or not login_limiter.hit(LOGIN_ACCOUNT_LIMIT, "verify-account", account_key):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.", headers={"Retry-After": "60"})
    raw_token = secrets.token_urlsafe(32)
    token_hash = _session_token_hash(raw_token)
    expires_at = _utc_now() + timedelta(hours=24)
    found = False
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            user = db.scalar(select(UserRecord).where(UserRecord.email == email).with_for_update())
            if user and user.is_active and not user.email_verified:
                db.query(EmailVerificationRecord).filter(EmailVerificationRecord.user_id == user.id).delete(synchronize_session=False)
                db.add(EmailVerificationRecord(token_hash=token_hash, user_id=user.id, expires_at=expires_at))
                db.commit()
                found = True
    else:
        with account_mutation_lock:
            user = users_by_email.get(email)
            if user and user.get("is_active", True) and not user.get("email_verified", True):
                for existing_hash, verification in list(email_verifications_by_token_hash.items()):
                    if verification["user_id"] == user["id"]:
                        del email_verifications_by_token_hash[existing_hash]
                email_verifications_by_token_hash[token_hash] = {"user_id": user["id"], "expires_at": expires_at}
                found = True
    if found:
        background_tasks.add_task(_send_verification_email, settings, email, raw_token)
    return {"message": "If the account needs verification, an email will be sent."}


@app.post("/auth/email-verification/confirm", status_code=204, tags=["auth"])
def confirm_email_verification(payload: EmailVerificationConfirm) -> Response:
    token_hash = _session_token_hash(payload.token)
    if not login_limiter.hit(LOGIN_GLOBAL_LIMIT, "verify-confirm-global") or not login_limiter.hit(LOGIN_ACCOUNT_LIMIT, "verify-confirm-token", token_hash):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.", headers={"Retry-After": "60"})
    now = _utc_now()
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            initial = db.get(EmailVerificationRecord, token_hash)
            user = db.scalar(select(UserRecord).where(UserRecord.id == initial.user_id).with_for_update()) if initial else None
            verification = db.scalar(select(EmailVerificationRecord).where(EmailVerificationRecord.token_hash == token_hash).with_for_update()) if user else None
            if not verification or not user or not user.is_active or _as_utc(verification.expires_at) <= now:
                raise HTTPException(status_code=400, detail="This verification link is invalid or expired.")
            user.email_verified = True
            db.query(EmailVerificationRecord).filter(EmailVerificationRecord.user_id == user.id).delete(synchronize_session=False)
            db.commit()
    else:
        with account_mutation_lock:
            verification = email_verifications_by_token_hash.get(token_hash)
            user = users_by_id.get(verification["user_id"]) if verification else None
            if not verification or not user or not user.get("is_active", True) or _as_utc(verification["expires_at"]) <= now:
                raise HTTPException(status_code=400, detail="This verification link is invalid or expired.")
            user["email_verified"] = True
            for existing_hash, existing_verification in list(email_verifications_by_token_hash.items()):
                if existing_verification["user_id"] == user["id"]:
                    del email_verifications_by_token_hash[existing_hash]
    return Response(status_code=204)


@app.post("/auth/password-reset/request", status_code=202, tags=["auth"])
def request_password_reset(payload: PasswordResetRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    settings = _password_reset_mail_settings()
    email = _validate_account_email(payload.email)
    account_key = hashlib.sha256(email.encode("utf-8")).hexdigest()
    if not login_limiter.hit(LOGIN_GLOBAL_LIMIT, "reset-global") or not login_limiter.hit(LOGIN_ACCOUNT_LIMIT, "reset-account", account_key):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.", headers={"Retry-After": "60"})
    raw_token = secrets.token_urlsafe(32)
    token_hash = _session_token_hash(raw_token)
    expires_at = _utc_now() + timedelta(minutes=30)
    found = False
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            user = db.scalar(select(UserRecord).where(UserRecord.email == email).with_for_update())
            if user and user.is_active:
                db.query(PasswordResetRecord).filter(PasswordResetRecord.user_id == user.id).delete(synchronize_session=False)
                db.add(PasswordResetRecord(token_hash=token_hash, user_id=user.id, expires_at=expires_at))
                db.commit()
                found = True
    else:
        with account_mutation_lock:
            user = users_by_email.get(email)
            if user and user.get("is_active", True):
                for existing_hash, reset in list(password_resets_by_token_hash.items()):
                    if reset["user_id"] == user["id"]:
                        del password_resets_by_token_hash[existing_hash]
                password_resets_by_token_hash[token_hash] = {"user_id": user["id"], "expires_at": expires_at}
                found = True
    if found:
        background_tasks.add_task(_send_password_reset_email, settings, email, raw_token)
    return {"message": "If the account exists, a reset email will be sent."}


@app.post("/auth/password-reset/confirm", status_code=204, tags=["auth"])
def confirm_password_reset(payload: PasswordResetConfirm) -> Response:
    token_hash = _session_token_hash(payload.token)
    if not login_limiter.hit(LOGIN_GLOBAL_LIMIT, "reset-confirm-global") or not login_limiter.hit(LOGIN_ACCOUNT_LIMIT, "reset-confirm-token", token_hash):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.", headers={"Retry-After": "60"})
    now = _utc_now()
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            initial = db.get(PasswordResetRecord, token_hash)
            user = db.scalar(select(UserRecord).where(UserRecord.id == initial.user_id).with_for_update()) if initial else None
            reset = db.scalar(select(PasswordResetRecord).where(PasswordResetRecord.token_hash == token_hash).with_for_update()) if user else None
            if not reset or not user or not user.is_active or _as_utc(reset.expires_at) <= now:
                raise HTTPException(status_code=400, detail="This reset link is invalid or expired.")
            user.password_hash = password_hasher.hash(payload.password)
            db.query(AuthSessionRecord).filter(AuthSessionRecord.user_id == user.id).delete(synchronize_session=False)
            db.query(PasswordResetRecord).filter(PasswordResetRecord.user_id == user.id).delete(synchronize_session=False)
            db.commit()
    else:
        with account_mutation_lock:
            reset = password_resets_by_token_hash.get(token_hash)
            user = users_by_id.get(reset["user_id"]) if reset else None
            if not reset or not user or not user.get("is_active", True) or _as_utc(reset["expires_at"]) <= now:
                raise HTTPException(status_code=400, detail="This reset link is invalid or expired.")
            user["password_hash"] = password_hasher.hash(payload.password)
            for existing_hash, session in list(user_sessions_by_token_hash.items()):
                if session["user_id"] == user["id"]:
                    del user_sessions_by_token_hash[existing_hash]
            for existing_hash, existing_reset in list(password_resets_by_token_hash.items()):
                if existing_reset["user_id"] == user["id"]:
                    del password_resets_by_token_hash[existing_hash]
    return Response(status_code=204)


@app.post("/auth/login", response_model=AuthUserResponse, tags=["auth"])
def login(payload: AuthLoginRequest, request: Request, response: Response) -> AuthUserResponse:
    account_key = hashlib.sha256(payload.email.strip().lower().encode("utf-8")).hexdigest()
    if not login_limiter.hit(LOGIN_GLOBAL_LIMIT, "login-global") or not login_limiter.hit(LOGIN_ACCOUNT_LIMIT, "login-account", account_key):
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Please wait a minute and try again.", headers={"Retry-After": "60"})
    email = _validate_account_email(payload.email)
    user = _get_user_by_email(email)
    password_hash = user.get("password_hash") if user else dummy_password_hash
    password_valid = False
    try:
        password_valid = password_hasher.verify(password_hash, payload.password)
    except (VerifyMismatchError, InvalidHashError):
        password_valid = False
    if not user or not user.get("is_active", True) or not password_valid:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    if EMAIL_VERIFICATION_REQUIRED and not user.get("email_verified", True):
        raise HTTPException(status_code=403, detail="Verify your email address before signing in.")
    if password_hasher.check_needs_rehash(password_hash):
        new_hash = password_hasher.hash(payload.password)
        if PERSISTENCE_MODE == "database":
            with SessionLocal() as db:
                record = db.scalar(select(UserRecord).where(UserRecord.id == user["id"]).with_for_update())
                if not record or record.password_hash != password_hash:
                    raise HTTPException(status_code=401, detail="Email or password is incorrect.")
                record.password_hash = new_hash
                db.commit()
        else:
            with account_mutation_lock:
                if user["password_hash"] != password_hash:
                    raise HTTPException(status_code=401, detail="Email or password is incorrect.")
                user["password_hash"] = new_hash
        password_hash = new_hash
    _set_login_session(response, request, user["id"], password_hash, payload.mfa_code)
    return AuthUserResponse(id=user["id"], email=user["email"], name=user["name"], is_admin=user["is_admin"], email_verified=user.get("email_verified", True))


@app.post("/auth/logout", status_code=204, tags=["auth"])
def logout(request: Request, response: Response) -> Response:
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if raw_token:
        token_hash = _session_token_hash(raw_token)
        if PERSISTENCE_MODE == "database":
            with SessionLocal() as db:
                session = db.get(AuthSessionRecord, token_hash)
                if session and session.revoked_at is None:
                    session.revoked_at = _utc_now()
                    db.commit()
        else:
            session = user_sessions_by_token_hash.get(token_hash)
            if session:
                session["revoked_at"] = _utc_now()
    _clear_login_session(response)
    response.status_code = 204
    return response


@app.delete("/auth/me", status_code=204, tags=["auth"])
def delete_current_account(payload: AuthPasswordRequest, request: Request, response: Response) -> Response:
    if not AUTH_REQUIRED:
        raise HTTPException(status_code=403, detail="Account deletion requires authentication.")
    actor = _authenticated_user(request)
    account_key = hashlib.sha256(actor["email"].strip().lower().encode("utf-8")).hexdigest()
    if not login_limiter.hit(LOGIN_GLOBAL_LIMIT, "login-global") or not login_limiter.hit(LOGIN_ACCOUNT_LIMIT, "login-account", account_key):
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait a minute and try again.", headers={"Retry-After": "60"})

    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            admins = []
            if actor["is_admin"]:
                admins = db.scalars(select(UserRecord).where(UserRecord.is_admin.is_(True), UserRecord.is_active.is_(True)).order_by(UserRecord.id).with_for_update()).all()
            user = db.scalar(select(UserRecord).where(UserRecord.id == actor["id"]).with_for_update())
            if not user or not user.is_active:
                raise HTTPException(status_code=401, detail="This account is unavailable.")
            try:
                password_valid = password_hasher.verify(user.password_hash, payload.password)
            except (VerifyMismatchError, InvalidHashError):
                password_valid = False
            if not password_valid:
                raise HTTPException(status_code=401, detail="Password is incorrect.")
            if user.is_admin and len(admins) <= 1:
                raise HTTPException(status_code=409, detail="The last active administrator cannot be deleted.")
            if db.scalar(select(ProjectRecord.id).where(ProjectRecord.owner_id == user.id).limit(1)):
                raise HTTPException(status_code=409, detail="This account owns projects. Contact an administrator before deletion.")
            _consume_mfa_database(db, user.id, payload.mfa_code)
            db.flush()
            db.query(AuthSessionRecord).filter(AuthSessionRecord.user_id == user.id).delete(synchronize_session=False)
            db.query(PasswordResetRecord).filter(PasswordResetRecord.user_id == user.id).delete(synchronize_session=False)
            db.query(EmailVerificationRecord).filter(EmailVerificationRecord.user_id == user.id).delete(synchronize_session=False)
            db.query(MfaRecoveryCodeRecord).filter(MfaRecoveryCodeRecord.user_id == user.id).delete(synchronize_session=False)
            db.query(MfaCredentialRecord).filter(MfaCredentialRecord.user_id == user.id).delete(synchronize_session=False)
            db.delete(user)
            db.commit()
    else:
        with account_mutation_lock:
            user = users_by_id.get(actor["id"])
            if not user or not user.get("is_active", True):
                raise HTTPException(status_code=401, detail="This account is unavailable.")
            try:
                password_valid = password_hasher.verify(user["password_hash"], payload.password)
            except (VerifyMismatchError, InvalidHashError):
                password_valid = False
            if not password_valid:
                raise HTTPException(status_code=401, detail="Password is incorrect.")
            if user["is_admin"] and sum(bool(item.get("is_admin") and item.get("is_active", True)) for item in users_by_id.values()) <= 1:
                raise HTTPException(status_code=409, detail="The last active administrator cannot be deleted.")
            if any(project.get("owner_id") == user["id"] for project in projects.values()):
                raise HTTPException(status_code=409, detail="This account owns projects. Contact an administrator before deletion.")
            _consume_mfa_memory(user["id"], payload.mfa_code)
            for token_hash, session in list(user_sessions_by_token_hash.items()):
                if session["user_id"] == user["id"]:
                    del user_sessions_by_token_hash[token_hash]
            for token_hash, reset in list(password_resets_by_token_hash.items()):
                if reset["user_id"] == user["id"]:
                    del password_resets_by_token_hash[token_hash]
            for token_hash, verification in list(email_verifications_by_token_hash.items()):
                if verification["user_id"] == user["id"]:
                    del email_verifications_by_token_hash[token_hash]
            for code_hash, owner_id in list(mfa_recovery_codes_by_hash.items()):
                if owner_id == user["id"]:
                    del mfa_recovery_codes_by_hash[code_hash]
            mfa_credentials_by_user.pop(user["id"], None)
            users_by_email.pop(user["email"], None)
            del users_by_id[user["id"]]
    _clear_login_session(response)
    response.status_code = 204
    return response


@app.get("/auth/registration", tags=["auth"])
def registration_availability() -> dict[str, bool]:
    if not AUTH_REQUIRED or not ALLOW_ACCOUNT_REGISTRATION or not EMAIL_VERIFICATION_REQUIRED:
        return {"available": False}
    try:
        _password_reset_mail_settings()
    except HTTPException:
        return {"available": False}
    return {"available": True}


@app.post("/auth/register", status_code=202, tags=["auth"])
def register_account(payload: AuthRegistrationRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    if not AUTH_REQUIRED or not ALLOW_ACCOUNT_REGISTRATION:
        raise HTTPException(status_code=403, detail="Account registration is unavailable. Contact an administrator.")
    if not EMAIL_VERIFICATION_REQUIRED:
        raise HTTPException(status_code=503, detail="Account registration is unavailable. Contact an administrator.")
    email = _validate_account_email(payload.email)
    account_key = hashlib.sha256(email.encode("utf-8")).hexdigest()
    if not login_limiter.hit(LOGIN_GLOBAL_LIMIT, "registration-global") or not login_limiter.hit(LOGIN_ACCOUNT_LIMIT, "registration-account", account_key):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.", headers={"Retry-After": "60"})
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be blank.")
    settings = _password_reset_mail_settings()
    password_hash = password_hasher.hash(payload.password)
    token = secrets.token_urlsafe(32)
    token_hash = _session_token_hash(token)
    expires_at = _utc_now() + timedelta(hours=24)
    user_data = {
        "id": str(uuid4()), "email": email, "name": name,
        "password_hash": password_hash, "is_admin": False, "is_active": True, "email_verified": False,
    }
    created = False
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            db.add(UserRecord(**user_data))
            db.add(EmailVerificationRecord(token_hash=token_hash, user_id=user_data["id"], expires_at=expires_at))
            try:
                db.commit()
                created = True
            except IntegrityError:
                db.rollback()
                if not db.scalar(select(UserRecord.id).where(UserRecord.email == email)):
                    raise
    else:
        with account_mutation_lock:
            if email not in users_by_email:
                users_by_email[email] = user_data
                users_by_id[user_data["id"]] = user_data
                email_verifications_by_token_hash[token_hash] = {"user_id": user_data["id"], "expires_at": expires_at}
                created = True
    if created:
        background_tasks.add_task(_send_verification_email, settings, email, token)
    return {"message": "If registration is available for this email, check your inbox for a verification link."}


@app.post("/auth/users", response_model=AuthUserResponse, status_code=201, tags=["auth"])
def create_account(payload: AuthUserCreateRequest, request: Request, background_tasks: BackgroundTasks) -> AuthUserResponse:
    actor = _authenticated_user(request) if AUTH_REQUIRED else {"is_admin": True}
    if not actor.get("is_admin"):
        raise HTTPException(status_code=403, detail="Administrator access is required to create accounts.")
    email = _validate_account_email(payload.email)
    existing = _get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    settings = _password_reset_mail_settings() if EMAIL_VERIFICATION_REQUIRED else None
    raw_token = secrets.token_urlsafe(32) if settings else None
    user_data = {
        "id": str(uuid4()), "email": email, "name": payload.name.strip(),
        "password_hash": password_hasher.hash(payload.password),
        "is_admin": payload.is_admin, "is_active": True, "email_verified": False,
    }
    if not user_data["name"]:
        raise HTTPException(status_code=422, detail="Name cannot be blank.")
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            db.add(UserRecord(**user_data))
            if raw_token:
                db.add(EmailVerificationRecord(token_hash=_session_token_hash(raw_token), user_id=user_data["id"], expires_at=_utc_now() + timedelta(hours=24)))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                raise HTTPException(status_code=409, detail="An account with this email already exists.") from None
    else:
        with account_mutation_lock:
            if email in users_by_email:
                raise HTTPException(status_code=409, detail="An account with this email already exists.")
            users_by_email[email] = user_data
            users_by_id[user_data["id"]] = user_data
            if raw_token:
                email_verifications_by_token_hash[_session_token_hash(raw_token)] = {"user_id": user_data["id"], "expires_at": _utc_now() + timedelta(hours=24)}
    if settings and raw_token:
        background_tasks.add_task(_send_verification_email, settings, email, raw_token)
    return AuthUserResponse(id=user_data["id"], email=email, name=user_data["name"], is_admin=user_data["is_admin"], email_verified=False)


@app.get("/camera/insta360/status", response_model=CameraStatusResponse, tags=["camera"])
def camera_status() -> CameraStatusResponse:
    status = camera_adapter.status()
    return CameraStatusResponse(
        mode=status.mode,
        supports_web_browser=status.supports_web_browser,
        supports_native_app=status.supports_native_app,
        sdk_available=status.sdk_available,
        supports_direct_sdk=status.supports_direct_sdk,
        browser_upload_supported=status.browser_upload_supported,
        recommended_action=status.recommended_action,
    )


@app.get("/camera/insta360/adapter", tags=["camera"])
def camera_adapter_status() -> dict[str, object]:
    return camera_adapter.status().as_dict()


@app.get("/capture-processing/status", tags=["capture-processing"])
def capture_processing_status() -> dict[str, object]:
    status = capture_processor.status()
    return {
        "processor": status.processor,
        "status": status.status,
        "capabilities": list(status.capabilities),
        "message": status.message,
    }


def _analytics_enabled() -> bool:
    return PERSISTENCE_MODE == "database" and os.getenv("ANALYTICS_ENABLED", "false").strip().lower() in {"1", "true", "yes"}


@app.get("/analytics/config", tags=["analytics"])
def get_analytics_config(request: Request) -> dict[str, bool]:
    if AUTH_REQUIRED:
        _authenticated_user(request)
    return {"enabled": _analytics_enabled()}


@app.post("/analytics/events", status_code=204, tags=["analytics"])
def submit_analytics_event(payload: AnalyticsEventRequest, request: Request) -> Response:
    if AUTH_REQUIRED:
        _authenticated_user(request)
    if not _analytics_enabled():
        raise HTTPException(status_code=404, detail="Analytics is disabled.")
    if not login_limiter.hit(ANALYTICS_GLOBAL_LIMIT, "analytics-global"):
        raise HTTPException(status_code=429, detail="Analytics rate limit exceeded.")
    with SessionLocal() as db:
        record_analytics_event(db, payload.event, _utc_now().date())
    return Response(status_code=204)


@app.get("/analytics/summary", tags=["analytics"])
def get_analytics_summary(request: Request) -> dict[str, Any]:
    actor = _authenticated_user(request) if AUTH_REQUIRED else {"is_admin": True}
    if not actor.get("is_admin"):
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    if not _analytics_enabled():
        raise HTTPException(status_code=404, detail="Analytics is disabled.")
    with SessionLocal() as db:
        return {"retention_days": 90, "daily": analytics_summary(db, _utc_now().date())}


@app.post("/projects/{project_id}/visual-odometry", tags=["capture-processing"])
def project_visual_odometry(project_id: str, request: Request) -> dict[str, object]:
    """Estimate motion across the ordered preview frames of a project's pins."""
    _ensure_project_ownership(project_id, _get_user_id(request))
    frame_paths: list[str] = []
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            pins = (db.query(PinRecord).filter(PinRecord.project_id == project_id)
                     .order_by(PinRecord.route_order.asc(), PinRecord.created_at.asc(), PinRecord.id.asc()).all())
            for pin in pins:
                if pin.preview_key:
                    candidate = UPLOAD_DIR / pin.preview_key.removeprefix("uploads/")
                    if candidate.exists():
                        frame_paths.append(str(candidate))
    else:
        for pin in pins_by_project.get(project_id, []):
            if pin.get("preview_key"):
                candidate = UPLOAD_DIR / pin["preview_key"].removeprefix("uploads/")
                if candidate.exists():
                    frame_paths.append(str(candidate))

    if not frame_paths:
        return {"source": "visual_odometry", "available": True, "segments": [], "message": "No preview frames are available yet. Save waypoints with native .insp/.insv files first."}

    if os.getenv("MEDIA_WORKER_SOCKET", "").strip():
        raise HTTPException(status_code=503, detail="Visual odometry is unavailable in isolated processing mode.")
    return capture_processor.estimate_visual_motion(frame_paths)


@app.post("/projects", response_model=ProjectResponse, status_code=201, tags=["projects"])
def create_project(payload: ProjectCreateRequest, request: Request) -> ProjectResponse:
    user_id = _get_user_id(request)
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            if AUTH_REQUIRED:
                user = db.scalar(select(UserRecord).where(UserRecord.id == user_id).with_for_update())
                if not user or not user.is_active:
                    raise HTTPException(status_code=401, detail="This account is unavailable.")
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

    with account_mutation_lock:
        if AUTH_REQUIRED and (user_id not in users_by_id or not users_by_id[user_id].get("is_active", True)):
            raise HTTPException(status_code=401, detail="This account is unavailable.")
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
def create_share_link(
    project_id: str, request: Request, payload: ShareLinkCreateRequest = Body(default=ShareLinkCreateRequest())
) -> ShareLinkResponse:
    user_id = _get_user_id(request)
    _ensure_project_ownership(project_id, user_id)
    now = _utc_now()
    expires_at = now + timedelta(days=payload.expires_in_days)
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            project = db.get(ProjectRecord, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            share_link = db.scalar(select(ShareLinkRecord).where(ShareLinkRecord.project_id == project_id))
            if not share_link:
                share_link = ShareLinkRecord(token=secrets.token_urlsafe(32), project_id=project_id)
                db.add(share_link)
            else:
                share_link.token = secrets.token_urlsafe(32)
            share_link.created_at = now
            share_link.expires_at = expires_at
            share_link.revoked_at = None
            db.commit()

            return ShareLinkResponse(
                project_id=project_id,
                share_token=share_link.token,
                share_link=_create_share_url(share_link.token),
                expires_at=expires_at,
            )

    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    previous_link = share_links_by_project.get(project_id)
    if previous_link:
        share_token_to_project.pop(previous_link["token"], None)
    share_token = secrets.token_urlsafe(32)
    project_share_tokens[project_id] = share_token
    share_token_to_project[share_token] = project_id
    share_links_by_project[project_id] = {
        "token": share_token, "created_at": now, "expires_at": expires_at, "revoked_at": None,
    }

    return ShareLinkResponse(
        project_id=project_id,
        share_token=share_token,
        share_link=_create_share_url(share_token),
        expires_at=expires_at,
    )


@app.delete("/projects/{project_id}/share-link", status_code=204, tags=["projects"])
def revoke_share_link(project_id: str, request: Request) -> Response:
    _ensure_project_ownership(project_id, _get_user_id(request))
    now = _utc_now()
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            if not db.get(ProjectRecord, project_id):
                raise HTTPException(status_code=404, detail="Project not found")
            link = db.scalar(select(ShareLinkRecord).where(ShareLinkRecord.project_id == project_id))
            if link and link.revoked_at is None:
                link.revoked_at = now
                db.commit()
        return Response(status_code=204)

    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    link = share_links_by_project.get(project_id)
    if link and link["revoked_at"] is None:
        link["revoked_at"] = now
        share_token_to_project.pop(link["token"], None)
    return Response(status_code=204)


@app.get("/share/{share_token}", response_model=ProjectDetailResponse, tags=["projects"])
def open_shared_project(share_token: str) -> ProjectDetailResponse:
    if PERSISTENCE_MODE == "database":
        set_share_token(share_token)
        with SessionLocal() as db:
            link = db.get(ShareLinkRecord, share_token)
            if not link or link.revoked_at is not None or _as_utc(link.expires_at) <= _utc_now():
                raise HTTPException(status_code=404, detail="Share link not found")

            project = db.get(ProjectRecord, link.project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            return _project_detail_from_record(db, project)

    project_id = share_token_to_project.get(share_token)
    if not project_id:
        raise HTTPException(status_code=404, detail="Share link not found")
    link = share_links_by_project.get(project_id)
    if not link or link["token"] != share_token or link["revoked_at"] is not None or _as_utc(link["expires_at"]) <= _utc_now():
        raise HTTPException(status_code=404, detail="Share link not found")

    return _build_project_detail_memory(project_id)


@app.post("/projects/{project_id}/annotations", response_model=AnnotationResponse, status_code=201, tags=["annotations"])
def create_annotation(project_id: str, payload: AnnotationCreateRequest, request: Request) -> AnnotationResponse:
    user_id = _get_user_id(request)
    _ensure_project_ownership(project_id, user_id)
    annotation_id = str(uuid4())

    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            if not db.get(ProjectRecord, project_id):
                raise HTTPException(status_code=404, detail="Project not found")
            if payload.pin_id:
                pin = db.get(PinRecord, payload.pin_id)
                if not pin or pin.project_id != project_id:
                    raise HTTPException(status_code=404, detail="Pin not found in project")
            annotation = AnnotationRecord(
                id=annotation_id,
                project_id=project_id,
                pin_id=payload.pin_id,
                author_id=user_id,
                body=payload.body,
                status=payload.status,
                assigned_to=payload.assigned_to,
                floor_plan_x=payload.floor_plan_x,
                floor_plan_y=payload.floor_plan_y,
            )
            db.add(annotation)
            db.commit()
            db.refresh(annotation)
            return _annotation_response_from_record(annotation)

    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.pin_id:
        pin = pins_by_id.get(payload.pin_id)
        if not pin or pin["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Pin not found in project")
    annotation = {
        "id": annotation_id,
        "project_id": project_id,
        "pin_id": payload.pin_id,
        "author_id": user_id,
        "body": payload.body,
        "status": payload.status,
        "assigned_to": payload.assigned_to,
        "floor_plan_x": payload.floor_plan_x,
        "floor_plan_y": payload.floor_plan_y,
    }
    annotations_by_project.setdefault(project_id, []).append(annotation)
    annotations_by_id[annotation_id] = annotation
    return _annotation_response_from_memory(annotation)


@app.get("/projects/{project_id}/annotations", response_model=list[AnnotationResponse], tags=["annotations"])
def list_annotations(project_id: str, request: Request) -> list[AnnotationResponse]:
    _ensure_project_ownership(project_id, _get_user_id(request))
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            if not db.get(ProjectRecord, project_id):
                raise HTTPException(status_code=404, detail="Project not found")
            records = db.query(AnnotationRecord).filter(AnnotationRecord.project_id == project_id).all()
            return [_annotation_response_from_record(record) for record in records]
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    return [_annotation_response_from_memory(item) for item in annotations_by_project.get(project_id, [])]


@app.post("/projects/{project_id}/pins", response_model=PinResponse, status_code=201, tags=["pins"])
def create_pin(project_id: str, payload: PinCreateRequest, request: Request) -> PinResponse:
    user_id = _get_user_id(request)
    _ensure_project_ownership(project_id, user_id)
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            project = db.get(ProjectRecord, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            next_route_order = (db.query(func.max(PinRecord.route_order)).filter(PinRecord.project_id == project_id).scalar() or 0) + 1
            pin = PinRecord(
                id=str(uuid4()),
                project_id=project_id,
                created_at=_utc_now(),
                route_order=next_route_order,
                latitude=payload.latitude,
                longitude=payload.longitude,
                heading=payload.heading,
                position_x=payload.position_x,
                position_y=payload.position_y,
                calibration_json=None,
                telemetry_json=json.dumps(payload.telemetry) if payload.telemetry else None,
                processing_status="metadata_received" if payload.telemetry else "not_requested",
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
        "route_order": len(pins_by_project[project_id]) + 1,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "heading": payload.heading,
        "position_x": payload.position_x,
        "position_y": payload.position_y,
        "auto_position_x": None,
        "auto_position_y": None,
        "alignment_confidence": 0.0,
        "calibration_state": "unreviewed",
        "calibration_data": None,
        "telemetry": payload.telemetry,
        "waypoints": None,
        "preview_key": None,
        "processing_status": "metadata_received" if payload.telemetry else "not_requested",
        "processing_error": None,
        "captured_on": payload.captured_on,
        "photo_key": payload.photo_key,
        "media_type": payload.media_type or "photo",
        "native_file_key": payload.native_file_key,
        "thumbnail_key": payload.thumbnail_key,
    }
    pins_by_project[project_id].append(pin)
    pins_by_id[pin_id] = pin
    return _pin_response_from_memory(pin)


@app.patch("/projects/{project_id}/pins/{pin_id}/calibration", response_model=PinResponse, tags=["pins"])
def update_pin_calibration(
    project_id: str,
    pin_id: str,
    payload: PinCalibrationRequest,
    request: Request,
) -> PinResponse:
    """Save a reviewer-verified floor-plan position while preserving auto-calibration."""
    user_id = _get_user_id(request)
    _ensure_project_ownership(project_id, user_id)
    calibration_update = {
        "state": "manually_verified",
        "position_x": payload.position_x,
        "position_y": payload.position_y,
        "reviewed_by": user_id,
        "note": payload.note,
    }

    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            pin = db.get(PinRecord, pin_id)
            if not pin or pin.project_id != project_id:
                raise HTTPException(status_code=404, detail="Pin not found")
            pin.position_x = payload.position_x
            pin.position_y = payload.position_y
            pin.calibration_json = json.dumps(calibration_update)
            db.commit()
            db.refresh(pin)
            return _pin_response_from_record(pin)

    pin = pins_by_id.get(pin_id)
    if not pin or pin["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Pin not found")
    pin["position_x"] = payload.position_x
    pin["position_y"] = payload.position_y
    pin["calibration_state"] = calibration_update["state"]
    pin["calibration_data"] = calibration_update
    return _pin_response_from_memory(pin)


@app.get("/projects/{project_id}/pins", response_model=list[PinResponse], tags=["pins"])
def list_pins(project_id: str, request: Request) -> list[PinResponse]:
    user_id = _get_user_id(request)
    _ensure_project_ownership(project_id, user_id)
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            project = db.get(ProjectRecord, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            pins = (db.query(PinRecord).filter(PinRecord.project_id == project_id)
                     .order_by(PinRecord.route_order.asc(), PinRecord.created_at.asc(), PinRecord.id.asc()).all())
            return [_pin_response_from_record(pin) for pin in pins]

    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    return [_pin_response_from_memory(pin) for pin in pins_by_project.get(project_id, [])]


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

    return _pin_response_from_memory(pin)


@app.delete("/projects/{project_id}/pins/{pin_id}", tags=["pins"])
def delete_pin(project_id: str, pin_id: str, request: Request) -> dict[str, object]:
    """Remove a waypoint and its capture from a project."""
    _ensure_project_ownership(project_id, _get_user_id(request))
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            pin = db.get(PinRecord, pin_id)
            if not pin or pin.project_id != project_id:
                raise HTTPException(status_code=404, detail="Pin not found")
            db.delete(pin)
            db.commit()
            return {"deleted": True, "id": pin_id}

    pin = pins_by_id.get(pin_id)
    if not pin or pin["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Pin not found")
    pins_by_project[project_id] = [p for p in pins_by_project.get(project_id, []) if p["id"] != pin_id]
    pins_by_id.pop(pin_id, None)
    return {"deleted": True, "id": pin_id}


@app.patch("/projects/{project_id}/pins/{pin_id}", response_model=PinResponse, tags=["pins"])
def update_pin(project_id: str, pin_id: str, request: Request, payload: PinUpdateRequest) -> PinResponse:
    """Update a pin's photo or heading."""
    _ensure_project_ownership(project_id, _get_user_id(request))
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            pin = db.get(PinRecord, pin_id)
            if not pin or pin.project_id != project_id:
                raise HTTPException(status_code=404, detail="Pin not found")
            if payload.heading is not None:
                pin.heading = payload.heading
            db.commit()
            db.refresh(pin)
            return _pin_response_from_record(pin)

    pin = pins_by_id.get(pin_id)
    if not pin or pin["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Pin not found")
    if payload.heading is not None:
        pin["heading"] = payload.heading
    return _pin_response_from_memory(pin)


@app.post("/projects/{project_id}/pins/{pin_id}/upload", response_model=UploadResponse, tags=["pins"])
def upload_pin_photo(project_id: str, pin_id: str, request: Request, file: UploadFile = File(...)) -> UploadResponse:
    if file.filename is None:
        raise HTTPException(status_code=400, detail="A filename is required")
    _validate_upload_file(file, {".jpg", ".jpeg", ".png", ".webp"}, MAX_IMAGE_UPLOAD_BYTES)

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


@app.post("/projects/{project_id}/pins/{pin_id}/native-upload", response_model=NativeUploadResponse, tags=["pins"])
def upload_pin_native_file(project_id: str, pin_id: str, request: Request, file: UploadFile = File(...)) -> NativeUploadResponse:
    if file.filename is None:
        raise HTTPException(status_code=400, detail="A filename is required")
    _validate_upload_file(
        file, {".insp", ".insv", ".mp4", ".zip", ".jpg", ".jpeg", ".png"}, MAX_NATIVE_UPLOAD_BYTES
    )

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

            native_key = _store_native_file(project_id, pin_id, file)
            pin.native_file_key = native_key
            pin.media_type = pin.media_type or "insta360"
            db.commit()
            return NativeUploadResponse(id=pin_id, native_file_key=native_key, photo_key=pin.photo_key)

    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    pin = pins_by_id.get(pin_id)
    if not pin or pin["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Pin not found")

    native_key = _store_native_file(project_id, pin_id, file)
    pin["native_file_key"] = native_key
    pin["media_type"] = pin.get("media_type") or "insta360"
    return NativeUploadResponse(id=pin_id, native_file_key=native_key, photo_key=pin.get("photo_key"))


@app.post("/projects/{project_id}/pins/{pin_id}/process", tags=["capture-processing"])
def process_pin_capture(project_id: str, pin_id: str, request: Request) -> dict[str, object]:
    _ensure_project_ownership(project_id, _get_user_id(request))

    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            pin = db.get(PinRecord, pin_id)
            if not pin or pin.project_id != project_id:
                raise HTTPException(status_code=404, detail="Pin not found")
            telemetry = json.loads(pin.telemetry_json) if pin.telemetry_json else None
            result = _process_capture_telemetry(telemetry)
            pin.processing_status = str(result["status"])
            pin.processing_error = None if result["status"] == "ready" else str(result["message"])
            
            if result.get("parsed_telemetry"):
                parsed = result["parsed_telemetry"]
                waypoint_result = capture_processor.estimate_route_waypoints(parsed)
                if waypoint_result.get("waypoints"):
                    pin.waypoints_json = json.dumps(waypoint_result)
                    
                    calibration_result = capture_processor.calibrate_to_floor_plan(waypoint_result)
                    pin.auto_position_x = calibration_result.get("auto_position_x")
                    pin.auto_position_y = calibration_result.get("auto_position_y")
                    pin.alignment_confidence = calibration_result.get("alignment_confidence", 0.0)
                    pin.calibration_json = json.dumps(calibration_result)
            
            if not pin.native_file_key and pin.photo_key and Path(pin.photo_key).suffix.lower() in {".insp", ".insv"}:
                pin.native_file_key = pin.photo_key
                pin.photo_key = None

            if pin.native_file_key and not pin.preview_key:
                _validate_capture_media_key(pin.native_file_key, project_id, pin_id)
                try:
                    with _materialized_media_path(pin.native_file_key) as native_file_path:
                        if native_file_path.exists():
                            preview_result = _extract_capture_preview(native_file_path)
                            if preview_result.get("preview_available") and preview_result.get("preview_data"):
                                pin.preview_key = _store_preview(project_id, pin_id, preview_result["preview_data"])
                            else:
                                result["preview_error"] = preview_result.get("message", "No browser preview could be generated.")
                except Exception:
                    logger.exception("Could not process native media for pin %s", pin_id)
                    result["preview_error"] = "The original capture could not be read for preview generation. Check the app logs."
            
            db.commit()
            return result

    pin = pins_by_id.get(pin_id)
    if not pin or pin["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Pin not found")
    result = _process_capture_telemetry(pin.get("telemetry"))
    pin["processing_status"] = str(result["status"])
    pin["processing_error"] = None if result["status"] == "ready" else str(result["message"])
    
    if result.get("parsed_telemetry"):
        parsed = result["parsed_telemetry"]
        waypoint_result = capture_processor.estimate_route_waypoints(parsed)
        if waypoint_result.get("waypoints"):
            pin["waypoints"] = waypoint_result.get("waypoints", [])
            
            calibration_result = capture_processor.calibrate_to_floor_plan(waypoint_result)
            pin["auto_position_x"] = calibration_result.get("auto_position_x")
            pin["auto_position_y"] = calibration_result.get("auto_position_y")
            pin["alignment_confidence"] = calibration_result.get("alignment_confidence", 0.0)
    
    if not pin.get("native_file_key") and pin.get("photo_key") and Path(pin["photo_key"]).suffix.lower() in {".insp", ".insv"}:
        pin["native_file_key"] = pin["photo_key"]
        pin["photo_key"] = None

    if pin.get("native_file_key") and not pin.get("preview_key"):
        _validate_capture_media_key(pin["native_file_key"], project_id, pin_id)
        try:
            with _materialized_media_path(pin["native_file_key"]) as native_file_path:
                if native_file_path.exists():
                    preview_result = _extract_capture_preview(native_file_path)
                    if preview_result.get("preview_available") and preview_result.get("preview_data"):
                        pin["preview_key"] = _store_preview(project_id, pin_id, preview_result["preview_data"])
                    else:
                        result["preview_error"] = preview_result.get("message", "No browser preview could be generated.")
        except Exception:
            logger.exception("Could not process native media for pin %s", pin_id)
            result["preview_error"] = "The original capture could not be read for preview generation. Check the app logs."
    
    return result




@app.post("/projects/{project_id}/floor-plan-upload", response_model=FloorPlanUploadResponse, tags=["projects"])
def upload_floor_plan(project_id: str, request: Request, file: UploadFile = File(...)) -> FloorPlanUploadResponse:
    if file.filename is None:
        raise HTTPException(status_code=400, detail="A filename is required")
    _validate_upload_file(file, {".pdf", ".jpg", ".jpeg", ".png"}, MAX_FLOOR_PLAN_UPLOAD_BYTES)

    _ensure_project_ownership(project_id, _get_user_id(request))
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            if not db.get(ProjectRecord, project_id):
                raise HTTPException(status_code=404, detail="Project not found")
    elif project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    media_key = _store_floor_plan(project_id, file)
    floor_plan = FloorPlanUploadResponse(
        filename=Path(media_key).name,
        media_key=media_key,
        media_url=f"/media/{media_key}",
        content_type="image/png" if media_key.endswith(".png") else file.content_type,
    )
    if PERSISTENCE_MODE == "database":
        with SessionLocal() as db:
            project = db.get(ProjectRecord, project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            project.floor_plan_json = floor_plan.model_dump_json()
            db.commit()
    else:
        projects[project_id]["floor_plan"] = floor_plan.model_dump()
    return floor_plan


@app.get("/media/{media_path:path}", tags=["media"])
def serve_media(media_path: str, request: Request):
    media_parts = media_path.split("/")
    if len(media_parts) < 3 or media_parts[0] not in {"uploads", "floorplans", "previews"}:
        raise HTTPException(status_code=404, detail="Media file not found")
    media_namespace, project_id = media_parts[:2]
    _ensure_project_ownership(project_id, _get_user_id(request))
    is_native = media_namespace == "uploads" and len(media_parts) > 3 and media_parts[3] == "native"
    safe_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".pdf": "application/pdf"}
    media_type = safe_types.get(Path(media_path).suffix.lower(), "application/octet-stream") if not is_native else "application/octet-stream"
    headers = {"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"}
    if media_type == "application/octet-stream":
        headers["Content-Disposition"] = "attachment"

    if STORAGE_BACKEND == "s3":
        if not media_path.startswith(f"{media_namespace}/{project_id}/"):
            raise HTTPException(status_code=404, detail="Media file not found")
        try:
            object_response = _s3_client().get_object(Bucket=os.environ["S3_BUCKET"], Key=media_path)
        except Exception as exc:
            logger.exception("Could not read Spaces media object %s", media_path)
            raise HTTPException(status_code=404, detail="Media file not found") from exc

        body = object_response["Body"]

        def stream_object():
            try:
                while chunk := body.read(64 * 1024):
                    yield chunk
            finally:
                body.close()

        content_length = object_response.get("ContentLength")
        if content_length is not None:
            headers["Content-Length"] = str(content_length)
        return StreamingResponse(
            stream_object(),
            media_type=media_type,
            headers=headers,
        )

    relative_path = media_path.removeprefix("uploads/")
    requested_path = (UPLOAD_DIR / relative_path).resolve()
    upload_root = UPLOAD_DIR.resolve()
    project_root = (
        UPLOAD_DIR / project_id
        if media_namespace == "uploads"
        else UPLOAD_DIR / media_namespace / project_id
    ).resolve()
    if upload_root not in requested_path.parents or project_root not in requested_path.parents or not requested_path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(requested_path, media_type=media_type, headers=headers)


@app.get("/index.html")
def serve_index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/map.html")
def serve_map() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "map.html")


@app.get("/review.html")
def serve_review() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "review.html")


@app.get("/share.html")
def serve_share() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "share.html")


@app.get("/{file_name}")
def serve_static_file(file_name: str) -> FileResponse:
    candidate = FRONTEND_DIR / file_name
    if candidate.is_file():
        return FileResponse(candidate)
    raise HTTPException(status_code=404, detail="File not found")


class PublicFrontendFiles(StaticFiles):
    async def get_response(self, path: str, scope: Any) -> Response:
        if any(part.startswith(".") for part in path.replace("\\", "/").split("/") if part):
            raise HTTPException(status_code=404, detail="Not Found")
        return await super().get_response(path, scope)


app.mount("/", PublicFrontendFiles(directory=str(FRONTEND_DIR)), name="frontend")
