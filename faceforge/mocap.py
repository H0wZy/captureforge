"""Face mocap CSV -> shape key F-Curves.

Generic: any CSV whose header has one column per shape (matched to shape keys by
name, case-insensitive, with an optional rename map) plus an optional time column:
  - Live Link Face: 'Timecode' as HH:MM:SS:FF.sub, FF counted at csv_fps;
  - our own format (e.g. a webcam/MediaPipe exporter): 'time' in seconds;
  - neither: row index / csv_fps.
Non-numeric columns and Live Link Face rotation columns are ignored.
"""

import csv
import math

import bpy
import numpy as np

from .presets import LIVELINK_ROTATION_COLUMNS

SKIP_COLUMNS = {"timecode", "time", "blendshapecount"} | {c.lower() for c in LIVELINK_ROTATION_COLUMNS}


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
