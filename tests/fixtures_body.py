"""Shared helpers for the BodyForge tests: plain-Python package import, a tiny test runner, and synthetic
skeleton motions written through the landmark schema (never real captures, Constitution VI).

Pure tests import the body modules without Blender: `captureforge/__init__.py` imports bpy, so the package
objects are stubbed here (only their search path) and the pure submodules import normally.
"""

import json
import os
import sys
import traceback
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def pure_import():
    """Make `captureforge.body.<pure module>` importable without bpy. No-op when the real package is loaded."""
    if "captureforge" not in sys.modules:
        for name, sub in (("captureforge", ""), ("captureforge.body", "body")):
            mod = types.ModuleType(name)
            mod.__path__ = [os.path.join(ROOT, "captureforge", sub) if sub else os.path.join(ROOT, "captureforge")]
            sys.modules[name] = mod
    return sys.modules["captureforge.body"]


def implemented(x):
    """Assertion used at the top of a test so an unwritten feature fails on an assertion, not an AttributeError."""
    assert x is not None, "not implemented yet"
    return x


def run_all(namespace):
    """Run every `test_*` function of a test module; print PASS/FAIL; exit non-zero on any failure."""
    failed = 0
    tests = [(n, f) for n, f in namespace.items() if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL", name, f"{type(e).__name__}: {e}")
            if not isinstance(e, AssertionError):
                traceback.print_exc()
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


def write_landmarks(path, times, pose_world, pose_vis=None, pose_image=None, fps_source=None, size=(1080, 1920),
                    hands_world=None, hands_vis=None, head_box=None, meta=None, version=1):
    """Write a landmarks.npz exactly as contracts/landmarks-file.md describes (used by tests and fixtures)."""
    times = np.asarray(times, np.float64)
    n = len(times)
    pose_world = np.asarray(pose_world, np.float32)
    if pose_vis is None:
        pose_vis = np.where(np.isnan(pose_world[:, :, 0]), 0.0, 1.0)
    if pose_image is None:
        pose_image = np.full((n, 33, 3), 0.5, np.float32)
    if fps_source is None:
        fps_source = (n - 1) / (times[-1] - times[0]) if n > 1 else 30.0
    m = {"helper_version": "test", "model": "synthetic", "model_sha256": "", "model_variant": "heavy",
         "hands": hands_world is not None, "people_seen": 1, "frames_without_person": 0,
         "rotation_applied": 0, "warnings": []}
    m.update(meta or {})
    data = dict(version=np.int64(version), times=times, fps_source=np.float64(fps_source),
                size=np.asarray(size, np.int64), pose_world=pose_world, pose_image=np.asarray(pose_image, np.float32),
                pose_vis=np.asarray(pose_vis, np.float32), meta=np.str_(json.dumps(m)))
    if hands_world is not None:
        data["hands_world"] = np.asarray(hands_world, np.float32)
        data["hands_vis"] = np.asarray(hands_vis if hands_vis is not None
                                       else np.ones((n, 2), np.float32), np.float32)
    if head_box is not None:
        data["head_box"] = np.asarray(head_box, np.float32)
    np.savez_compressed(path, **data)
    return path


# ------------------------------------------------------------------ synthetic skeleton motions
# An independent forward-kinematics oracle: it builds the landmarks from the profile's rest geometry and
# known local Euler angles (degrees, XYZ, in each bone's canonical rest frame), so a solver test can check that
# the angles come back. It does not use the solver's or the quaternion module's code.

def _lazy_profile():
    pure_import()
    from captureforge.body import landmarks as lm, profile
    return profile, lm


def euler_matrix(deg):
    """Blender XYZ Euler (degrees) -> 3x3: R = Rz Ry Rx."""
    a, b, c = np.radians(deg)
    rx = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
    ry = np.array([[np.cos(b), 0, np.sin(b)], [0, 1, 0], [-np.sin(b), 0, np.cos(b)]])
    rz = np.array([[np.cos(c), -np.sin(c), 0], [np.sin(c), np.cos(c), 0], [0, 0, 1]])
    return rz @ ry @ rx


NEUTRAL = {"LeftArm": (-90, 0, 0), "RightArm": (-90, 0, 0)}  # standing, arms down (T-pose is the rig's rest)


def _attachments():
    """Landmark index -> (bone, offset from the bone head in the rest frame, character space)."""
    profile, lm = _lazy_profile()
    att = {lm.NOSE: ("Head", (0, -0.10, 0.06)), lm.L_EAR: ("Head", (0.075, 0, 0.10)),
           lm.R_EAR: ("Head", (-0.075, 0, 0.10))}
    for k, (dx, dz) in {lm.L_EYE_IN: (0.015, 0.10), lm.L_EYE: (0.03, 0.10), lm.L_EYE_OUT: (0.045, 0.10),
                        lm.R_EYE_IN: (-0.015, 0.10), lm.R_EYE: (-0.03, 0.10), lm.R_EYE_OUT: (-0.045, 0.10),
                        lm.MOUTH_L: (0.02, 0.02), lm.MOUTH_R: (-0.02, 0.02)}.items():
        att[k] = ("Head", (dx, -0.09, dz))
    for side, sx, ids in (("Left", 1, (lm.L_SHOULDER, lm.L_ELBOW, lm.L_WRIST, lm.L_PINKY, lm.L_INDEX, lm.L_THUMB,
                                       lm.L_HIP, lm.L_KNEE, lm.L_ANKLE, lm.L_HEEL, lm.L_FOOT)),
                          ("Right", -1, (lm.R_SHOULDER, lm.R_ELBOW, lm.R_WRIST, lm.R_PINKY, lm.R_INDEX, lm.R_THUMB,
                                         lm.R_HIP, lm.R_KNEE, lm.R_ANKLE, lm.R_HEEL, lm.R_FOOT))):
        sh, el, wr, pk, ix, th, hip, kn, an, he, ft = ids
        att.update({sh: (f"{side}Arm", (0, 0, 0)), el: (f"{side}ForeArm", (0, 0, 0)),
                    wr: (f"{side}Hand", (0, 0, 0)),
                    pk: (f"{side}Hand", (0.07 * sx, 0.03, 0)), ix: (f"{side}Hand", (0.09 * sx, -0.025, 0)),
                    th: (f"{side}Hand", (0.02 * sx, -0.045, 0)),
                    hip: (f"{side}UpLeg", (0, 0, 0)), kn: (f"{side}Leg", (0, 0, 0)),
                    an: (f"{side}Foot", (0, 0, 0)), he: (f"{side}Foot", (0, 0.07, -0.10)),
                    ft: (f"{side}ToeBase", (0, 0, 0))})
    return att


def skeleton(euler=None, hips=(0.0, 0.0, 0.0), scale=1.0):
    """Posed points. `euler`: {bone: (x, y, z) degrees} local rotations, others at rest. Returns
    (positions, G): the 33 landmarks in character space (hips head at its rest height plus `hips`, all scaled
    about the origin by `scale`) and the global delta rotation of every bone (dict)."""
    profile, lm = _lazy_profile()
    euler = euler or {}
    G, heads = {}, {}
    for i, bone in enumerate(profile.BONES):
        r = profile.ROT[i]
        g_parent = G[bone.parent] if bone.parent else np.eye(3)
        b = euler_matrix(euler.get(bone.name, (0, 0, 0)))
        G[bone.name] = g_parent @ r @ b @ r.T
        heads[bone.name] = (profile.HEAD[i] + np.asarray(hips) if not bone.parent
                            else heads[bone.parent] + g_parent @ profile.OFFSET[i])
    pts = np.zeros((33, 3))
    for k, (bone, off) in _attachments().items():
        pts[k] = heads[bone] + G[bone] @ np.asarray(off)
    return pts * scale, G


def char_to_landmark(p):
    """Character space (+X left, -Y forward, +Z up) -> landmark space (+X right-on-image, +Y up, +Z to camera)."""
    p = np.asarray(p)
    return np.stack([p[..., 0], p[..., 2], -p[..., 1]], axis=-1)


def rot_y(deg):
    a = np.radians(deg)
    return np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])


def rot_x(deg):
    a = np.radians(deg)
    return np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])


class Clip:
    """A synthetic landmark clip (arrays as in the landmark file) plus the euler angles that made it."""

    def __init__(self, times, pose_world, pose_image, pose_vis, euler, size=(1080, 1920)):
        self.times, self.pose_world, self.pose_image, self.pose_vis = times, pose_world, pose_image, pose_vis
        self.euler, self.size = euler, size

    def save(self, path, **kw):
        return write_landmarks(path, self.times, self.pose_world, self.pose_vis, self.pose_image,
                               size=self.size, **kw)

    def landmarks(self):
        """The same data as a landmarks.Landmarks object, without a file."""
        pure_import()
        from captureforge.body import landmarks as lm
        n = len(self.times)
        fps = (n - 1) / (self.times[-1] - self.times[0])
        return lm.Landmarks(times=self.times, fps_source=fps, size=self.size, pose_world=self.pose_world,
                            pose_image=self.pose_image, pose_vis=self.pose_vis, meta={"warnings": []})


def motion(euler_frames, fps=30.0, scale=1.0, yaw=0.0, pitch=0.0, hips=None, vis=1.0, noise=0.0, seed=0,
           size=(1080, 1920)):
    """Landmarks of a person performing `euler_frames` (a list of {bone: degrees} dicts), seen by an
    orthographic camera: 1 m = 540 px, image centre at the hips' rest position. `yaw` turns the person about the
    vertical (degrees), `pitch` tilts the camera about its X axis, `hips` is an (n, 3) character-space
    displacement of the hips (sway, travel, height), `noise` adds white jitter (meters) to every point."""
    n = len(euler_frames)
    rng = np.random.default_rng(seed)
    world = np.zeros((n, 33, 3))
    image = np.zeros((n, 33, 3))
    hips = np.zeros((n, 3)) if hips is None else np.asarray(hips, float)
    turn, tilt = rot_y(yaw), rot_x(pitch)
    for t in range(n):
        pts, _ = skeleton(euler_frames[t], hips[t], scale)
        lmpts = char_to_landmark(pts)
        centre = (lmpts[23] + lmpts[24]) / 2
        local = (lmpts - centre) @ turn.T @ tilt.T
        world[t] = local + rng.normal(0, noise, local.shape) if noise else local
        absolute = char_to_landmark(pts) @ tilt.T
        image[t, :, 0] = (size[0] / 2 + absolute[:, 0] * 540) / size[0]
        image[t, :, 1] = (size[1] / 2 - absolute[:, 1] * 540) / size[1]
        image[t, :, 2] = 0.0
    pose_vis = np.full((n, 33), vis, np.float32) if np.isscalar(vis) else np.asarray(vis, np.float32)
    return Clip(np.arange(n) / fps, world.astype(np.float32), image.astype(np.float32), pose_vis,
                list(euler_frames), size)


def lerp_euler(a, b, t):
    """Blend two euler dicts (per axis, linear); t in 0..1."""
    keys = set(a) | set(b)
    zero = (0, 0, 0)
    return {k: tuple((1 - t) * np.array(a.get(k, zero)) + t * np.array(b.get(k, zero))) for k in keys}


def hands_up_clip(neutral=45, raise_=30, hold=30, fps=30.0, **kw):
    """Stand still with the arms down, then raise both arms straight up (through the T-pose)."""
    up = {"LeftArm": (90, 0, 0), "RightArm": (90, 0, 0)}
    frames = [dict(NEUTRAL)] * neutral
    frames += [lerp_euler(NEUTRAL, up, (i + 1) / raise_) for i in range(raise_)]
    frames += [dict(up)] * hold
    return motion(frames, fps=fps, **kw)


# ------------------------------------------------------------------ synthetic MotionClips (no solver involved)

def motion_clip(euler_frames, hips=None, fps=30.0):
    """A solve.MotionClip built straight from local Euler angles (degrees) and hips offsets, so clean-up code is
    tested without the solver. `hips` is an (n, 3) character-space displacement from the rest hips position."""
    pure_import()
    from captureforge.body import profile, quat, solve
    n = len(euler_frames)
    rot = np.zeros((n, len(profile.BONES), 4))
    for t, euler in enumerate(euler_frames):
        for i, name in enumerate(profile.NAMES):
            rot[t, i] = quat.from_matrix(euler_matrix(euler.get(name, (0, 0, 0))))
    for i in range(rot.shape[1]):
        rot[:, i] = quat.continuity(rot[:, i])
    offset = np.zeros((n, 3)) if hips is None else np.asarray(hips, float)
    return solve.MotionClip(fps=fps, times=np.arange(n) / fps, rot=rot, hips_pos=profile.HEAD[0] + offset,
                            contact=np.zeros((n, 2), bool), conf=np.ones((n, len(profile.BONES))))


def planted_clip(n=60, fps=30.0, drift=0.04):
    """Standing on straight legs. The left foot stays on the floor the whole time while the hips (and so the foot)
    slide `drift` meters along +X between frames 20 and 40 (skate); the right leg lifts at 15-20 and lands at 40-45."""
    stand = dict(NEUTRAL)
    lifted = dict(NEUTRAL, RightUpLeg=(-70, 0, 0), RightLeg=(90, 0, 0), RightFoot=(-20, 0, 0))
    frames = []
    for t in range(n):
        up = min(max((t - 15) / 5.0, 0.0), 1.0) - min(max((t - 40) / 5.0, 0.0), 1.0)
        frames.append(lerp_euler(stand, lifted, up))
    hips = np.zeros((n, 3))
    hips[:, 0] = drift * np.clip((np.arange(n) - 20) / 20.0, 0.0, 1.0)
    return motion_clip(frames, hips, fps)
