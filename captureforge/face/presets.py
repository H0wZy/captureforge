"""Shape name presets (pure Python, no bpy)."""

# Apple ARFaceAnchor.BlendShapeLocation, in Apple / Live Link Face column order.
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

# Left/Right here is a direction, not a side: never split or merge these.
NOT_MIRROR = {"jawLeft", "jawRight", "mouthLeft", "mouthRight"}

# Extra Live Link Face columns (head and eye rotations), ignored by the MVP.
LIVELINK_ROTATION_COLUMNS = [
    "HeadYaw", "HeadPitch", "HeadRoll",
    "LeftEyeYaw", "LeftEyePitch", "LeftEyeRoll",
    "RightEyeYaw", "RightEyePitch", "RightEyeRoll",
]

NEUTRAL_MARKER = "neutral"


def mirror_base(name):
    """'eyeBlinkLeft' -> 'eyeBlink'; None for unpaired names and NOT_MIRROR."""
    if name in NOT_MIRROR:
        return None
    for side in ("Left", "Right"):
        if name.endswith(side) and len(name) > len(side):
            return name[: -len(side)]
    return None


def symmetric_names(names):
    """Collapse each Left/Right pair into its base name, keeping first-seen order."""
    out = []
    for name in names:
        base = mirror_base(name) or name
        if base not in out:
            out.append(base)
    return out


ARKIT_SYMMETRIC = symmetric_names(ARKIT_52)
# Base names that split_all turns into <base>Left / <base>Right.
MIRROR_BASES = {mirror_base(n) for n in ARKIT_52} - {None}


def parse_names(text):
    """Custom list: names separated by commas or new lines, duplicates dropped."""
    out = []
    for part in text.replace("\n", ",").split(","):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out
