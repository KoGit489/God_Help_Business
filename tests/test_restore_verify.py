import io
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from app.models import Base
from app.restore_verify import capture_inventory, verify_inventory


class FakeStorage:
    def __init__(self, objects):
        self.objects = objects

    def get_object(self, *, Bucket, Key):
        data = self.objects[Key]
        return {"Body": io.BytesIO(data), "ContentLength": len(data)}


def test_restore_inventory_checks_all_referenced_media_and_row_counts() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO projects (id, owner_id, title, status, floor_plan_json) VALUES ('p', 'u', 'Site', 'draft', :plan)"), {"plan": json.dumps({"media_key": "floorplans/p/map.png"})})
        connection.execute(text("INSERT INTO pins (id, project_id, latitude, longitude, heading, captured_on, alignment_confidence, processing_status, photo_key, created_at, route_order) VALUES ('pin', 'p', 0, 0, 0, '2026-01-01', 0, 'ready', 'uploads/p/pin/photo.jpg', :created_at, 1)"), {"created_at": datetime.now(timezone.utc)})
    storage = FakeStorage({"floorplans/p/map.png": b"plan", "uploads/p/pin/photo.jpg": b"photo"})
    with engine.connect() as connection:
        expected = capture_inventory(connection, storage, "source")
    with engine.connect() as connection:
        restored = capture_inventory(connection, storage, "restore")
    verify_inventory(expected, restored)
    assert len(expected["objects"]) == 2
    storage.objects["uploads/p/pin/photo.jpg"] = b"wrong"
    with engine.connect() as connection:
        changed = capture_inventory(connection, storage, "restore")
    with pytest.raises(ValueError, match="do not match"):
        verify_inventory(expected, changed)
    del storage.objects["floorplans/p/map.png"]
    with engine.connect() as connection, pytest.raises(KeyError):
        capture_inventory(connection, storage, "restore")


def test_restore_inventory_rejects_malformed_floor_plans() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO projects (id, owner_id, title, status, floor_plan_json) VALUES ('p', 'u', 'Site', 'draft', '{}')"))
    with engine.connect() as connection, pytest.raises(ValueError, match="no media key"):
        capture_inventory(connection, FakeStorage({}), "restore")