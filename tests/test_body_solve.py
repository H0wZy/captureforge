"""Pure tests for the body profile, calibration and solver. Run: python tests/test_body_solve.py (needs numpy)."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures_body as fx  # noqa: E402

fx.pure_import()
from captureforge.body import calibrate, profile, solve  # noqa: E402

# ------------------------------------------------------------------ profile (T007)

REQUIRED_15 = {"Hips", "Spine", "Head",
               "LeftArm", "LeftForeArm", "LeftHand", "RightArm", "RightForeArm", "RightHand",
               "LeftUpLeg", "LeftLeg", "LeftFoot", "RightUpLeg", "RightLeg", "RightFoot"}


def test_normalise_names():
    n = fx.implemented(profile.normalise("mixamorig:Hips"))
    assert n == "Hips"
    assert profile.normalise("Hips") == "Hips"
    assert profile.normalise("mixamorig:LeftArm.001") == "LeftArm"
    assert profile.normalise("mixamorig_RightFoot") == "RightFoot"
    assert profile.normalise("LeftHand") == "LeftHand"


def test_fifteen_required_bones():
    req = fx.implemented(profile.REQUIRED)
    assert set(req) == REQUIRED_15 and len(req) == 15
    names = [b.name for b in profile.BONES]
    assert set(names) >= REQUIRED_15 and len(set(names)) == len(names)
    for b in profile.BONES:
        assert b.parent is None or names.index(b.parent) < names.index(b.name), f"{b.name}: parent must come first"


def test_validate_missing_and_extra():
    names = [b.name for b in profile.BONES]
    res = fx.implemented(profile.validate(["mixamorig:" + n for n in names]))
    assert res == ([], []), res
    got = [n for n in names if n not in ("LeftForeArm", "Head")] + ["Tail_Helper"]
    missing, extra = profile.validate(got)
    assert sorted(missing) == ["Head", "LeftForeArm"] and extra == ["Tail_Helper"]
    missing, _ = profile.validate([n for n in names if n != "Neck"])
    assert missing == [], "optional bones are not reported as missing"


def test_landmark_map_covers_required():
    lm_map = fx.implemented(profile.LANDMARK_MAP)
    for b in REQUIRED_15:
        assert b in lm_map, f"landmark map has no entry for {b}"
        a, c = lm_map[b]
        assert a != c


def test_rest_geometry():
    B = len(fx.implemented(profile.BONES))
    assert profile.HEAD.shape == (B, 3) and profile.DIR.shape == (B, 3) and profile.ROT.shape == (B, 3, 3)
    assert np.allclose(np.linalg.norm(profile.DIR, axis=1), 1)
    y = np.array([0, 1.0, 0])
    for i in range(B):
        r = profile.ROT[i]
        assert np.allclose(r @ r.T, np.eye(3), atol=1e-9) and np.linalg.det(r) > 0.99
        assert np.allclose(r @ y, profile.DIR[i], atol=1e-9), "bone Y axis points along the bone"
    idx = profile.INDEX
    for parent, child in (("LeftArm", "LeftForeArm"), ("LeftForeArm", "LeftHand"), ("LeftUpLeg", "LeftLeg"),
                          ("LeftLeg", "LeftFoot"), ("Spine", "Spine1"), ("Spine2", "Neck"), ("Neck", "Head")):
        assert np.allclose(profile.TAIL[idx[parent]], profile.HEAD[idx[child]]), f"{parent} tail meets {child} head"
    assert profile.HEAD[idx["LeftArm"]][0] > 0 > profile.HEAD[idx["RightArm"]][0], "person's left is +X"
    assert np.allclose(profile.DIR[idx["LeftArm"]], (1, 0, 0)) and np.allclose(profile.DIR[idx["LeftLeg"]], (0, 0, -1))


def test_limits_reference_known_bones():
    lim = fx.implemented(profile.LIMITS)
    for name, (lo, hi) in lim.items():
        assert name in profile.INDEX and len(lo) == 3 and len(hi) == 3
        assert all(a <= b for a, b in zip(lo, hi))
    assert "LeftForeArm" in lim and "LeftLeg" in lim


# ------------------------------------------------------------------ calibration (T009)

def test_calibrate_neutral_window():
    clip = fx.hands_up_clip(neutral=60, scale=1.1)
    c = fx.implemented(calibrate.calibrate(clip.landmarks(), neutral_seconds=1.5))
    assert c.source == "neutral" and c.window == (0, 45), (c.source, c.window)
    assert abs(c.bone_len["LeftForeArm"] - 0.26 * 1.1) < 0.005 and abs(c.bone_len["RightUpLeg"] - 0.44 * 1.1) < 0.005
    assert np.allclose(c.up, (0, 1, 0), atol=1e-3) and np.allclose(c.facing, (0, 0, 1), atol=1e-3)
    assert abs(c.floor_y - (-1.1)) < 0.01, c.floor_y
    assert abs(c.scale - 1 / 1.1) < 0.01 and c.warnings == []


def test_calibrate_up_and_facing_follow_the_camera_and_the_person():
    clip = fx.hands_up_clip(neutral=60, pitch=10, yaw=30)
    c = fx.implemented(calibrate.calibrate(clip.landmarks(), neutral_seconds=1.5))
    up = fx.rot_x(10) @ (0, 1, 0)
    fwd = fx.rot_x(10) @ fx.rot_y(30) @ (0, 0, 1)
    assert np.allclose(c.up, up, atol=1e-3), (c.up, up)
    assert np.allclose(c.facing, fwd, atol=1e-3), (c.facing, fwd)
    assert abs(np.dot(c.up, c.facing)) < 1e-6 and abs(np.linalg.norm(c.facing) - 1) < 1e-9


def test_calibrate_fallback_without_a_still_start():
    clip = fx.hands_up_clip(neutral=0, raise_=8, hold=50)  # the arms are already flying at frame 0
    c = fx.implemented(calibrate.calibrate(clip.landmarks(), neutral_seconds=1.5))
    assert c.source == "rig_default" and any("neutral" in w for w in c.warnings), (c.source, c.warnings)
    assert abs(c.bone_len["LeftArm"] - profile.LEN[profile.INDEX["LeftArm"]]) < 1e-9 and c.scale == 1.0
    assert abs(np.linalg.norm(c.up) - 1) < 1e-9


def test_calibrate_warns_when_the_body_is_cut_off():
    clip = fx.hands_up_clip(neutral=60, raise_=1, hold=1)
    clip.pose_vis[:, 25:33] = 0.1  # knees, ankles, heels, toes not seen
    c = fx.implemented(calibrate.calibrate(clip.landmarks(), neutral_seconds=1.5))
    assert any("cut off" in w for w in c.warnings), c.warnings
    assert c.source == "rig_default"


# ------------------------------------------------------------------ solver (T010)

def angle_between(a, b):
    """Angle in degrees between rotation matrices (broadcast)."""
    tr = np.einsum("...ij,...ij->...", a, b)
    return np.degrees(np.arccos(np.clip((tr - 1) / 2, -1, 1)))


POSE_A = {
    "LeftArm": (30, 20, -40), "LeftForeArm": (0, 30, -70), "LeftHand": (8, 0, 6),
    "RightArm": (-20, -10, 30), "RightForeArm": (0, -20, 60), "RightHand": (-6, 0, -5),
    "LeftUpLeg": (-20, 5, 0), "LeftLeg": (50, 0, 0), "LeftFoot": (15, 0, 0),
    "RightUpLeg": (10, -8, 0), "RightLeg": (25, 0, 0), "RightFoot": (-10, 0, 0),
    "Head": (10, 25, 5),
}


def solved(frames, keep_travel=False, **kw):
    clip = fx.motion(frames, **kw)
    lm = clip.landmarks()
    calib = calibrate.calibrate(lm, neutral_seconds=1.5)
    out = solve.solve(lm, calib, keep_travel=keep_travel)
    return clip, calib, fx.implemented(out)


def global_error(out, euler_frames, bones):
    """Max angle error per bone between the solver's global bone orientation and the oracle's."""
    G, _ = solve.fk(out.rot, out.hips_pos)
    err = {}
    for b in bones:
        i = profile.INDEX[b]
        exp = np.array([fx.skeleton(e)[1][b] for e in euler_frames])
        err[b] = angle_between(G[:len(exp), i], exp).max()
    return err


def make_calib(facing=(0, 0, 1.0)):
    return calibrate.Calibration(bone_len={}, up=np.array([0, 1.0, 0]), facing=np.array(facing),
                                 floor_y=-1.0, window=(0, 1), source="neutral", warnings=[], scale=1.0)


def test_to_character_axes():
    out = fx.implemented(solve.to_character(np.array([[1.0, 2.0, 3.0]]), make_calib()))
    assert np.allclose(out, [[1, -3, 2]]), out  # +X left stays, forward (+Z toward camera) becomes -Y, up is Z
    s, c = np.sin(np.radians(30)), np.cos(np.radians(30))
    assert np.allclose(solve.to_character(np.array([[s, 0, c]]), make_calib((s, 0, c))), [[0, -1, 0]], atol=1e-9)


def test_swing_and_twist_of_the_limbs_come_back():
    frames = [dict(fx.NEUTRAL)] * 45 + [POSE_A] * 20
    clip, calib, out = solved(frames)
    assert out.rot.shape == (65, len(profile.BONES), 4)
    limbs = ["LeftArm", "LeftForeArm", "LeftHand", "RightArm", "RightForeArm", "RightHand",
             "LeftUpLeg", "LeftLeg", "LeftFoot", "RightUpLeg", "RightLeg", "RightFoot"]
    err = global_error(out, frames, limbs)
    # the forearm roll is read from the palm, so a bent wrist leaks into it (a few degrees for these wrists)
    assert max(v for k, v in err.items() if "ForeArm" not in k) < 2.0 and max(err.values()) < 4.5, err
    err = global_error(out, frames, ["Head", "Hips"])
    assert max(err.values()) < 3.0, err


def test_straight_arm_twist_comes_from_the_palm():
    twist = dict(fx.NEUTRAL, LeftArm=(-90, 70, 0), RightArm=(-90, -40, 0))  # roll about their own axis
    frames = [dict(fx.NEUTRAL)] * 45 + [twist] * 10
    clip, calib, out = solved(frames)
    err = global_error(out, frames, ["LeftArm", "RightArm", "LeftForeArm", "LeftHand"])
    assert max(err.values()) < 2.5, err


def test_forearm_twist_follows_the_hand_with_a_bent_elbow():
    bent = dict(fx.NEUTRAL, LeftArm=(0, 0, 0), LeftForeArm=(0, 80, -90), RightArm=(0, 0, 0),
                RightForeArm=(0, -60, 100))
    frames = [dict(fx.NEUTRAL)] * 45 + [bent] * 10
    clip, calib, out = solved(frames)
    err = global_error(out, frames, ["LeftArm", "LeftForeArm", "RightArm", "RightForeArm"])
    assert max(err.values()) < 2.5, err


def test_hips_height_and_sway_and_default_drops_travel():
    crouch = dict(fx.NEUTRAL, LeftUpLeg=(-70, 0, 0), LeftLeg=(100, 0, 0), RightUpLeg=(-70, 0, 0),
                  RightLeg=(100, 0, 0), LeftFoot=(-30, 0, 0), RightFoot=(-30, 0, 0))
    frames = [dict(fx.NEUTRAL)] * 45 + [crouch] * 10
    hips = np.zeros((55, 3))
    hips[45:, 0] = 0.2  # the person slides 20 cm to the left of the picture
    clip, calib, out = solved(frames, keep_travel=True, hips=hips)
    pts, _ = fx.skeleton(crouch)
    expected_h = 1.0 - min(pts[k][2] for k in (29, 30, 31, 32))  # hips head above the lowest foot point
    assert abs(out.hips_pos[0, 2] - 1.0) < 0.01, out.hips_pos[0]
    assert abs(out.hips_pos[-1, 2] - expected_h) < 0.02, (out.hips_pos[-1, 2], expected_h)
    assert abs(out.hips_pos[-1, 0] - 0.2) < 0.02 and abs(out.hips_pos[0, 0]) < 0.01
    _, _, flat = solved(frames, hips=hips)
    assert np.abs(flat.hips_pos[:, :2]).max() < 1e-9, "horizontal travel is dropped unless keep_travel"
    assert abs(flat.hips_pos[-1, 2] - expected_h) < 0.02


def test_rotated_camera_and_person_give_the_same_rotations():
    from captureforge.body import quat
    frames = [dict(fx.NEUTRAL)] * 45 + [POSE_A] * 15
    _, _, ref = solved(frames)
    _, _, turned = solved(frames, yaw=40, pitch=10)
    err = angle_between(quat.to_matrix(ref.rot), quat.to_matrix(turned.rot))
    assert err.max() < 1.0, err.max()


def test_quaternions_are_sign_continuous_and_unit():
    clip, calib, out = solved(fx.hands_up_clip().euler, noise=0.004)
    assert np.allclose(np.linalg.norm(out.rot, axis=-1), 1, atol=1e-9)
    dots = np.sum(out.rot[1:] * out.rot[:-1], axis=-1)
    assert (dots > 0).all(), "no sign jump between frames"


def test_hands_up_fixture_end_to_end():
    clip, calib, out = solved(fx.hands_up_clip().euler)
    _, head = solve.fk(out.rot, out.hips_pos)
    ix = profile.INDEX
    top = head[-1, ix["Head"], 2] + 0.22
    assert head[-1, ix["LeftHand"], 2] > top and head[-1, ix["RightHand"], 2] > top, "both wrists above the head"
    assert head[0, ix["LeftHand"], 2] < head[0, ix["Head"], 2], "wrists start below the head"
    err = global_error(out, clip.euler[:45], ["LeftUpLeg", "LeftLeg", "RightFoot", "Head", "Hips"])
    assert max(err.values()) < 2.0, "the rest of the body stays near neutral"
    assert out.fps == 30.0 and out.times.shape == (105,) and out.flags["in_place"] is False


def test_low_confidence_range_is_bridged_not_followed():
    frames = [dict(fx.NEUTRAL)] * 45 + [fx.lerp_euler(fx.NEUTRAL, POSE_A, i / 30) for i in range(30)]
    ref = solved(frames)[2]
    clip = fx.motion(frames)
    bad = slice(60, 70)
    clip.pose_vis[bad, 11:23] = 0.0  # arms not seen
    clip.pose_world[bad, 11:23] += 0.5  # and the estimator returns garbage there
    lm = clip.landmarks()
    out = fx.implemented(solve.solve(lm, calibrate.calibrate(lm, 1.5)))
    i = profile.INDEX["LeftArm"]
    G, _ = solve.fk(out.rot, out.hips_pos)
    Gr, _ = solve.fk(ref.rot, ref.hips_pos)
    assert angle_between(G[bad, i], Gr[bad, i]).max() < 12, "bridged between the good frames on both sides"
    assert out.conf[65, i] < 0.5 and out.conf[0, i] > 0.9


def test_single_frame_flip_is_rejected():
    frames = [dict(fx.NEUTRAL)] * 45 + [POSE_A] * 15
    clip = fx.motion(frames)
    clean = solved(frames)[2]
    clip.pose_world[50, 13, 2] *= -1.0
    clip.pose_world[50, 13, 0] += 0.3  # the left elbow jumps for one frame
    lm = clip.landmarks()
    out = fx.implemented(solve.solve(lm, calibrate.calibrate(lm, 1.5)))
    i = profile.INDEX["LeftArm"]
    G, _ = solve.fk(out.rot, out.hips_pos)
    Gc, _ = solve.fk(clean.rot, clean.hips_pos)
    assert angle_between(G[50, i], Gc[50, i]) < 5, "the one-frame spike must not reach the clip"


def test_retarget_to_the_canonical_rest_frames_changes_nothing_and_follows_rolled_rigs():
    clip, calib, out = solved(fx.hands_up_clip().euler)
    present = np.ones(len(profile.BONES), bool)
    same = fx.implemented(solve.retarget(out.rot, profile.ROT, profile.PARENT, present))
    assert np.allclose(np.abs(np.sum(same * out.rot, axis=-1)), 1, atol=1e-9)
    # a rig with every bone rolled 40 degrees about its own Y axis: global poses must stay identical
    roll = fx.euler_matrix((0, 40, 0))
    rest = np.array([r @ roll for r in profile.ROT])
    rolled = solve.retarget(out.rot, rest, profile.PARENT, present)
    from captureforge.body import quat
    local = quat.to_matrix(rolled)
    P = np.empty((len(local), len(profile.BONES), 3, 3))
    for i, p in enumerate(profile.PARENT):  # the rolled rig's own chain: P = P_parent (Rp^T R) B, root: R B
        P[:, i] = rest[i] @ local[:, i] if p < 0 else P[:, p] @ (rest[p].T @ rest[i]) @ local[:, i]
    G, _ = solve.fk(out.rot, out.hips_pos)
    for i in range(len(profile.BONES)):
        assert angle_between(P[:, i], G[:, i] @ rest[i]).max() < 0.01, profile.NAMES[i]


def test_from_file_reads_resamples_calibrates_and_solves():
    import tempfile
    clip = fx.hands_up_clip(neutral=100, raise_=30, hold=30, fps=60.0)
    clip.pose_vis[130:134] = 0.0
    clip.pose_world[130:134] = np.nan
    path = clip.save(os.path.join(tempfile.mkdtemp(), "hands_up.npz"))
    res = fx.implemented(solve.from_file(path, fps=30.0))
    assert abs(res.clip.fps - 30.0) < 1e-9 and len(res.clip.times) == 80, len(res.clip.times)
    assert res.calib.source == "neutral" and res.lm.gaps and any("no person" in w.lower() for w in res.warnings)
    kept = solve.from_file(path, keep_source_fps=True)
    assert abs(kept.clip.fps - 60.0) < 1e-6 and len(kept.clip.times) == 160


if __name__ == "__main__":
    fx.run_all(globals())
