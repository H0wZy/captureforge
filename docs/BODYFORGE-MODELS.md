# BodyForge models: sources, licenses and checksums

No model file is ever committed (`models/` and `*.task` are git-ignored). The one exception to "never shipped" is the
3.6 MB face model `face_landmarker.task`: from the release that carries the live capture panel, the release workflow
downloads it from the pinned URL below, checks the SHA-256 below and adds it to the extension zip together with the
Apache-2.0 text and an attribution note (Constitution v1.0.1; `specs/004-live-capture-panel`, task T026). The pose and hand
models stay downloads. **Install helper** downloads them
into the helper environment's `models` folder, only after the user confirms, from the URLs below, and checks the
SHA-256 listed here (`captureforge/body/helpers/setup_env.py` pins the same values).

| File | Size | Used for | URL | SHA-256 |
|---|---|---|---|---|
| `pose_landmarker_heavy.task` | 30.7 MB | default pose model | <https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task> | `64437af838a65d18e5ba7a0d39b465540069bc8aae8308de3e318aad31fcbc7b` |
| `pose_landmarker_lite.task` | 5.8 MB | automatic fallback when the heavy model is too slow | <https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task> | `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a` |
| `hand_landmarker.task` | 7.8 MB | optional, fingers and palm-driven forearm twist | <https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task> | `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1` |
| `face_landmarker.task` | 3.6 MB | FaceForge face model (BlazeFace + Face Mesh V2 + Blendshape V2 in one bundle); bundled in the release zip, the URL is for development installs | <https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task> | `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff` (3,758,596 bytes, recorded 2026-10-05; bundled in the release zip, see above) |

The URLs are the ones in Google's MediaPipe documentation ([pose landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker),
[hand landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker)), checked on
2026-10-03. They end in `latest`, so Google may replace the files; if a checksum stops matching, the download is
refused with the file name and the actual digest, and this table and `setup_env.py` are updated together after the new
model card is read.

## License status (Constitution V)

- **Software**: `mediapipe` and `opencv-contrib-python` are Apache-2.0, GPL-3.0-compatible, and run only in the helper process; the pinned versions and the other packages are listed in `THIRD_PARTY_NOTICES.md` and `captureforge/helper-requirements.txt`.
- **Model files**: all MediaPipe weights used here are Apache-2.0. Verified 2026-10-04 on the Google model cards, whose
  "Licensed under" field reads "Apache License, Version 2.0" for each of them: pose landmarker lite/full/heavy
  ([BlazePose GHUM 3D](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf)),
  hand landmarker ([Hand Tracking](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20(Lite_Full)%20with%20Fairness%20Oct%202021.pdf)),
  and the three models inside `face_landmarker.task`
  ([BlazeFace short range](https://storage.googleapis.com/mediapipe-assets/MediaPipe%20BlazeFace%20Model%20Card%20(Short%20Range).pdf),
  [Face Mesh V2](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf),
  [Blendshape V2](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Blendshape%20V2.pdf)). The
  documentation pages themselves are CC BY 4.0 (text) and Apache-2.0 (code samples) and do not state the weight
  license; the cards do. The cards also say the models do no recognition or identification. No SMPL, SMPL-X, AMASS or
  other non-commercial weight is used or required by the default path. Full research: `docs/pt-BR/BODYFORGE-T051-LICENCA.md`.
- **Default path rule**: nothing in the add-on needs a non-commercial or research-only model; an optional SMPL-based
  importer would be a user-installed add-on with a license warning (not part of v1).

Privacy: model downloads are the only network access BodyForge makes, only on the user's click, and the destination is
shown first. No telemetry.
