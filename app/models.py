from dataclasses import dataclass


@dataclass(slots=True)
class ProjectPin:
    id: str
    latitude: float
    longitude: float
    heading: float
    captured_on: str
    photo_key: str | None = None
