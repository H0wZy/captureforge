# BodyForge models: sources, licenses and checksums

BodyForge never ships or commits model files (`models/` and `*.task` are git-ignored). **Install helper** downloads them
into the helper environment's `models` folder, only after the user confirms, from the URLs below, and checks the
SHA-256 listed here (`captureforge/body/helpers/setup_env.py` pins the same values).

| File | Size | Used for | URL | SHA-256 |
|---|---|---|---|---|
| `pose_landmarker_heavy.task` | 30.7 MB | default pose model | <https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task> | `64437af838a65d18e5ba7a0d39b465540069bc8aae8308de3e318aad31fcbc7b` |
| `pose_landmarker_lite.task` | 5.8 MB | automatic fallback when the heavy model is too slow | <https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task> | `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a` |
| `hand_landmarker.task` | 7.8 MB | optional, fingers and palm-driven forearm twist | <https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task> | `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1` |

The URLs are the ones in Google's MediaPipe documentation ([pose landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker),
[hand landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker)), checked on
2026-10-03. They end in `latest`, so Google may replace the files; if a checksum stops matching, the download is
refused with the file name and the actual digest, and this table and `setup_env.py` are updated together after the new
model card is read.

## License status (Constitution V)

- **Software**: `mediapipe` and `opencv-python` are Apache-2.0, GPL-3.0-compatible, and run only in the helper process.
- **Model files**: MediaPipe is an Apache-2.0 project and its model pages list these files as the stock models of
  the Pose and Hand Landmarker tasks. Model cards:
  [BlazePose GHUM 3D](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf),
  [Hand Tracking](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20(Lite_Full)%20with%20Fairness%20Oct%202021.pdf).
  **Open verification item (research item 1):** the documentation page states Creative Commons Attribution 4.0 for its
  text and Apache 2.0 for its code samples, and does not itself state the license of the weight files; the model-card
  PDFs could not be machine-read during the automated check (they are image or font-encoded). Several secondary sources
  report Apache 2.0 for the models, but the maintainer should read the two PDFs once and record the wording here
  before the first release that points users at these URLs. No SMPL, SMPL-X, AMASS or other non-commercial weight is
  used or required by the default path.
- **Default path rule**: nothing in the add-on needs a non-commercial or research-only model; an optional SMPL-based
  importer would be a user-installed add-on with a license warning (not part of v1).

Privacy: model downloads are the only network access BodyForge makes, only on the user's click, and the destination is
shown first. No telemetry.
