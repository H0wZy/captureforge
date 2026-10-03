# Data Model: BodyForge v1

All arrays are numpy, dtype float32 unless stated. `n` is the frame count. Conventions: right-handed, meters,
**+Y up, +Z toward the camera** inside the landmark file; the solver converts to Blender (+Z up, -Y forward)
in one place (`solve.py`). Bone names are the Mixamo names without the `mixamorig:` prefix inside the code.

## LandmarkFile (`landmarks.npz`, see contracts/landmarks-file.md)

| Field | Shape | Meaning |
|---|---|---|
| `version` | scalar int | interface version (1) |
| `times` | (n,) float64 | seconds from the first frame, from the video's real timestamps |
| `fps_source` | scalar float | nominal frame rate of the file |
| `size` | (2,) int | frame width and height after rotation metadata is applied |
| `pose_world` | (n, 33, 3) | MediaPipe world landmarks (meters, origin at the hips) |
| `pose_image` | (n, 33, 3) | normalized image landmarks (x, y in 0..1, z relative depth) |
| `pose_vis` | (n, 33) | visibility 0..1 per point; 0 with NaN points when no person was found |
| `hands_world` | (n, 2, 21, 3) | optional; index 0 = left hand, 1 = right hand; NaN when absent |
| `hands_vis` | (n, 2) | optional; 1 if that hand was detected in the frame |
| `head_box` | (n, 4) | optional; x0, y0, x1, y1 normalized, for the face crop (user story 6) |
| `meta` | JSON string | model name and hash, helper version, per-run options, warnings |

Validation rules: finite `times`, strictly increasing; `n >= 2`; shapes agree; `version` known; points outside
0..1 in `pose_image` are allowed (limb outside the frame) but flagged.

## Calibration

| Field | Meaning |
|---|---|
| `bone_len` | dict bone name to length in meters, measured on the neutral window |
| `up` | (3,) unit vector pointing up in landmark space |
| `facing` | (3,) unit vector the person faces in the neutral pose |
| `floor_y` | floor height along `up`, from the lowest heel and toe in the window |
| `window` | (start, end) frame indices used; `source` = `neutral` or `rig_default` |
| `warnings` | list of strings (no stable window, body cut off, and so on) |

## BodyProfile (`profile.py`)

- `BONES`: ordered tuple of the Mixamo/Unity bones (Hips, Spine, Spine1, Spine2, Neck, Head, Left/Right Shoulder,
  Arm, ForeArm, Hand, UpLeg, Leg, Foot, ToeBase; finger bones optional) with `parent` and `required` (the 15
  required humanoid bones are flagged).
- `LANDMARK_MAP`: bone to (landmark index from, landmark index to) for the swing direction.
- `TWIST_REF`: bone to the landmark triple that defines the twist.
- `LIMITS`: bone to (min, max) Euler range in the bone's rest frame, used for clamping and for the violation metric.
- `normalise(name)`: strips `mixamorig:` and a numeric suffix; `validate(bone_names)` returns (missing, extra).

## MotionClip

| Field | Shape | Meaning |
|---|---|---|
| `fps` | float | output frame rate (scene rate, or the source rate on request) |
| `times` | (m,) | seconds, uniform at `fps` |
| `rot` | (m, B, 4) | local quaternions (w, x, y, z), sign-continuous, per bone in `BONES` order |
| `hips_pos` | (m, 3) | hips position in rig space (height and sway; horizontal drift removed when in place) |
| `contact` | (m, 2) bool | planted flags for left and right foot |
| `conf` | (m, B) | confidence per bone from the landmark visibility (drives hold and blend) |
| `flags` | dict | `in_place`, `looped`, `mirrored`, `lock_left`, `lock_right`, `fingers` |

State transitions: `raw` (solver output) to `cleaned` (smoothing, foot lock) to `edited` (in place, trim, loop,
mirror) to `exported`. Each clip operation returns a new MotionClip; the Blender action is rewritten from it, so
every step can be re-run from the raw clip stored in a custom property on the action.

## QualityReport

| Field | Meaning |
|---|---|
| `skate_cm_s` | per foot, mean horizontal speed during planted frames |
| `bone_drift` | per bone, max relative length change versus calibration |
| `limit_violations` | per bone, count of frames outside `LIMITS` |
| `jitter` | mean absolute second difference of rotations (a single number, lower is better) |
| `low_conf_ranges` | list of (start, end, bone group) with confidence under threshold |
| `warnings` | capture warnings (fps, framing, several people) |

Written as `report.json` and a short text; `filmstrip.png` is a grid of evenly spaced rendered frames.

## ReferenceArmature

A T-pose armature with the Mixamo bone names, built by `rigtools.create_reference_armature()`: used by tests, by
users without a rig, and as the rest-pose reference for the solver. Profile validation compares a user armature to it
(names, hierarchy, rest orientations within a tolerance).

## Settings (`Scene.bodyforge`, one `PropertyGroup`)

`video_path`, `landmarks_path`, `armature` (pointer), `use_hands`, `neutral_seconds`, `keep_source_fps`,
`in_place`, `smooth_mode` (preview/final), `smooth_strength`, `foot_lock_left`, `foot_lock_right`, `loop_blend_frames`,
`trim_start`, `trim_end`, `mirror`, `export_path`. Preferences (shared, `prefs.py`): `python`, `face_model`,
`pose_model`, `hand_model`.
