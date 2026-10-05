# Tasks: Live capture inside Blender

**Input**: `specs/004-live-capture-panel/` (spec.md, plan.md, research.md)

**Tests**: REQUIRED (Constitution III): each test task comes first and MUST be seen failing before its implementation task. Pure tests: `python tests/test_capture_*.py`; Blender tests join `tests/run_tests.py`.

**Format**: `[ID] [P?] [Story] Description`; `[P]` = different files, no dependency on an unfinished task. Paths relative to the repository root.

## Phase 0: Gates (throwaway spikes, not committed)

- [ ] T001 Spike on real hardware, one machine per OS: camera, MediaPipe LIVE_STREAM, loopback TCP, a draw handler with a `GPUTexture` on Blender 4.4 and 5.2; measure p95 latency from frame capture to key update and the Blender UI frame rate. Go/no-go for SC-002; the numbers go into `research.md`
- [ ] T002 Spike: macOS camera permission for a helper started by Blender (does the prompt appear, for which process); Linux `video` group message; Windows privacy toggle. Record in `research.md`
- [x] T003 Maintainer decisions recorded (2026-10-05): the face model is bundled through CI (constitution v1.0.1, `docs/BODYFORGE-MODELS.md` and `THIRD_PARTY_NOTICES.md` updated), Intel macOS is officially unsupported (README en and pt-BR, spec test matrix)

## Phase 1: Tracker contract and shared post-processing (US2, US4, FR-004)

- [x] T004 [P] Tests `tests/test_capture_post.py`: `post.process` equals the current `video_to_csv` steps on the same arrays (golden values from the current functions), including head pose
- [x] T005 [P] Test `tests/test_capture_contract.py`: only `helpers/tracker.py` imports `mediapipe` (a grep over the package); `Result` shapes and `None` handling with a stub tracker
- [x] T006 Move the pure steps to `captureforge/face/capture/post.py` (importable by path from the helper), make `video_to_csv.py` use it; existing tests stay green
- [x] T007 Implement `captureforge/face/helpers/tracker.py` (open, process, close; image, video and live-stream constructors) and move `video_to_csv.detect`, `webcam_stream.py`, `face_landmarks.py` behind it; write `docs/TRACKER-CONTRACT.md`

## Phase 2: Protocol and helper (US1, FR-002, FR-003)

- [x] T008 [P] Tests `tests/test_capture_protocol.py`: encode and decode round trip, partial reads byte by byte, oversized header or payload rejected, unknown type ignored, wrong token refused, interface version mismatch reported
- [x] T009 Implement `captureforge/face/capture/protocol.py`
- [ ] T010 [P] Tests `tests/test_capture_helper.py`: with the fake camera (`--source file` or synthetic frames) the helper connects, says hello, streams states and frames, exits on stdin end of file within 2 s, on `stop`, and on a fatal error after an `error` message; `--list-cameras` prints valid JSON; `--self-test` passes with a stub tracker
- [ ] T011 Implement `captureforge/face/helpers/capture_helper.py` (camera loop with downsizing, calibration like `Stream`, preview frames capped at 15 Hz, stdin watchdog, camera listing with the optional `cv2-enumerate-cameras`, error codes)
- [ ] T012 [P] Tests `tests/test_capture_errors.py`: every code of FR-012 has a message and a fix per OS; helper exit and socket errors map to codes
- [ ] T013 Implement `captureforge/face/capture/errors.py`

## Phase 3: Blender session, live drive, record and bake (US1)

- [ ] T014 Refactor (tests first): split the per-frame head rotation of `mocap.apply_head_pose` into a function the live drive and the bake share; the spec 002 tests stay green
- [ ] T015 Blender tests in `tests/run_tests.py` with a fake sender thread: `Session` states, live drive of shape keys and head bone, a second `Capture` refused, the helper killed mid-capture keeps the recorded part and reports `helper_crashed`, `Stop` leaves no process and no timer
- [ ] T016 Implement `captureforge/face/capture/session.py` (spawn with stdin pipe and stderr file, non-blocking socket, state machine, record buffer, stop sequence, quit and unregister hooks)
- [ ] T017 Blender tests: record then stop bakes one undo step into `<target>_facemocap` and the head bone, starting at the chosen frame; equals a `Video to face` import of the same fake footage within 0.02 RMS (SC-004); `Save CSV` and `Keep capture file` write what they say and nothing is written otherwise (FR-015)
- [ ] T018 Implement the bake in `session.py` using `post.process`, `mocap.apply_mocap`, `mocap.apply_head_pose`, the CSV writer and the capture file writer (interface version 2, a superset of spec 003's file)

## Phase 4: Preview overlay (US1)

- [ ] T019 [P] Tests `tests/test_capture_overlay.py`: the landmark-to-overlay projection (aspect, mirror, corner placement, UI scale), no division by zero on an empty frame
- [ ] T020 Implement `captureforge/face/capture/overlay.py` (pure projection, the `SpaceView3D` handler, `GPUTexture` upload, points); import smoke test in the Blender suite (including background mode, where it must be a no-op)

## Phase 5: Setup and panel (US3, US2)

- [ ] T021 [P] Tests `tests/test_capture_setup.py`: `plan_text` lists packages, versions, sizes, sources, folder and the model checksum; nothing runs without confirmation; the pip command line uses `--only-binary=:all:` and the pins; the folder install uses `--no-index --find-links`; the checksum mismatch path deletes the partial file
- [ ] T022 Implement `captureforge/face/capture/setup.py` (venv by Blender's interpreter with a system Python fallback, pins from `requirements-mocap.txt`, model download or bundled model, `--self-test` check, background job with progress); pin `requirements-mocap.txt`; record the face model SHA-256 in `docs/BODYFORGE-MODELS.md` and `THIRD_PARTY_NOTICES.md` (add numpy and `cv2-enumerate-cameras`)
- [ ] T023 Blender tests: settings, operators (`capture`, `stop`, `record`, `refresh_cameras`, `install_helper`, `import_video`, `delete_capture_file`), the panel draws in background mode without errors, `Import video` goes through the same bake
- [ ] T024 Implement the panel and operators in `captureforge/face/ui.py` and `ops.py`; `camera` permission in `blender_manifest.toml` (`extension validate` stays green); mark `4c. Live webcam` as advanced

## Phase 6: CI matrix and the model in the zip (FR-016, FR-013)

- [ ] T025 CI: pure and Blender suites on Ubuntu, Windows and macOS runners; a job per OS that installs the helper environment from the pinned lock file and runs the real helper on a synthetic video; a Linux job without a system Python
- [ ] T026 CI release step in `.github/workflows/ci.yml`: download `face_landmarker.task` from the pinned `float16/1` URL, check SHA-256 `64184e22...c9ff` (3,758,596 bytes), copy it with `licenses/Apache-2.0.txt` into the extension source before `extension build`, and fail the release on a mismatch; a test checks that the add-on finds the bundled model first and falls back to the installer's download; the repository still never holds the file

## Phase 7: Docs and checks

- [ ] T027 [P] README.md, README.pt-BR.md and `docs/pt-BR/CAPTURA-AO-VIVO.md`: setup dialog, panel, camera list, preview, record and bake, failure messages with the per-OS fix, privacy note, supported platforms and the macOS Intel gap
- [ ] T028 Run the manual checklist of the plan on each OS with a real camera; record results (latency p95, leftover process check, permission behavior) in `research.md`
- [ ] T029 Run every suite (spec 001 to 003 included) and the extension validation on Blender 4.4 and 5.2

## Later specs that build on this one (not tasks here)

Anchor frames and refine (research idea 2); character-fitted weights (spec 003) reading the capture file; a second tracking backend behind the contract; Android and iOS capture sending the same CSV contract.

## Dependencies

T001 to T003 gate Phases 3 to 6. Phase 1 first (the shared steps and the contract), then Phase 2 (T008 to T013 in parallel where marked), then Phase 3 (T014 before T015, T015 before T016, T017 before T018), Phase 4 and Phase 5 can run in parallel after T016, Phase 6 after T022, docs and checks last. T026 depends on T022 (the model lookup order) and needs the constitution amendment approved.

## Estimate

About 1,800 lines of code, 1,500 of tests, a CI change and docs: more than a week of focused work, with three checks that need real hardware. Not started in this branch; this branch ends at tasks.
