# God_Help_Business

A Python-first starter repo for a construction field capture MVP.

## Stack
- FastAPI for the backend API
- PostgreSQL + PostGIS for geospatial data
- Cloud storage integration planned for photos
- Map UI planned for pin placement and direction capture

## Quick start
1. Create and activate a Python virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the API:
   ```bash
   uvicorn app.main:app --reload
   ```
4. Open the docs at http://localhost:8000/docs
