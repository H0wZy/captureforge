# Feature Specification: Live capture inside Blender

**Feature Branch**: `004-live-capture-panel` (stacked on `003-character-fitted-weights`, `002-face-head-pose`, `001-bodyforge-v1`; rebase when those merge)

**Created**: 2026-10-05

**Status**: Draft. Decisions of 2026-10-05 applied (model bundled, Intel macOS unsupported). This branch stops at spec, plan and tasks; nothing is implemented.

**Input**: User description: "A FaceForge sidebar panel in Blender with a camera picker that lists the webcams it finds, a live preview with the landmarks drawn on top, and a Capture button that records straight onto the selected character. The recording drives its ARKit shape keys and the head bone live, then bakes into an Action and optionally saves the CSV. The same panel has an Import video button that runs the video pipeline internally, so there is no separate external step. Over time it covers the FaceTracker workflow of `docs/research/keentools-facetracker.md`: anchor frames and refine (idea 2) and character-fitted weights (spec 003). Hard constraints: everything free and open source and GPL-3.0 compatible, no paid add-ons or services; it works for any user anywhere, on Windows, macOS and Linux, on every Blender version the add-on supports, offline after the one-time setup."

## Clarifications

### Session 2026-10-05

Answered with the recommended default; no user was blocked. The maintainer should confirm or override. Facts marked "checked" were read from PyPI metadata, a local venv or a local Blender run on 2026-10-05; nothing was installed.

- Q: Install MediaPipe and OpenCV into Blender's Python (a), or a sidecar helper from our own venv (b)? -> A: **(b), the sidecar.** Wheels are not the blocker (checked: current MediaPipe wheels are tagged `py3-none-<platform>`, so they install on Blender 5.2's Python 3.13 and on 4.4's 3.11). The reasons are the others: (1) a second copy of numpy and of native libraries (OpenCV, protobuf, abseil) in Blender's own process risks an ABI clash that crashes Blender with unsaved work, while a crash in a sidecar only ends the capture; (2) camera reads and inference would share Blender's GIL and UI thread; (3) Blender's site-packages is not writable on many installs (Program Files, a signed macOS bundle, a system Linux package); (4) a venv we own can be pinned, repaired and deleted without touching the user's Blender. Option (a) stays documented as the rejected alternative.
- Q: How do Blender and the helper talk? -> A: TCP on `127.0.0.1`, an ephemeral port chosen by Blender and passed on the command line, a random per-session token that must be the first message, length-prefixed frames (a JSON header, an optional binary payload). TCP is reliable and carries a preview frame (UDP datagrams top out at 64 KB). The existing UDP path (`faceforge.live_start`) stays for external senders and is not touched. Blender reads the socket non-blocking from a modal timer.
- Q: How does the helper learn that Blender is gone? -> A: Blender starts it with a stdin pipe and the helper exits on end of file, which works on all three operating systems, also after a Blender crash, with no extra package. `Stop` sends a goodbye, then terminates, then kills after 3 s. The add-on also stops it on unregister and on the Blender quit handler.
- Q: Where is the preview drawn? -> A: a viewport overlay: a `SpaceView3D` draw handler that uploads the newest frame to a `gpu.types.GPUTexture` and draws a textured quad plus the landmarks as points, in a corner, sized in UI units (default 320 px wide at 1x), at most 15 Hz. An Image Editor area was rejected: it needs a datablock and a pixel copy through `Image.pixels` for each frame. No GPU (background mode) means no preview, nothing else changes. The projection from landmarks to overlay coordinates is a pure function and unit tested; the draw call is checked by hand and by an import smoke test.
- Q: Latency budget? -> A: the 150 ms p95 of SC-002, split as: capture and MediaPipe at most 60 ms (the LIVE_STREAM mode is asynchronous), the local socket under 2 ms, the Blender timer at 60 Hz (at most 17 ms), the depsgraph update after the keys change under 30 ms for a face rig. The helper stamps each message with its capture time on the host clock, Blender logs the difference on receipt, so the budget is measured, not guessed (a task in the plan).
- Q: What is recorded and when is it baked? -> A: while `Record` is armed Blender appends every message (helper time, raw scores, landmarks, head matrix) to an in-memory buffer; `Stop` runs the same pure post-processing as the video path (hold gaps, neutral, gain, smoothing, head pose) on that buffer in-process and keys it with the existing `apply_mocap` and `apply_head_pose`, in one undo step, starting at the chosen frame at the scene frame rate. The live drive during capture uses the calibrated values the helper streams; the bake uses the raw buffer, so the result equals a video import of the same footage and can be rebaked with other neutral, gain or smoothing. Nothing is written to disk unless `Save CSV` or `Keep capture file` is ticked.
- Q: How does the camera list work? -> A: the helper has a `--list-cameras` mode printing JSON (`index`, `name`, `backend`). It uses the optional MIT package `cv2-enumerate-cameras` (checked: MIT, pure Python wheel plus Windows extensions) when present for names, and falls back to probing OpenCV indices 0 to 9 with a short open and read. Probing turns the camera light on and may trigger the macOS permission prompt, so it runs only on `Refresh cameras`, never when the panel draws.
- Q: Set the environment up by a consent dialog, or bundle wheels? -> A: **a consent dialog, no bundled wheels.** The wheels for three operating systems and two CPU families (MediaPipe, OpenCV, numpy) are well over 100 MB per platform, which does not suit an extension zip, and pinned PyPI downloads with `--only-binary=:all:` and published hashes are reproducible. The dialog (the existing `bodyforge.install_helper` pattern, widened to the face helper) lists the packages with pinned versions, the approximate sizes, the sources (PyPI, Google model storage) and the folder, and nothing downloads before `Install`. An offline path exists for air-gapped machines: `Install from folder` runs pip with `--no-index --find-links` on a folder of wheels the user brought. After setup no network is needed.
- Q: Which Python creates the venv? -> A: **Blender's own interpreter** (checked: Blender 5.2's bundled Python 3.13.13 imports `venv` and `ensurepip` and creates a working venv with `pip`), so a machine with no Python works. The current installer looks for a system Python 3.10 to 3.12; it changes to prefer Blender's. A system Python stays a fallback.
- Q: Bundle the face model in the add-on? -> A: **Yes (decided by the maintainer 2026-10-05).** `face_landmarker.task` is 3.6 MB (checked: the local copy is 3,758,596 bytes, SHA-256 `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`, from the pinned `float16/1` URL), Apache-2.0 on the Google model cards (verified 2026-10-04 in `docs/pt-BR/BODYFORGE-T051-LICENCA.md`), and bundling is allowed with the Apache-2.0 text and an attribution note (Apache-2.0 section 4; the `.task` has no NOTICE). The repository stays clean: the release workflow downloads the file from the pinned URL, checks the SHA-256, and adds it to the zip with `licenses/Apache-2.0.txt` and the `THIRD_PARTY_NOTICES.md` entry. The constitution was amended to v1.0.1 (PATCH) to say so, `docs/BODYFORGE-MODELS.md` records the checksum, and the amendment still needs the maintainer's approval to merge. The add-on prefers the bundled file and falls back to the installer's download for development installs. The pose and hand models keep being downloaded on demand.
- Q: Insurance against MediaPipe being archived or changed? -> A: (1) pin the package version and the model checksum in one lock file (`requirements-mocap.txt` becomes pinned, CI installs from it on all three systems); (2) vendor the model as above; (3) one tracker module behind the contract of FR-004, written in `docs/TRACKER-CONTRACT.md`: input `frame` (uint8, height x width x 3, RGB) and `timestamp_ms`; output `scores` (dict of the ARKit names, or none), `landmarks` (478 x 3 float32, normalized, or none), `matrix` (4x4 float32, or none). The existing `video_to_csv.detect`, `webcam_stream.py` and `face_landmarks.py` move behind it. A different backend replaces that one file later. No registry, no plugin loader.
- Q: Python 3.13 and a source build as a fallback? -> A: checked on PyPI 2026-10-05: `mediapipe` 1.0.1 (uploaded 2026-08-14, Apache-2.0) ships `py3-none` wheels for Windows x86-64 and ARM64, macOS arm64, Linux x86-64 and aarch64, so Python 3.13 works. There is no macOS Intel wheel in the current releases; that platform is officially unsupported (decision 2026-10-05). A source build would need Bazel, a C++ toolchain and OpenCV development files and is a long, fragile build; it is a documented last resort for unsupported platforms and not something the add-on automates. `opencv-python` 5.0.0.93 (Apache-2.0) ships `cp37-abi3` wheels for all of those and macOS Intel; `numpy` is BSD.
- Q: Which operating systems and Blender versions? -> A: Windows 10 and 11 (x86-64, ARM64 by wheel availability), Linux x86-64 and aarch64 (glibc 2.28 or later, from the wheel tag) and macOS 12 or later on Apple Silicon (M1 and later) are supported. **Intel macOS is officially unsupported** (decided 2026-10-05; MediaPipe publishes no current wheel for it), and the README says so; Blender 4.4 LTS and 5.2, the two lines of Constitution IV. Camera backends: Windows Media Foundation (DirectShow fallback), macOS AVFoundation, Linux V4L2.
- Q: Camera permission? -> A: the manifest declares `camera`. On macOS the camera prompt is attributed to the app that started the helper (Blender); whether Blender's bundle carries a usage description so that the prompt appears instead of a silent failure is unverified and is the first macOS check in the test matrix. On Linux the user needs access to the video device (usually the `video` group); the message says so.
- Q: Error codes? -> A: `no_camera`, `camera_busy`, `permission_denied`, `no_frames`, `helper_missing`, `model_missing`, `model_corrupt`, `helper_crashed`, `port_busy`, `token_mismatch`. The helper reports the first six it can see as an error message before it exits; Blender derives `helper_crashed` from an unexpected exit and shows the last lines of the helper's error output.
- Q: Test matrix? -> A: in the plan. CI runs on Ubuntu, Windows and macOS hosted runners: pure tests everywhere, the Blender suite on both Blender lines, and the helper environment install from the pinned lock file plus the real helper on a synthetic video on each OS (this also tests setup and the wheels). The camera itself is a per-OS manual checklist on real hardware; a fake camera (a video file or synthetic frames behind the same helper interface) covers the protocol, lifecycle and error paths in CI.
- Q: Does the existing live mode go away? -> A: no. `4c. Live webcam` (UDP, external senders) stays as it is; the new panel replaces its camera and recording flow in the docs, and the old box is marked "advanced" when the new one ships.
- Q: Is this implemented now? -> A: no. This branch ends at tasks. The estimate is large (about 1,800 lines plus tests, a CI matrix change and docs), three of the checks need real hardware, and the two maintainer decisions (model bundling, Intel macOS unsupported) are made.

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
- **FR-013**: The face model file MUST be pinned by URL and SHA-256 and MUST be included in the release zip by CI (never committed), with the Apache-2.0 text and an attribution note, so capture works offline with no model download.
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
