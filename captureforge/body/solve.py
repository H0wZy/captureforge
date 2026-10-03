"""Landmarks to bone rotations (pure numpy), for the fixed Mixamo/Unity profile (research D2, D4).

Every driven bone gets an absolute target: its swing is the turn that takes the rest direction to the observed
segment direction, and a second observed vector fixes the twist (palm plane, knee plane, foot plane, shoulder
and hip lines, ears and nose). Targets are "global deltas" G (the rotation applied to the rest pose in character
space); local rotations follow from G_bone = G_parent * R * B * R^T with R the bone's rest frame, so no
constraints or Blender context are needed. This is the only module that converts landmark axes to Blender axes
(`to_character`).
"""

from collections import namedtuple
from dataclasses import dataclass, field, replace

import numpy as np

from . import landmarks as lm
from . import calibrate as calibration
from . import profile, quat
from .calibrate import point

LOW_CONF = 0.5          # below this a bone is bridged from its good neighbours in time
SPIKE = 0.15            # m, one-frame point jump (front/back flip) that is replaced by its neighbours' mean
NEUTRAL_BIAS = ("Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "LeftUpLeg", "RightUpLeg", "LeftLeg",
                "RightLeg", "LeftFoot", "RightFoot")
FEET = (lm.L_HEEL, lm.R_HEEL, lm.L_FOOT, lm.R_FOOT)
DRIVEN = ("Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "LeftArm", "RightArm", "LeftForeArm", "RightForeArm",
          "LeftHand", "RightHand", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg", "LeftFoot", "RightFoot")
B = len(profile.BONES)


@dataclass
class MotionClip:
    fps: float
    times: np.ndarray        # (m,) seconds, uniform at fps
    rot: np.ndarray          # (m, B, 4) local quaternions (w, x, y, z), sign-continuous, in profile.BONES order
    hips_pos: np.ndarray     # (m, 3) hips head position in character space (height; sway when travel is kept)
    contact: np.ndarray      # (m, 2) bool, planted flags for the left and right foot
    conf: np.ndarray         # (m, B) confidence per bone from the landmark visibility
    flags: dict = field(default_factory=dict)

    def __post_init__(self):
        flags = dict(in_place=False, looped=False, mirrored=False, lock_left=True, lock_right=True, fingers=False)
        flags.update(self.flags)
        self.flags = flags

    def replace(self, **kw):
        return replace(self, **kw)


def basis(calib):
    """(left, forward, up) unit vectors of the person in landmark space."""
    u = np.asarray(calib.up, float)
    f = np.asarray(calib.facing, float)
    return np.cross(u, f), f, u


def to_character(pts, calib):
    """Landmark space (+Y up, +Z toward the camera, any camera tilt) to character space (+X left, -Y forward,
    +Z up), using the up and facing measured on the neutral pose. Works on any (..., 3) array of points or vectors."""
    left, fwd, up = basis(calib)
    p = np.asarray(pts, float)
    return np.stack([p @ left, -(p @ fwd), p @ up], axis=-1)


# ------------------------------------------------------------------ rotation targets

def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def _frame(a, s):
    """Orthonormal frames (..., 3, 3) with columns [a, s made perpendicular to a, their cross product]."""
    a = _unit(a)
    sp = s - np.sum(s * a, axis=-1, keepdims=True) * a
    weak = np.linalg.norm(sp, axis=-1, keepdims=True) < 1e-6
    other = np.where(np.abs(a[..., :1]) < 0.9, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]))
    sp = np.where(weak, other - np.sum(other * a, axis=-1, keepdims=True) * a, sp)
    sp = _unit(sp)
    return np.stack([a, sp, np.cross(a, sp)], axis=-1)


def _target(a, s, d_rest, s_rest):
    """Global delta rotations that take the rest frame (d_rest, s_rest) to the observed frame (a, s)."""
    return _frame(a, s) @ np.swapaxes(_frame(np.asarray(d_rest, float), np.asarray(s_rest, float)), -1, -2)


def _smooth01(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def _normal(P, key):
    """Plane normal (unit, sign applied) of a bone's twist reference triple, and its rest value."""
    a, b, c, sign, rest = profile.TWIST_REF[key]
    return sign * _unit(np.cross(P[:, b] - P[:, a], P[:, c] - P[:, a])), np.asarray(rest, float)


def _targets(P):
    """Global delta rotation matrices (m, B, 3, 3) for the driven bones; others stay identity."""
    m = len(P)
    G = np.tile(np.eye(3), (m, B, 1, 1))
    ix = profile.INDEX
    up_rest = np.array([0.0, 0.0, 1.0])
    left_rest = np.array([1.0, 0.0, 0.0])
    hips_c, sh_c, ears_c = (point(P, s) for s in (profile.HIPS_MID, profile.SHOULDERS_MID, profile.EARS_MID))
    spine = sh_c - hips_c
    # torso: the pelvis follows the hip line, the chest the shoulder line, the spine bones split the difference
    g_hips = _target(spine, P[:, lm.L_HIP] - P[:, lm.R_HIP], up_rest, left_rest)
    g_chest = _target(spine, P[:, lm.L_SHOULDER] - P[:, lm.R_SHOULDER], up_rest, left_rest)
    qh, qc = quat.from_matrix(g_hips), quat.from_matrix(g_chest)
    G[:, ix["Hips"]] = g_hips
    for name, t in (("Spine", 1 / 3), ("Spine1", 2 / 3)):
        G[:, ix[name]] = quat.to_matrix(quat.slerp(qh, qc, t))
    G[:, ix["Spine2"]] = g_chest
    # head: frame from the ears (left) and the nose (forward); the neck points at the ears
    ear_off = np.array(profile.FACE_REST["ear"])
    nose_off = np.array(profile.FACE_REST["nose"])
    left_r = 2 * ear_off * np.array([1, 0, 0])
    fwd_r = nose_off - ear_off * np.array([0, 1, 1])
    up_r = np.cross(fwd_r, left_r)
    left_h = P[:, lm.L_EAR] - P[:, lm.R_EAR]
    fwd_h = P[:, lm.NOSE] - ears_c
    fwd_h = fwd_h - np.sum(fwd_h * _unit(left_h), axis=-1, keepdims=True) * _unit(left_h)
    G[:, ix["Head"]] = _target(np.cross(fwd_h, left_h), fwd_h, up_r, fwd_r)
    G[:, ix["Neck"]] = _target(ears_c - sh_c, fwd_h, up_rest, fwd_r)
    for side, S in (("Left", dict(sh=lm.L_SHOULDER, el=lm.L_ELBOW, wr=lm.L_WRIST, idx=lm.L_INDEX, pk=lm.L_PINKY,
                                  hip=lm.L_HIP, kn=lm.L_KNEE, an=lm.L_ANKLE, ft=lm.L_FOOT)),
                    ("Right", dict(sh=lm.R_SHOULDER, el=lm.R_ELBOW, wr=lm.R_WRIST, idx=lm.R_INDEX, pk=lm.R_PINKY,
                                   hip=lm.R_HIP, kn=lm.R_KNEE, an=lm.R_ANKLE, ft=lm.R_FOOT))):
        d = {n: profile.DIR[ix[side + n]] for n in ("Arm", "ForeArm", "Hand", "Foot")}
        palm, palm_rest = _normal(P, side + "Hand")
        foot, foot_rest = _normal(P, side + "Foot")
        upper, fore = P[:, S["el"]] - P[:, S["sh"]], P[:, S["wr"]] - P[:, S["el"]]
        # arm: the elbow plane when the elbow is bent, the palm when the arm is straight
        bend, bend_rest = _normal(P, side + "Arm")
        w = _smooth01((np.linalg.norm(np.cross(_unit(upper), _unit(fore)), axis=-1, keepdims=True) - 0.2) / 0.3)
        G[:, ix[side + "Arm"]] = _target(upper, w * bend - (1 - w) * palm, d["Arm"], bend_rest)
        G[:, ix[side + "ForeArm"]] = _target(fore, palm, d["ForeArm"], palm_rest)
        G[:, ix[side + "Hand"]] = _target(point(P, (S["idx"], S["pk"])) - P[:, S["wr"]], palm, d["Hand"], palm_rest)
        # leg: the knee plane when the knee is bent, the foot when the leg is straight
        thigh, shin = P[:, S["kn"]] - P[:, S["hip"]], P[:, S["an"]] - P[:, S["kn"]]
        knee, knee_rest = _normal(P, side + "UpLeg")
        w = _smooth01((np.linalg.norm(np.cross(_unit(thigh), _unit(shin)), axis=-1, keepdims=True) - 0.2) / 0.3)
        G[:, ix[side + "UpLeg"]] = _target(thigh, w * knee - (1 - w) * foot, profile.DIR[ix[side + "UpLeg"]], knee_rest)
        G[:, ix[side + "Leg"]] = _target(shin, foot, profile.DIR[ix[side + "Leg"]], foot_rest)
        G[:, ix[side + "Foot"]] = _target(P[:, S["ft"]] - P[:, S["an"]], foot, d["Foot"], foot_rest)
    return G


def _confidence(vis):
    """Per-bone confidence (m, B): the smallest visibility among the landmarks the bone is solved from."""
    conf = np.ones((len(vis), B))
    for name, (a, c) in profile.LANDMARK_MAP.items():
        ids = set(np.atleast_1d(a)) | set(np.atleast_1d(c))
        if name in profile.TWIST_REF:
            ids |= set(profile.TWIST_REF[name][:3])
        conf[:, profile.INDEX[name]] = vis[:, sorted(ids)].min(axis=1)
    for side in ("Left", "Right"):
        conf[:, profile.INDEX[side + "Shoulder"]] = conf[:, profile.INDEX["Spine2"]]
        conf[:, profile.INDEX[side + "ToeBase"]] = conf[:, profile.INDEX[side + "Foot"]]
    return conf


def _bridge(q, good):
    """Replace the quaternions (m, 4) where `good` is False by a slerp between the nearest good frames
    (a run at either end holds the nearest good frame)."""
    if good.all() or not good.any():
        return q
    q = q.copy()
    ids = np.flatnonzero(good)
    for k in np.flatnonzero(~good):
        after = np.searchsorted(ids, k)
        if after == 0:
            q[k] = q[ids[0]]
        elif after == len(ids):
            q[k] = q[ids[-1]]
        else:
            i0, i1 = ids[after - 1], ids[after]
            q[k] = quat.slerp(q[i0], q[i1], (k - i0) / (i1 - i0))
    return q


def despike(P):
    """Replace single-frame jumps (a limb point that flips front/back for one frame) by the neighbours' mean."""
    P = P.copy()
    mid = (P[:-2] + P[2:]) / 2
    dev = np.linalg.norm(P[1:-1] - mid, axis=-1)
    gap = np.linalg.norm(P[2:] - P[:-2], axis=-1)
    bad = (dev > SPIKE) & (dev > 2 * gap)
    P[1:-1] = np.where(bad[..., None], mid, P[1:-1])
    return P


# ------------------------------------------------------------------ forward kinematics

def fk(rot, hips_pos, offset=None):
    """Global orientation deltas G (m, B, 3, 3) and bone head positions (m, B, 3) of a clip's rotations,
    on the profile's rest proportions (or `offset`, (B, 3) head offsets from the parent head)."""
    offset = profile.OFFSET if offset is None else offset
    local = quat.to_matrix(rot)
    m = len(local)
    G = np.empty((m, B, 3, 3))
    head = np.empty((m, B, 3))
    for i, p in enumerate(profile.PARENT):
        r = profile.ROT[i]
        loc = r @ local[:, i] @ r.T
        if p < 0:
            G[:, i], head[:, i] = loc, hips_pos
        else:
            G[:, i] = G[:, p] @ loc
            head[:, i] = head[:, p] + G[:, p] @ offset[i]
    return G, head


def retarget(rot, rest_rot, parent, present):
    """Local quaternions (m, B, 4) that pose an armature the same way the profile clip `rot` poses the profile rig.

    `rest_rot` (B, 3, 3): each bone's rest frame in armature space (a rolled rig differs from `profile.ROT`);
    `parent` (B,): the armature's own parent of each bone as a profile index, -1 for none or a non-profile bone;
    `present` (B,) bool: bones the armature has (the others stay at identity). The pose is carried by the global
    delta rotations, so any hierarchy and any roll gives the same bone directions and twists."""
    G, _ = fk(rot, np.zeros((len(rot), 3)))
    out = np.tile(quat.IDENTITY, (len(rot), B, 1))
    eye = np.tile(np.eye(3), (len(rot), 1, 1))
    for i in range(B):
        if present[i]:
            gp = G[:, parent[i]] if parent[i] >= 0 else eye
            out[:, i] = quat.continuity(quat.from_matrix(rest_rot[i].T @ np.swapaxes(gp, -1, -2) @ G[:, i] @ rest_rot[i]))
    return out


# ------------------------------------------------------------------ the solver

def _to_local(G_target, bias):
    """Chain the targets into clamped local quaternions. Returns (m, B, 4)."""
    m = len(G_target)
    Gm = np.empty((m, B, 3, 3))
    out = np.empty((m, B, 4))
    for i, bone in enumerate(profile.BONES):
        r = profile.ROT[i]
        gp = Gm[:, profile.PARENT[i]] if profile.PARENT[i] >= 0 else np.tile(np.eye(3), (m, 1, 1))
        gt = G_target[:, i]
        if bone.name in bias:
            gt = gt @ bias[bone.name].T
        q = quat.from_matrix(r.T @ np.swapaxes(gp, -1, -2) @ gt @ r)
        lim = profile.LIMITS.get(bone.name)
        if lim is not None:
            e = np.degrees(quat.to_euler(q))
            clipped = np.clip(e, lim[0], lim[1])
            if (clipped != e).any():
                q = quat.from_euler(np.radians(clipped))
        out[:, i] = q
        Gm[:, i] = gp @ r @ quat.to_matrix(q) @ r.T
    return out


def solve(landmark_file, calib, keep_travel=False):
    """Landmarks (resampled Landmarks object) and their calibration to a MotionClip on the profile."""
    L = landmark_file
    P = despike(to_character(L.pose_world.astype(float), calib))
    conf = _confidence(L.pose_vis)
    G = _targets(P)
    # bridge low-confidence bones, in global space, before the chain turns them into local rotations
    Gq = quat.continuity(quat.from_matrix(G))
    for i in range(B):
        Gq[:, i] = _bridge(Gq[:, i], conf[:, i] >= LOW_CONF)
    G = quat.to_matrix(Gq)
    bias = {}
    if calib.source == "neutral":
        w = slice(*calib.window)
        for name in NEUTRAL_BIAS:
            i = profile.INDEX[name]
            bias[name] = quat.to_matrix(quat.mean(Gq[w, i], axis=0))
    rot = _to_local(G, bias)
    for i in range(B):
        rot[:, i] = quat.continuity(rot[:, i])
    hips = _hips(L, P, calib, keep_travel)
    return MotionClip(fps=L.fps, times=L.times.copy(), rot=rot, hips_pos=hips,
                      contact=np.zeros((len(P), 2), bool), conf=conf)


def _hips(L, P, calib, keep_travel):
    """Hips head position: height from the lowest foot point, sway from the image (only with keep_travel)."""
    m = len(P)
    height = -(P[:, FEET, 2]).min(axis=1)
    seen = (L.pose_vis[:, FEET] >= LOW_CONF).any(axis=1)
    if seen.any():
        idx = np.where(seen, np.arange(m), -1)
        idx = np.maximum.accumulate(idx)
        idx[idx < 0] = int(np.argmax(seen))
        height = height[idx]
    h0 = -calib.floor_y if calib.source == "neutral" else float(np.median(height))
    pos = np.tile(profile.HEAD[0], (m, 1))
    pos[:, 2] += calib.scale * (height - h0)
    if keep_travel:
        hip_img = point(L.pose_image, profile.HIPS_MID)[:, 0] * L.size[0]
        torso_px = np.linalg.norm((point(L.pose_image, profile.SHOULDERS_MID)[:, :2]
                                   - point(L.pose_image, profile.HIPS_MID)[:, :2]) * np.array(L.size), axis=-1)
        torso_m = np.linalg.norm(point(L.pose_world, profile.SHOULDERS_MID) - point(L.pose_world, profile.HIPS_MID),
                                 axis=-1)
        mpp = float(np.median(torso_m / np.maximum(torso_px, 1e-6)))
        w = slice(*calib.window)
        dx = (hip_img - hip_img[w].mean()) * mpp * calib.scale
        pos[:, :2] += to_character(np.stack([dx, 0 * dx, 0 * dx], axis=-1), calib)[:, :2]
    return pos


Result = namedtuple("Result", "clip calib lm warnings")


def from_file(path, fps=30.0, keep_source_fps=False, neutral_seconds=1.5, keep_travel=False):
    """Read, resample, calibrate and solve a landmark file. Returns Result(clip, calib, lm, warnings), where the
    warnings are plain-text lines for the user (no person for some frames, no neutral pose, estimator notes)."""
    lm_file = lm.resample(lm.read(path), None if keep_source_fps else fps)
    calib = calibration.calibrate(lm_file, neutral_seconds)
    warnings = list(calib.warnings) + list(lm_file.meta.get("warnings", []))
    for start, end in lm_file.gaps:
        warnings.append(f"No person found in frames {start} to {end - 1}: the pose is bridged across the gap.")
    return Result(solve(lm_file, calib, keep_travel), calib, lm_file, warnings)
