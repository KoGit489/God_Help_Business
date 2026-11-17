# CASAI Draft 2: Complete 360 Capture Operator Manual

Document date: November 16, 2026

Source reviewed: Draft 2, commit `da7504a`

Audience: A first-time operator using the browser application with a 360 camera

Scope: Preparing a capture, recording it, building a floor-plan walkthrough, reviewing it, and returning later

This manual describes the current Draft 2 workflow. Your administrator must confirm that the server has this version or a newer compatible version. Some older page headings still say "Draft 1"; that heading alone does not identify the deployed software version.

## 1. Start Here: What You Are Actually Doing

You will create a series of photographs taken at specific places in a building. You will attach each photograph to the matching place on a floor plan. The app joins the saved places in a sequence so you can move through the photographs using arrows.

Think of the floor plan as a paper map, each waypoint as a numbered pushpin, and each 360 photograph as the view from that pushpin.

**The short answer to "What do I do first?" is:**

1. Prepare the camera, the correct floor plan, and a safe route.
2. Sign in and create a project.
3. Open that project in **Open floor plan walkthrough**.
4. Upload the floor plan and check its dimensions.
5. At the first location, take a stationary 360 photograph using the camera.
6. Put your current position on the drawing, select the matching photograph, and click **Save waypoint here**.
7. Check that the saved photograph opens correctly.
8. Move to the next physical location and repeat.
9. Review the entire sequence in both directions.

**Do I need to decide the path first?** Decide a sensible, safe order before starting. You do not need to draw a complete route or save empty waypoints in the app first. For your first test, save one completed photo waypoint at a time, in the order someone should visit it.

**Important:** This is a sequence of stationary capture locations, not a live video tour, automatic indoor positioning system, or complete 3D scan. The app does not automatically know where you walked.

## 2. Words and Basic Computer Actions

| Term or action | Meaning |
| --- | --- |
| Browser | The program used to open websites, such as Edge, Chrome, or Safari. |
| Address bar | The long box at the top of the browser that contains the website address. It is not the search box inside a webpage. |
| Click | Move the mouse pointer onto an item and press the left mouse button once. Do not double-click unless instructed. |
| Tap | Touch an item once on a phone or tablet. It is the touch-screen equivalent of a click. |
| Scroll | Move down or up a page using the mouse wheel, trackpad, or a finger swipe. Some lists scroll separately from the page. |
| Dropdown | A box with choices. Click it, then click the choice you want. |
| Field | A box in which you type text or a number. Click inside it before typing. |
| Slider | A horizontal line with a small movable handle. Drag the handle to change its value. |
| File | A saved item on your device, such as a drawing PDF or a photograph JPG. |
| Upload | Copy a file from your device to the application's server using the website. |
| Project | The application's container for one inspection route, its plan, photos, and notes. |
| Waypoint or pin | One saved location on the plan. It should have the correct photograph attached. |
| Preview | The image the browser displays when you open a waypoint. |
| Original or native file | The camera's original capture, such as an Insta360 `.insp` or `.insv` file. |
| Stitched panoramic JPG | A full 360 image assembled from the camera's lenses, often in a 2:1 rectangular image. It is not a screenshot or a normal narrow-view photograph. |
| Heading | A direction, expressed in degrees. In the plan controls, 0 points up, 90 right, 180 down, and 270 left. |
| Status message | A sentence near the controls explaining what the app is doing or reporting an error. Read it before clicking again. |

Throughout this manual, "click" also means "tap" when using a touch screen.

## 3. What You Need Before Visiting the Site

Gather the following:

- Permission to enter the site and photograph the areas involved.
- Required site PPE and a safe place to stop while operating the camera or computer.
- A charged 360 camera, a supported memory card with sufficient space, and the camera manufacturer's capture controls.
- A stable support appropriate to the site, such as a monopod or tripod, when permitted.
- A phone, tablet, or laptop with a supported browser and access to your exported photo files.
- A reliable internet connection for signing in, uploading, saving, and reopening captures.
- Your individual CASAI email address and password, provided by the administrator.
- The correct floor plan for the correct floor, revision, and work area.
- A known real-world dimension for calibrating the plan width.
- A notebook or capture log for matching file names to actual locations.
- A separate backup location for the original camera files and exported images.

Do not operate the app while physically walking through hazards. Stop in a safe location first. Do not place a tripod in an exit route or capture confidential information or people without the required permission.

The current app is not an offline-first system. Do not assume it will queue and synchronize unsaved work when the connection returns.

## 4. Prepare the Camera and Image Files

### Recommended first-test method

Use the camera manufacturer's software to produce **stitched, full 360 panoramic JPG images**. Upload those to CASAI's **Preview image (JPG, PNG, or WebP)** field.

Keep the original camera files as separate backups. For the very first three-point test, using a known-good panoramic JPG without a native upload makes problems easier to diagnose.

### Choose where you will assemble the walkthrough

There are two valid arrangements:

- **Capture and save on site:** At each safe stopping point, take the photo, transfer/export it, and save that waypoint in CASAI. This lets you inspect the result immediately but requires a practical file-transfer method and internet access.
- **Capture on site, assemble at a desk:** Take and log the photos in order at the site, marking each location on a paper or otherwise available copy of the exact plan. Later, transfer/export the photos and follow the same project/plan/save steps in CASAI at a computer. Select the corresponding recorded location and file for each waypoint in order. The app does not discover those locations automatically, and the camera log is essential.

For a first test, a laptop and a three-photo route may be easier than doing transfers on a phone. If using the desk method, test the export and CASAI viewer before leaving the site so an unusable capture can still be retaken. Recording photos on the camera without internet is not the same as offline saving in CASAI.

### Camera preparation

1. Charge the camera and confirm that the memory card is recognized.
2. Clean both lenses using the manufacturer's recommended method.
3. Choose the camera's full 360 photo mode, not a single-lens or ordinary flat-photo mode.
4. Use the manufacturer's recommended settings for stationary indoor capture. Menu names vary by camera and firmware; use its manual rather than guessing from this document.
5. Keep the camera upright and level. Use a consistent practical height throughout the route.
6. Keep fingers, equipment, and clothing away from the lenses.
7. Take a practice photograph in a safe location.
8. Open that photograph in the manufacturer's viewer and confirm that you can look all around it.

### Export preparation

1. Transfer the practice capture to the manufacturer's phone app or desktop software.
2. Choose its stitched full-panorama export, preferably a JPG. A full equirectangular image commonly has a width about twice its height.
3. Do not export only the currently visible view, a screenshot, a cropped thumbnail, or a normal flat photograph.
4. Keep exported panoramas consistently oriented. Avoid manually rotating or recentering each export differently.
5. Confirm where the exported file was saved. You must be able to find it in the device's file picker.
6. Keep a second copy of the exported file and the original camera capture.

The current default upload limits are 25 MiB per preview image, 100 MiB per floor plan, and 2 GiB per native capture. The administrator may configure different limits. Export a smaller full-panorama image if needed; do not crop out part of the 360 view just to reduce its size.

### A simple file organization example

Create a folder such as `SiteA_Level1_2026-11-16`. Inside it, keep a `Plan` folder, an `Originals` folder, and a `Panoramas` folder. This organization is a recommendation, not an app requirement.

On Windows, press **Windows key + E** to open File Explorer. Navigate to a location such as Documents. Right-click an empty area, choose **New**, then **Folder**, and type the folder name. If someone assists with export, ask them to show you exactly where the panorama files are located.

Record an explicit match between files and places. For example:

| Capture order | Physical location | Original camera file | Exported panoramic JPG |
| --- | --- | --- | --- |
| 1 | Entrance, inside the door | Original file name A | `001_entrance.jpg` |
| 2 | Middle of corridor | Original file name B | `002_corridor.jpg` |
| 3 | Before the corridor turn | Original file name C | `003_turn.jpg` |

You may name exported copies descriptively. Preserve manufacturer file groupings and original names where the manufacturer's workflow requires them. CASAI does not infer a waypoint's correct location from a file name.

## 5. Prepare the Floor Plan

1. Confirm the building, floor, drawing revision, and inspection area with the site contact.
2. Prefer a single, clear JPG or PNG showing one floor or one continuous route area.
3. PDF is supported, but the server rasterizes the first page when conversion succeeds. Do not upload a multipage drawing package and expect a floor selector.
4. Crop the drawing before starting if necessary. Remove irrelevant surrounding pages or large margins when practical, but keep useful landmarks.
5. Preserve the image proportions. Do not stretch it horizontally or vertically.
6. Orient the plan consistently. If you need the displayed compass to correspond to actual north, have the plan and capture orientation checked rather than assuming that the top of every drawing is north.
7. Determine the real-world width represented by the complete uploaded image from its left edge to its right edge.

**The width is not automatically the width of one room.** If the uploaded image includes space outside the building or a title block, its complete image width covers more than the building's dimension. Have someone calibrate that image correctly or prepare a clean crop first.

Do not replace an already mapped plan with a rotated, differently cropped, or differently proportioned drawing. Existing normalized pin positions are not automatically reprojected onto changed drawing geometry. For a substantially different plan, start a separate project.

## 6. Plan a Safe Capture Route

1. Walk through or inspect the intended area with the site contact, without operating the app while moving.
2. Pick an obvious starting point, such as the inside of a recognizable entrance.
3. Choose the order of locations a remote viewer should follow.
4. Add capture locations at entrances, room transitions, turns, and important work areas.
5. Choose positions with a clear relationship to neighboring positions. Include intermediate captures where otherwise an arrow would appear to pass through a wall or obstruction.
6. Use enough photographs that each move is understandable. There is no single required spacing that works for every room and corridor.
7. Plan safe return movement if the route enters a room and comes back out. The current walkthrough is a sequence, not a branching graph that automatically connects every nearby pin.
8. Record the locations in order in the capture log.

For a first test, use just three points: **entrance -> corridor -> turn or adjoining room**. Include a turn so you can check direction changes before photographing an entire floor.

Use a separate project for another floor or a substantially different inspection date/route. The current project has one active floor-plan reference, not a stack of independently selectable floor plans.

Do not pre-save empty pins as route placeholders for this first workflow. Empty pins can still become part of the navigation sequence and make the walkthrough confusing.

## 7. Sign In

1. Open Edge, Chrome, Safari, or another supported browser.
2. Click the browser's address bar at the top.
3. Type `https://casaifield.com/login.html` and press **Enter** or the device's **Go** button.
4. Check that the address is spelled correctly. Do not continue through a certificate or unsafe-site warning.
5. Find the **Email** field, click inside it, and type the email associated with your CASAI account.
6. Find the **Password** field, click inside it, and type your password. Hidden password characters are normal.
7. Click **Sign in** once.
8. Wait for the Dashboard. If an account page appears instead, click **Dashboard** near the top.

Use the individual account supplied by the administrator. The earlier shared site login is not necessarily a CASAI account. An administrator may have initially created the first account using bootstrap credentials; ordinary operators do not need to open a terminal or edit server settings.

If the credentials are rejected, check spelling and the keyboard's Caps Lock setting, then contact the administrator. Do not paste passwords into support messages.

## 8. Create the Project

Skip project creation if the administrator has already made the correct project in your account.

1. On the Dashboard, scroll down until you see **Create project**.
2. Click **Project title** and type a clear title, for example `Site A - Level 1 - 2026-11-16 Test`.
3. Click **Short description** and record the area, drawing revision, date, and purpose of the capture.
4. Click **Create project** once.
5. Wait for the project to appear in the **Projects** list.
6. Do not click **Add demo pin to first project**. That is a demonstration control, not a real site-capture step.
7. Near the top of the Dashboard, click **Open floor plan walkthrough**. You may need to scroll back up to find it.

You can also open `https://casaifield.com/floorplan.html` after signing in. The separate **Open capture view** page is not required for this floor-plan walkthrough procedure.

## 9. Select the Project and Upload the Plan

1. Find **Project** near the top of the floor-plan page.
2. Click its dropdown and select the exact project title you intend to use. Do not assume that the first project displayed is the correct one.
3. Read the status message below the plan controls. It should name the project that loaded.
4. If the correct floor plan is already visible, do not upload it again. Continue to the calibration section.
5. If no plan is visible, find **Upload floor plan (PDF, JPG, or PNG)**.
6. Click **Choose File** or the equivalent file-selection button. The browser may call it **Browse** or use a similar label.
7. In the window that opens, navigate to the folder containing the plan. On a phone, choose the saved file from the appropriate Files or document location.
8. Click the correct plan file, then click **Open** or confirm the selection.
9. Wait. Selecting the plan starts its upload automatically; there is not a separate plan-upload confirmation button.
10. Look for a status such as **Plan loaded: ...** and confirm that the drawing actually appears.
11. Check its landmarks: doors, corridors, stairs, and room outlines should match the physical site.

The browser's file picker may show **No file chosen** after returning to the site even when the plan is saved on the server. Judge the saved state by the visible drawing, not by whether the browser retained a local file selection.

The updated app stores plan references and can recover older plan files from the project's storage folder. Recovery still requires that the file exists and storage access works. If it does not appear, do not start guessing pin locations on a blank area; use the troubleshooting section.

When recovering a project that has multiple older plan files but no saved reference, the app selects the most recently modified supported file in that project's plan folder. Verify the drawing and revision that appears; automatic recovery does not prove it is the intended revision.

## 10. Set the Drawing Dimensions and Manual Controls

1. Find **Plan width (feet)**. Click inside it, select the existing number, and type the correct whole-image width in feet.
2. Do not accept the default `120` unless the complete image really represents 120 feet horizontally.
3. Find **Drawing scale**. Select the scale printed on the drawing if it is known and applicable.
4. Understand that selecting **Drawing scale** does not automatically determine or correct **Plan width (feet)**. The width field drives the current waypoint distance calculation; the scale choice is not an automatic calibration tool.
5. Find **Position updates** and choose **On each walk step**.
6. Leave **Use current GPS location** and **Enable device heading** alone for the first test.
7. Find **Walk distance (feet)** and leave it at `1` until you reach the optional measured-step instructions.

**Recheck these controls every time you reopen the page or change projects.** The current app saves the floor-plan reference and waypoints, but it does not persist all of these browser control settings as project calibration. A remembered or default width may belong to another drawing.

The app displays positions as **X ... ft, Y ... ft**. X increases from the image's left edge toward the right. Y increases from the bottom edge toward the top. These are drawing-based coordinates, not latitude/longitude or survey coordinates. Their accuracy depends on your plan dimensions and pin placement.

If the image represents a 100-foot-wide by 50-foot-high area, a point one-quarter of the way from the left and halfway up is approximately **X 25 ft, Y 25 ft**.

## 11. Understand the Two Ways to Set Your Position

### Method A: Click the actual location on the plan -- recommended

At each capture location, click the matching point on the visible drawing. This is the simplest first-time method and avoids accumulating estimated movement errors.

Clicking the drawing sets your current, unsaved position. It does **not** create a saved waypoint or attach a photograph. You still need **Save waypoint here**.

### Method B: Use the measured-step controls -- optional

After selecting a starting point, choose a heading and a distance, then click **Walk one step**. The app moves its current marker by that distance in that direction.

This is a manual drawing calculation. It is not a pedometer, does not detect your actual movement, and does not trigger a camera exposure. One button press means the number in **Walk distance (feet)**, not necessarily one human footstep.

The **Route ... ft** display accumulates these button-driven moves in the current session. It is not a reconstruction of every physical movement or of the complete saved route. Clicking new map positions does not add their physical travel distance to that readout.

## 12. Set and Check Your Heading

For the first test, use the manual **Heading** slider.

| Plan direction of travel | Heading setting |
| --- | --- |
| Toward the top of the drawing | 0 degrees; 360 degrees is equivalent |
| Toward the right | 90 degrees |
| Toward the bottom | 180 degrees |
| Toward the left | 270 degrees |

1. Find the small handle on the **Heading** slider.
2. Press and hold the left mouse button on the handle, move it left or right, then release. On a touch screen, drag the handle with a finger.
3. Read the highlighted heading value rather than estimating from handle position alone.
4. On a desktop keyboard, a focused range slider can also be adjusted with the arrow keys for finer changes.
5. Recheck the heading before saving each capture, particularly after a turn.

Map-up is not automatically verified geographic north. The in-photo compass uses the app's reference heading and the panorama view, not an independent survey instrument. Phone heading sensors can also be affected by device support, metal, and the environment.

For the three-photo test, align the first capture's intended forward view with the starting route heading. Keep the camera upright and, where practical, keep the same marked camera-front orientation throughout the test, even when your walking direction changes. Export each panorama consistently. The current app does not independently recover and correct every image's true north orientation.

If recognizable doors or corridors do not line up with the arrows in the first few images, stop and check the capture/export orientation with the administrator. Do not keep changing unrelated headings to conceal the problem.

## 13. Capture and Save the First Waypoint

Perform the camera work while stationary and safe. You may use a two-person team: one person operates the camera and the other handles the app and file matching.

1. Go to the physical starting location selected in your route plan.
2. Record that location and its sequence number in your capture log.
3. Position the camera upright at the agreed height.
4. Make sure both lenses have a clear view and that the camera is not immediately against a wall or behind an obstruction.
5. Take a stationary full 360 photograph using the camera or its manufacturer's remote control.
6. Confirm the camera has finished writing the capture.
7. Transfer and export the capture as a stitched panoramic JPG using the prepared manufacturer workflow.
8. Confirm the exported file is the photograph from this location, not the previous location.
9. In CASAI, verify the project title and the displayed floor plan.
10. Click once on the plan at the precise location where the camera stood. A current-position marker should appear, and the save controls should become available.
11. Set or verify the manual **Heading** value for this capture's route direction.
12. Under **2. Save a capture**, find **Preview image (JPG, PNG, or WebP)**.
13. Click its file-selection button, choose the matching panoramic JPG, and confirm the selection.
14. Check that the selected file name matches your log.
15. For the first test, leave **Original Insta360 X6 file** empty and retain the original in your backup folder. The optional native workflow is described later.
16. Click **Save waypoint here** once.
17. Wait for **Waypoint saved. Click its dot to open the capture.** Do not double-click Save or repeatedly press it while the upload is running.
18. Confirm that **Saved waypoints** contains a numbered entry and that the corresponding dot is visible on the plan.
19. Record the saved number beside the file name in your capture log.

Selecting a preview file is not the same as saving it. The photo upload happens as part of **Save waypoint here**. Do not close the tab, change projects, or sign out during the save.

If the save reports an error, do not immediately save a second time. The server may already have created a pin before a later upload failed. Check the troubleshooting instructions for partial saves.

## 14. Check That First Photograph Immediately

1. In **Saved waypoints**, locate the number you just saved.
2. Click **View** next to it, or click the corresponding dot on the drawing.
3. A photograph viewer should open above the page.
4. Click and hold on the photograph, move the mouse left or right, then release to look around. On a touch screen, drag your finger across the photograph.
5. Look around the entire scene and check that it is the real location you recorded.
6. Check for clear details, reasonable stitching, usable exposure, and a level view.
7. Check the floor and ceiling where captured. A distorted normal photograph is not a valid panoramic export.
8. Click **Close** at the top of the viewer to return to the floor plan.

With only one waypoint, there is no previous or next waypoint. Navigation arrows may be absent and previous/next controls may be hidden or unavailable. This is normal. After saving a second point, reopen the first to test the forward arrow.

Do not proceed to a full floor until you have proved that your camera export produces a recognizable, usable panorama in the app.

## 15. Move to the Next Physical Location and Repeat

### Recommended: set each point directly on the drawing

1. Close the photo viewer if it is open.
2. Put the device away or have the second operator manage it while you move safely to the next planned location.
3. Stop and take the next stationary 360 photograph.
4. Transfer/export it and check the file name against the new location in your log.
5. In CASAI, click the actual new camera location on the floor plan.
6. Change the **Heading** slider if the intended route direction has changed.
7. Choose this location's panoramic JPG in **Preview image (JPG, PNG, or WebP)**.
8. Click **Save waypoint here** once and wait for confirmation.
9. Check that the count increased by one and the new point is in the correct place.
10. Click **View** on the new point and verify that the photograph is the right one.
11. Close the viewer, then repeat for each remaining location.

After a successful save, the file-selection fields are cleared. Select the next photograph before saving the next point. Otherwise you can create a waypoint without the intended media.

### Optional: move the marker using measured steps

Suppose the next camera position is 8 feet to the right of the current point on a correctly calibrated plan:

1. Set **Heading** to 90 degrees.
2. Set **Walk distance (feet)** to `8`.
3. Click **Walk one step** once.
4. Check that the current marker moved right to the expected place.
5. If it is not at the actual camera location, click the correct point on the drawing instead of pretending the estimate is exact.
6. Physically capture the photograph at the new location using the same stationary procedure.
7. Select that image and click **Save waypoint here**.

If the next move is 6 feet toward the top of the plan, set the heading to 0 and the walk distance to `6` before the next button press. Remember that the distance field retains its previous value until you change it.

Neither moving a marker nor physically walking takes a photograph. The camera capture and the CASAI save are separate actions.

## 16. Why Capture Order Matters

The walkthrough uses the waypoint sequence shown in the app. It does not automatically arrange photos by their file names, physical closeness, or the room a reviewer probably wants next.

- Save the entrance before the corridor, the corridor before the turn, and so on.
- Check the displayed order after reopening the project. Do not assume that file names enforce ordering.
- Capture at doorways and corners so the path remains understandable.
- Do not save unrelated areas between adjacent points in your intended route.
- Do not upload an entire long walk video as one point and expect the app to create all the intermediate locations.
- For a branched or backtracking route, write down the intended sequence first. The current UI does not provide a general branching-route editor or drag-and-drop sequence editor.

If you discover a missing point in the middle after saving a long sequence, stop and ask for help with the route structure. Simply appending that point at the end does not insert it into the middle of the tour.

## 17. Test the Finished Walkthrough in Both Directions

1. Close any open viewer and locate waypoint #1.
2. Open it using its **View** button.
3. Confirm that a yellow forward arrow is visible when another waypoint follows.
4. Click the yellow arrow. The next photograph should open.
5. When another forward waypoint exists, the new view should open facing its yellow arrow, including around turns.
6. Continue to the last capture. There is no yellow next-point arrow beyond the end of the sequence.
7. At the end, use the white backward arrow to return.
8. Continue backward through the sequence. A continuing white arrow should be centered when a previous point exists.
9. Test **Previous capture** and **Next capture** below the viewer as an alternative to clicking in-photo arrows.
10. Close the viewer and open a middle point directly from **View**. Its yellow arrow should be centered when it has a next point.
11. Close the viewer and open that same middle point by clicking its map dot. Check the same behavior.
12. At the last waypoint, a direct open centers the available backward arrow instead.
13. Look around by dragging the photo. The compass dial should turn so the direction the app considers your facing direction is at the top. N, NE, E, SE, S, SW, W, and NW are shown.
14. Compare visible landmarks and the map. Confirm that every arrow leads to the intended adjacent location.

Yellow means the next saved route point. White means the previous saved route point. Neither color is an emergency-exit instruction or a guarantee of a physically unobstructed path.

The app positions arrows toward the floor but does not detect people, faces, walls, or other objects to route around them automatically. Choose safe capture positions and a sensible waypoint path yourself.

## 18. Optional: Preserve Native Insta360 Files in the Project

Use this after your panoramic JPG workflow has passed its three-point test.

1. Before saving a new capture, select its exported panoramic JPG in **Preview image (JPG, PNG, or WebP)**.
2. Find **Original Insta360 X6 file** below it.
3. Select the original `.insp` photo or `.insv` video file that corresponds to this same location and capture.
4. Recheck both file names against your log.
5. Click **Save waypoint here** once.
6. Leave the page open while the original uploads and processing runs. Large files can take significantly longer than JPG previews.
7. Wait for confirmation, then open the saved waypoint and inspect the real image.

The current processing path can attempt an image decode or extract a video frame. It is not a complete manufacturer stitching engine or automatic continuous-video-to-tour pipeline. A generated placeholder can be reported as a preview when native decoding fails. A colored or generic placeholder is not proof that your site photograph was successfully decoded.

Do not rely on native-only upload for your first complete inspection. Keep a verified stitched JPG available. Although the native file chooser includes ZIP, do not assume an archive will be unpacked, stitched, or converted into a route. Do not rename a ZIP, video, or normal photograph to make it look like a different supported file type.

For a continuous walk video, retain the original and use an agreed extraction/export workflow to create the required stationary-view images. Record their timestamps and locations. CASAI does not currently determine all video positions for you.

## 19. Correct a Photograph or a Misplaced Point

### Correct photograph attached to the wrong file

If the saved location is correct but its displayed photograph is wrong:

1. Close the photo viewer.
2. Find the correct waypoint number in **Saved waypoints**.
3. Click **Edit** beside that waypoint.
4. Scroll to the **Edit waypoint** panel if it is not already in view.
5. Check the waypoint number shown in that panel.
6. Under **Replace photo**, select the correct stitched panoramic JPG.
7. Click **Save changes**.
8. Wait for confirmation, then click **View** on that waypoint and inspect it again.

**Edit** is not a general location, heading, or sequence editor in the current UI.

### Correct a position

If a point appears in **Calibration review**, click its **Correct on plan** button, then click the correct physical camera location on the drawing. Wait for confirmation before doing anything else.

Not every manually placed waypoint appears in that review list. If the incorrect point has no correction control, do not assume you can drag it or fix it just by clicking somewhere else. A normal click changes the current unsaved position, not the stored location of an existing pin.

For a short disposable test, it may be simplest to start a clean test project and save the correct sequence. For an important or long route, ask the administrator for help before deleting and recreating points, because a new point is appended and can change the intended route order.

### Delete only when you are certain

1. Record the point's location and file names first.
2. Check the waypoint number carefully.
3. Click **Delete** beside that waypoint.
4. Read the confirmation message. Confirm only if it is the intended point.
5. Recheck the remaining route afterward. Displayed numbers and the sequence can change.

Deletion is not an undo command, and there is no operator recycle-bin workflow in this UI. Do not assume deleting a waypoint securely erases every underlying media object or your camera backups.

## 20. Add an Optional Plan Note

1. Close the viewer and scroll to **Plan notes**.
2. Click **What needs attention?** and type a short, factual note.
3. If appropriate, select a captured pin in the dropdown below the note. Leave **General plan note** selected for a note about the overall area.
4. Click **Place note on plan**.
5. Click the location on the drawing to which the note applies.
6. Wait for confirmation and check that the note appears in the list and on the plan.

When note-placement mode is active, your next plan click places the note rather than setting a normal capture position. Finish that action and verify the status message before resuming captures. Avoid recording passwords, access codes, or unnecessary personal information in notes.

## 21. Finish and Check That Work Was Saved

1. Compare the number of saved waypoints with the number in your capture log.
2. Open each point and confirm it shows the correct real photograph.
3. Verify both forward and backward navigation, including turns and room transitions.
4. Close the viewer.
5. Confirm that the last save has completed and no upload is still running.
6. Refresh the browser page using its circular-arrow refresh button.
7. If asked, sign in again using the same individual account.
8. Select the correct project from the **Project** dropdown.
9. Confirm that its floor plan and saved waypoints reappear without another upload.
10. Re-enter or verify the correct **Plan width (feet)**, **Drawing scale**, and manual position settings before judging displayed feet or continuing the route.
11. Open at least the first, a middle, and the last photo after the refresh.
12. Keep your separate file backup and capture log. Do not erase the camera card solely because you saw one successful upload message.

What should persist in production: the project, successfully saved pins, uploaded media references, plan reference, and saved notes. What should not be assumed to persist: an unsaved position, a file merely selected in the browser, the open viewer, browser calibration controls, or the current-session route distance.

## 22. Review Status and Sharing

### Mark the project ready

1. After completing your checks, click **Review view** on the floor-plan page. If you are on the Dashboard instead, use **Open review view**.
2. Find the project in **Existing projects** and click **Open** beside the correct title.
3. Check its title, capture count, and summary.
4. Click **Mark ready for review** only after you have personally checked the route.

That button changes a status. It does not automatically verify image quality, completeness, measurement accuracy, or permissions.

### Create a limited review link when authorized

1. In the selected project's review page, find **Share link expires in**.
2. Choose the authorized duration: 1, 7, 14, or 30 days. The default is 7 days.
3. Click **Create share link**.
4. Confirm that a URL and expiration are displayed.
5. Click **Copy share link**.
6. Paste it into the approved message or communication system. On a computer, click the message field and press **Ctrl+V** to paste.
7. Send it only to authorized recipients. Anyone who possesses the valid link can open its supported review response.
8. Test the recipient experience in a signed-out/private browser before promising that it provides the complete authenticated floor-plan walkthrough.

**Current limitation:** The public shared-review page is a project summary/evidence-list view, not the full signed-in floor-plan photo-navigation interface. Direct media endpoints still require the owning account. Do not give out your password to work around that distinction. Ask the administrator to arrange an approved review method.

Creating a replacement share link invalidates the previous link. **Revoke share link** invalidates the current link when that control is available. If you left the page and the old link is not shown for management, creating a new one invalidates the older one; revoke the replacement too if no link should remain active. Previously downloaded information cannot be recalled by revocation.

Another user's account, including an administrator account, should not be assumed to see your projects automatically. The current ownership model is not a general team-membership system.

## 23. Sign Out and Return Later

1. Wait until saving and uploads have finished.
2. Click **Account** near the top of the page, or open `https://casaifield.com/login.html`.
3. Confirm the displayed account is yours.
4. Click **Sign out**.
5. Close the browser on shared equipment.

When returning:

1. Sign in with the same individual account.
2. Open the floor-plan walkthrough.
3. Select the same project.
4. Wait for its plan and pins to load.
5. Recheck the plan width and other manual controls.
6. Continue only after verifying the last saved location, file, and route order.

A session may expire and require another sign-in. Closing the browser alone is not the same action as clicking **Sign out**.

## 24. Troubleshooting: Stop, Check, Then Continue

| What you see | What to do |
| --- | --- |
| **Save waypoint here** is gray or unavailable | Select the correct project, confirm the plan is visible, and click the actual camera location on the drawing. Clicking only a file picker does not set a map position. |
| Plan area is blank but waypoints are listed | Confirm the project and wait for loading. Refresh once after all saves finish. The updated server can recover older files, but missing files, storage permissions, or an older deployed version can prevent this. Stop and ask the administrator if it remains blank. If instructed to reupload, use the exact same crop and proportions. |
| File picker says **No file chosen** after reopening | Browser file selections are temporary. If the plan is displayed and saved photos open, those server copies can still be present. |
| Numbers in feet look different after reopening | Recheck **Plan width (feet)** and drawing proportions. Do not move all pins just to compensate for an incorrect width setting. |
| The current marker moved while you were not walking | Check **Position updates**. Select **On each walk step**; timed mode can move the app's marker every five seconds without measuring physical motion. |
| A panorama looks stretched, cropped, or nothing like a 360 view | Verify that you exported a stitched full panorama rather than a screenshot, single-lens image, or normal JPG. Replace the preview with a known-good export. |
| A generic colored image appears | It may be a native-processing placeholder. Do not accept it as completed evidence. Use the verified exported panoramic JPG and check again. |
| No yellow arrow is visible | Check whether this is the last waypoint. If it is not, verify that a next placed point exists, use **Next capture**, and report an unexpected orientation problem with the waypoint numbers. |
| No white arrow is visible | Check whether this is the first waypoint. There is no previous point at the beginning. |
| Photo is correct but the dot is in the wrong place | Use **Correct on plan** only if available for that pin; otherwise stop and ask for help. Clicking the map normally does not move an existing saved point. |
| You selected a photograph, but it is not in the project | Selecting is not saving. Confirm that you clicked **Save waypoint here** and received its completion message. |
| A save failed or the connection dropped | Do not keep clicking Save. Reconnect, reopen the project, check whether a partial/empty or duplicate pin exists, and inspect its photo before retrying. Record the error. |
| You appear to have the wrong person's project list | Check **Account** and the selected project. Sign out and use the correct individual account. Do not share credentials. |
| The app asks you to sign in again | Sign in, reopen the correct project, and inspect the last saved point before resuming. Do not assume an interrupted upload completed. |
| You see **502**, a server error, or a certificate warning | Do not edit server settings or repeatedly reupload. Record the time and visible error and contact the administrator. A server restart may briefly interrupt service. |
| Share link opens a summary but not the full tour | That is a limitation of the current public review path. Do not send your account password; ask for an approved review arrangement. |

When asking for help, provide the project title, waypoint number, approximate time, device/browser, file type and approximate size, exact error text, and a screenshot with sensitive information removed. Never send account passwords, camera credentials, storage keys, or the server environment file.

## 25. First-Test Acceptance Checklist

Do not declare the workflow ready for a complete site capture until every applicable item is checked:

- [ ] I can sign in using my own account.
- [ ] I selected the intended project rather than the first project by accident.
- [ ] The floor plan matches the site, floor, revision, and orientation.
- [ ] The complete-image plan width is known and entered correctly.
- [ ] Position updates are manual for this test.
- [ ] I understand that camera capture, marker movement, file selection, and saving are separate actions.
- [ ] I saved three real capture points in the intended order, including a turn.
- [ ] Each point opens the correct stitched full panorama, not a placeholder.
- [ ] Yellow arrows advance to the correct next location.
- [ ] White arrows return to the correct previous location.
- [ ] Direct opens from both **View** and the map dots behave as expected.
- [ ] I checked recognizable landmarks rather than relying solely on the compass graphic.
- [ ] The plan, pins, and photographs still load after refreshing and reopening the project.
- [ ] I rechecked the manual calibration settings after reopening.
- [ ] I retained the original files, exported previews, and a location/file capture log.
- [ ] Any intended recipient has tested the approved review method.

If one of these checks fails, resolve it with the three-point test before expanding to an entire floor.

## 26. One-Page Repeatable Field Routine

**Before the route:** Permission -> safe route -> charged camera -> known-good panoramic export -> correct plan -> sign in -> project -> upload/load plan -> verify dimensions -> manual position mode.

**At every location:** Stop safely -> capture -> export/match the image -> click actual plan position -> verify heading -> choose preview -> optionally choose matching original -> save once -> wait -> open and verify -> log the saved number.

**At every turn:** Confirm the next physical location, mark it accurately, recheck heading, and verify that the saved sequence does not jump through walls or skip an important transition.

**Before leaving:** Count captures -> inspect every photo -> test both directions -> refresh and reopen -> recheck plan persistence -> back up files -> arrange approved review -> sign out.

## Document Maintenance Note

This is an operator procedure, not a promise of features beyond the current app. Button names and limitations were checked against Draft 2 source at `da7504a`, including the floor-plan controller, Dashboard, account page, review controls, and backend storage/processing behavior. The physical camera workflow and the production server were not independently tested while preparing this document. Camera menu details must be confirmed using the actual manufacturer's documentation and device firmware.