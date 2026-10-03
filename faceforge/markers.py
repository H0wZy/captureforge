"""Timeline markers as the pose library: marker name = shape key name."""

from .presets import NEUTRAL_MARKER


def create_markers(scene, names, start_frame=1, neutral_frame=0, clear=True):
    """One marker per shape at start_frame + i, plus the neutral marker."""
    if neutral_frame in range(start_frame, start_frame + len(names)):
        raise ValueError(
            f"Neutral frame {neutral_frame} falls inside the shape frames "
            f"{start_frame}..{start_frame + len(names) - 1}")
    markers = scene.timeline_markers
    if clear:
        markers.clear()
    markers.new(NEUTRAL_MARKER, frame=neutral_frame)
    for i, name in enumerate(names):
        markers.new(name, frame=start_frame + i)
    return len(names) + 1


def frames_from_markers(scene):
    """[(shape_name, frame)] sorted by frame, neutral excluded."""
    pairs = [(m.name, m.frame) for m in scene.timeline_markers if m.name != NEUTRAL_MARKER]
    return sorted(pairs, key=lambda p: p[1])


def neutral_frame(scene):
    """Frame of the neutral marker, or None if there is none."""
    for m in scene.timeline_markers:
        if m.name == NEUTRAL_MARKER:
            return m.frame
    return None


_ROTATION_PATH = {"QUATERNION": "rotation_quaternion", "AXIS_ANGLE": "rotation_axis_angle"}


def key_pose(armature, frame):
    """Keyframe loc/rot/scale of every pose bone at frame (honours rotation_mode)."""
    for pb in armature.pose.bones:
        rot = _ROTATION_PATH.get(pb.rotation_mode, "rotation_euler")
        for path in ("location", rot, "scale"):
            pb.keyframe_insert(path, frame=frame)
    return len(armature.pose.bones)
