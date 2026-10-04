"""Landmark file reader (pure numpy). Interface: specs/001-bodyforge-v1/contracts/landmarks-file.md.

The helper process writes `landmarks.npz`; this module reads and validates it, holds the frames where no
person was found, and resamples to a uniform frame rate. It never imports the estimator.
"""

import json
import os
from dataclasses import dataclass, field, replace

import numpy as np

VERSION = 1
REQUIRED = ("version", "times", "fps_source", "size", "pose_world", "pose_image", "pose_vis", "meta")

# MediaPipe Pose's 33-point order, the only layout the file may use (see contracts/landmarks-file.md).
NOSE, L_EYE_IN, L_EYE, L_EYE_OUT, R_EYE_IN, R_EYE, R_EYE_OUT, L_EAR, R_EAR, MOUTH_L, MOUTH_R = range(11)
L_SHOULDER, R_SHOULDER, L_ELBOW, R_ELBOW, L_WRIST, R_WRIST = range(11, 17)
L_PINKY, R_PINKY, L_INDEX, R_INDEX, L_THUMB, R_THUMB = range(17, 23)
L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE, L_HEEL, R_HEEL, L_FOOT, R_FOOT = range(23, 33)


@dataclass
class Landmarks:
    times: np.ndarray            # (n,) seconds
    fps_source: float            # nominal rate reported by the container
    size: tuple                  # (width, height)
    pose_world: np.ndarray       # (n, 33, 3) meters, +X right, +Y up, +Z toward the camera, origin at the hips
    pose_image: np.ndarray       # (n, 33, 3)
    pose_vis: np.ndarray         # (n, 33)
    meta: dict
    hands_world: object = None   # (n, 2, 21, 3) or None
    hands_vis: object = None     # (n, 2) or None
    head_box: object = None      # (n, 4) or None
    valid: object = None         # (n,) bool, False where no person was found (the frame was held)
    gaps: list = field(default_factory=list)   # [(start, end)) frame ranges, end exclusive
    fps: float = 0.0             # rate of `times` after a resample (the nominal rate before)

    def __post_init__(self):
        if self.valid is None:
            self.valid = np.ones(len(self.times), bool)
        if not self.fps:
            self.fps = float(self.fps_source)

    @property
    def n(self):
        return len(self.times)

    def replace(self, **kw):
        return replace(self, **kw)


def _runs(mask):
    """[(start, end)) of the consecutive True runs of a bool array."""
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()))


def _hold(arr, valid):
    """Replace rows where valid is False with the last good row (leading gap: the first good row)."""
    idx = np.where(valid, np.arange(len(valid)), -1)
    idx = np.maximum.accumulate(idx)
    idx[idx < 0] = int(np.argmax(valid))
    return arr[idx]


def read(path):
    """Read and validate a landmarks.npz. ValueError names the problem; NaN rows are held and listed in `gaps`."""
    if not path or not os.path.isfile(path):
        raise ValueError(f"Landmark file not found: '{path}'")
    try:
        d = dict(np.load(path, allow_pickle=False))
    except (OSError, ValueError) as e:
        raise ValueError(f"Cannot read the landmark file: {e}") from e
    for key in REQUIRED:
        if key not in d:
            raise ValueError(f"Landmark file is missing the required key '{key}'")
    if int(d["version"]) != VERSION:
        raise ValueError(f"Unknown landmark file version {int(d['version'])} (this add-on reads version {VERSION})")
    times = d["times"].astype(np.float64)
    n = len(times)
    if n < 2:
        raise ValueError("Landmark file needs at least 2 frames")
    if not np.isfinite(times).all() or not (np.diff(times) > 0).all():
        raise ValueError("Landmark times must be finite and strictly increasing")
    shapes = {"pose_world": (n, 33, 3), "pose_image": (n, 33, 3), "pose_vis": (n, 33),
              "hands_world": (n, 2, 21, 3), "hands_vis": (n, 2), "head_box": (n, 4)}
    for key, shape in shapes.items():
        if key in d and d[key].shape != shape:
            raise ValueError(f"Landmark array shape mismatch: {key} is {d[key].shape}, expected {shape}")
    try:
        meta = json.loads(str(d["meta"]))
    except ValueError as e:
        raise ValueError(f"Landmark meta is not valid JSON: {e}") from e

    pose_world = d["pose_world"].astype(np.float32)
    valid = ~np.isnan(pose_world).any(axis=(1, 2))
    if not valid.any():
        raise ValueError("No person found in any frame of the landmark file")
    pose_image = d["pose_image"].astype(np.float32)
    pose_vis = d["pose_vis"].astype(np.float32)
    head_box = d["head_box"].astype(np.float32) if "head_box" in d else None
    if not valid.all():
        pose_world, pose_image = _hold(pose_world, valid), _hold(pose_image, valid)
        pose_vis = np.where(valid[:, None], pose_vis, 0.0).astype(np.float32)
        if head_box is not None:
            head_box = _hold(head_box, valid & ~np.isnan(head_box).any(axis=1))
    return Landmarks(
        times=times, fps_source=float(d["fps_source"]), size=tuple(int(v) for v in d["size"]),
        pose_world=pose_world, pose_image=pose_image, pose_vis=pose_vis, meta=meta,
        hands_world=d["hands_world"].astype(np.float32) if "hands_world" in d else None,
        hands_vis=d["hands_vis"].astype(np.float32) if "hands_vis" in d else None,
        head_box=head_box, valid=valid, gaps=_runs(~valid))


def _lerp(t, arr, new_t):
    i = np.clip(np.searchsorted(t, new_t, side="right") - 1, 0, len(t) - 2)
    w = np.clip((new_t - t[i]) / (t[i + 1] - t[i]), 0.0, 1.0).reshape((-1,) + (1,) * (arr.ndim - 1))
    return (arr[i] * (1 - w) + arr[i + 1] * w).astype(arr.dtype)


def resample(lm, fps=None):
    """Uniform grid at `fps` (None = the file's nominal rate) by linear interpolation on the real timestamps.
    `fps_source` is never trusted over `times`."""
    fps = float(fps or lm.fps_source)
    t = lm.times
    count = int(np.floor((t[-1] - t[0]) * fps + 1e-9)) + 1
    new_t = t[0] + np.arange(count) / fps
    i = np.clip(np.searchsorted(t, new_t, side="right") - 1, 0, len(t) - 2)
    near = np.where(new_t - t[i] < t[i + 1] - new_t, i, i + 1)
    valid = lm.valid[near]

    def lerp(a):
        return None if a is None else _lerp(t, a, new_t)

    return lm.replace(times=new_t, pose_world=lerp(lm.pose_world), pose_image=lerp(lm.pose_image),
                      pose_vis=lerp(lm.pose_vis), hands_world=lerp(lm.hands_world),
                      hands_vis=lerp(lm.hands_vis), head_box=lerp(lm.head_box),
                      valid=valid, gaps=_runs(~valid), fps=fps)


# ------------------------------------------------------------------ capture check

MIN_FPS = 30.0
OUT_OF_FRAME = 0.10  # share of frames with a body point outside the picture that earns a warning
MIN_VISIBILITY = 0.6


def container_warnings(fps):
    """Warnings that need only the frame rate (known before the helper has tracked anything)."""
    if fps and fps < MIN_FPS - 0.5:
        return [f"The video is {fps:g} fps; 30 fps or more tracks fast moves better (60 fps for dancing)."]
    return []


def capture_check(lm):
    """Warnings about a take that is likely to track badly: low frame rate, body out of the picture, low confidence,
    several people. [] for a good take. Frames held for lack of a person are left out (they are reported as gaps)."""
    measured = (lm.n - 1) / (lm.times[-1] - lm.times[0])
    warnings = container_warnings(min(measured, lm.fps_source))
    if lm.valid.any():
        body = lm.pose_image[lm.valid][:, L_SHOULDER:R_FOOT + 1, :2]
        out = float(((body < 0) | (body > 1)).any(axis=(1, 2)).mean())
        if out > OUT_OF_FRAME:
            warnings.append(f"Part of the body leaves the picture in {out:.0%} of the frames: film from further "
                            "away so head to feet stay in view, or expect weak limbs there.")
        mean_vis = float(lm.pose_vis[lm.valid][:, L_SHOULDER:R_FOOT + 1].mean())
        if mean_vis < MIN_VISIBILITY:
            warnings.append(f"Low confidence (mean visibility {mean_vis:.2f}): more light, a plainer background "
                            "and tighter clothes help.")
    people = int(lm.meta.get("people_seen", 1))
    if people > 1:
        warnings.append(f"{people} people were seen in one frame; the most prominent one is tracked.")
    return warnings
