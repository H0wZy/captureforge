"""Pure tests for filters, foot contact and lock, clip operations and the quality report.
Run: python tests/test_body_cleanup.py (needs numpy)."""

import json
import os
import struct
import sys
import tempfile
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures_body as fx  # noqa: E402

fx.pure_import()
from captureforge.body import clipops, contact, filters, profile, quat, report, solve  # noqa: E402

TMP = tempfile.mkdtemp()
IX = profile.INDEX


def jitter(a):
    """Mean absolute second difference along time, computed here independently of the report module."""
    return float(np.mean(np.abs(a[2:] - 2 * a[1:-1] + a[:-2])))


def angle_deg(q1, q2):
    return np.degrees(quat.angle(quat.mul(q1, quat.conj(q2))))


# ------------------------------------------------------------------ filters (T022)

def test_one_euro_is_causal_and_lags_a_step():
    t = np.arange(90) / 30.0
    x = np.where(t < 1.5, 0.0, 1.0)[:, None] * np.array([[1.0, 0.0, 0.0]])
    out = fx.implemented(filters.one_euro(x, 30.0))
    assert out.shape == x.shape and abs(out[0, 0]) < 1e-9
    assert 0.0 < out[45, 0] < 1.0, "the step is not followed instantly"
    assert out[-1, 0] > 0.95, "but it is reached"
    x2 = x.copy()
    x2[60:] = 7.0  # a different future
    out2 = filters.one_euro(x2, 30.0)
    assert np.allclose(out[:60], out2[:60]), "causal: frames before the change are untouched"


def test_one_euro_smooths_a_still_pose_and_follows_fast_motion():
    rng = np.random.default_rng(2)
    still = rng.normal(0, 0.01, (120, 3))
    sm = fx.implemented(filters.one_euro(still, 30.0))
    assert jitter(sm) < 0.4 * jitter(still)
    q = quat.from_euler(np.radians(np.stack([np.linspace(0, 120, 60), 0 * np.arange(60), 0 * np.arange(60)], -1)))
    out = filters.one_euro_quat(q, 30.0)
    assert out.shape == q.shape and np.allclose(np.linalg.norm(out, axis=-1), 1)
    assert angle_deg(out[-1], q[-1]) < 20, "a fast sweep is followed (the filter opens up with speed)"
    assert (np.sum(out[1:] * out[:-1], axis=-1) > 0).all()


def test_zero_phase_butterworth_has_no_lag_and_removes_jitter():
    fps = 30.0
    t = np.arange(150) / fps
    clean = np.sin(2 * np.pi * 1.0 * t)
    rng = np.random.default_rng(5)
    noisy = clean + rng.normal(0, 0.05, t.shape)
    out = fx.implemented(filters.zero_phase(noisy[:, None], fps, 6.0))[:, 0]
    assert out.shape == t.shape
    lag = np.argmax(np.correlate(out - out.mean(), clean - clean.mean(), "full")) - (len(t) - 1)
    assert lag == 0, f"zero phase: the lag must be 0 frames, got {lag}"
    assert jitter(out - clean) < 0.3 * jitter(noisy - clean), "injected jitter falls by at least 70 percent"
    assert np.sqrt(np.mean((out - clean)[10:-10] ** 2)) < 0.04, "rms error is well under the 0.05 noise level"
    shape = fx.implemented(filters.zero_phase(np.zeros((40, 2, 3)) + 1.0, fps, 6.0))
    assert shape.shape == (40, 2, 3) and np.allclose(shape, 1.0, atol=1e-9), "a constant stays constant, any shape"


def test_peaks_of_a_fast_gesture_keep_their_amplitude():
    fps = 30.0
    t = np.arange(90) / fps
    bump = np.exp(-0.5 * ((t - 1.5) / 0.12) ** 2)  # a quick flick about a quarter second wide
    out = fx.implemented(filters.zero_phase(bump[:, None], fps, 6.0))[:, 0]
    assert out.max() >= 0.85 * bump.max(), out.max()
    assert abs(np.argmax(out) - np.argmax(bump)) == 0


def test_quaternion_smoothing_survives_sign_flips():
    angles = np.radians(40) * np.sin(2 * np.pi * 0.7 * np.arange(120) / 30.0)
    q = quat.from_euler(np.stack([angles, 0 * angles, 0 * angles], -1))
    flipped = q.copy()
    flipped[::3] *= -1  # q and -q are the same rotation
    rng = np.random.default_rng(1)
    noisy = quat.normalize(flipped + rng.normal(0, 0.01, flipped.shape))
    out = fx.implemented(filters.smooth_quat(noisy, 30.0, 6.0))
    assert np.allclose(np.linalg.norm(out, axis=-1), 1)
    assert (np.sum(out[1:] * out[:-1], axis=-1) > 0).all(), "sign continuous"
    err = np.degrees(quat.angle(quat.mul(out, quat.conj(q))))
    assert err[10:-10].max() < 3.0, err.max()


# ------------------------------------------------------------------ foot contact and lock (T023)

def ankles(clip):
    _, head = solve.fk(clip.rot, clip.hips_pos)
    return head[:, [IX["LeftFoot"], IX["RightFoot"]]]


def skate(clip, foot, mask):
    """Mean horizontal speed in cm/s of an ankle over the steps that start on `mask` frames (independent of report)."""
    p = ankles(clip)[:, foot, :2]
    speed = np.linalg.norm(np.diff(p, axis=0), axis=1) * clip.fps * 100
    return float(speed[mask[:-1]].mean())


def test_planted_frames_are_detected_with_hysteresis():
    clip = fx.planted_clip()
    flags = fx.implemented(contact.detect(ankles(clip), clip.fps))
    assert flags.shape == (60, 2) and flags.dtype == bool
    assert flags[:, 0].all(), "the left foot never leaves the floor"
    right = flags[:, 1]
    assert right[:10].all() and right[50:].all() and not right[20:40].any(), right
    assert np.count_nonzero(np.diff(right.astype(int))) == 2, "one lift and one landing, no flicker"
    # a foot hovering still, touching the floor for only 3 frames (0.1 s): too short to be a plant; 6 frames count
    p = np.zeros((60, 2, 3))
    p[:, :, 2] = 0.30
    p[10:13, 1, 2] = 0.10
    p[20:26, 1, 2] = 0.10
    brief = contact.detect(p, 30.0)
    assert not brief[8:15, 1].any(), "shorter than the minimum duration"
    assert brief[21:25, 1].all(), "a long enough touch is a plant"


def test_foot_lock_removes_skate_and_keeps_the_leg_valid():
    clip = fx.planted_clip()
    clip = clip.replace(contact=contact.detect(ankles(clip), clip.fps))
    before = skate(clip, 0, clip.contact[:, 0])
    assert before > 2.0, f"fixture should skate, got {before:.2f} cm/s"
    out = fx.implemented(contact.lock(clip))
    after = skate(out, 0, out.contact[:, 0])
    assert after < 0.5, f"planted foot must not slide, got {after:.2f} cm/s"
    G, head = solve.fk(out.rot, out.hips_pos)
    ix = IX
    up, knee, ank = (head[:, ix[n]] for n in ("LeftUpLeg", "LeftLeg", "LeftFoot"))
    assert np.allclose(np.linalg.norm(knee - up, axis=1), profile.LEN[ix["LeftUpLeg"]], atol=1e-9), "thigh length kept"
    assert np.allclose(np.linalg.norm(ank - knee, axis=1), profile.LEN[ix["LeftLeg"]], atol=1e-9), "shin length kept"
    flex = np.degrees(quat.to_euler(out.rot[:, ix["LeftLeg"]]))[:, 0]
    assert flex.min() > -6 and flex.max() < 156, "knee stays inside its limits"
    assert np.abs(out.hips_pos[:, 2] - clip.hips_pos[:, 2]).max() < 0.02, "hips height barely changes"
    right_before, right_after = ankles(clip)[:, 1], ankles(out)[:, 1]
    assert np.allclose(right_before[20:40], right_after[20:40], atol=0.03), "the lifted foot is left alone"
    assert out.flags["lock_left"] and out.flags["lock_right"]


def test_foot_lock_can_be_switched_off_per_foot_and_per_range():
    clip = fx.planted_clip()
    clip = clip.replace(contact=contact.detect(ankles(clip), clip.fps))
    off_left = contact.lock(clip, left=False)
    assert np.allclose(off_left.rot, clip.rot) and np.allclose(off_left.hips_pos, clip.hips_pos)
    assert off_left.flags["lock_left"] is False
    ranged = contact.lock(clip, off_ranges=[(20, 40)])
    assert np.allclose(ranged.rot[20:40], clip.rot[20:40]), "frames in the range are untouched"
    assert skate(ranged, 0, np.arange(60) < 20) < 0.5 and skate(ranged, 0, (np.arange(60) >= 20) & (np.arange(60) < 40)) > 2


# ------------------------------------------------------------------ clip operations (T024)

def test_in_place_keeps_height_and_removes_drift():
    clip = fx.planted_clip(drift=0.5)
    clip = clip.replace(hips_pos=clip.hips_pos + np.array([0, 0, 0.1]) * np.sin(np.arange(60) / 5.0)[:, None])
    out = fx.implemented(clipops.in_place(clip))
    assert np.allclose(out.hips_pos[:, :2], clip.hips_pos[0, :2]), "no horizontal drift"
    assert np.allclose(out.hips_pos[:, 2], clip.hips_pos[:, 2]), "height is kept"
    assert np.allclose(out.rot, clip.rot) and out.flags["in_place"] is True


def test_trim_keeps_a_frame_range():
    clip = fx.planted_clip()
    out = fx.implemented(clipops.trim(clip, 10, 29))
    assert len(out.times) == 20 and out.rot.shape[0] == 20 and out.times[0] == 0
    assert np.allclose(out.rot, clip.rot[10:30]) and out.contact.shape == (20, 2) and out.conf.shape[0] == 20
    assert len(clipops.trim(clip, 0, None).times) == 60 and len(clipops.trim(clip, 5, 0).times) == 55, "0 = the end"


def dance(n=60):
    frames = [{"LeftArm": (-90 + 30 * np.sin(2 * np.pi * t / 40.0), 0, 0), "RightArm": (-90, 0, 0),
               "Head": (0, 15 * np.sin(2 * np.pi * t / 40.0 + 1), 0)} for t in range(n)]
    hips = np.zeros((n, 3))
    hips[:, 2] = 0.03 * np.sin(2 * np.pi * np.arange(n) / 40.0)
    return fx.motion_clip(frames, hips)  # 60 frames of a 40-frame cycle: the end does not match the start


def test_loop_closer_matches_first_and_last_frame():
    clip = dance()
    gap = angle_deg(clip.rot[-1], clip.rot[0]).max()
    assert gap > 5, "the fixture must not loop by itself"
    out = fx.implemented(clipops.loop(clip, 10))
    assert angle_deg(out.rot[-1], out.rot[0]).max() < 0.01 and np.allclose(out.hips_pos[-1], out.hips_pos[0])
    assert np.allclose(out.rot[:49], clip.rot[:49]), "only the last blend frames change"
    steps = angle_deg(out.rot[1:], out.rot[:-1]).max(axis=1)
    wrap = angle_deg(out.rot[0], out.rot[-1]).max()
    assert steps.max() < 10 and wrap < 0.01, "no pop at the seam"
    assert out.flags["looped"] is True


def test_mirror_swaps_left_and_right():
    frames = [dict(fx.NEUTRAL, LeftArm=(90, 0, 0), LeftForeArm=(0, 20, -60), Head=(0, 30, 0), LeftUpLeg=(-40, 0, 0))
              for _ in range(5)]
    clip = fx.motion_clip(frames, np.tile([0.1, 0.0, 0.0], (5, 1)))
    clip = clip.replace(contact=np.array([[True, False]] * 5), conf=np.tile(np.linspace(0.2, 1, len(profile.BONES)), (5, 1)))
    out = fx.implemented(clipops.mirror(clip))
    G0, h0 = solve.fk(clip.rot, clip.hips_pos)
    G1, h1 = solve.fk(out.rot, out.hips_pos)
    M = np.diag([-1.0, 1.0, 1.0])
    for left, right in (("LeftArm", "RightArm"), ("LeftForeArm", "RightForeArm"), ("LeftHand", "RightHand"),
                        ("LeftUpLeg", "RightUpLeg"), ("LeftFoot", "RightFoot")):
        want = M @ G0[0, IX[left]] @ M
        assert np.degrees(np.arccos(np.clip((np.trace(G1[0, IX[right]].T @ want) - 1) / 2, -1, 1))) < 0.05, right
        want = M @ G0[0, IX[right]] @ M
        assert np.degrees(np.arccos(np.clip((np.trace(G1[0, IX[left]].T @ want) - 1) / 2, -1, 1))) < 0.05, left
    for c in ("Head", "Hips", "Spine"):
        want = M @ G0[0, IX[c]] @ M
        assert np.degrees(np.arccos(np.clip((np.trace(G1[0, IX[c]].T @ want) - 1) / 2, -1, 1))) < 0.05, c
    assert np.allclose(out.hips_pos[:, 0], -0.1 + 0.0) and np.allclose(out.hips_pos[:, 2], clip.hips_pos[:, 2])
    assert out.contact[0].tolist() == [False, True] and out.flags["mirrored"] is True
    assert np.isclose(out.conf[0, IX["RightArm"]], clip.conf[0, IX["LeftArm"]])
    back = clipops.mirror(out)
    assert np.abs(np.sum(back.rot * clip.rot, axis=-1)).min() > 1 - 1e-9 and back.flags["mirrored"] is False


# ------------------------------------------------------------------ report (T025)

def test_report_numbers_match_independent_values():
    clip = fx.planted_clip()
    clip = clip.replace(contact=contact.detect(ankles(clip), clip.fps))
    rep = fx.implemented(report.build(clip))
    expected = skate(clip, 0, clip.contact[:, 0])
    assert abs(rep["skate_cm_s"]["left"] - expected) < 1e-6, (rep["skate_cm_s"], expected)
    hips = clip.hips_pos[:, :2]
    by_hand = np.linalg.norm(np.diff(hips, axis=0), axis=1)[clip.contact[:-1, 0]].mean() * clip.fps * 100
    assert abs(rep["skate_cm_s"]["left"] - by_hand) < 1e-6, "the planted ankle moves exactly like the hips"
    q = clip.rot
    assert abs(rep["jitter"] - jitter(q)) < 1e-12
    assert rep["limit_violations"] == {} and rep["low_conf_ranges"] == [] and rep["warnings"] == []


def test_report_limit_violations_and_low_confidence_ranges():
    frames = [dict(fx.NEUTRAL) for _ in range(30)]
    for t in range(10, 15):
        frames[t] = dict(fx.NEUTRAL, LeftForeArm=(0, 0, 40))  # the elbow bent backwards (limit: -155..5 degrees)
    clip = fx.motion_clip(frames)
    conf = np.ones_like(clip.conf)
    conf[8:16, IX["LeftArm"]] = 0.2
    conf[8:16, IX["LeftForeArm"]] = 0.3
    conf[20:25, IX["RightUpLeg"]] = 0.1
    rep = fx.implemented(report.build(clip.replace(conf=conf)))
    assert rep["limit_violations"] == {"LeftForeArm": 5}, rep["limit_violations"]
    assert [list(r) for r in rep["low_conf_ranges"]] == [[8, 16, "left arm"], [20, 25, "right leg"]], rep["low_conf_ranges"]


def test_report_bone_drift_and_warnings_from_the_landmarks():
    clip = fx.hands_up_clip(neutral=60, raise_=10, hold=5)
    lm = clip.landmarks()
    from captureforge.body import calibrate
    calib = calibrate.calibrate(lm, 1.5)
    stretched = lm.replace(pose_world=lm.pose_world.copy(), meta={"warnings": ["The video is 24 fps."]})
    stretched.pose_world[70, 15] = stretched.pose_world[70, 13] + (
        stretched.pose_world[70, 15] - stretched.pose_world[70, 13]) * 1.12  # the left forearm grows 12 percent
    fit = solve.solve(stretched, calib)
    rep = fx.implemented(report.build(fit, stretched, calib))
    seg = np.linalg.norm(stretched.pose_world[:, 15] - stretched.pose_world[:, 13], axis=1)
    want = float(np.abs(seg / calib.bone_len["LeftForeArm"] - 1).max())
    assert abs(rep["bone_drift"]["LeftForeArm"] - want) < 1e-6 and 0.11 < want < 0.13
    assert rep["bone_drift"]["RightForeArm"] < 1e-4
    assert rep["warnings"] == ["The video is 24 fps."]


def test_report_json_roundtrip_and_text():
    clip = fx.planted_clip()
    clip = clip.replace(contact=contact.detect(ankles(clip), clip.fps))
    rep = fx.implemented(report.build(clip))
    path = os.path.join(TMP, "report.json")
    report.write(path, rep)
    assert report.read(path) == json.loads(json.dumps(rep))
    text = report.text(rep)
    assert "skate" in text.lower() and "jitter" in text.lower() and "cm/s" in text


def test_filmstrip_is_a_valid_png_grid():
    clip = fx.planted_clip()
    img = fx.implemented(report.filmstrip(clip, columns=4, rows=2, tile=(90, 120)))
    assert img.shape == (240, 360, 4) and img.dtype == np.uint8
    assert len(np.unique(img.reshape(-1, 4), axis=0)) > 3, "something is drawn"
    path = os.path.join(TMP, "filmstrip.png")
    report.write_png(path, img)
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (360, 240)
    pos, raw = 8, b""
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind == b"IDAT":
            raw += data[pos + 8:pos + 8 + n]
        pos += 12 + n
    assert len(zlib.decompress(raw)) == height * (1 + width * 4)


if __name__ == "__main__":
    fx.run_all(globals())
