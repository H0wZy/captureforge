# Tasks: FaceForge head pose from the video

**Tests**: REQUIRED (Constitution III): each test task is written first and seen failing.

## Phase 1: Pure math (helper)

- [x] T001 [US1] Tests in `tests/test_video_to_csv.py`: orthonormalize (with scale), matrix to Euler round trip, `unbreak`, neutral-relative calibration, CSV with and without head columns, reader ignores head columns as shapes
- [x] T002 [US1] Implement `orthonormalize`, `matrix_to_euler`, `unbreak`, `head_pose_rows` (hold, calibrate, unbreak, smooth) and the CSV columns in `captureforge/face/helpers/video_to_csv.py`; `--no-head-pose`; request the matrix from MediaPipe

## Phase 2: Blender importer

- [x] T003 [US1] Headless tests in `tests/run_tests.py`: `read_head_pose` (new and old CSV), yaw 30 degrees checked in world space, Euler and Quaternion bones, existing animation kept
- [x] T004 [US1] Implement `read_head_pose` and `apply_head_pose` in `captureforge/face/mocap.py`
- [x] T005 [US2] Tests: gain 0.5, neck share 0.3 (neck plus head equal the full rotation), switch off, missing bone message
- [x] T006 [US2] Settings in `ui.py` (`head_*` properties and the panel box), call from the import operators in `ops.py` (no plumbing in `video.py`: the helper always writes the columns, the importer switch decides)

## Phase 3: Docs and checks

- [x] T007 README.md and README.pt-BR.md: CSV columns, options, known limit removed, roadmap line removed
- [ ] T008 Run the whole test suite (pure and Blender 5.2) and the real-MediaPipe run on a real video (not committed)
