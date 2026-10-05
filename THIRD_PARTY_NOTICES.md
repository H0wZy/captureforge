# Third-party notices

CaptureForge itself is GPL-3.0-or-later (see `LICENSE`). The software components below are installed by the user
into the helper environment, on the user's confirmation, and are not part of the CaptureForge distribution. Of the models,
only the Face Landmarker file `face_landmarker.task` is included in the release zip (added by the release workflow from
the pinned URL and SHA-256 listed in `docs/BODYFORGE-MODELS.md`); the others are downloaded by the user. All are under the Apache License, Version 2.0 (<https://www.apache.org/licenses/LICENSE-2.0>), which is compatible with
GPL-3.0. Checked 2026-10-04; details in `docs/BODYFORGE-MODELS.md`.

## Software

| Component | License | Source |
|---|---|---|
| `mediapipe` | Apache-2.0 | <https://github.com/google-ai-edge/mediapipe> |
| `opencv-python` | Apache-2.0 (the wheel also bundles third-party libraries under their own licenses, see the package) | <https://github.com/opencv/opencv-python> |

## Models (downloaded by the user; the face model is also bundled in the release zip)

| Model (file) | License | Source (model card) |
|---|---|---|
| BlazePose GHUM 3D, lite, full and heavy (`pose_landmarker_lite.task`, `pose_landmarker_full.task`, `pose_landmarker_heavy.task`) | Apache-2.0 | <https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf> |
| Hand landmarker, Hand Tracking lite/full (`hand_landmarker.task`) | Apache-2.0 | <https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20(Lite_Full)%20with%20Fairness%20Oct%202021.pdf> |
| BlazeFace short range, inside `face_landmarker.task` | Apache-2.0 | <https://storage.googleapis.com/mediapipe-assets/MediaPipe%20BlazeFace%20Model%20Card%20(Short%20Range).pdf> |
| Face Mesh V2, inside `face_landmarker.task` | Apache-2.0 | <https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf> |
| Blendshape V2, inside `face_landmarker.task` | Apache-2.0 | <https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Blendshape%20V2.pdf> |

Model files come from `https://storage.googleapis.com/mediapipe-models/`. The release zip carries
`face_landmarker.task` (BlazeFace short range, Face Mesh V2 and Blendshape V2, copyright Google LLC, Apache-2.0, unmodified)
and the Apache-2.0 text (`licenses/Apache-2.0.txt`) next to `LICENSE`; the file has no NOTICE of its own. If another
model is ever bundled, the same applies to it.
