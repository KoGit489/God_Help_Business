from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.models import AnalyticsDailyRecord

EVENTS = frozenset({"dashboard_opened", "project_created"})
RETENTION_DAYS = 90


def prune_analytics(db: Session, today: date) -> None:
    cutoff = (today - timedelta(days=RETENTION_DAYS - 1)).isoformat()
    db.execute(delete(AnalyticsDailyRecord).where(AnalyticsDailyRecord.day < cutoff))


def record_event(db: Session, event: str, today: date) -> None:
    if event not in EVENTS:
        raise ValueError("Unknown analytics event.")
    if db.bind is None or db.bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError("Analytics requires SQLite or PostgreSQL.")
    prune_analytics(db, today)
    db.execute(
        text("INSERT INTO analytics_daily (day, event, count) VALUES (:day, :event, 1) "
             "ON CONFLICT (day, event) DO UPDATE SET count = analytics_daily.count + 1"),
        {"day": today.isoformat(), "event": event},
    )
    db.commit()


def summary(db: Session, today: date) -> list[dict[str, object]]:
    prune_analytics(db, today)
    rows = db.scalars(select(AnalyticsDailyRecord).order_by(AnalyticsDailyRecord.day.desc(), AnalyticsDailyRecord.event)).all()
    result = [{"day": row.day, "event": row.event, "count": row.count} for row in rows]
    db.commit()
    return result