# Implementation Plan: Live capture inside Blender

**Branch**: `004-live-capture-panel` | **Date**: 2026-10-05 | **Spec**: [spec.md](spec.md) | **Evidence**: [research.md](research.md)

## Summary

The main architecture decision: **a sidecar helper process in a private venv (option b), not MediaPipe inside
Blender's Python (option a).** The add-on starts the helper when the user presses `Capture`; the helper reads the
camera, runs the tracker behind a one-file contract, and streams framed messages (scores, landmarks, head matrix, a
small preview frame) over loopback TCP to a modal timer in Blender. Blender drives the shape keys and the head bone
live, draws the preview as a viewport overlay, buffers the raw stream while `Record` is armed, and on `Stop` bakes it
through the same pure post-processing and keying code as `Video to face`. The helper environment is created on
consent by Blender's own Python, so a machine with no Python works; after setup everything is offline.

## Technical Context

- Blender 4.4 LTS (Python 3.11) and 5.2 (Python 3.13); helper venv created by Blender's interpreter; MediaPipe, OpenCV and numpy from pinned wheels (MediaPipe wheels are `py3-none`, see research).
- Helper: Python, MediaPipe Face Landmarker in LIVE_STREAM mode, OpenCV for the camera; stdlib `socket`, `struct`, `json` for the protocol. Optional `cv2-enumerate-cameras` (MIT) for camera names.
- Blender side: `socket` non-blocking in a modal timer, `gpu` module for the overlay, numpy for the buffer.
- Platforms: Windows 10/11 (x86-64, ARM64), macOS 12+ on Apple Silicon, Linux x86-64 and aarch64; Intel macOS is officially unsupported (no current MediaPipe wheel).
- Performance goals: SC-002 (150 ms p95, UI at 30 fps, preview at 15 fps).
- Constraints: local only, no telemetry, opt-in face data on disk, no paid component.

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Clean room | Pass | Standard sockets, OpenCV and MediaPipe public APIs; the FaceTracker research is credited for the workflow idea only. |
| II. Blender API only inside the extension, ML outside | Pass, strengthened | The tracker is one helper module behind a documented contract; MediaPipe is never imported in Blender; the interface is the framed local protocol and the capture file. |
| III. Headless-testable, test first | Pass | The protocol codec, record buffer, post-processing, preview projection and error mapping are pure and tested first; Blender tests use a fake sender; a fake camera drives the helper in CI. The GPU draw call is the one untestable piece, kept to a few lines and checked by hand. |
| IV. CI green on both Blender lines | Pass, matrix grows | Existing suites on 4.4 and 5.2; new jobs on Windows and macOS runners (see test matrix). |
| V. GPL-compatible dependencies, no NC weights | Pass | All Apache-2.0, BSD or MIT; the model is Apache-2.0 (verified 2026-10-04); `THIRD_PARTY_NOTICES.md` gains `cv2-enumerate-cameras` and `numpy`. |
| VI. Privacy and responsible use | Pass | Loopback only with a session token, no frame or landmark on disk unless asked, preview frames only in memory, the manifest declares `camera`, POLICY.md linked from the panel. |
| VII. English first, pt-BR for users | Pass | README, README.pt-BR and a short `docs/pt-BR/` setup note. |
| VIII. Lean code | Pass, three entries in Complexity Tracking | Python, bpy, numpy and the stdlib in the add-on; no framework. |
| IX. Android and no-iPhone friendly | Pass | Any webcam or a phone used as a webcam; iOS and Android capture are future and optional. |
| X. Semantic versioning | Pass | New interface (the local protocol, the capture file) gets an interface version; the manifest version moves at release. |

**Decided by the maintainer 2026-10-05:** (1) the 3.6 MB face model is added to the release zip by CI with the pinned
SHA-256, the Apache-2.0 text and an attribution note; the constitution was amended to v1.0.1 (PATCH, commit on this
branch, still to be approved in review); (2) Intel macOS is officially unsupported, Windows, Linux and Apple Silicon
macOS are supported.

## Project Structure

```text
specs/004-live-capture-panel/       spec.md, plan.md, research.md, tasks.md
captureforge/face/helpers/
  tracker.py                        the ONE module that imports MediaPipe: Tracker.open(model), Tracker.process(frame, ts) -> Result
  capture_helper.py                 camera loop + tracker + framed protocol server/client side, --list-cameras, --source file for the fake camera, stdin watchdog
  video_to_csv.py, webcam_stream.py, face_landmarks.py   call tracker.py instead of MediaPipe directly
captureforge/face/capture/
  protocol.py                       pure: frame codec (length + JSON header + payload), message types, token handshake
  post.py                           pure: the video path's hold/neutral/gain/smooth/head-pose steps shared by video, live bake and tests
  session.py                        Blender side: spawn, socket, state machine, record buffer, error mapping (no bpy beyond data access)
  errors.py                         pure: error codes, OS-specific fix text
  overlay.py                        pure projection + the small gpu draw handler
  setup.py                          helper environment: plan text, venv by Blender's Python, pip with pins, model, offline folder install
captureforge/face/ops.py, ui.py     operators (capture, stop, record, refresh cameras, install helper, import video, delete capture file) and the panel
captureforge/blender_manifest.toml  camera permission
requirements-mocap.txt              pinned versions
licenses/Apache-2.0.txt             license text shipped in the release zip next to the bundled face model
docs/TRACKER-CONTRACT.md            the contract (en), docs/pt-BR/CAPTURA-AO-VIVO.md (setup and failures, pt-BR)
tests/test_capture_*.py             pure tests; tests/run_tests.py gets the Blender tests; tests/fake_camera support in the helper
.github/workflows/ci.yml            OS matrix additions
```

## Design

### Why the sidecar (decision record)

| | (a) MediaPipe and OpenCV in Blender's Python | (b) sidecar from our venv |
|---|---|---|
| Wheels for Blender's Python | exist (`py3-none`), so possible | same wheels, in our venv |
| Crash isolation | a native crash kills Blender and unsaved work | a crash ends the capture |
| Second numpy and native libs in-process | ABI clash risk with Blender's numpy | none |
| Writable install location | often not (Program Files, signed macOS bundle, system Linux) | our own folder |
| Camera and inference vs Blender UI | share the GIL and the UI thread | separate process, UI stays smooth |
| Pin, repair, delete | touches the user's Blender | delete a folder |
| Cost | none extra | a local protocol and a lifecycle to get right |

(b) wins on safety and portability; its cost is the protocol and the lifecycle, which are small and fully testable.

### Tracker contract (FR-004, insurance against MediaPipe changes)

`helpers/tracker.py`: `Tracker.open(model_path)`, `Tracker.process(frame_rgb_uint8, timestamp_ms) -> Result` with
`scores` (dict ARKit name to float or None), `landmarks` ((478, 3) float32 normalized or None), `matrix` ((4, 4)
float32 or None), and `Tracker.close()`. Image mode, video mode and live-stream mode are three constructors of the
same class. Nothing else imports MediaPipe (a test greps for it). Another backend would be one file with the same
three outputs; there is no registry.

### Protocol (pure, `capture/protocol.py`)

A message is `[uint32 header length][uint32 payload length][JSON header][payload]`, little endian. Types: `hello`
(first message, carries the session token and the interface version), `state` (`starting`, `calibrating`, `live`,
`noface`), `frame` (header: sequence number, helper capture time, scores raw and calibrated, landmarks, matrix;
payload: optional preview RGB bytes with its width and height in the header), `error` (code, detail), `bye`.
The reader tolerates partial reads, rejects absurd lengths (a bound on header and payload), and ignores unknown
types so the interface can grow. Blender sends `config` (smooth, neutral seconds, gain, preview on or off) and `stop`.

### Helper lifecycle

Blender spawns `python capture_helper.py --port N --token T --camera I --model M ...` with a stdin pipe, stderr to a
temp file. The helper connects to `127.0.0.1:N`, sends `hello`, runs the camera loop, and exits when stdin reaches end
of file, when it receives `stop`, or on a fatal error after sending `error`. `Stop`: send `stop`, wait 1 s, terminate,
wait 2 s, kill. Blender also stops it on add-on unregister and on `bpy.app.handlers` quit and load events. One session
per Blender process; a second `Capture` says so.

### Blender side

A modal operator on a 60 Hz timer calls `Session.tick()`: read all pending bytes non-blocking, decode messages, update
state, apply the newest calibrated frame to the shape keys and head bone (the per-frame head rotation math of spec 002
is split out of `apply_head_pose` so the live drive and the bake use the same function), append raw samples to the
record buffer when armed, hand the newest preview frame to the overlay, and request a redraw. Applying to keys sets
values directly; it does not keyframe. `Stop` closes the session and, when a recording exists, runs the bake.

### Bake and post-processing

`post.py` holds the pure steps now in `video_to_csv.py` (`hold_gaps`, `calibrate`, `smooth`, `head_pose`) and a
`process(times, scores, matrices, options)` that returns the shape rows and the head rows. The video helper imports
it (the helper stays runnable on its own, so `post.py` is a plain module next to it, importable by path) and so does
the bake. Both then go through `mocap.apply_mocap` and `mocap.apply_head_pose`. Resampling to scene frames uses the
existing `frame_rows` rule. One `bpy.ops` undo push wraps the bake. `Save CSV` uses the existing writer; `Keep
capture file` writes the capture file (spec 003's landmark file at interface version 2, plus the head matrices).

### Preview overlay

`overlay.py`: a pure function maps normalized landmarks and the frame to quad and point coordinates inside a corner
rectangle of the 3D viewport region (UI units, aspect kept, optional mirror for selfie view). The draw handler
(`SpaceView3D`, POST_PIXEL) keeps the last frame as a `GPUTexture` created from the received RGB bytes, draws the
textured quad with the built-in image shader, and the points with the built-in uniform color shader. It never runs in
background mode. Capped at 15 Hz and 320 px wide by default. API names that differ between 4.4 and 5.2 are isolated
in this file and checked by the Blender suite's import smoke test and the manual checklist.

### Setup (`capture/setup.py`, replaces the system-Python lookup of the BodyForge installer for both modules)

1. `plan_text` lists: folder, Python used (Blender's), packages with pinned versions and approximate sizes,
   the face model (URL, 3.6 MB, SHA-256), `cv2-enumerate-cameras`, "no admin rights, nothing system-wide".
2. On `Install`: `python -m venv` with Blender's interpreter, then `pip install --only-binary=:all: -r
   requirements-mocap.txt` (pins), then the model download with checksum check (or the bundled model when the release
   zip carries it), run as a background job with progress, never blocking the UI.
3. `Install from folder`: the same with `--no-index --find-links DIR`.
4. A `Check helper` step runs `capture_helper.py --self-test` (imports, model loads, one synthetic frame) and shows the
   result. Preferences keep `python_path` and `model_path`, filled by the installer.

### Errors (`capture/errors.py`)

A fixed table: code, one-line message, a fix per OS (Windows: Settings, Privacy, Camera, allow desktop apps; macOS:
System Settings, Privacy and Security, Camera, enable Blender; Linux: add the user to the `video` group, check
`/dev/video*`; busy: close the other app). The helper maps OpenCV and MediaPipe failures to codes; Blender maps exits
and socket errors to the rest.

### Test matrix

| Area | Linux | Windows | macOS Apple Silicon (M1+) | How |
|---|---|---|---|---|
| Pure tests (protocol, post, errors, overlay projection, tracker contract grep) | CI | CI | CI | plain Python with numpy |
| Blender suite, fake sender, bake, undo, head bone, lifecycle (helper killed, Blender-side stop) | CI 4.4 + 5.2 | CI 4.4 + 5.2 | CI 5.2 (4.4 if a runner build exists) | `run_tests.py` |
| Helper env install from the pinned lock file, then the real helper on a synthetic video | CI | CI | CI | validates wheels and setup on each OS |
| Fake camera end to end (helper `--source file`, TCP, Blender, bake, compare with the video path, SC-004) | CI | CI | CI | no hardware |
| Error paths (no camera index, busy, corrupt model, helper exits, port busy, bad token) | CI | CI | CI | scripted |
| Real camera, preview, latency p95 | manual | manual | manual (Apple Silicon) | checklist below |
| macOS camera permission prompt for a helper started by Blender | n/a | n/a | manual, first check | unverified assumption |
| Offline after setup | CI (network off for the run step where the runner allows) | manual | manual | |
| No-Python machine | CI container without system Python | manual | manual | Blender's own interpreter |

Intel macOS is officially unsupported and is not in the matrix (no run, no CI job; the README says so).

Manual checklist per OS: list cameras, capture 5 minutes, unplug the camera, kill Blender during capture and look for a
leftover process and a lit camera, deny the permission, bake and compare with a video import, read the p95 latency
from the log.

## Risks

- macOS camera permission attribution and Blender's usage description: unverified, first manual check. If the prompt
  does not appear, the fix is to document granting the camera to Blender by hand in System Settings; if Blender
  cannot even be listed there, the alternative (a signed helper app) is out of scope and would be its own decision.
- Preview drawing cost and the `gpu` API differences between 4.4 and 5.2: contained in `overlay.py`; if a version
  cannot draw it, the preview is off and the capture still works.
- Latency on slow CPUs: the helper downsizes the tracking input and the preview; `Smooth` trades latency for jitter.
- Wheel availability changes: the lock file and CI install catch it before a release; the contract and the model
  checksum limit the blast radius.
- MediaPipe archived: contract, pins and the bundled model keep the add-on working; a second backend is a later spec.
- Scope: this is the largest spec so far; it is split into the phases in `tasks.md` so each ends in something that runs.

## Complexity Tracking

| Item | Why it is needed | Simpler option rejected |
|---|---|---|
| A local protocol with a token and framing | a preview frame does not fit UDP, and a localhost listener must not accept strangers | the existing UDP JSON (no preview, no auth) |
| `capture/` package with six small modules | each is pure and testable without Blender or a camera (Principle III) | one big file that needs Blender to test |
| Helper environment created by Blender's Python with a consent dialog | works with no system Python, offline afterwards, reproducible | bundling wheels (over 100 MB per platform) or asking users to run pip |
