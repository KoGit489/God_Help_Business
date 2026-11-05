from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ProjectRecord(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False, default="demo-user")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft")

    pins: Mapped[list[PinRecord]] = relationship(back_populates="project", cascade="all, delete-orphan")
    share_links: Mapped[list[ShareLinkRecord]] = relationship(back_populates="project", cascade="all, delete-orphan")
    capture_sessions: Mapped[list[CaptureSessionRecord]] = relationship(back_populates="project", cascade="all, delete-orphan")


class PinRecord(Base):
    __tablename__ = "pins"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    heading: Mapped[float] = mapped_column(Float, nullable=False)
    position_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    auto_position_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    auto_position_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    alignment_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    telemetry_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    waypoints_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    calibration_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(64), nullable=False, default="not_requested")
    processing_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    captured_on: Mapped[str] = mapped_column(String(64), nullable=False)
    photo_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(64), nullable=True, default="photo")
    native_file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    project: Mapped[ProjectRecord] = relationship(back_populates="pins")


class AnnotationRecord(Base):
    __tablename__ = "annotations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    pin_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("pins.id"), nullable=True)
    author_id: Mapped[str] = mapped_column(String(128), nullable=False, default="demo-user")
    body: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    assigned_to: Mapped[str | None] = mapped_column(String(128), nullable=True)
    floor_plan_x: Mapped[float] = mapped_column(Float, nullable=False)
    floor_plan_y: Mapped[float] = mapped_column(Float, nullable=False)


class ShareLinkRecord(Base):
    __tablename__ = "share_links"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False, unique=True)

    project: Mapped[ProjectRecord] = relationship(back_populates="share_links")


class CaptureSessionRecord(Base):
    __tablename__ = "capture_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    floor_plan_key: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="recording")
    started_at: Mapped[str] = mapped_column(String(64), nullable=False)
    ended_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    calibration_json: Mapped[str] = mapped_column(Text, nullable=False)
    device_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    pin_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[ProjectRecord] = relationship(back_populates="capture_sessions")
    events: Mapped[list[CaptureSessionEventRecord]] = relationship(back_populates="session", cascade="all, delete-orphan")


class CaptureSessionEventRecord(Base):
    __tablename__ = "capture_session_events"
    __table_args__ = (UniqueConstraint("session_id", "sequence", name="uq_capture_session_event_sequence"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("capture_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_at: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    session: Mapped[CaptureSessionRecord] = relationship(back_populates="events")
