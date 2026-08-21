# Capture Processing Architecture

Draft 1 now has a stable place for automatic capture processing without claiming that SLAM is already running.

## Current behavior

- A pin may include a `telemetry` object.
- Telemetry is preserved with the pin in database mode.
- `GET /capture-processing/status` reports the configured processor and capabilities.
- `POST /projects/{project_id}/pins/{pin_id}/process` runs the configured processor boundary.
- The default processor is `manual` and uses calibrated dead reckoning.

## Future processor names

Set this environment variable before starting the API:

```powershell
$env:CAPTURE_PROCESSOR="insp_parser"
```

Supported reserved names are:

- `insp_parser` for reading native Insta360 metadata
- `vio` for visual-inertial odometry using camera motion sensors
- `slam` for trajectory and map estimation

These names currently report `not_configured`. A worker can later implement the `CaptureProcessor` contract in `app/capture_processing.py` without changing the pin API or the floor-plan viewer.

## What the future worker must provide

1. Read `.insp` or an exported telemetry stream.
2. Normalize timestamps, GPS, gyro, accelerometer, and camera orientation.
3. Estimate a route and confidence score.
4. Convert the route into calibrated floor-plan coordinates.
5. Update pin positions and processing status.
6. Produce browser-readable equirectangular previews for the 360 viewer.

The current demo remains usable while that processor is being built.
