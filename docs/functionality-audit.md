# Functionality Preservation Audit

Date: 2026-11-01. Target: God_Help_Draft_2.
Arrow behavior corrected and browser-checked: 2026-11-03.

This is a bounded workflow audit, not certification of every function, input,
device, concurrency scenario, or production service. Checks used temporary
projects/uploads, a local FastAPI server, and an isolated SQLite database.
Production data and credentials were not accessed.

## Repairs

- Use one shared floor-arrow shape and Pannellum hotspot renderer for yellow
  forward and white backward arrows. The earlier fixed white triangle was an
  incorrect substitute and has been removed from panorama navigation.
- Derive direction from capture order, never viewing history. The first capture
  has no backward arrow; the last has no forward arrow. Previous/next commands
  stop at route endpoints instead of wrapping.
- Prevent arrow presses from starting camera drags. Both arrows stay anchored
  to scene bearings, so an arrow behind the camera appears when looking back,
  not as an always-visible screen overlay.
- Clear the previous drawing, route controls, editing selection, and navigation
  history when changing projects.
- Refresh the real project after creating a share link, preserving completed
  capture checklist items.

Existing previous/next buttons, waypoint walking, native-file preservation,
automatic previews, editing, calibration, notes, and sharing remain present.
Comparison with Draft 1 at 2677eac found no removed frontend controller functions
or API route declarations in the deployment-era changes. That comparison does
not prove every implementation has identical behavior.

## Verification

| Workflow | Evidence |
| --- | --- |
| Dashboard project creation and sample capture | Real browser with local API |
| Floor-plan image upload and route start | Real browser with local API |
| Manual and interval walking, heading control | Real browser; frontend regression tests |
| Yellow forward and white backward floor hotspots, previous/next, close | Actual Pannellum browser clicks; frontend tests |
| Desktop/mobile panorama rendering | Screenshots at 1280x900 and 390x844; nonblank canvas |
| Regular-image fallback arrows | Shared floor-arrow shape and direction-filtering regression tests; prior browser fallback check |
| Waypoint photo replacement, calibration, notes, deletion | Real browser with local API |
| Project switching and share checklist state | Browser reproduction and regression tests |
| Map capture with photo and original .insp | Real browser and local API |
| Automatic preview and failure feedback | Frontend regression tests; backend processing tests |
| Review status, shared project, invalid token | Real browser and backend tests |
| Copy-link event wiring | Browser with stubbed clipboard; OS clipboard not read |
| Database-backed capture, media, calibration, notes, review/sharing | Isolated SQLite regression test |
| Ownership and share-token isolation | Backend regression tests |
| PDF rasterization, telemetry, calibration estimation, VIO | Existing backend tests; not field accuracy certification |
| Spaces upload, same-origin streaming, native download for processing | Mocked S3 backend tests; not live Spaces connectivity |

The 2026-11-03 arrow check used three temporary captures. Desktop mouse clicks
completed 2 -> 1 -> 2 -> 3 -> 2 -> 1; mobile-viewport mouse clicks completed
2 -> 1 -> 2 -> 1. Computed colors were yellow rgb(242, 182, 50) and white
rgb(255, 255, 255), with matching shapes/projection. Panning moved both hotspots
with the scene. Screenshots confirmed the shapes and absence of fixed triangles.
These are local browser checks, not certification of every physical touch device
or confirmation that the live Droplet has deployed this revision.

Run the preserved-behavior gates from the repository root:

```powershell
py -3 -m pytest -q
node --test tests/test_floorplan_navigation.cjs tests/test_review_workflow.cjs
node --check frontend/app.js
node --check frontend/map.js
node --check frontend/review.js
node --check frontend/floorplan.js
git diff --check
```

## Remaining Limits

- Live Droplet/Caddy, managed PostgreSQL, Spaces credentials/connectivity, and
  Docker image execution were not certified here. SQLite is not PostgreSQL.
- Phone GPS/compass accuracy and device-specific permission flows were not
  exercised. Heading events and unavailable-GPS feedback were simulated.
- GPS availability does not georeference a floor plan. Walking remains a
  manually calibrated dead-reckoning prototype.
- Native preview tests use JPEG-encoded .insp files or the existing placeholder
  fallback. Placeholder generation is not proof that real X6 imagery decoded.
- Uploaded drawing bytes are stored, but reopening a project does not currently
  restore its drawing automatically from project metadata. This is an existing
  limitation, not a newly implemented persistence feature.
- Review error/copy feedback remains limited by the existing setReviewStatus
  guard when a project is active; successful review/share workflows were tested.
- Unusual concurrent actions and complete branch/error-path coverage remain
  unverified. No claim of 100% function coverage is made.