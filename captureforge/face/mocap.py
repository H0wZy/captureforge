"""Face mocap CSV -> shape key F-Curves.

Generic: any CSV whose header has one column per shape (matched to shape keys by
name, case-insensitive, with an optional rename map) plus an optional time column:
  - Live Link Face: 'Timecode' as HH:MM:SS:FF.sub, FF counted at csv_fps;
  - our own format (e.g. a webcam/MediaPipe exporter): 'time' in seconds;
  - neither: row index / csv_fps.
Non-numeric columns and Live Link Face rotation columns are ignored.

Optional head pose columns (written by helpers/video_to_csv.py, never shapes): headRotX/Y/Z in radians, relative to
the neutral head, Euler order Ry * Rx * Rz (yaw about Y, pitch about X, roll about Z) in the head frame (X = the
person's left, Y up, Z out of the face); headPosX/Y/Z in centimeters. read_head_pose + apply_head_pose key them on a
pose bone; CSVs without them import exactly as before.
"""

import csv
import math

import bpy
import numpy as np

from .presets import LIVELINK_ROTATION_COLUMNS

HEAD_ROT_COLUMNS = ("headRotX", "headRotY", "headRotZ")
HEAD_POS_COLUMNS = ("headPosX", "headPosY", "headPosZ")
SKIP_COLUMNS = ({"timecode", "time", "blendshapecount"} | {c.lower() for c in LIVELINK_ROTATION_COLUMNS}
                | {c.lower() for c in HEAD_ROT_COLUMNS + HEAD_POS_COLUMNS})


def parse_timecode(text, fps):
    """'HH:MM:SS:FF.sub' -> seconds (FF.sub is a frame count at fps)."""
    h, m, s, ff = text.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + int(s) + float(ff) / fps


def _times(header, raw_rows, csv_fps):
    lower = [h.lower() for h in header]
    try:
        if "timecode" in lower:
            i = lower.index("timecode")
            t = [parse_timecode(r[i], csv_fps) for r in raw_rows]
        elif "time" in lower:
            i = lower.index("time")
            t = [float(r[i]) for r in raw_rows]
        else:
            raise ValueError("no time column")
    except (ValueError, IndexError):
        t = [i / csv_fps for i in range(len(raw_rows))]
    t0 = t[0] if t else 0.0
    return [x - t0 for x in t]


def read_csv(path, csv_fps=60.0):
    """Returns (names, times, rows): shape columns, seconds from the first row, (n, len(names)) floats."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        table = [r for r in csv.reader(f) if any(c.strip() for c in r)]
    if len(table) < 2:
        raise ValueError(f"'{path}' has no data rows")
    header, raw_rows = [h.strip() for h in table[0]], table[1:]

    cols = []
    for i, name in enumerate(header):
        if not name or name.lower() in SKIP_COLUMNS:
            continue
        try:
            [float(r[i]) for r in raw_rows]
        except (ValueError, IndexError):
            continue  # text or ragged column: not a shape weight
        cols.append(i)
    names = [header[i] for i in cols]
    rows = np.array([[float(r[i]) for i in cols] for r in raw_rows], dtype=np.float64)
    return names, _times(header, raw_rows, csv_fps), rows


read_livelink_csv = read_csv


def read_head_pose(path, csv_fps=60.0):
    """(times, rot, pos) of the head pose columns: seconds, (n, 3) radians, (n, 3) centimeters or None when the
    file has no headPos columns. None when it has no headRot columns at all (old and Live Link Face CSVs)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        table = [r for r in csv.reader(f) if any(c.strip() for c in r)]
    if len(table) < 2:
        return None
    header, raw_rows = [h.strip() for h in table[0]], table[1:]
    lower = [h.lower() for h in header]

    def block(cols):
        try:
            idx = [lower.index(c.lower()) for c in cols]
            return np.array([[float(r[i]) for i in idx] for r in raw_rows], dtype=np.float64)
        except (ValueError, IndexError):
            return None  # a column is missing or not numeric

    rot = block(HEAD_ROT_COLUMNS)
    if rot is None:
        return None
    return _times(header, raw_rows, csv_fps), rot, block(HEAD_POS_COLUMNS)


def parse_mapping(text):
    """'Col=key, Other=key2' -> {'col': 'key', 'other': 'key2'} (lower-case column names)."""
    out = {}
    for part in text.replace("\n", ",").split(","):
        if "=" in part:
            col, key = part.split("=", 1)
            if col.strip() and key.strip():
                out[col.strip().lower()] = key.strip()
    return out


def frame_rows(times, scene_fps, start_frame):
    """{frame: row index}; frame = start + round(t * fps) (halves round up), last row wins."""
    # The epsilon keeps exact halves (60 fps CSV -> 30 fps scene) from flipping on float noise.
    return {start_frame + int(math.floor(t * scene_fps + 0.5 + 1e-6)): i
            for i, t in enumerate(times)}


def apply_mocap(obj, names, times, rows, scene_fps, start_frame=1, mapping=None):
    """Key every matched column on obj's shape keys. Returns (matched_keys, unmatched_columns)."""
    keys = obj.data.shape_keys
    if keys is None:
        raise ValueError(f"'{obj.name}' has no shape keys")
    by_lower = {kb.name.lower(): kb.name for kb in keys.key_blocks if kb != keys.reference_key}
    mapping = mapping or {}

    pairs, unmatched = [], []
    for col, name in enumerate(names):
        target = mapping.get(name.lower(), name).lower()
        if target in by_lower:
            pairs.append((col, by_lower[target]))
        else:
            unmatched.append(name)
    if not pairs:
        return [], unmatched

    fr = sorted(frame_rows(times, scene_fps, start_frame).items())
    frames = np.array([f for f, _ in fr], dtype=np.float64)
    idx = [i for _, i in fr]

    ad = keys.animation_data or keys.animation_data_create()
    action_name = f"{obj.name}_facemocap"
    action = bpy.data.actions.get(action_name) or bpy.data.actions.new(action_name)
    ad.action = action
    for col, key_name in pairs:
        fc = action.fcurve_ensure_for_datablock(keys, f'key_blocks["{key_name}"].value')
        fc.keyframe_points.clear()
        fc.keyframe_points.add(len(frames))
        co = np.column_stack([frames, rows[idx, col]]).ravel()
        fc.keyframe_points.foreach_set("co", co.astype(np.float32))
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
        fc.update()
    return [k for _, k in pairs], unmatched


def import_csv(scene, targets, path, csv_fps=60.0, start_frame=1, mapping=None, profile=None):
    """Read a CSV and key it onto every target that has shape keys. profile: an actor profile (spec 005) that
    corrects the rows first (for FaceForge CSVs made without one).
    Returns (matched_keys, unmatched_columns, row_count); unmatched = columns no target took."""
    names, times, rows = read_csv(path, csv_fps)
    if profile is not None:
        from .capture import calib
        rows = calib.apply(profile, names, rows)
    fps = scene.render.fps / scene.render.fps_base
    matched, unmatched = set(), set(names)
    for obj in targets:
        if obj.data.shape_keys is None:
            continue
        m, u = apply_mocap(obj, names, times, rows, fps, start_frame, mapping)
        matched |= set(m)
        unmatched &= set(u)
    if not matched:
        raise ValueError("No CSV column matches a shape key on the targets")
    return sorted(matched), sorted(unmatched), len(times)


# ---- head pose -> pose bones --------------------------------------------------------------------

def _pose_bone(arm, name):
    """The pose bone called name (case-insensitive) or None."""
    low = name.strip().lower()
    return next((pb for pb in arm.pose.bones if pb.name.lower() == low), None)


def find_armature(scene, targets, bone_name):
    """The armature that has a bone called bone_name: the one on a target (parent or Armature modifier), else the
    only one in the scene that has it. None when there is none or it is ambiguous."""
    for obj in targets:
        for arm in [obj.parent] + [m.object for m in obj.modifiers if m.type == "ARMATURE"]:
            if arm is not None and arm.type == "ARMATURE" and _pose_bone(arm, bone_name):
                return arm
    found = [o for o in scene.objects if o.type == "ARMATURE" and _pose_bone(o, bone_name)]
    return found[0] if len(found) == 1 else None


def apply_head_pose(arm, head_bone, times, rot, pos=None, scene_fps=30.0, start_frame=1, gain=1.0,
                    neck_bone="", neck_share=0.0, translate=False, translate_scale=0.01):
    """Key the head rotation (rot, (n, 3) radians, see read_head_pose) on arm's head_bone, and a neck_share (0..1)
    of it on neck_bone (the head keeps the rest, so they add up). gain multiplies the angles. With translate, pos
    (centimeters) times translate_scale moves the head bone (it must not be Connected). Keys follow the bone's rotation mode (Quaternion or
    any Euler) in the armature's current action, a new <armature>_headmocap one when it has none; its other
    channels stay. Returns the names of the keyed bones.

    Assumes the armature is in Blender's default orientation (the character faces -Y, +Z up); the bone rolls are
    compensated. The head frame X = left, Y up, Z forward maps to armature space with (x, y, z) -> (x, -z, y)."""
    from mathutils import Euler, Matrix, Quaternion, Vector

    head = _pose_bone(arm, head_bone)
    if head is None:
        raise ValueError(f"Bone '{head_bone}' not found in '{arm.name}'")
    neck = None
    if neck_share > 0.0:
        neck = _pose_bone(arm, neck_bone)
        if neck is None:
            raise ValueError(f"Bone '{neck_bone}' not found in '{arm.name}'")
    if translate and pos is not None and head.bone.use_connect:
        raise ValueError(f"Bone '{head.name}' is Connected to its parent, so it cannot move: "
                         "switch Connected off (Bone properties > Relations) or turn Translation off")
    bones = [head] + ([neck] if neck else [])
    if any(b.rotation_mode == "AXIS_ANGLE" for b in bones):
        raise ValueError("Set the head and neck bones to Quaternion or Euler rotation: Axis-Angle is not supported")
    share = min(neck_share, 1.0) if neck else 0.0
    neck_is_parent = neck is not None and neck in head.parent_recursive

    to_arm = Matrix.Rotation(math.pi / 2, 3, "X")
    rest = {b.name: b.bone.matrix_local.to_3x3().normalized() for b in bones}
    ident = Quaternion()

    def local(b, world):  # the pose rotation that turns bone b by `world` (armature space) away from its rest
        r = rest[b.name]
        return (r.inverted() @ world.to_matrix() @ r).to_quaternion()

    fr = sorted(frame_rows(times, scene_fps, start_frame).items())
    frames = np.array([f for f, _ in fr], dtype=np.float64)
    idx = [i for _, i in fr]
    quats = {b.name: [] for b in bones}
    locs = []
    for i in idx:
        x, y, z = (float(v) * gain for v in rot[i])
        q = (to_arm @ Euler((x, y, z), "ZXY").to_matrix() @ to_arm.transposed()).to_quaternion()
        qn = ident.slerp(q, share)
        if neck is None:
            qh = q
        elif neck_is_parent:
            qh = qn.inverted() @ q
        else:
            qh = ident.slerp(q, 1.0 - share)
        for b, w in ((head, qh), (neck, qn)):
            if b is not None:
                quats[b.name].append(local(b, w))
        if translate and pos is not None:
            locs.append(tuple(rest[head.name].inverted() @ (to_arm @ Vector(pos[i]) * translate_scale)))

    ad = arm.animation_data or arm.animation_data_create()
    action = ad.action
    if action is None:
        action = ad.action = bpy.data.actions.new(f"{arm.name}_headmocap")

    def key(bone, prop, columns):
        columns = np.array(columns)
        for c in range(columns.shape[1]):
            fc = action.fcurve_ensure_for_datablock(arm, f'pose.bones["{bone}"].{prop}', index=c, group_name=bone)
            fc.keyframe_points.clear()
            fc.keyframe_points.add(len(frames))
            fc.keyframe_points.foreach_set("co", np.column_stack([frames, columns[:, c]]).ravel().astype(np.float32))
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
            fc.update()

    for b in bones:
        qs = quats[b.name]
        for k in range(1, len(qs)):
            qs[k].make_compatible(qs[k - 1])  # same hemisphere: no flips between keys
        if b.rotation_mode == "QUATERNION":
            key(b.name, "rotation_quaternion", [list(q) for q in qs])
        else:
            eulers, prev = [], None
            for q in qs:
                prev = q.to_euler(b.rotation_mode, prev) if prev is not None else q.to_euler(b.rotation_mode)
                eulers.append(tuple(prev))
            key(b.name, "rotation_euler", eulers)
    if locs:
        key(head.name, "location", locs)
    return [b.name for b in bones]
