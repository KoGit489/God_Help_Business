from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from fastapi.testclient import TestClient

from app.analytics import record_event, summary
from app.models import AnalyticsDailyRecord


def test_analytics_counts_only_approved_events_and_prunes_old_days() -> None:
    engine = create_engine("sqlite://")
    AnalyticsDailyRecord.__table__.create(engine)
    today = date(2026, 6, 1)
    with Session(engine) as db:
        db.add(AnalyticsDailyRecord(day=(today - timedelta(days=90)).isoformat(), event="dashboard_opened", count=100))
        db.commit()
        record_event(db, "dashboard_opened", today)
        record_event(db, "dashboard_opened", today)
        record_event(db, "project_created", today)
        assert summary(db, today) == [
            {"day": today.isoformat(), "event": "dashboard_opened", "count": 2},
            {"day": today.isoformat(), "event": "project_created", "count": 1},
        ]
        with pytest.raises(ValueError):
            record_event(db, "https://example.com/share/secret", today)
        assert len(summary(db, today)) == 2


def test_analytics_endpoints_require_opt_in_and_admin_for_summary(monkeypatch, tmp_path) -> None:
    from app import main

    engine = create_engine(f"sqlite:///{tmp_path / 'analytics.db'}", connect_args={"check_same_thread": False})
    AnalyticsDailyRecord.__table__.create(engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(main, "PERSISTENCE_MODE", "database")
    monkeypatch.setattr(main, "AUTH_REQUIRED", True)
    actor = {"is_admin": False}
    monkeypatch.setattr(main, "_authenticated_user", lambda request: actor)
    client = TestClient(main.app)
    headers = {"Origin": "http://localhost:8000"}
    monkeypatch.delenv("ANALYTICS_ENABLED", raising=False)
    assert client.get("/analytics/config").json() == {"enabled": False}
    assert client.post("/analytics/events", headers=headers, json={"event": "dashboard_opened", "consent": True}).status_code == 404
    monkeypatch.setenv("ANALYTICS_ENABLED", "true")
    assert client.post("/analytics/events", headers=headers, json={"event": "dashboard_opened", "consent": False}).status_code == 422
    assert client.post("/analytics/events", headers=headers, json={"event": "dashboard_opened", "consent": True, "url": "secret"}).status_code == 422
    assert client.post("/analytics/events", headers=headers, json={"event": "dashboard_opened", "consent": True}).status_code == 204
    assert client.get("/analytics/summary").status_code == 403
    actor["is_admin"] = True
    data = client.get("/analytics/summary").json()
    assert data["retention_days"] == 90
    assert data["daily"][0]["event"] == "dashboard_opened"
    assert data["daily"][0]["count"] == 1