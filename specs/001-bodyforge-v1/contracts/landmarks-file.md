# Contract: `landmarks.npz` (helper to add-on)

The only data interface between the helper process (MediaPipe, OpenCV) and the add-on. The add-on never imports the
estimator; the helper never imports `bpy`. Interface version: **1**. A change that breaks readers bumps `version`
and is a MAJOR (MINOR below 1.0) change per Constitution X.

Written with `numpy.savez_compressed`; read with `numpy.load(..., allow_pickle=False)` (no pickled objects).

## Arrays

| Key | Type and shape | Required | Notes |
|---|---|---|---|
| `version` | int scalar | yes | must be `1` |
| `times` | float64 (n,) | yes | seconds from the first frame, strictly increasing, from the file's real timestamps (variable frame rate is preserved) |
| `fps_source` | float scalar | yes | nominal frame rate reported by the container |
| `size` | int (2,) | yes | width, height after the rotation metadata is applied |
| `pose_world` | float32 (n, 33, 3) | yes | metric landmarks, origin at the hips. **The helper converts MediaPipe's native axes to +X right, +Y up, +Z toward the camera**, so no reader depends on MediaPipe conventions. NaN for frames with no person |
| `pose_image` | float32 (n, 33, 3) | yes | normalized image coordinates (x right, y down, 0..1) and relative depth; NaN for no person |
| `pose_vis` | float32 (n, 33) | yes | visibility 0..1; 0 for no person |
| `hands_world` | float32 (n, 2, 21, 3) | no | index 0 = the person's left hand, 1 = right; same axis convention; NaN when absent |
| `hands_vis` | float32 (n, 2) | no | 1 when detected, else 0 |
| `head_box` | float32 (n, 4) | no | x0, y0, x1, y1 normalized, margin included; for the face crop |
| `meta` | str scalar (JSON) | yes | see below |

`meta` JSON keys: `helper_version`, `model` (file name), `model_sha256`, `model_variant` (`heavy` or `lite`),
`hands` (bool), `people_seen` (max people detected in one frame), `frames_without_person` (int), `rotation_applied`
(degrees), `warnings` (list of strings).

## Reader rules (`landmarks.read`)

1. Reject a missing required key, an unknown `version`, shapes that disagree on `n`, or `n < 2` with a `ValueError`
   whose message names the problem.
2. Treat NaN rows as "no person": the reader fills them by holding the last good frame (leading gap: the first good
   frame) and reports the gap ranges; raises if there is no good frame at all.
3. Resample to a uniform grid at the target frame rate by linear interpolation on `times` (keep the source rate on
   request); never trust `fps_source` over `times`.

## Compatibility

Other producers (a future RTMW helper, a Pose2Sim importer) MUST write the same schema; extra keys are ignored by
readers. The 33-point order is MediaPipe Pose's, documented in `body/profile.py`.
