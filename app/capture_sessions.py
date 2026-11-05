from __future__ import annotations

import math
from typing import Any

import numpy as np


EARTH_RADIUS_METERS = 6_378_137.0


def fit_floor_plan_transform(anchors: list[dict[str, Any]]) -> dict[str, Any]:
    if len(anchors) < 3:
        raise ValueError("At least three GPS-to-floor-plan calibration anchors are required.")

    latitudes = np.asarray([float(anchor["latitude"]) for anchor in anchors], dtype=float)
    longitudes = np.asarray([float(anchor["longitude"]) for anchor in anchors], dtype=float)
    plan_x = np.asarray([float(anchor["position_x"]) for anchor in anchors], dtype=float)
    plan_y = np.asarray([float(anchor["position_y"]) for anchor in anchors], dtype=float)
    values = np.column_stack((latitudes, longitudes, plan_x, plan_y))
    if not np.isfinite(values).all():
        raise ValueError("Calibration coordinates must be finite numbers.")
    if np.any(np.abs(latitudes) > 90) or np.any(np.abs(longitudes) > 180):
        raise ValueError("Calibration latitude or longitude is out of range.")
    if np.any((plan_x < 0) | (plan_x > 1) | (plan_y < 0) | (plan_y > 1)):
        raise ValueError("Calibration floor-plan coordinates must be between 0 and 1.")

    origin_latitude = float(latitudes.mean())
    origin_longitude = float(longitudes.mean())
    longitude_scale = math.cos(math.radians(origin_latitude))
    east_meters = EARTH_RADIUS_METERS * longitude_scale * np.radians(longitudes - origin_longitude)
    north_meters = EARTH_RADIUS_METERS * np.radians(latitudes - origin_latitude)
    design = np.column_stack((east_meters, north_meters, np.ones(len(anchors))))
    if np.linalg.matrix_rank(design) < 3:
        raise ValueError("Calibration anchors must span a two-dimensional area on the floor plan.")

    x_coefficients, _, _, _ = np.linalg.lstsq(design, plan_x, rcond=None)
    y_coefficients, _, _, _ = np.linalg.lstsq(design, plan_y, rcond=None)
    predicted_x = design @ x_coefficients
    predicted_y = design @ y_coefficients
    residuals = np.sqrt((predicted_x - plan_x) ** 2 + (predicted_y - plan_y) ** 2)

    return {
        "type": "local_affine_gps_to_floor_plan",
        "origin_latitude": origin_latitude,
        "origin_longitude": origin_longitude,
        "longitude_scale": longitude_scale,
        "x_coefficients": x_coefficients.tolist(),
        "y_coefficients": y_coefficients.tolist(),
        "anchor_count": len(anchors),
        "anchor_rms_error_normalized": float(np.sqrt(np.mean(residuals**2))),
        "anchors": anchors,
    }


def project_gps_to_floor_plan(
    transform: dict[str, Any], latitude: float, longitude: float
) -> tuple[float, float]:
    east_meters = (
        EARTH_RADIUS_METERS
        * float(transform["longitude_scale"])
        * math.radians(float(longitude) - float(transform["origin_longitude"]))
    )
    north_meters = EARTH_RADIUS_METERS * math.radians(float(latitude) - float(transform["origin_latitude"]))
    vector = np.asarray([east_meters, north_meters, 1.0], dtype=float)
    position_x = float(vector @ np.asarray(transform["x_coefficients"], dtype=float))
    position_y = float(vector @ np.asarray(transform["y_coefficients"], dtype=float))
    if not math.isfinite(position_x) or not math.isfinite(position_y):
        raise ValueError("GPS position could not be projected onto this floor plan.")
    return position_x, position_y