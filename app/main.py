from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="God_Help_Business API",
    version="0.1.0",
    description="Backend scaffold for a construction field capture MVP.",
)


class HealthResponse(BaseModel):
    status: str
    service: str


@app.get("/", tags=["core"])
def read_root() -> dict[str, str]:
    return {"message": "God_Help_Business API is ready", "docs": "/docs"}


@app.get("/health", response_model=HealthResponse, tags=["core"])
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="god-help-business")
