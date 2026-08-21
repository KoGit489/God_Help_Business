from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String
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


class PinRecord(Base):
    __tablename__ = "pins"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    heading: Mapped[float] = mapped_column(Float, nullable=False)
    position_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_on: Mapped[str] = mapped_column(String(64), nullable=False)
    photo_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(64), nullable=True, default="photo")
    native_file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    project: Mapped[ProjectRecord] = relationship(back_populates="pins")


class ShareLinkRecord(Base):
    __tablename__ = "share_links"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.id"), nullable=False, unique=True)

    project: Mapped[ProjectRecord] = relationship(back_populates="share_links")
