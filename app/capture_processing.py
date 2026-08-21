from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CaptureProcessingStatus:
    processor: str
    status: str
    capabilities: tuple[str, ...]
    message: str


class CaptureProcessor:
    """Extension point for future .insp, VIO, and SLAM worker integrations."""

    def __init__(self) -> None:
        self.provider = os.getenv("CAPTURE_PROCESSOR", "manual").strip().lower()

    def status(self) -> CaptureProcessingStatus:
        if self.provider in {"slam", "vio", "insp_parser"}:
            return CaptureProcessingStatus(
                processor=self.provider,
                status="not_configured",
                capabilities=("telemetry_ingest", "trajectory_estimation", "floor_plan_alignment"),
                message="The selected processor is reserved for a future worker integration.",
            )
        return CaptureProcessingStatus(
            processor="manual",
            status="ready",
            capabilities=("telemetry_metadata", "calibrated_dead_reckoning"),
            message="Manual calibrated positioning is active; automatic SLAM is not configured.",
        )

    def process(self, telemetry: dict[str, Any] | None = None) -> dict[str, Any]:
        status = self.status()
        return {
            "processor": status.processor,
            "status": status.status,
            "capabilities": list(status.capabilities),
            "message": status.message,
            "telemetry_received": bool(telemetry),
        }