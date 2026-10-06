# Implementation Plan: BodyForge v1, markerless body mocap from phone video

**Branch**: `001-bodyforge-v1` | **Date**: 2026-10-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-bodyforge-v1/spec.md`

## Summary

BodyForge adds a `captureforge/body/` module next to FaceForge. A helper process, run in the shared venv
(MediaPipe Pose and optional Hands), turns a video into a documented `landmarks.npz`. Everything after that is
pure Python plus numpy inside the add-on: calibrate from a neutral pose, solve bone rotations for a fixed
Mixamo/Unity Humanoid profile, clean up (One Euro for preview, zero-phase Butterworth for the final clip, heuristic
foot contact and lock, in place, trim, loop closer, mirror), report quality metrics and a filmstrip, and export an
FBX with a validated Unity preset. Hands curl and twist are an optional layer. Body plus face from one video reuses
the FaceForge video helper on a head crop. The module delivers flow, clean-up and the preset; it does not build a
new estimator (see `docs/pt-BR/BODYFORGE-RESEARCH.md`, sections 0 and 5).

## Technical Context

**Language/Version**: Python as bundled with Blender (3.11 on 4.4, 3.13 on 5.x); the helper uses its own venv with
any Python 3.10 to 3.12 that MediaPipe supports.

**Primary Dependencies**: inside Blender, `bpy`, `mathutils`, numpy (bundled), nothing else. In the helper venv,
`mediapipe` (Apache-2.0), `opencv-python` (Apache-2.0), numpy; all GPL-3.0-compatible. Pose and hand model files
are downloaded by the user, never committed.

**Storage**: files only: `landmarks.npz` (helper output, see [contracts/landmarks-file.md](contracts/landmarks-file.md)),
`report.json` and `filmstrip.png` next to it, the Blender action itself, and the FBX.

**Testing**: plain `tests/test_body_*.py` (pure numpy, run in the CI unit stage with numpy installed there as a
dev-only step) and `tests/run_body_tests.py` (headless Blender, run on 4.4 and 5.2). Fixtures are synthetic skeleton
motions generated in code (hands up, planted foot, jitter, loop), never real captures. Every test is seen failing
first (Constitution III).

**Target Platform**: Windows 11 first (reference: RTX 3050 laptop); Linux and macOS best effort because the helper
is plain Python. Blender 4.4 LTS and 5.2.

**Project Type**: Blender extension module (library plus operators plus panel) with one external helper script.

**Performance Goals**: 10 s at 30 fps from video to animated rig in under 3 minutes on the reference laptop
(SC-006), with the pose model on CPU or GPU; solve and clean-up of that clip in under 5 s inside Blender.

**Constraints**: no non-commercial weights in the default path; no network access except explicit user actions
(model download, helper install) with the destination shown; the add-on loads and stays usable when the helper
is missing; no telemetry; no real-person data in the repo.

**Scale/Scope**: one person, one fixed camera, clips from 2 to 60 s, one target profile (Mixamo/Unity Humanoid).
About 14 small modules, each under 300 lines.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Clean room | Pass | Only public docs and permissively licensed or GPL ideas; credits go in code comments (One Euro: Casiez et al.; Butterworth: standard filter; Kovar et al. foot-skate clean-up as an idea). Nothing copied from paid tools; BlendArMocap, KeeMap and mixamo-llm-mocap were read as ideas only and are cited, not copied. |
| II. Blender API only inside the extension, ML outside | Pass | MediaPipe and OpenCV live only in `body/helpers/`, run by subprocess in the shared venv; the interface is `landmarks.npz`. A missing helper gives a message and nothing else breaks. |
| III. Headless-testable, test first | Pass | Core modules take arrays and objects, never `bpy.context`; operators are thin; pure parts are tested without Blender. Test tasks precede implementation tasks. |
| IV. CI green on 4.4 and 5.2 | Pass | New `run_body_tests.py` step added to the existing matrix; FBX read-back runs on both lines. |
| V. GPL-compatible dependencies, no NC weights | Pass | MediaPipe, OpenCV, numpy only. SMPL and similar are out of scope; the optional importer is a v2 item and would carry a license warning. The pose model card license is confirmed and recorded in `docs/` before the model URL ships (research note: not verified). |
| VI. Privacy and responsible use | Pass | Synthetic fixtures only; POLICY.md is linked from the panel and the recording guide; no capture of a real person is committed. |
| VII. English first, pt-BR for users | Pass | Code and specs in English; README and README.pt-BR get a BodyForge section in the same PR; the recording guide ships in both languages. |
| VIII. Lean code | Pass, two entries in Complexity Tracking | Python, bpy, numpy only; each module self-contained, settings in one `PropertyGroup`, shared sidebar tab. No `holes_fill` or `edgenet_fill`. |
| IX. Android and no-iPhone friendly | Pass | Any video file; guidance written around an Android phone; nothing needs TrueDepth or LiDAR. |
| X. Semantic versioning, release on tag | Pass | Adds a module and a helper interface; the manifest goes to 0.2.0 at release; the interface version is stored in the landmark file. |

Post-design re-check: still Pass after Phase 1; see Complexity Tracking for the two justified items.

## Project Structure

### Documentation (this feature)

```text
specs/001-bodyforge-v1/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── landmarks-file.md
│   ├── helper-cli.md
│   └── unity-export-preset.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
captureforge/
├── __init__.py                 # registers face and body
├── prefs.py                    # NEW: single AddonPreferences (python, face model, body models)
├── face/                       # existing; its preferences class moves to prefs.py (property names unchanged)
└── body/                       # NEW
    ├── __init__.py             # register/unregister, Scene.bodyforge PointerProperty
    ├── landmarks.py            # read/validate landmarks.npz, hold gaps, resample to scene fps (pure numpy)
    ├── profile.py              # Mixamo/Unity profile: bone map, rest axes, joint limits, name normalising (pure)
    ├── calibrate.py            # bone lengths, up vector, floor, facing from the neutral pose (pure)
    ├── solve.py                # positions to local rotations, hips height/sway, optional fingers (pure)
    ├── filters.py              # One Euro, zero-phase Butterworth (biquad forward-backward), quaternion smoothing (pure)
    ├── contact.py              # foot contact detection and foot lock (pure)
    ├── clipops.py              # in place, trim, loop closer, mirror (pure, on rotation arrays)
    ├── report.py               # metrics, report json and text (pure)
    ├── rigtools.py             # reference armature builder, profile validation against a real armature (bpy)
    ├── apply.py                # writes and reads the action on the armature, filmstrip render (bpy)
    ├── export.py               # FBX preset and read-back check (bpy)
    ├── video.py                # subprocess runner for the helper, setup text (no bpy)
    ├── ops.py                  # thin operators bodyforge.*
    ├── ui.py                   # PropertyGroup and panel in the shared CaptureForge tab
    └── helpers/
        ├── pose_to_landmarks.py   # MediaPipe Pose (+Hands) -> landmarks.npz (runs in the venv)
        └── setup_env.py           # creates the shared venv, installs wheels, downloads models after consent

tests/
├── fixtures_body.py            # synthetic motions (hands up, planted foot, jitter, loop, hands open/closed)
├── test_body_landmarks.py      # pure: format, gaps, resample, orientation
├── test_body_solve.py          # pure: calibrate, profile, solve on synthetic skeletons
├── test_body_cleanup.py        # pure: filters, contact, clip ops, report
├── test_body_helper.py         # pure: helper CLI arguments and landmark writer without mediapipe
└── run_body_tests.py           # headless Blender: armature, apply, validation, FBX read-back, operators

docs/
├── BODYFORGE-RECORDING.md      # how to film the four clips (+ docs/pt-BR/BODYFORGE-RECORDING.md)
└── pt-BR/BODYFORGE-RESEARCH.md # existing
```

**Structure Decision**: a self-contained `captureforge/body/` package that mirrors `captureforge/face/`
(pure core, thin `ops.py`, one `ui.py`, helper scripts in `helpers/`). Pure modules import only numpy so the CI
unit stage can run them without Blender. The helper is a separate script run by a subprocess, the same pattern as
FaceForge's `video.py`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| `captureforge/prefs.py`: one shared `AddonPreferences` for the whole suite (touches `face/ui.py`) | Blender allows exactly one `AddonPreferences` per add-on id; BodyForge needs its own model paths and both modules share one venv (spec Clarifications) | A second class cannot register under the same id; a duplicate venv per module doubles the install and breaks "Install helper" for non-terminal users |
| numpy installed in the CI unit stage (dev-only) | Pure body tests use numpy arrays; the ubuntu runner's Python has none | Mocking numpy in tests would hide real array bugs; running everything inside Blender would slow the fast stage and break the "pure tests need no Blender" rule |
