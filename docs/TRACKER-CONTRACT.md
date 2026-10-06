# Tracker contract

FaceForge talks to its face tracker through one file: `captureforge/face/helpers/tracker.py`. It is the only module
that imports MediaPipe (a test, `tests/test_capture_contract.py`, greps for it). Every helper that tracks a face goes
through it: `video_to_csv.py` (video files), `face_landmarks.py` (the auto rig fit render), `webcam_stream.py` (the
UDP live mode) and the live capture helper. If MediaPipe is ever archived or changes its API, a different backend
replaces this one file; nothing else changes. There is no registry and no plugin loader.

The tracker runs in the helper's own Python (a venv), never inside Blender (Constitution, principle II).

## Interface

```python
from tracker import Tracker, TrackerError

with Tracker.video(model_path) as t:        # or Tracker.image(model_path), Tracker.live(model_path)
    result = t.process(frame_rgb, timestamp_ms)
```

| Mode | `process` returns | Timestamps |
|---|---|---|
| `image` | the result of this frame | ignored |
| `video` | the result of this frame | strictly increasing, in ms |
| `live` | the newest finished result, which may belong to an earlier frame (see `result.timestamp_ms`), or `None` before the first one | strictly increasing, in ms |

### Input

- `frame_rgb`: `uint8` array, height x width x 3, **RGB** (OpenCV reads BGR: convert first).
- `timestamp_ms`: integer milliseconds.

### Output: `Result`

| Field | Type | Meaning |
|---|---|---|
| `timestamp_ms` | `int` | the frame this result belongs to |
| `scores` | `dict` or `None` | ARKit blendshape name to 0..1 (MediaPipe gives 51 of the 52 `ARKIT_52` names, no `tongueOut`; `_neutral` is dropped) |
| `landmarks` | `(478, 3) float32` or `None` | normalized: x to the right and y down in 0..1 of the image, z toward the camera negative, in x units; 468 face mesh points then 10 iris points (canonical MediaPipe face mesh order) |
| `matrix` | `(4, 4) float32` or `None` | facial transformation matrix (head rotation and translation in centimeters, row-major) |
| `face` | `bool` property | `scores is not None` |

`None` in `scores` means no face in that frame; `landmarks` and `matrix` are then `None` too. A backend without a head
matrix returns `matrix = None` and the head pose columns are simply not written.

### Errors

`TrackerError(code, message)` with the codes of `captureforge/face/capture/errors.py`:

| Code | When |
|---|---|
| `helper_missing` | the tracker package is not installed in the helper Python |
| `model_missing` | the model file does not exist |
| `model_corrupt` | the model file exists but does not load |

## A second backend

A replacement keeps the names (`Tracker`, `Result`, `TrackerError`, `ARKIT_52`, `LANDMARKS`), the three
constructors and the output units above. If it produces fewer than 52 scores, the missing ones are absent from
`scores` (not zero); if it has no 478-point mesh, `landmarks` is `None` and features that need the mesh (the auto rig
fit, the capture file) say so.
