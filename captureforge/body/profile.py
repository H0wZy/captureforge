"""The Mixamo/Unity Humanoid body profile (pure numpy): bones, rest pose, landmark map, twist references, limits.

Coordinates here are "character space" = Blender's: +X is the person's left, -Y is forward, +Z is up, meters.
Bone names are the Mixamo names without the `mixamorig:` prefix. The rest pose is a T-pose, palms down, hips at
1 m, feet flat on Z = 0. Every bone's rest frame is the one Blender builds for roll 0: local Y runs from the head
to the tail, local X and Z follow from the shortest turn from +Y (see `_roll0`).

Landmark indices are MediaPipe Pose's 33-point order (see landmarks.py).
"""

import re
from collections import namedtuple

import numpy as np

from . import landmarks as lm

Bone = namedtuple("Bone", "name parent required")

# (name, parent, required, head, tail) for the head and tail in character space.
_REST = [
    ("Hips", None, True, (0, 0, 1.00), (0, 0, 1.08)),
    ("Spine", "Hips", True, (0, 0, 1.08), (0, 0, 1.20)),
    ("Spine1", "Spine", False, (0, 0, 1.20), (0, 0, 1.32)),
    ("Spine2", "Spine1", False, (0, 0, 1.32), (0, 0, 1.44)),
    ("Neck", "Spine2", False, (0, 0, 1.44), (0, 0, 1.54)),
    ("Head", "Neck", True, (0, 0, 1.54), (0, 0, 1.76)),
]
for _side, _sx in (("Left", 1), ("Right", -1)):
    _REST += [
        (f"{_side}Shoulder", "Spine2", False, (0.02 * _sx, 0, 1.40), (0.17 * _sx, 0, 1.40)),
        (f"{_side}Arm", f"{_side}Shoulder", True, (0.17 * _sx, 0, 1.40), (0.45 * _sx, 0, 1.40)),
        (f"{_side}ForeArm", f"{_side}Arm", True, (0.45 * _sx, 0, 1.40), (0.71 * _sx, 0, 1.40)),
        (f"{_side}Hand", f"{_side}ForeArm", True, (0.71 * _sx, 0, 1.40), (0.80 * _sx, 0, 1.40)),
    ]
for _side, _sx in (("Left", 1), ("Right", -1)):
    _REST += [
        (f"{_side}UpLeg", "Hips", True, (0.09 * _sx, 0, 1.00), (0.09 * _sx, 0, 0.56)),
        (f"{_side}Leg", f"{_side}UpLeg", True, (0.09 * _sx, 0, 0.56), (0.09 * _sx, 0, 0.10)),
        (f"{_side}Foot", f"{_side}Leg", True, (0.09 * _sx, 0, 0.10), (0.09 * _sx, -0.20, 0.0)),
        (f"{_side}ToeBase", f"{_side}Foot", False, (0.09 * _sx, -0.20, 0.0), (0.09 * _sx, -0.27, 0.0)),
    ]

# Fingers (optional bones, solved only with hand tracking): MediaPipe Hand landmark indices per finger, and the
# rest geometry (head offset from the wrist side of the palm, bone lengths, direction) in the T-pose, palm down.
FINGER_NAMES = ("Thumb", "Index", "Middle", "Ring", "Pinky")
FINGER_LANDMARKS = {"Thumb": (1, 2, 3, 4), "Index": (5, 6, 7, 8), "Middle": (9, 10, 11, 12),
                    "Ring": (13, 14, 15, 16), "Pinky": (17, 18, 19, 20)}
_FINGER_REST = {  # name: (base y, base x, lengths of the three bones, direction in the palm plane)
    "Thumb": (-0.035, 0.74, (0.035, 0.030, 0.025), (0.6, -0.8)),
    "Index": (-0.025, 0.80, (0.040, 0.025, 0.020), (1.0, 0.0)),
    "Middle": (0.000, 0.80, (0.045, 0.028, 0.022), (1.0, 0.0)),
    "Ring": (0.020, 0.80, (0.040, 0.026, 0.020), (1.0, 0.0)),
    "Pinky": (0.038, 0.79, (0.032, 0.020, 0.018), (1.0, 0.0)),
}
for _side, _sx in (("Left", 1), ("Right", -1)):
    for _finger in FINGER_NAMES:
        _y, _x, _lens, (_dx, _dy) = _FINGER_REST[_finger]
        _d = np.array([_dx, _dy, 0.0]) / np.hypot(_dx, _dy)
        _head, _parent = np.array([_x * _sx, _y, 1.40]), f"{_side}Hand"
        for _k, _len in enumerate(_lens, 1):
            _tail = _head + _d * np.array([_sx, 1, 1]) * _len
            _REST.append((f"{_side}Hand{_finger}{_k}", _parent, False, tuple(_head), tuple(_tail)))
            _head, _parent = _tail, f"{_side}Hand{_finger}{_k}"
FINGER_BONES = tuple(f"{side}Hand{f}{k}" for side in ("Left", "Right") for f in FINGER_NAMES for k in (1, 2, 3))

BONES = tuple(Bone(n, p, r) for n, p, r, _, _ in _REST)
NAMES = tuple(b.name for b in BONES)
INDEX = {n: i for i, n in enumerate(NAMES)}
REQUIRED = frozenset(b.name for b in BONES if b.required)
PARENT = np.array([INDEX[b.parent] if b.parent else -1 for b in BONES])
HEAD = np.array([h for *_, h, _ in _REST], float)
TAIL = np.array([t for *_, t in _REST], float)
LEN = np.linalg.norm(TAIL - HEAD, axis=1)
DIR = (TAIL - HEAD) / LEN[:, None]
# Offset of each bone's head from its parent's head at rest (FK uses it; it is the rig's own proportions).
OFFSET = HEAD - np.where(PARENT[:, None] >= 0, HEAD[np.maximum(PARENT, 0)], 0.0)


def _roll0(d):
    """3x3 rotation whose Y column is d: the shortest turn from +Y (Blender's roll 0 bone matrix)."""
    c = d[1]
    if 1.0 + c < 1e-6:
        return np.diag([-1.0, -1.0, 1.0])
    v = np.cross((0.0, 1.0, 0.0), d)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + (k @ k) / (1.0 + c)


ROT = np.array([_roll0(d) for d in DIR])


# Bone -> (from, to): the segment of landmarks that defines the bone's direction. An entry that is a tuple
# of indices means the midpoint of those landmarks. Used for confidence and bone-length drift.
HIPS_MID = (lm.L_HIP, lm.R_HIP)
SHOULDERS_MID = (lm.L_SHOULDER, lm.R_SHOULDER)
EARS_MID = (lm.L_EAR, lm.R_EAR)
LANDMARK_MAP = {
    "Hips": (HIPS_MID, SHOULDERS_MID),
    "Spine": (HIPS_MID, SHOULDERS_MID),
    "Spine1": (HIPS_MID, SHOULDERS_MID),
    "Spine2": (HIPS_MID, SHOULDERS_MID),
    "Neck": (SHOULDERS_MID, EARS_MID),
    "Head": (EARS_MID, lm.NOSE),
    "LeftArm": (lm.L_SHOULDER, lm.L_ELBOW), "RightArm": (lm.R_SHOULDER, lm.R_ELBOW),
    "LeftForeArm": (lm.L_ELBOW, lm.L_WRIST), "RightForeArm": (lm.R_ELBOW, lm.R_WRIST),
    "LeftHand": (lm.L_WRIST, (lm.L_INDEX, lm.L_PINKY)), "RightHand": (lm.R_WRIST, (lm.R_INDEX, lm.R_PINKY)),
    "LeftUpLeg": (lm.L_HIP, lm.L_KNEE), "RightUpLeg": (lm.R_HIP, lm.R_KNEE),
    "LeftLeg": (lm.L_KNEE, lm.L_ANKLE), "RightLeg": (lm.R_KNEE, lm.R_ANKLE),
    "LeftFoot": (lm.L_ANKLE, lm.L_FOOT), "RightFoot": (lm.R_ANKLE, lm.R_FOOT),
}

# Limb bones whose roll comes from a plane of three landmarks: secondary = sign * (b - a) x (c - a), compared
# with the rest value (a character-space vector) of the same expression on the T-pose.
#   bone: (a, b, c, sign, rest)
TWIST_REF = {
    "LeftHand": (lm.L_WRIST, lm.L_INDEX, lm.L_PINKY, 1, (0, 0, 1)),
    "RightHand": (lm.R_WRIST, lm.R_INDEX, lm.R_PINKY, -1, (0, 0, 1)),
    "LeftForeArm": (lm.L_WRIST, lm.L_INDEX, lm.L_PINKY, 1, (0, 0, 1)),
    "RightForeArm": (lm.R_WRIST, lm.R_INDEX, lm.R_PINKY, -1, (0, 0, 1)),
    "LeftArm": (lm.L_SHOULDER, lm.L_ELBOW, lm.L_WRIST, 1, (0, 0, -1)),
    "RightArm": (lm.R_SHOULDER, lm.R_ELBOW, lm.R_WRIST, -1, (0, 0, -1)),
    "LeftUpLeg": (lm.L_HIP, lm.L_KNEE, lm.L_ANKLE, 1, (1, 0, 0)),
    "RightUpLeg": (lm.R_HIP, lm.R_KNEE, lm.R_ANKLE, 1, (1, 0, 0)),
    "LeftLeg": (lm.L_HEEL, lm.L_FOOT, lm.L_ANKLE, 1, (-1, 0, 0)),
    "RightLeg": (lm.R_HEEL, lm.R_FOOT, lm.R_ANKLE, 1, (-1, 0, 0)),
    "LeftFoot": (lm.L_HEEL, lm.L_FOOT, lm.L_ANKLE, 1, (-1, 0, 0)),
    "RightFoot": (lm.R_HEEL, lm.R_FOOT, lm.R_ANKLE, 1, (-1, 0, 0)),
}

# Nominal face geometry on the head bone at rest (offsets from the head bone's head, character space): the left
# ear (the right one mirrors it) and the nose. The solver's rest head frame is built from them, so a nominal head
# solves to the identity rotation.
FACE_REST = {"ear": (0.075, 0.0, 0.10), "nose": (0.0, -0.10, 0.06)}

# Euler XYZ ranges in degrees in the bone's rest frame: bone -> (lo, hi). Bones left out are unlimited.
# Elbows and knees are hinges that cannot bend backwards; the rest are wide guards against solver flips.
LIMITS = {
    **{f"{side}Hand{f}{k}": ((-110, -30, -30), (20, 30, 30)) for side in ("Left", "Right")
       for f in ("Index", "Middle", "Ring", "Pinky") for k in (1, 2, 3)},
    "Spine": ((-60, -45, -45), (60, 45, 45)),
    "Spine1": ((-60, -45, -45), (60, 45, 45)),
    "Spine2": ((-60, -45, -45), (60, 45, 45)),
    "Neck": ((-70, -70, -70), (70, 70, 70)),
    "Head": ((-80, -80, -80), (80, 80, 80)),
    "LeftForeArm": ((-20, -110, -155), (20, 110, 5)),
    "RightForeArm": ((-20, -110, -5), (20, 110, 155)),
    "LeftHand": ((-90, -60, -90), (90, 60, 90)),
    "RightHand": ((-90, -60, -90), (90, 60, 90)),
    "LeftLeg": ((-5, -60, -15), (155, 60, 15)),
    "RightLeg": ((-5, -60, -15), (155, 60, 15)),
    "LeftFoot": ((-70, -60, -45), (70, 60, 45)),
    "RightFoot": ((-70, -60, -45), (70, 60, 45)),
}

_PREFIX = re.compile(r"^mixamorig[:_]?")
_SUFFIX = re.compile(r"\.\d+$")


def normalise(name):
    """Mixamo bone name without the `mixamorig:` prefix and without a Blender numeric suffix (`.001`)."""
    return _SUFFIX.sub("", _PREFIX.sub("", name))


def validate(bone_names):
    """(missing, extra) for armature bone names: required profile bones that are absent, and names the
    profile does not know. Optional bones (spine chain, neck, shoulders, toes) are never reported missing."""
    seen = {normalise(n): n for n in bone_names}
    missing = [n for n in NAMES if n in REQUIRED and n not in seen]
    extra = [orig for norm, orig in seen.items() if norm not in INDEX]
    return missing, extra
