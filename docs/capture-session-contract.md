# Automatic Capture Session Contract

Draft 1 adds a backend capture-session boundary for a future camera/GPS adapter.
It accepts timestamped observations and image/native-file events, then finalizes
the image events as ordinary ordered project pins for the existing viewer.

## Recording Lifecycle

1. Upload the floor plan and keep its returned `media_key`.
2. Calibrate GPS against the drawing by selecting at least three non-collinear
   points whose latitude/longitude and normalized `position_x`/`position_y` are
   known. Three anchors define a local affine transform; the server stores the
   fitted coefficients and RMS residual on the session.
3. Create a session with the floor-plan key, anchors and optional device metadata:

```http
POST /projects/{project_id}/capture-sessions
Content-Type: application/json
```

```json
{
  "floor_plan_key": "floorplans/{project_id}/first-floor.png",
  "calibration_anchors": [
    {"latitude": 0.0, "longitude": 0.0, "position_x": 0.0, "position_y": 0.0},
    {"latitude": 0.0, "longitude": 0.001, "position_x": 1.0, "position_y": 0.0},
    {"latitude": 0.001, "longitude": 0.0, "position_x": 0.0, "position_y": 1.0}
  ],
  "device_metadata": {"camera_model": "adapter supplied"}
}
```

4. Batch sensor observations to `POST .../observations`. A single monotonic
   sequence covers every sensor sample and every image capture. Timestamps must
   include a timezone. Observations may include GPS accuracy, heading, pitch,
   roll, accelerometer and gyroscope values.
5. Upload each image/frame with its capture timestamp and latest available
   position/orientation to `POST .../captures` as multipart fields `file` and
   `metadata_json`. JPG, PNG, WebP, INSP, INSV and MP4 files are accepted.
6. Call `POST .../finalize`. Every capture event becomes a normal pin, ordered by
   the shared event sequence. Explicit capture coordinates take precedence;
   missing GPS/heading/plan coordinates fall back to the latest earlier sensor
   observation and the session transform. Repeated finalization is idempotent.
7. Fetch the project review/pins list and open the generated pins in the
   existing image/arrow viewer.

## Adapter Boundary

The camera adapter is responsible for obtaining permission, starting/stopping
the camera, subscribing to GPS and device orientation, choosing when to capture
frames, and sending the ordered events. It may send observations periodically
and upload one preview frame per desired waypoint. This API does not control a
physical Insta360 camera or decide a safe capture cadence. Those responsibilities
belong to the device-specific SDK/browser adapter and still require camera
hardware and vendor-package validation.

GPS is not assumed to be accurate indoors. `horizontal_accuracy_m` is retained
with observations, but the current affine fit does not weight anchors by
accuracy, reject noisy fixes, or fuse inertial measurements. The client should
only upload capture events when it has a usable fix or an independently
calibrated floor-plan position; finalization rejects captures without either.

## Current Limits

- The affine calibration is local and two-dimensional. It assumes surveyed
  anchors describe one floor plan and does not model multiple floors, GPS drift,
  map rotations between levels, or building/indoor multipath.
- The session stores observations/events as JSON and creates pins at finalize;
  it does not yet provide resumable streaming, upload retries, duplicate-event
  reconciliation, session cancellation, or partial-session review.
- Automatically generated pins are saved in capture order, but the UI does not
  yet expose a recording lifecycle or continuously place live route dots. A
  camera/GPS client must call these endpoints.
- The existing SLAM path remains an experimental 2D visual-motion prototype,
  not metric, sensor-fused indoor localization.