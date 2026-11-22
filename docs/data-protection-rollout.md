# Data Protection and Operations Rollout

This Draft 2 change adds a constrained media worker, optional first-party aggregate analytics, project-data PostgreSQL RLS policies, and a read-only database/media restore comparison tool. It does not configure cloud backups, run a production restore, or activate RLS on an existing database. Do not describe production backups as verified until an isolated restore drill has succeeded.

## Isolated media worker

The production Compose configuration runs media jobs in a separate container with no network, a read-only root filesystem, no Linux capabilities, a non-root UID, process/memory/temp-space limits, and only the worker socket mounted. The API mounts that socket read-only. Each PDF, preview, or telemetry job gets a fresh temporary directory and a sanitized child-process environment; request and result sizes and processing time are bounded. Production startup requires `MEDIA_WORKER_SOCKET`, configured by Compose.

Native/PDF/telemetry jobs use the worker. Visual odometry is rejected in worker mode until it has a corresponding isolated implementation. The existing development path is intentionally not a sandbox. Build and exercise the Compose services in staging before deployment; Docker and representative camera files were not available for container-level validation here. The worker's resource limits may need adjustment based on safe, representative files.

## PostgreSQL RLS

RLS covers `projects`, `pins`, `annotations`, and `share_links`. Projects and child data are owner-scoped; valid, unexpired share tokens grant read-only project/pin/annotation access. PostgreSQL transaction-local `casai.user_id` and `casai.share_token` settings are set automatically for SQLAlchemy sessions. Owner and child tables use `FORCE ROW LEVEL SECURITY`.

1. Take and verify a restorable backup, then restore to a separate staging database. Test the change there first.
2. Apply `deploy/project-rls.sql` as the table-owner/migration role after the current application schema exists. Do not run it against production before staging passes.
3. Create a dedicated runtime login that is not a superuser, has no `BYPASSRLS`, and owns none of the four RLS tables. Grant only the application privileges needed on the schema's tables; grant `USAGE` on `casai_security` and `EXECUTE` on `casai_security.can_read_shared_project(text, text)` to that runtime role. Keep the migration/owner credential separate from the runtime `DATABASE_URL`.
4. Provision and migrate the schema out of band before deploying the runtime role. Set `DATABASE_URL` to the restricted runtime login and `DATABASE_REQUIRE_RLS=true`. In this mode the app skips schema creation/migrations and fails startup unless the four tables have enabled policies, owner/child policies are forced, the expected policy names/commands are present without additional policies, and the runtime role cannot bypass RLS through superuser, `BYPASSRLS`, ownership membership, `TRUNCATE`, privileged role membership, or policy-schema creation. This readiness check does not verify the exact policy expressions. Apply the reviewed SQL and test the actual effective grants separately.
5. Run `TEST_POSTGRES_RLS_URL` against a disposable PostgreSQL database to execute `tests/test_postgres_rls.py`. Then test login, account recovery, creating/editing projects, pins, annotations and sharing as two owners, and valid, expired and revoked public share links. The integration test drops and recreates the four named tables and `casai_security` schema; only use it on a disposable database.

RLS does not currently protect account/session/authentication tables. The current share-media route also remains owner-authenticated; this policy does not create guest access to media files. A separate migration workflow is required for future schema changes while strict RLS mode is active.

## Restore inventory drill

`app.restore_verify` captures exact table row counts and SHA-256/size checks for every media object referenced by pin and floor-plan records. It streams object contents and does not modify either database or bucket. Use separate read-only source and restored-target credentials, isolated restore resources, and a protected manifest. PostgreSQL inventory reads require a role able to see all rows despite RLS; keep that elevated read-only credential restricted. The manifest contains object keys and hashes, not file contents.

Set `BACKUP_CHECK_DATABASE_URL`, `BACKUP_CHECK_BUCKET`, `BACKUP_CHECK_S3_ENDPOINT` (HTTPS), and `BACKUP_CHECK_S3_REGION` through the server's secret manager. Capture a source inventory before restoring:

```powershell
python -m app.restore_verify capture .\protected-backup-manifest.json
```

Restore PostgreSQL and Spaces objects to different, isolated resources. Set the same `BACKUP_CHECK_*` variables to those restored targets and confirm they differ from `DATABASE_URL` and `S3_BUCKET`, then run:

```powershell
python -m app.restore_verify verify .\protected-backup-manifest.json --confirm-isolated-restore
```

The comparison is intentionally exact: writes between capture and the database backup can cause a mismatch. Capture an inventory for the same consistent recovery point as the database and object-store snapshot. A passing comparison establishes only that table counts and referenced object bytes match that manifest; it does not prove backup scheduling, encryption, retention, point-in-time consistency, recovery time, access controls, or disaster-recovery readiness. Arrange provider-side PostgreSQL backups and Spaces versioning/replication independently, set recovery objectives and owners, and repeat restore drills.

## Optional analytics

Analytics is disabled unless `ANALYTICS_ENABLED=true` and PostgreSQL persistence is active. The dashboard asks for browser-local consent; without consent it sends no events. Only the fixed `dashboard_opened` and `project_created` event names are accepted, and only per-day aggregate totals are stored for 90 days. No user ID, IP address, URL, share token, project text, or device identifier is recorded by the analytics table. The dashboard summarizes totals for administrators only. Turning consent off stops future events but cannot subtract past events from aggregate counts; browser-local preference does not synchronize across devices. Operational access logs remain separate and may contain request metadata.

Review and publish the organization's real privacy notice before enabling analytics. Provider choice is not needed because this implementation is first-party, but legal/privacy approval is still required. Leave analytics disabled until that review and the user-facing consent wording have been approved.

## Local verification and pending production work

Local tests cover protocol limits, real PDF/image conversion in an isolated interpreter, event consent and aggregation, restore mismatch detection, and PostgreSQL row policies against a disposable PostgreSQL 17 instance. They do not validate Docker isolation, managed-Postgres role privileges, Spaces credentials/versioning, actual backup snapshots, production networking, or legal approval. No production deployment or cloud configuration was changed.
