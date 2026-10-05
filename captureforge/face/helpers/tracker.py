"""The face tracker behind one small contract (docs/TRACKER-CONTRACT.md). This is the ONLY module of FaceForge that
imports MediaPipe; replacing the tracking backend means replacing this file.

    with Tracker.video(model_path) as t:          # also Tracker.image(...) and Tracker.live(...)
        result = t.process(frame_rgb, timestamp_ms)

frame_rgb: uint8 array, height x width x 3, RGB. Result: timestamp_ms, scores ({ARKit name: 0..1} or None),
landmarks ((478, 3) float32, normalized x right, y down, z toward the camera negative in x units, or None), matrix
((4, 4) float32 facial transformation, or None). None everywhere means no face. Image and video mode return the
result of the frame given; live mode is asynchronous and returns the newest finished result (an earlier frame's,
see its timestamp), or None before the first one.

Runs in the helper Python (not inside Blender). mediapipe and numpy are imported only when a tracker is built, so
this module imports anywhere.
"""

import os
from typing import NamedTuple, Optional

LANDMARKS = 478
# The names and order FaceForge expects (captureforge/face/presets.py ARKIT_52). MediaPipe returns 51 of them (no
# tongueOut) plus "_neutral", which is dropped.
ARKIT_52 = [
    "eyeBlinkLeft", "eyeLookDownLeft", "eyeLookInLeft", "eyeLookOutLeft",
    "eyeLookUpLeft", "eyeSquintLeft", "eyeWideLeft",
    "eyeBlinkRight", "eyeLookDownRight", "eyeLookInRight", "eyeLookOutRight",
    "eyeLookUpRight", "eyeSquintRight", "eyeWideRight",
    "jawForward", "jawLeft", "jawRight", "jawOpen",
    "mouthClose", "mouthFunnel", "mouthPucker", "mouthLeft", "mouthRight",
    "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight",
    "mouthDimpleLeft", "mouthDimpleRight", "mouthStretchLeft", "mouthStretchRight",
    "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper",
    "mouthPressLeft", "mouthPressRight", "mouthLowerDownLeft", "mouthLowerDownRight",
    "mouthUpperUpLeft", "mouthUpperUpRight",
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight",
    "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
    "noseSneerLeft", "noseSneerRight",
    "tongueOut",
]
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")


class TrackerError(Exception):
    """A failure with an error code of captureforge/face/capture/errors.py (model_missing, model_corrupt,
    helper_missing)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Result(NamedTuple):
    timestamp_ms: int
    scores: Optional[dict]
    landmarks: object  # (478, 3) float32 or None
    matrix: object     # (4, 4) float32 or None

    @property
    def face(self):
        return self.scores is not None


def to_result(timestamp_ms, blendshapes, landmarks, matrices):
    """Result from MediaPipe's per-face lists (the first face counts): blendshapes (categories with category_name and
    score), landmarks (points with x, y, z), matrices (4x4 arrays, or None when not requested)."""
    import numpy as np
    if not blendshapes or not landmarks:
        return Result(int(timestamp_ms), None, None, None)
    scores = {c.category_name: float(c.score) for c in blendshapes[0] if c.category_name != "_neutral"}
    points = np.array([(p.x, p.y, p.z) for p in landmarks[0]], dtype=np.float32)
    matrix = np.asarray(matrices[0], dtype=np.float32).reshape(4, 4) if matrices else None
    return Result(int(timestamp_ms), scores, points, matrix)


def _mediapipe():
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
    except ImportError as e:
        raise TrackerError("helper_missing",
                           f"missing package ({e.name}). Install with: pip install -r requirements.txt") from e
    return mp, mp_python, vision


class Tracker:
    """MediaPipe Face Landmarker, one face, blendshapes and the transformation matrix on."""

    def __init__(self, model_path, mode):
        if not os.path.isfile(model_path):
            raise TrackerError("model_missing",
                               f"model file not found: {model_path}\nDownload it (about 3.6 MB) from {MODEL_URL}")
        self._mp, mp_python, vision = _mediapipe()
        self.mode, self.latest = mode, None
        running = {"image": vision.RunningMode.IMAGE, "video": vision.RunningMode.VIDEO,
                   "live": vision.RunningMode.LIVE_STREAM}[mode]
        extra = {"result_callback": self._on_result} if mode == "live" else {}
        opts = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model_path)), running_mode=running,
            output_face_blendshapes=True, output_facial_transformation_matrixes=True, num_faces=1, **extra)
        try:
            self._lm = vision.FaceLandmarker.create_from_options(opts)
        except (RuntimeError, ValueError) as e:
            raise TrackerError("model_corrupt", f"cannot load the face model {model_path}: {e}") from e

    @classmethod
    def image(cls, model_path):
        return cls(model_path, "image")

    @classmethod
    def video(cls, model_path):
        return cls(model_path, "video")

    @classmethod
    def live(cls, model_path):
        return cls(model_path, "live")

    def _on_result(self, res, _image, timestamp_ms):
        self.latest = to_result(timestamp_ms, res.face_blendshapes, res.face_landmarks,
                                res.facial_transformation_matrixes)

    def process(self, frame_rgb, timestamp_ms):
        """See the module docstring. Video and live mode need strictly increasing timestamps."""
        import numpy as np
        img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame_rgb))
        if self.mode == "live":
            self._lm.detect_async(img, int(timestamp_ms))
            return self.latest
        res = self._lm.detect(img) if self.mode == "image" else self._lm.detect_for_video(img, int(timestamp_ms))
        return to_result(timestamp_ms, res.face_blendshapes, res.face_landmarks, res.facial_transformation_matrixes)

    def close(self):
        self._lm.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
