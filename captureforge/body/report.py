"""Quality report (pure numpy): foot skate, bone length drift, joint limit violations, jitter, low-confidence ranges,
warnings; written as JSON and text, plus a review filmstrip (a PNG grid of evenly spaced stick-figure frames)."""

import json
import struct
import zlib

import numpy as np

from . import calibrate, landmarks, profile, quat, solve

LOW_CONF = 0.5
LIMIT_TOLERANCE = 1.0  # degrees outside a joint limit that still count as inside
GROUPS = {
    "torso": ("Hips", "Spine", "Spine1", "Spine2"), "head": ("Neck", "Head"),
    "left arm": ("LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand"),
    "right arm": ("RightShoulder", "RightArm", "RightForeArm", "RightHand"),
    "left leg": ("LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase"),
    "right leg": ("RightUpLeg", "RightLeg", "RightFoot", "RightToeBase"),
}


def _runs(mask):
    edges = np.diff(np.concatenate(([0], np.asarray(mask, np.int8), [0])))
    return list(zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()))


def build(clip, lm=None, calib=None):
    """The QualityReport dict of a clip. With the landmarks and their calibration it also reports bone length
    drift and carries the capture warnings."""
    ix = profile.INDEX
    _, head = solve.fk(clip.rot, clip.hips_pos)
    skate = {}
    for f, side in enumerate(("left", "right")):
        ankle = head[:, ix[("Left" if f == 0 else "Right") + "Foot"], :2]
        speed = np.linalg.norm(np.diff(ankle, axis=0), axis=1) * clip.fps * 100  # cm/s
        planted = clip.contact[:-1, f]
        skate[side] = float(speed[planted].mean()) if planted.any() else 0.0
    drift = {}
    warnings = []
    if lm is not None and calib is not None:
        for bone, ref in calib.bone_len.items():
            a, b = profile.LANDMARK_MAP[bone]
            seg = np.linalg.norm(calibrate.point(lm.pose_world, b) - calibrate.point(lm.pose_world, a), axis=-1)
            drift[bone] = float(np.abs(seg / ref - 1).max())
        for w in landmarks.capture_check(lm) + list(calib.warnings) + list(lm.meta.get("warnings", [])):
            if w not in warnings:
                warnings.append(w)
    violations = {}
    euler = np.degrees(quat.to_euler(clip.rot))
    for bone, (lo, hi) in profile.LIMITS.items():
        e = euler[:, ix[bone]]
        bad = ((e < np.array(lo) - LIMIT_TOLERANCE) | (e > np.array(hi) + LIMIT_TOLERANCE)).any(axis=1)
        if bad.any():
            violations[bone] = int(bad.sum())
    ranges = []
    for group, bones in GROUPS.items():
        weak = clip.conf[:, [ix[b] for b in bones]].min(axis=1) < LOW_CONF
        ranges += [[a, b, group] for a, b in _runs(weak)]
    return {"frames": int(len(clip.times)), "fps": float(clip.fps), "skate_cm_s": skate, "bone_drift": drift,
            "limit_violations": violations, "jitter": float(np.mean(np.abs(clip.rot[2:] - 2 * clip.rot[1:-1]
                                                                      + clip.rot[:-2]))) if len(clip.rot) > 2 else 0.0,
            "low_conf_ranges": sorted(ranges, key=lambda r: (r[0], r[2])), "warnings": warnings}


def write(path, rep):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def text(rep):
    """A short human-readable summary, one line per entry."""
    lines = [f"{rep['frames']} frames at {rep['fps']:g} fps",
             "Foot skate: left {left:.1f} cm/s, right {right:.1f} cm/s (on planted frames)".format(**rep["skate_cm_s"]),
             f"Jitter: {rep['jitter']:.5f} (mean second difference of the rotations, lower is better)"]
    if rep["bone_drift"]:
        worst = max(rep["bone_drift"].items(), key=lambda kv: kv[1])
        lines.append(f"Bone length drift: worst {worst[0]} {worst[1]:.1%}")
    if rep["limit_violations"]:
        lines.append("Joint limit violations: " + ", ".join(f"{b} {n} frames" for b, n in
                                                            rep["limit_violations"].items()))
    for a, b, group in rep["low_conf_ranges"]:
        lines.append(f"Low confidence: {group}, frames {a} to {b - 1}")
    lines += [f"Warning: {w}" for w in rep["warnings"]]
    return "\n".join(lines)


# ------------------------------------------------------------------ filmstrip

BG, FLOOR = (28, 30, 34, 255), (70, 72, 78, 255)
COLORS = {"left": (90, 170, 255, 255), "right": (255, 150, 70, 255), "centre": (225, 225, 225, 255)}


def _line(img, p0, p1, color):
    n = int(max(abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))) + 1
    x = np.round(np.linspace(p0[0], p1[0], n)).astype(int)
    y = np.round(np.linspace(p0[1], p1[1], n)).astype(int)
    for dx, dy in ((0, 0), (1, 0), (0, 1)):
        xs, ys = x + dx, y + dy
        ok = (xs >= 0) & (xs < img.shape[1]) & (ys >= 0) & (ys < img.shape[0])
        img[ys[ok], xs[ok]] = color


def filmstrip(clip, columns=6, rows=2, tile=(160, 220)):
    """RGBA uint8 image (rows * h, columns * w, 4): evenly spaced frames, each a front view (left half of the tile)
    and a side view (right half) of the skeleton, left bones blue, right bones orange."""
    tw, th = tile
    G, head = solve.fk(clip.rot, clip.hips_pos)
    tails = head + np.einsum("mbij,bj->mbi", G, profile.TAIL - profile.HEAD)
    count = columns * rows
    frames = np.unique(np.round(np.linspace(0, len(clip.times) - 1, count)).astype(int))
    img = np.empty((rows * th, columns * tw, 4), np.uint8)
    img[:] = BG
    scale = th / 2.3
    floor_y = th - int(0.05 * th)
    for k, frame in enumerate(frames):
        r, c = divmod(k, columns)
        tile_img = img[r * th:(r + 1) * th, c * tw:(c + 1) * tw]
        tile_img[floor_y] = FLOOR
        tile_img[:, tw // 2] = FLOOR
        for view, (cx, axis, sign) in enumerate(((tw // 4, 0, 1), (3 * tw // 4, 1, -1))):
            for i, name in enumerate(profile.NAMES):
                side = "left" if name.startswith("Left") else "right" if name.startswith("Right") else "centre"
                a, b = head[frame, i], tails[frame, i]
                p0 = (cx + sign * a[axis] * scale, floor_y - a[2] * scale)
                p1 = (cx + sign * b[axis] * scale, floor_y - b[2] * scale)
                _line(tile_img, p0, p1, COLORS[side])
    return img


def write_png(path, rgba):
    """Write an RGBA uint8 array as a PNG (standard library only)."""
    h, w = rgba.shape[:2]
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))
