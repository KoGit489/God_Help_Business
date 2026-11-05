# Capture Processing Architecture

Draft 1 has a capture-session API boundary for timestamped camera and positioning observations. The SLAM implementation remains experimental.

## Current behavior

- A pin may include a `telemetry` object.
- Telemetry is preserved with the pin in database mode.
- `GET /capture-processing/status` reports the configured processor and capabilities.
- `POST /projects/{project_id}/pins/{pin_id}/process` runs the configured processor boundary.
- `POST /projects/{project_id}/capture-sessions` starts a recording session with a floor-plan key and GPS-to-plan calibration anchors.
- `POST .../observations` records sequenced GPS/orientation/motion samples; `POST .../captures` stores sequenced preview/native media events; `POST .../finalize` creates ordered project pins.
- The default processor is `manual` and uses calibrated dead reckoning.

## Future processor names

Set this environment variable before starting the API to opt into the experimental video path:

```powershell
$env:CAPTURE_PROCESSOR="insp_parser"
```

Processor status:

- `insp_parser` parses XML-like `.insp`/`.insv` telemetry payloads when supplied as telemetry; native X6 containers are not generally parsed as XML automatically.
- `vio` remains reserved and reports `not_configured`.
- `slam` runs frame extraction, SIFT visual translation, heuristic 2D trajectory chaining, descriptor-based loop-closure candidates, and heuristic XY drift correction for `.insv`/`.mp4` when enabled.

SLAM does not estimate metric scale, use camera calibration, fuse GPS/IMU, verify loop closures geometrically, optimize full SE(3) poses, or reliably register a route to a surveyed floor plan. Treat its positions/confidence as experimental until validated against ground truth. The session API is transport/persistence groundwork; it does not itself control the camera or choose capture cadence.

## What the future worker must provide

1. Read `.insp`/`.insv` (Insta360 X6) or an exported telemetry stream.
2. Normalize timestamps, GPS, gyro, accelerometer, and camera orientation.
3. Estimate a route and confidence score.
4. Convert the route into calibrated floor-plan coordinates.
5. Update pin positions and processing status.
6. Produce browser-readable equirectangular previews for the 360 viewer.

The manual walkthrough remains usable when no camera adapter or SLAM provider is configured.
