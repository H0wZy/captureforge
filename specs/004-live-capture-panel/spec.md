# Feature Specification: Live capture inside Blender

**Feature Branch**: `004-live-capture-panel` (stacked on `003-character-fitted-weights`, `002-face-head-pose`, `001-bodyforge-v1`; rebase when those merge)

**Created**: 2026-10-05

**Status**: Draft (specify). This branch stops at spec, plan and tasks; nothing is implemented.

**Input**: User description: "A FaceForge sidebar panel in Blender with a camera picker that lists the webcams it finds, a live preview with the landmarks drawn on top, and a Capture button that records straight onto the selected character. The recording drives its ARKit shape keys and the head bone live, then bakes into an Action and optionally saves the CSV. The same panel has an Import video button that runs the video pipeline internally, so there is no separate external step. Over time it covers the FaceTracker workflow of `docs/research/keentools-facetracker.md`: anchor frames and refine (idea 2) and character-fitted weights (spec 003). Hard constraints: everything free and open source and GPL-3.0 compatible, no paid add-ons or services; it works for any user anywhere, on Windows, macOS and Linux, on every Blender version the add-on supports, offline after the one-time setup."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Capture from a webcam straight onto the character (Priority: P1)

An animator opens the CaptureForge sidebar, picks the character, picks a camera from a list, sees themselves in a small
preview with the tracked face points on top, presses Capture, watches the character's face and head follow them live,
presses Record, performs, presses Stop, and the performance is baked into an Action on the character (shape keys and
the head bone). Optionally they save the CSV.

**Why this priority**: it is the whole request. Today live mode needs a hand-set Python path, a UDP port, and has no
preview, no camera list, no head, and records only while the modal timer runs.

**Independent Test**: with a fake camera (a video file played as a camera) the helper streams to Blender, the shape
keys and the head bone move, Record then Stop produces an Action whose curves match what was streamed.

**Acceptance Scenarios**:

1. **Given** a machine with the helper installed and a camera, **When** the user opens the panel and presses `Refresh cameras`, **Then** the cameras are listed by name where the OS gives names, by index otherwise, and the camera is only opened for that check.
2. **Given** a chosen camera, **When** the user presses `Capture`, **Then** a preview with the landmarks appears within 2 s and the character's shape keys and head bone follow the face with the latency of SC-002.
3. **Given** `Record` is armed, **When** the user presses `Stop`, **Then** one undo step bakes shape keys and head pose into an Action starting at the chosen frame, using the same calibration and smoothing as `Video to face`, and the helper process is gone.
4. **Given** the user ticks `Save CSV`, **When** the capture is baked, **Then** a CSV in the generic format (with the head pose columns of spec 002) is written next to the .blend.

---

### User Story 2 - One panel for a video file too (Priority: P2)

The same panel has `Source: Camera | Video file`. With a video file, `Import video` runs the existing pipeline
internally (`Video to face`) and ends in the same bake as a live capture, so the two give the same result for the same
footage.

**Independent Test**: the same fake footage through both sources yields curves that agree within the smoothing tolerance.

**Acceptance Scenarios**:

1. **Given** a video file and the helper, **When** the user presses `Import video`, **Then** no terminal step is needed and the character is keyed as in Story 1.
2. **Given** the same footage played as a camera and imported as a file, **Then** the baked weights agree within 0.02 RMS (the two paths share one post-processing).

---

### User Story 3 - It sets itself up and fails politely (Priority: P2)

On first use the add-on offers to set up its helper, shows exactly what it will download and how big it is, and works
offline afterwards. Every failure (no camera, camera busy, permission denied, helper missing or crashed, model
missing) ends in a message that says what to do on the user's operating system, never a traceback, and never leaves a
process running or Blender stuck.

**Independent Test**: scripted failures (no camera index, a busy camera, a helper that exits at once, a corrupt
model) each produce the documented message and a clean state.

**Acceptance Scenarios**:

1. **Given** no helper, **When** the user presses `Capture`, **Then** a dialog lists the packages, versions, sizes and sources, and nothing is downloaded before `Install` is pressed.
2. **Given** the helper is installed, **When** the network is off, **Then** capture, import and bake all work.
3. **Given** the camera is in use by another app, **When** the user presses `Capture`, **Then** the message says so and Capture stays available.
4. **Given** the helper crashes mid-capture, **Then** Blender keeps running, the recorded part is kept so far, and the message says what happened.

---

### User Story 4 - A foundation for the FaceTracker-style workflow (Priority: P3)

What a capture or an imported video produces (raw scores, landmarks, head matrix per frame, with times) is one capture
file with a documented format, so that anchor frames and refine (research idea 2) and character-fitted weights (spec
003) can work on it later without rerunning the tracker. This spec only defines the file and keeps it opt-in; the two
features are their own specs.

**Independent Test**: a capture file written by a live capture and one written by a video import have the same
arrays, and spec 003's loader reads both.

### Edge Cases

- Several cameras, a camera unplugged mid-capture, a camera that opens but delivers no frames (some virtual cameras).
- Two Blender windows or two captures at once: one capture per Blender process; the second press says so.
- Blender closes, crashes or is killed during a capture: the helper ends by itself within 2 s and releases the camera.
- The user switches scene, frame range or target during a capture: capture keeps running, the bake uses the settings of the moment Record started.
- The face leaves the frame: the character holds its last pose, the preview says "no face", the recording holds (as the video path does).
- A very high camera resolution or frame rate: the helper downsizes for tracking and for the preview; the preview is capped.
- A laptop without a GPU texture path or a headless Blender (`--background`): capture and bake still work, the preview is simply absent.
- High-DPI and multiple monitors: the preview is sized in UI units, not pixels.
- Non-ASCII user names and paths with spaces on any OS.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every component MUST be free and open source under a GPL-3.0-compatible license, and no feature may need a paid add-on, account or service. The licenses of each runtime component are recorded in `THIRD_PARTY_NOTICES.md` before it ships.
- **FR-002**: Capture MUST run in a **sidecar helper process** started by the add-on on `Capture` and ended on `Stop`, on Blender quit, on add-on unregister and when Blender dies. It is not a service, is never autostarted, and leaves nothing running.
- **FR-003**: The helper and Blender MUST talk over a connection that is local only (loopback, an ephemeral port, a per-session token checked on the first message), carrying framed messages (JSON header plus optional binary preview frame). No data MAY leave the machine, and no network access happens during capture.
- **FR-004**: Everything tracker-specific MUST live in one helper module with a small documented contract: one RGB frame and a timestamp in; the 52 blendshape scores, the 478 landmarks and the 4x4 head matrix (each possibly absent when there is no face) out. No other module may import MediaPipe. No plugin framework and no second backend now.
- **FR-005**: The panel MUST list cameras on an explicit `Refresh cameras` press (probing opens devices), with names where available.
- **FR-006**: The panel MUST show a live preview of the camera frame with the landmarks drawn on top, as a viewport overlay, switchable off, capped in size and rate.
- **FR-007**: While capturing, the selected targets' shape keys and head bone (spec 002 options: bone, neck share, gain) MUST follow the face live.
- **FR-008**: `Record` MUST buffer the raw per-frame data with helper timestamps; `Stop` MUST bake it into an Action (shape keys and head bone) in one undo step with the same post-processing as the video path (neutral, gain, smoothing, head pose), and MAY save the generic CSV and the capture file.
- **FR-009**: `Source: Video file` with `Import video` MUST run the existing video pipeline internally and end in the same bake.
- **FR-010**: On first use the add-on MUST offer to set the helper up: show the packages, versions, sizes and sources, ask for confirmation, download only after it, verify checksums where a checksum is published or pinned, and create a private environment with no admin rights and nothing system-wide. After that all features MUST work offline.
- **FR-011**: The helper environment MUST be creatable on a machine with no other Python installed (Blender's own interpreter is enough), and on Windows, macOS and Linux.
- **FR-012**: Failures MUST map to a fixed set of error codes (no camera, camera busy, permission denied, no frames, helper missing, model missing or corrupt, helper crashed, port busy) with a one-line fix per operating system, and MUST NOT leave a process or a timer running.
- **FR-013**: The face model file MUST be pinned by URL and SHA-256, and MUST work without the network once present (see the plan for bundling).
- **FR-014**: The add-on manifest MUST declare the camera permission, and the panel MUST say which process uses the camera.
- **FR-015**: Capture MUST not write a frame, a landmark or a score to disk unless the user asks (`Save CSV`, `Keep capture file`); the capture file is face data and is documented as personal data.
- **FR-016**: A documented test matrix MUST exist and the parts that do not need a physical camera MUST run in CI on Windows, macOS and Linux (see the plan).
- **FR-017**: README and README.pt-BR MUST document setup, the panel, the failure messages and the privacy note.

### Key Entities

- **Tracker contract**: the one-frame-in, three-things-out interface of FR-004.
- **Capture session**: helper process, connection, token, state (`starting`, `calibrating`, `live`, `no face`, `stopped`, `error`), the record buffer.
- **Capture file**: `.npz` with times, raw scores, landmarks, head matrices, image size and an interface version (superset of spec 003's landmark file).
- **Helper environment**: a private venv with pinned packages and the model.

## Success Criteria *(mandatory)*

- **SC-001**: a fresh machine with no Python of its own goes from the add-on zip to a working capture with one dialog, on Windows, macOS and Linux.
- **SC-002**: with a 30 fps camera on a mid-range laptop CPU, the character reacts to a face within 150 ms (p95) of the frame being captured, the Blender UI stays at 30 fps or more, and the preview shows at 15 fps or more.
- **SC-003**: after `Stop`, no helper process exists and the camera is released within 2 s, in every scripted failure and when Blender is killed.
- **SC-004**: the same footage through camera and file sources bakes to weights within 0.02 RMS of each other.
- **SC-005**: with the network disabled after setup, every user story works.
- **SC-006**: every error code of FR-012 has a test that triggers it and checks the message and the clean state.
- **SC-007**: the existing suites (spec 001 to 003) pass unchanged.

## Out of scope for this spec

- Anchor frames and refine (own spec, research idea 2) and character-fitted weights (spec 003); this spec only makes sure the capture file can feed them.
- A second tracking backend, a plugin system, iPhone ARKit, depth cameras (Constitution IX), audio.
- Android capture (MediaPipe running on the phone) is future work and would send the same CSV contract (or the capture file).
- iOS capture (the iPhone's native ARKit 52 blendshapes and head pose) is future work, optional (Constitution IX), and would send the same CSV contract.
