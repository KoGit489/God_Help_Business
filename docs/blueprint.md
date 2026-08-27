# God_Help_Business MVP Blueprint

This blueprint turns the product idea into a practical, buildable first version.

## 1. MVP vision

The first version of God_Help_Business should prove one core workflow:

1. A user creates a project.
2. They place pins on a map.
3. Each pin captures a location, a date, a heading/direction, and a photo.
4. The project can be reviewed later and shared securely with a limited audience.

That is the minimum valuable product.

## 2. What the MVP includes

### In scope

- User sign-in and project ownership
- Create and view projects
- Add map pins with location and heading
- Attach one photo per pin
- Save capture date and metadata
- View pins in a project timeline/review view
- Share a project through a restricted link

### Out of scope for v1

- Real-time multi-user editing
- Full 3D scene reconstruction
- Advanced measurement tools
- AI analysis
- Complex permissions beyond project-level access

### Planned after v1

- Floor-plan-guided 360 walkthroughs so office users can inspect a job site remotely
- Two-dimensional markups and notes tied to a floor-plan position or capture waypoint
- Three-dimensional spatial notes anchored to observed objects in a 360 scene
- Automated waypoint placement using capture telemetry, visual-inertial odometry, and SLAM

## 3. Recommended architecture

### Frontend

- Next.js + TypeScript
- Mapbox or MapLibre for map interaction
- React components for pin placement, direction control, and review screens

### Backend

- FastAPI (Python)
- SQLAlchemy for database access
- Pydantic for request and response validation

### Database

- PostgreSQL + PostGIS
- Stores projects, pins, photo metadata, users, and share links

### Storage

- Cloudflare R2 or AWS S3
- Stores uploaded photos, while the database stores the reference key

### Authentication and sharing

- Clerk or Supabase Auth
- Share links limited to a single project

## 4. Suggested repository structure

- frontend/ — Next.js app
- backend/ — FastAPI service
- db/ — schema, migrations, seed data
- docs/ — product and technical documentation
- app/ — current Python FastAPI starter package

The current Python starter in [app/main.py](app/main.py) should become the backend entry point for the MVP.

## 5. Core data model

### Users

- id
- email
- name
- created_at

### Projects

- id
- owner_id
- title
- description
- created_at

### ProjectMembers

- id
- project_id
- user_id
- role

### Pins

- id
- project_id
- latitude
- longitude
- heading
- captured_on
- created_by
- created_at
- photo_key

### Photos

- id
- pin_id
- storage_key
- original_name
- content_type
- uploaded_at

### Annotations (Phase 2 and later)

- id
- project_id
- pin_id
- author_id
- body
- status
- floor_plan_x
- floor_plan_y
- panorama_yaw
- panorama_pitch
- spatial_anchor
- created_at

### ShareLinks

- id
- project_id
- token
- created_by
- expires_at
- is_active

## 6. User experience blueprint

### Screen 1: Landing / sign-in

- Sign-in or create account
- See project dashboard after login

### Screen 2: Dashboard

- List all user projects
- Create new project
- Open existing project

### Screen 3: Project detail page

- Map view
- Existing pins plotted on the map
- Buttons to add a new pin
- Summary panel with project info

### Screen 4: Add pin experience

- Click on the map to place a pin
- Drag an arrow to set camera heading
- Select capture date
- Upload a photo
- Save pin

### Screen 5: Review page

- Show list of pins ordered by date
- Display photo, location, heading, and capture time

### Screen 6: Share settings

- Generate a share link for one project
- Restrict shared access to that project only

### Screen 7: Remote walkthrough (Phase 2)

- Show the floor plan with capture waypoints
- Let office users choose a waypoint and open its 360 view
- Show camera direction so the view matches the field capture
- Let reviewers move between connected captures without being on site

### Screen 8: Markups and annotations (Phase 2 and later)

- Add a note or markup to a floor-plan position or waypoint
- Assign an issue, status, or owner to a note
- In later releases, anchor a note to yaw/pitch or a recognized 3D object in the 360 view

## 7. Backend API blueprint

### Auth routes

- POST /auth/sign-up
- POST /auth/sign-in
- GET /auth/me

### Project routes

- POST /projects
- GET /projects
- GET /projects/{project_id}
- PATCH /projects/{project_id}

### Pin routes

- POST /projects/{project_id}/pins
- GET /projects/{project_id}/pins
- GET /projects/{project_id}/pins/{pin_id}

### Photo routes

- POST /projects/{project_id}/pins/{pin_id}/upload
- GET /photos/{photo_id}

### Share routes

- POST /projects/{project_id}/share-links
- GET /share/{token}

## 8. Build plan by phase

### Phase 1 — Foundation

- Set up Next.js frontend
- Set up FastAPI backend
- Connect Postgres + PostGIS
- Add auth starter
- Create project and pin models

### Phase 2 — Core capture workflow

- Build map UI
- Add pin placement
- Add heading control
- Add photo upload
- Save pins to the database

### Phase 3 — Review and sharing

- Build project detail and review page
- Add share-link support
- Limit access to one project
- Test permission rules

### Phase 4 — Hardening and launch

- Add error handling
- Add loading and empty states
- Deploy frontend and backend
- Connect storage and database in production

### Phase 5 — Remote walkthrough and collaboration

- Add a floor-plan-guided 360 walkthrough for office reviewers
- Link each capture to a floor-plan waypoint and viewing direction
- Add two-dimensional plan markups, notes, assignments, and issue status
- Add project members and role-based collaboration
- Add audit history for review decisions and annotations

### Phase 6 — Spatial intelligence

- Read telemetry from supported camera files such as Insta360 `.insp`
- Generate equirectangular preview images for browser viewing
- Fuse timestamps, GPS, gyroscope, accelerometer, and camera orientation data
- Use visual-inertial odometry and SLAM to estimate capture positions and route confidence
- Align the estimated route to a calibrated floor plan
- Add three-dimensional spatial annotation anchors within 360 scenes
- Validate accuracy on measured routes at real job sites

### Phase 4 implementation notes

- Backend now returns consistent error envelopes with request IDs for traceability.
- Frontend pages now include explicit loading, empty, and error states.
- Production deployment files are provided for backend, frontend, and database containers.
- Backend supports `APP_PERSISTENCE=database` with SQLAlchemy models and PostgreSQL.
- Upload storage supports `STORAGE_BACKEND=local` (volume) and `STORAGE_BACKEND=s3`.

## 9. Implementation order

1. Set up the repo and environments
2. Create the database schema
3. Create authentication and project ownership flow
4. Build the backend API for projects and pins
5. Build the map UI and add pin placement
6. Add photo upload and object storage integration
7. Build the review page
8. Add share-link restrictions
9. Deploy and test

## 10. Definition of done for the MVP

The MVP is successful when a user can:

- sign in,
- create a project,
- add a pin to the map,
- set its direction,
- attach a photo,
- review the captured pin data,
- and share that project through a limited link.

The following phases are successful when an office reviewer can open a floor plan, travel through linked 360 captures as if they were on the job site, and leave notes that remain tied to the relevant plan position or spatial view.

## 11. Recommended first-week priorities

- Set up the frontend and backend folders
- Add database connection and schema
- Create the project and pin API
- Build the map screen with a single test pin
- Connect image upload to storage

That first week should deliver a visible, working prototype even if it is simple.
