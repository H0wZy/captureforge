"""Foot contact detection and foot lock (pure numpy), research D6.

A foot is planted when its ankle is low and slow for a minimum time (with hysteresis). During a plant the ankle's
horizontal position is frozen in world space and a two-bone leg solve (thigh and shin lengths of the rig) makes
the leg reach it: the leg bends, and the hips are pulled only if the target is out of reach. Foot-skate clean-up
as an idea: Kovar, Schreiner and Gleicher (2002). Known failure modes (jumps, deep crouches, a seated rider) are
handled by switching the lock off per foot or per frame range.
"""

import numpy as np

from . import profile, quat, solve


def detect(foot_pos, fps, rest_ankle=None, height_in=0.06, height_out=0.10, speed_in=0.25, speed_out=0.5,
           min_seconds=0.12):
    """Planted flags (m, 2) bool from the ankle positions (m, 2, 3) [left, right] in rig space.
    Enters a plant when the ankle is within `height_in` of its rest height and slower than `speed_in` m/s,
    stays planted until it is above `height_out` or faster than `speed_out`; plants shorter than `min_seconds`
    are dropped."""
    rest = profile.HEAD[profile.INDEX["LeftFoot"], 2] if rest_ankle is None else rest_ankle
    pos = np.asarray(foot_pos, float)
    m = len(pos)
    h = pos[..., 2] - rest
    speed = np.linalg.norm(np.gradient(pos, axis=0), axis=-1) * fps if m > 1 else np.zeros_like(h)
    out = np.zeros((m, 2), bool)
    for f in range(2):
        on = False
        for t in range(m):
            on = (h[t, f] < height_out and speed[t, f] < speed_out) if on else (h[t, f] < height_in
                                                                              and speed[t, f] < speed_in)
            out[t, f] = on
        out[:, f] = _drop_short(out[:, f], int(np.ceil(min_seconds * fps)))
    return out


def _runs(mask):
    edges = np.diff(np.concatenate(([0], np.asarray(mask, np.int8), [0])))
    return list(zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist()))


def _drop_short(mask, n):
    mask = mask.copy()
    for a, b in _runs(mask):
        if b - a < n:
            mask[a:b] = False
    return mask


def _arc(a, b):
    """Rotation matrix taking unit vector a to unit vector b along the shortest arc."""
    v, c = np.cross(a, b), float(np.dot(a, b))
    if c < -1 + 1e-9:
        axis = np.cross(a, (1.0, 0, 0) if abs(a[0]) < 0.9 else (0, 1.0, 0))
        axis /= np.linalg.norm(axis)
        return 2 * np.outer(axis, axis) - np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + (k @ k) / (1 + c)


def _unit(v):
    return v / max(np.linalg.norm(v), 1e-12)


def _reach(rot, hips, side, target):
    """Pose one leg so the ankle reaches `target`. rot (B, 4) and hips (3,) are updated in place."""
    ix = profile.INDEX
    up, leg, foot = ix[side + "UpLeg"], ix[side + "Leg"], ix[side + "Foot"]
    G, head = solve.fk(rot[None], hips[None])
    G, head = G[0], head[0]
    hip, knee = head[up], head[leg]
    l1, l2 = profile.LEN[up], profile.LEN[leg]
    v = target - hip
    d = np.linalg.norm(v)
    if d > l1 + l2:  # out of reach: bring the hips towards the foot
        hips += v / d * (d - (l1 + l2))
        hip = hip + v / d * (d - (l1 + l2))
        v, d = target - hip, l1 + l2
    d = max(d, abs(l1 - l2) + 1e-6)
    u = _unit(v)
    cos_a = np.clip((l1 * l1 + d * d - l2 * l2) / (2 * l1 * d), -1.0, 1.0)
    pole = (knee - hip) - np.dot(knee - hip, u) * u  # keep the knee bending the way it already bends
    if np.linalg.norm(pole) < 1e-6:
        forward = np.array([0.0, -1.0, 0.0])  # a straight leg: bend the knee forward
        pole = forward - np.dot(forward, u) * u
    w = _unit(pole)
    new_knee = hip + l1 * (cos_a * u + np.sqrt(1 - cos_a * cos_a) * w)
    ankle = hip + u * d
    g_up = _arc(G[up] @ profile.DIR[up], _unit(new_knee - hip)) @ G[up]
    g_leg = _arc(G[leg] @ profile.DIR[leg], _unit(ankle - new_knee)) @ G[leg]
    g_foot = G[foot]  # the foot keeps its orientation in the world
    g_hips = G[profile.PARENT[up]]
    R = profile.ROT
    for i, parent_g, g in ((up, g_hips, g_up), (leg, g_up, g_leg), (foot, g_leg, g_foot)):
        q = quat.from_matrix(R[i].T @ parent_g.T @ g @ R[i])
        rot[i] = q if np.dot(q, rot[i]) >= 0 else -q


def lock(clip, left=True, right=True, off_ranges=()):
    """Remove sliding on planted feet (`clip.contact`). `left`/`right` switch a foot off, `off_ranges` is a list of
    (start, end) frame ranges (end exclusive) where the lock is skipped. Returns a new clip."""
    rot, hips = clip.rot.copy(), clip.hips_pos.copy()
    _, head = solve.fk(rot, hips)
    off = np.zeros(len(rot), bool)
    for a, b in off_ranges:
        off[a:b] = True
    plan = {}  # frame -> [(side, target)]
    for f, (side, enabled) in enumerate((("Left", left), ("Right", right))):
        if not enabled:
            continue
        ankle = head[:, profile.INDEX[side + "Foot"]]
        for a, b in _runs(clip.contact[:, f] & ~off):
            xy = np.median(ankle[a:b, :2], axis=0)  # frozen where the foot sat for most of the plant
            for t in range(a, b):
                plan.setdefault(t, []).append((side, np.array([xy[0], xy[1], ankle[t, 2]])))
    for t, jobs in plan.items():
        for side, target in jobs:
            _reach(rot[t], hips[t], side, target)
    flags = dict(clip.flags, lock_left=bool(left), lock_right=bool(right))
    return clip.replace(rot=rot, hips_pos=hips, flags=flags)
