from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import boto3
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection

EXPECTED_TABLES = frozenset({
    "projects", "pins", "annotations", "share_links", "users", "user_sessions",
    "password_resets", "email_verifications", "mfa_credentials", "mfa_recovery_codes", "analytics_daily",
})


def database_inventory(connection: Connection) -> tuple[dict[str, int], set[str]]:
    if connection.dialect.name == "postgresql":
        connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        connection.execute(text("SET LOCAL row_security = off"))
    existing = set(inspect(connection).get_table_names())
    missing = EXPECTED_TABLES - existing
    if missing:
        raise ValueError("Database is missing expected application tables.")
    counts = {}
    preparer = connection.dialect.identifier_preparer
    for table in sorted(EXPECTED_TABLES):
        counts[table] = connection.execute(text(f"SELECT COUNT(*) FROM {preparer.quote(table)}")).scalar_one()
    keys: set[str] = set()
    for row in connection.execute(text("SELECT photo_key, thumbnail_key, native_file_key, preview_key FROM pins")):
        keys.update(value for value in row if isinstance(value, str) and value)
    for (floor_plan_json,) in connection.execute(text("SELECT floor_plan_json FROM projects WHERE floor_plan_json IS NOT NULL")):
        floor_plan = json.loads(floor_plan_json)
        if not isinstance(floor_plan, dict) or not isinstance(floor_plan.get("media_key"), str) or not floor_plan["media_key"]:
            raise ValueError("A stored floor plan has no media key.")
        keys.add(floor_plan["media_key"])
    return counts, keys


def object_digest(client: Any, bucket: str, key: str) -> dict[str, Any]:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    digest = hashlib.sha256()
    size = 0
    try:
        while chunk := body.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    finally:
        body.close()
    if size != response["ContentLength"]:
        raise ValueError("Media object length did not match its response.")
    return {"size": size, "sha256": digest.hexdigest()}


def capture_inventory(connection: Connection, client: Any, bucket: str) -> dict[str, Any]:
    counts, keys = database_inventory(connection)
    objects = {key: object_digest(client, bucket, key) for key in sorted(keys)}
    return {"version": 1, "table_counts": counts, "objects": objects}


def verify_inventory(expected: Any, actual: dict[str, Any]) -> None:
    if not isinstance(expected, dict) or expected.get("version") != 1 or set(expected) != {"version", "table_counts", "objects"}:
        raise ValueError("Invalid restore manifest.")
    if not isinstance(expected["table_counts"], dict) or set(expected["table_counts"]) != EXPECTED_TABLES:
        raise ValueError("Invalid restore manifest table counts.")
    objects = expected["objects"]
    if not isinstance(objects, dict):
        raise ValueError("Invalid restore manifest objects.")
    for key, value in objects.items():
        if (not isinstance(key, str) or not key or not isinstance(value, dict) or set(value) != {"size", "sha256"}
                or type(value["size"]) is not int or value["size"] < 0 or not isinstance(value["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])):
            raise ValueError("Invalid restore manifest object checksum.")
    if expected != actual:
        raise ValueError("Restored table counts or referenced media do not match the manifest.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture or compare a read-only database and referenced-media inventory.")
    parser.add_argument("mode", choices=("capture", "verify"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--confirm-isolated-restore", action="store_true")
    args = parser.parse_args()
    if args.mode == "verify" and not args.confirm_isolated_restore:
        parser.error("verify requires --confirm-isolated-restore")
    database_url = os.getenv("BACKUP_CHECK_DATABASE_URL", "").strip()
    bucket = os.getenv("BACKUP_CHECK_BUCKET", "").strip()
    endpoint = os.getenv("BACKUP_CHECK_S3_ENDPOINT", "").strip()
    region = os.getenv("BACKUP_CHECK_S3_REGION", "").strip()
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")) or not bucket or not endpoint.startswith("https://") or not region:
        parser.error("Set BACKUP_CHECK_DATABASE_URL, BACKUP_CHECK_BUCKET, BACKUP_CHECK_S3_ENDPOINT (HTTPS), and BACKUP_CHECK_S3_REGION.")
    if args.mode == "verify" and (database_url == os.getenv("DATABASE_URL") or bucket == os.getenv("S3_BUCKET")):
        parser.error("Restore targets must differ from production environment settings.")
    expected = json.loads(args.manifest.read_text(encoding="utf-8")) if args.mode == "verify" else None
    engine = create_engine(database_url, pool_pre_ping=True)
    client = boto3.client("s3", endpoint_url=endpoint, region_name=region)
    try:
        with engine.connect() as connection:
            actual = capture_inventory(connection, client, bucket)
        if args.mode == "verify":
            verify_inventory(expected, actual)
            print(f"Restore inventory matched: {len(actual['table_counts'])} tables and {len(actual['objects'])} referenced objects.")
        else:
            descriptor = os.open(args.manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(actual, output, sort_keys=True, separators=(",", ":"))
            print(f"Inventory captured: {len(actual['table_counts'])} tables and {len(actual['objects'])} referenced objects.")
    finally:
        engine.dispose()
        client.close()


if __name__ == "__main__":
    main()