"""Calibration from the neutral pose at the start of a clip (pure numpy): bone lengths, up vector, facing
direction and floor level (research D3). Without a still start it falls back to the rig's own proportions."""

from dataclasses import dataclass, field

import numpy as np

from . import landmarks as lm
from . import profile

STILL_STD = 0.05      # m, largest position spread of a key joint inside the neutral window
MIN_VIS = 0.5         # mean visibility the key joints need in the window
MIN_FRAMES = 4
KEY_VIS = (lm.L_SHOULDER, lm.R_SHOULDER, lm.L_HIP, lm.R_HIP, lm.L_KNEE, lm.R_KNEE, lm.L_ANKLE, lm.R_ANKLE,
           lm.L_HEEL, lm.R_HEEL, lm.L_FOOT, lm.R_FOOT)
KEY_STILL = (lm.L_ELBOW, lm.R_ELBOW, lm.L_WRIST, lm.R_WRIST, lm.L_KNEE, lm.R_KNEE, lm.L_ANKLE, lm.R_ANKLE)
FEET = (lm.L_HEEL, lm.R_HEEL, lm.L_FOOT, lm.R_FOOT)
# Segments whose length is calibrated: the limbs plus the torso (as "Hips"), neck and head segments.
LENGTH_BONES = ("Hips", "Neck", "Head", "LeftArm", "RightArm", "LeftForeArm", "RightForeArm", "LeftHand", "RightHand",
                "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg", "LeftFoot", "RightFoot")
LIMB_BONES = LENGTH_BONES[3:]


@dataclass
class Calibration:
    bone_len: dict          # bone name -> length in meters of its landmark segment on the neutral window
    up: np.ndarray          # (3,) unit vector pointing up in landmark space
    facing: np.ndarray      # (3,) unit vector the person faces, perpendicular to up
    floor_y: float          # floor height along `up` relative to the hips (negative: below them)
    window: tuple           # (start, end) frame range used (end exclusive)
    source: str             # "neutral" or "rig_default"
    warnings: list = field(default_factory=list)
    scale: float = 1.0      # rig units per person meter (rig hips height / person hips height)


def point(pts, spec):
    """Landmark point(s) of a profile spec: an index, or a tuple of indices meaning their midpoint."""
    return pts[..., spec, :] if isinstance(spec, int) else pts[..., list(spec), :].mean(axis=-2)


def _unit(v, default):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.asarray(default, float)


def _directions(w, use_legs):
    """Up and facing (landmark space) averaged over the frames `w` (n, 33, 3), origin at the hips."""
    sh = (w[:, lm.L_SHOULDER] + w[:, lm.R_SHOULDER]).mean(axis=0) / 2
    if use_legs:
        ank = (w[:, lm.L_ANKLE] + w[:, lm.R_ANKLE]).mean(axis=0) / 2
        up = _unit(sh - ank, (0, 1, 0))
    else:
        up = _unit(sh, (0, 1, 0))
    left = (w[:, lm.L_HIP] - w[:, lm.R_HIP]).mean(axis=0) + (w[:, lm.L_SHOULDER] - w[:, lm.R_SHOULDER]).mean(axis=0)
    left = left - np.dot(left, up) * up
    left = _unit(left, np.cross(up, (0, 0, 1)))
    return up, _unit(np.cross(left, up), (0, 0, 1))


def calibrate(landmark_file, neutral_seconds=1.5):
    """Measure the person on the first `neutral_seconds` of the clip (a Landmarks object)."""
    src = landmark_file
    t = src.times - src.times[0]
    end = int(np.searchsorted(t, neutral_seconds - 1e-9, side="left")) if neutral_seconds > 0 else 0
    start = 0
    idx = [i for i in range(start, end) if src.valid[i]]
    warnings = []
    ok = len(idx) >= MIN_FRAMES
    use_legs = True
    if not ok:
        warnings.append("No neutral pose: the video has no still start of " f"{neutral_seconds:g} s; "
                        "using the rig's standard proportions.")
        idx = [i for i in range(min(src.n, max(end, MIN_FRAMES))) if src.valid[i]] or [0]
    w = src.pose_world[idx].astype(float)
    vis = src.pose_vis[idx]
    if ok and vis[:, list(KEY_VIS)].mean() < MIN_VIS:
        warnings.append("Body cut off: shoulders, hips or legs are not visible at the start; "
                        "using the rig's standard proportions.")
        ok, use_legs = False, False
    if ok:
        spread = max(np.linalg.norm(w[:, j].std(axis=0)) for j in KEY_STILL)
        if spread > STILL_STD:
            warnings.append("No neutral pose: the person moves during the first "
                            f"{neutral_seconds:g} s; using the rig's standard proportions.")
            ok = False
    up, facing = _directions(w, use_legs)
    if not ok:
        floor = float(np.median((w[:, FEET] @ up).min(axis=1))) if use_legs else -1.0
        lens = {b: float(profile.LEN[profile.INDEX[b]]) for b in LIMB_BONES}
        return Calibration(lens, up, facing, floor, (idx[0], idx[-1] + 1), "rig_default", warnings, 1.0)
    floor = float((w[:, FEET] @ up).min(axis=1).mean())
    lens = {}
    for b in LENGTH_BONES:
        a, c = profile.LANDMARK_MAP[b]
        lens[b] = float(np.linalg.norm(point(w, c) - point(w, a), axis=-1).mean())
    scale = float(profile.HEAD[0, 2] / -floor) if floor < -0.05 else 1.0
    return Calibration(lens, up, facing, floor, (idx[0], idx[-1] + 1), "neutral", warnings, scale)
