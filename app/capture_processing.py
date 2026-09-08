from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CaptureProcessingStatus:
    processor: str
    status: str
    capabilities: tuple[str, ...]
    message: str


class CaptureProcessor:
    """Extension point for .insp parsing, VIO, and future SLAM worker integrations."""

    def __init__(self) -> None:
        self.provider = os.getenv("CAPTURE_PROCESSOR", "manual").strip().lower()

    def _float_value(self, value: str | None, default: float = 0.0) -> float:
        try:
            return float(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    def parse_insp_payload(self, payload: bytes | str | None) -> dict[str, Any]:
        if payload is None:
            return {
                "source": "insp_parser",
                "device": None,
                "file_type": None,
                "start_time": None,
                "route": [],
                "motion": {"samples": 0, "average_speed_mps": 0.0, "max_speed_mps": 0.0},
                "confidence": 0.0,
                "message": "No .insp payload was supplied.",
            }

        text = payload.decode("utf-8", errors="ignore") if isinstance(payload, (bytes, bytearray)) else str(payload)
        text = text.strip()
        if not text:
            return {
                "source": "insp_parser",
                "device": None,
                "file_type": None,
                "start_time": None,
                "route": [],
                "motion": {"samples": 0, "average_speed_mps": 0.0, "max_speed_mps": 0.0},
                "confidence": 0.0,
                "message": "The supplied payload was empty.",
            }

        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return {
                "source": "insp_parser",
                "device": None,
                "file_type": None,
                "start_time": None,
                "route": [],
                "motion": {"samples": 0, "average_speed_mps": 0.0, "max_speed_mps": 0.0},
                "confidence": 0.0,
                "message": "The payload was not valid XML and could not be parsed as .insp metadata.",
            }

        file_type = root.findtext("FileType") or root.findtext("./FileType") or "INSP"
        device = root.findtext("Device") or root.findtext("./Device") or "unknown"
        start_time = root.findtext("./Session/StartTime") or root.findtext("Session/StartTime")

        route: list[dict[str, Any]] = []
        speeds: list[float] = []
        for point in root.findall(".//Point"):
            point_time = point.attrib.get("time")
            position = {
                "time": point_time,
                "x": self._float_value(point.attrib.get("x")),
                "y": self._float_value(point.attrib.get("y")),
                "z": self._float_value(point.attrib.get("z")),
                "yaw": self._float_value(point.attrib.get("yaw")),
                "pitch": self._float_value(point.attrib.get("pitch")),
                "roll": self._float_value(point.attrib.get("roll")),
                "speed_mps": self._float_value(point.attrib.get("speed")),
            }
            route.append(position)
            speeds.append(position["speed_mps"])

        average_speed = sum(speeds) / len(speeds) if speeds else 0.0
        max_speed = max(speeds) if speeds else 0.0
        confidence = 0.5 + min(0.45, average_speed / 2.0) + min(0.1, max(0, len(route) - 1) * 0.02)

        return {
            "source": "insp_parser",
            "device": device,
            "file_type": file_type,
            "start_time": start_time,
            "route": route,
            "motion": {
                "samples": len(route),
                "average_speed_mps": round(average_speed, 4),
                "max_speed_mps": round(max_speed, 4),
                "start_time": start_time,
                "end_time": route[-1]["time"] if route else None,
            },
            "confidence": round(min(0.99, max(0.5, confidence)), 4),
            "message": "Native .insp telemetry was parsed successfully.",
        }

    def estimate_route_waypoints(self, parsed_telemetry: dict[str, Any]) -> dict[str, Any]:
        """Convert parsed route coordinates to normalized floor-plan waypoints (0-1 space)."""
        route = parsed_telemetry.get("route", [])
        if not route:
            return {
                "waypoints": [],
                "bounds": None,
                "route_confidence": 0.0,
                "message": "No route data was available for waypoint estimation.",
            }

        xs = [p.get("x", 0.0) for p in route]
        ys = [p.get("y", 0.0) for p in route]
        zs = [p.get("z", 0.0) for p in route]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)

        range_x = max_x - min_x if max_x > min_x else 1.0
        range_y = max_y - min_y if max_y > min_y else 1.0
        range_z = max_z - min_z if max_z > min_z else 1.0

        margin = 0.05
        norm_min_x = min_x - (range_x * margin)
        norm_max_x = max_x + (range_x * margin)
        norm_min_y = min_y - (range_y * margin)
        norm_max_y = max_y + (range_y * margin)

        norm_range_x = norm_max_x - norm_min_x if norm_max_x > norm_min_x else 1.0
        norm_range_y = norm_max_y - norm_min_y if norm_max_y > norm_min_y else 1.0

        waypoints: list[dict[str, Any]] = []
        point_separations: list[float] = []

        for i, point in enumerate(route):
            px = point.get("x", 0.0)
            py = point.get("y", 0.0)

            position_x = (px - norm_min_x) / norm_range_x if norm_range_x > 0 else 0.5
            position_y = (py - norm_min_y) / norm_range_y if norm_range_y > 0 else 0.5

            position_x = max(0.0, min(1.0, position_x))
            position_y = max(0.0, min(1.0, position_y))

            waypoint = {
                "index": i,
                "time": point.get("time"),
                "position_x": round(position_x, 4),
                "position_y": round(position_y, 4),
                "heading": point.get("yaw", 0.0),
                "pitch": point.get("pitch", 0.0),
                "roll": point.get("roll", 0.0),
                "speed_mps": point.get("speed_mps", 0.0),
                "confidence": 0.7,
            }
            waypoints.append(waypoint)

            if i > 0:
                prev_x = (route[i - 1].get("x", 0.0) - norm_min_x) / norm_range_x if norm_range_x > 0 else 0.5
                prev_y = (route[i - 1].get("y", 0.0) - norm_min_y) / norm_range_y if norm_range_y > 0 else 0.5
                dx = position_x - prev_x
                dy = position_y - prev_y
                separation = (dx**2 + dy**2) ** 0.5
                point_separations.append(separation)

        motion_confidence = min(0.25, sum(point_separations) / len(point_separations)) if point_separations else 0.0
        coverage_confidence = min(0.25, (range_x + range_y) / 10.0)
        stability_confidence = 0.2 if len(route) > 5 else 0.1

        route_confidence = parsed_telemetry.get("confidence", 0.5)
        route_confidence = round(route_confidence * 0.5 + 0.25, 4)

        for wp in waypoints:
            wp["confidence"] = round(route_confidence - (0.05 if wp["speed_mps"] < 0.1 else 0.0), 4)

        return {
            "waypoints": waypoints,
            "bounds": {
                "min_x": round(norm_min_x, 4),
                "max_x": round(norm_max_x, 4),
                "min_y": round(norm_min_y, 4),
                "max_y": round(norm_max_y, 4),
                "min_z": round(min_z, 4),
                "max_z": round(max_z, 4),
            },
            "route_confidence": route_confidence,
            "motion_samples": len(route),
            "message": f"Route estimated with {len(waypoints)} normalized waypoints.",
        }

    def status(self) -> CaptureProcessingStatus:
        if self.provider == "insp_parser":
            return CaptureProcessingStatus(
                processor="insp_parser",
                status="ready",
                capabilities=("telemetry_ingest", "trajectory_estimation", "floor_plan_alignment"),
                message="The native .insp parser is active and can normalize captured route telemetry.",
            )
        if self.provider in {"slam", "vio"}:
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

    def process(self, telemetry: dict[str, Any] | bytes | str | None = None) -> dict[str, Any]:
        status = self.status()
        parsed: dict[str, Any] | None = None

        if isinstance(telemetry, (bytes, bytearray, str)):
            parsed = self.parse_insp_payload(telemetry)
        elif isinstance(telemetry, dict):
            source = telemetry.get("source")
            if source == "insp_parser":
                payload = telemetry.get("payload") or telemetry.get("raw_payload") or telemetry.get("file_content")
                if payload is not None:
                    parsed = self.parse_insp_payload(payload)
                elif telemetry.get("route"):
                    parsed = {
                        "source": "insp_parser",
                        "device": telemetry.get("device"),
                        "file_type": telemetry.get("file_type", "INSP"),
                        "start_time": telemetry.get("start_time"),
                        "route": telemetry.get("route", []),
                        "motion": telemetry.get("motion", {"samples": 0, "average_speed_mps": 0.0, "max_speed_mps": 0.0}),
                        "confidence": telemetry.get("confidence", 0.5),
                        "message": telemetry.get("message", "Native .insp telemetry was parsed successfully."),
                    }
                else:
                    parsed = self.parse_insp_payload(None)
            elif source in {"slam", "vio"}:
                parsed = {"source": source, "route": [], "motion": {}, "confidence": 0.0, "message": "Reserved worker is not configured yet."}

        result = {
            "processor": status.processor,
            "status": status.status,
            "capabilities": list(status.capabilities),
            "message": status.message,
            "telemetry_received": bool(telemetry),
        }

        if parsed is not None:
            result.update({
                "parsed_telemetry": parsed,
                "telemetry_received": True,
                "status": "ready" if parsed.get("confidence", 0.0) >= 0.5 else "partial",
                "message": parsed.get("message", status.message),
            })

        return result