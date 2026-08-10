# God_Help_Business

A Python-first construction field capture MVP with project review, sharing, and launch hardening.

## What phase 4 adds

- Centralized backend error envelopes with request IDs
- Readiness check endpoint at `/health/ready`
- Frontend loading, empty, and error states
- Optional production persistence with PostgreSQL
- Optional production photo storage via local volume or S3
- Containerized frontend + backend deployment setup

## Stack

- FastAPI for the backend API
- SQLAlchemy + Psycopg for persistence
- PostgreSQL + PostGIS for production database
- Local filesystem or S3-compatible object storage for uploads
- Static frontend pages for dashboard, capture, review, and shared review

## Local development quick start

1. Create and activate a Python virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and keep `APP_PERSISTENCE=memory` for local MVP mode.
4. Start the API:
   ```bash
   uvicorn app.main:app --reload
   ```
5. Open docs at http://localhost:8000/docs
6. Open frontend pages from the `frontend/` folder (for example with VS Code Live Server).

## Production deployment

Use Docker Compose to launch database, backend, and frontend together:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

Default production behavior in `docker-compose.prod.yml`:

- `APP_PERSISTENCE=database`
- Backend runs on internal port `8000`
- Frontend runs on port `80`
- Frontend proxies `/api/*` to backend
- Uploads are persisted in the `uploads` volume

## Storage configuration

Set these values in your production environment:

- `STORAGE_BACKEND=local` for volume-backed files
- `STORAGE_BACKEND=s3` for S3-compatible object storage
- `S3_BUCKET`, `S3_REGION`, and optional `S3_ENDPOINT_URL` when using S3

## Notes

- The app supports both `memory` and `database` persistence modes.
- Existing tests run in memory mode and remain fast for MVP iteration.
