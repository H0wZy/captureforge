# Implementation Plan: FaceForge head pose from the video

**Branch**: `002-face-head-pose` | **Date**: 2026-10-05 | **Spec**: [spec.md](spec.md)

## Summary

The video helper asks MediaPipe for `facial_transformation_matrixes`, turns each matrix into neutral-relative,
unbroken, smoothed Euler angles (and a translation) with pure-Python math, and appends them to the CSV as
`headRot*` / `headPos*`. The Blender importer reads those columns and keys one head bone (and an optional neck
share) in the armature's action. No new dependency, no new file in the add-on: three existing files grow.

## Technical Context

- Language: Python 3.11+ (helper: stdlib only for the math, so the unit test runs without numpy); Blender 4.4 and 5.2 (`mathutils`, numpy in the importer).
- Interface: the CSV (backward compatible: extra optional columns; readers that ignore unknown names keep working).
- Testing: `tests/test_video_to_csv.py` (pure) and `tests/run_tests.py` (headless Blender); the real-MediaPipe run is the manual check on a real video.
- Constraint: the matrix convention (OpenGL camera, right-handed, X right, Y up, Z toward the viewer) is MediaPipe's documented face geometry; a frontal face is the identity, which the real-video check confirms (translation Z negative).

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Clean room | Pass | Math from textbooks (rotation matrix to Euler); the idea of an Euler unbreak step is credited to the research note and rewritten, nothing copied from KeenTools. |
| II. Blender API only inside the extension, ML outside | Pass | The matrix is read in `helpers/video_to_csv.py`; Blender only reads the CSV. |
| III. Headless-testable, test first | Pass | Failing tests first (T001, T003); math is pure; the importer core takes explicit objects. |
| IV. CI green on 4.4 and 5.2 | Pass | New tests join the existing steps; only API already used by the importer is called (`fcurve_ensure_for_datablock`). |
| V. GPL-compatible dependencies | Pass | None added. |
| VI. Privacy | Pass | Tests use synthetic matrices; no capture committed; docs have no personal paths. |
| VII. English first, pt-BR for users | Pass | README and README.pt-BR in the same change. |
| VIII. Lean code | Pass | One helper file and `mocap.py` grow; settings join the existing `PropertyGroup`; no new class. |
| IX. Android friendly | Pass | Same phone video as before. |
| X. Semantic versioning | Pass | Additive CSV and settings; no version bump in this change. |

## Project Structure

```text
specs/002-face-head-pose/        spec.md, plan.md, tasks.md
captureforge/face/helpers/video_to_csv.py   matrix math, calibration, CSV columns, --no-head-pose
captureforge/face/mocap.py       read_head_pose, apply_head_pose (mathutils)
captureforge/face/video.py       passes the switch to the helper
captureforge/face/ops.py, ui.py  import with the head options
tests/test_video_to_csv.py       pure math tests
tests/run_tests.py               headless Blender tests (axis check, gain, neck, off, old CSV)
README.md, README.pt-BR.md       docs
```

## Design notes

- `R_rel = R_neutral^T * R_frame` in the head frame; Euler order `Ry * Rx * Rz`.
- Blender: face frame to armature space is `M = Rx(+90 deg)` (x, y, z) -> (x, -z, y). For a bone with rest orientation `H`, the pose rotation is `P = H^T * (M R M^T) * H`. With a neck share `s` the neck gets `slerp(identity, q, s)` and the head the remainder, so the sum is exact whatever the rolls.
- Keys follow the bone's rotation mode; the armature's own action is reused so other bones keep their animation.

## Complexity Tracking

No violations.
