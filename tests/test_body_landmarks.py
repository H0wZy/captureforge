"""Pure tests for captureforge/body/landmarks.py. Run: python tests/test_body_landmarks.py (needs numpy)."""

import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures_body as fx  # noqa: E402

fx.pure_import()
from captureforge.body import landmarks  # noqa: E402

TMP = tempfile.mkdtemp()
COUNTER = [0]


def make(n=10, fps=30.0, **kw):
    """A tiny valid file: landmark 0 moves along x at 1 m/s, the rest sit still."""
    times = kw.pop("times", np.arange(n) / fps)
    pw = np.zeros((len(times), 33, 3), np.float32)
    pw[:, 0, 0] = times
    COUNTER[0] += 1
    path = os.path.join(TMP, f"lm_{COUNTER[0]}.npz")
    fx.write_landmarks(path, times, pw, **kw)
    return path


def raises(fn, text):
    try:
        fn()
    except ValueError as e:
        assert text.lower() in str(e).lower(), f"message {e!r} should mention {text!r}"
        return
    except Exception as e:  # noqa: BLE001
        raise AssertionError(f"expected ValueError, got {type(e).__name__}: {e}")
    raise AssertionError("expected ValueError")


def test_read_roundtrip():
    lm = fx.implemented(landmarks.read(make(10, 30.0)))
    assert lm.pose_world.shape == (10, 33, 3) and lm.pose_vis.shape == (10, 33)
    assert lm.times.shape == (10,) and abs(lm.fps_source - 30.0) < 1e-6 and lm.size == (1080, 1920)
    assert lm.hands_world is None and lm.head_box is None and lm.meta["model_variant"] == "heavy"
    assert lm.gaps == [] and lm.valid.all()


def test_missing_key_and_bad_version():
    path = make()
    d = dict(np.load(path, allow_pickle=False))
    del d["pose_vis"]
    p2 = os.path.join(TMP, "nokey.npz")
    np.savez(p2, **d)
    fx.implemented(getattr(landmarks, "read", None))
    raises(lambda: landmarks.read(p2), "pose_vis")
    raises(lambda: landmarks.read(make(version=2)), "version")
    raises(lambda: landmarks.read(os.path.join(TMP, "nope.npz")), "not found")


def test_shape_mismatch_and_too_short():
    path = make(10)
    d = dict(np.load(path, allow_pickle=False))
    d["pose_vis"] = d["pose_vis"][:5]
    p2 = os.path.join(TMP, "shape.npz")
    np.savez(p2, **d)
    fx.implemented(getattr(landmarks, "read", None))
    raises(lambda: landmarks.read(p2), "shape")
    raises(lambda: landmarks.read(make(1, times=[0.0])), "at least 2")
    bad = make(5)
    d = dict(np.load(bad, allow_pickle=False))
    d["times"] = np.array([0, 0.1, 0.1, 0.3, 0.4])
    p3 = os.path.join(TMP, "times.npz")
    np.savez(p3, **d)
    raises(lambda: landmarks.read(p3), "increasing")


def test_nan_gap_hold():
    times = np.arange(10) / 30.0
    pw = np.zeros((10, 33, 3), np.float32)
    pw[:, 0, 0] = np.arange(10)
    pw[0:2] = np.nan  # leading gap
    pw[5:8] = np.nan  # middle gap
    path = os.path.join(TMP, "gap.npz")
    fx.write_landmarks(path, times, pw)
    lm = fx.implemented(landmarks.read(path))
    assert lm.gaps == [(0, 2), (5, 8)], lm.gaps
    assert np.isfinite(lm.pose_world).all()
    assert lm.pose_world[0, 0, 0] == 2 and lm.pose_world[1, 0, 0] == 2, "leading gap holds the first good frame"
    assert [lm.pose_world[i, 0, 0] for i in (5, 6, 7)] == [4, 4, 4], "middle gap holds the last good frame"
    assert list(lm.valid) == [False] * 2 + [True] * 3 + [False] * 3 + [True] * 2
    assert (lm.pose_vis[~lm.valid] == 0).all(), "held frames carry zero confidence"
    allnan = os.path.join(TMP, "allnan.npz")
    fx.write_landmarks(allnan, times, np.full((10, 33, 3), np.nan, np.float32))
    raises(lambda: landmarks.read(allnan), "no person")


def test_resample_variable_rate():
    # Variable frame rate: timestamps jitter around 30 fps; landmark 0 moves at exactly 1 m/s along x.
    rng = np.random.default_rng(3)
    times = np.cumsum(rng.uniform(0.02, 0.05, 40))
    times -= times[0]
    lm = fx.implemented(landmarks.read(make(times=times)))
    out = fx.implemented(landmarks.resample(lm, 30.0))
    assert np.allclose(np.diff(out.times), 1 / 30.0)
    assert abs(out.times[-1] - times[-1]) < 1 / 30.0 and out.times[0] == 0
    assert np.allclose(out.pose_world[:, 0, 0], out.times, atol=1e-5), "linear motion must stay linear"
    assert out.pose_world.shape[0] == len(out.times) == out.pose_vis.shape[0]
    assert abs(out.fps - 30.0) < 1e-9


def test_resample_keep_source_rate():
    # The file claims 25 fps but the real timestamps run at 60: times win, "keep source" uses fps_source.
    lm = fx.implemented(landmarks.read(make(61, 60.0, fps_source=25.0)))
    out = fx.implemented(landmarks.resample(lm, None))
    assert abs(out.fps - 25.0) < 1e-9 and np.allclose(np.diff(out.times), 1 / 25.0)
    assert np.allclose(out.pose_world[:, 0, 0], out.times, atol=1e-5)


# ------------------------------------------------------------------ capture check (T041)

def good_lm(n=60, fps=30.0, **kw):
    path = make(n, fps, **kw)
    lm = landmarks.read(path)
    lm.pose_image[:] = 0.5  # everything well inside the picture
    return lm


def test_capture_check_is_quiet_on_a_good_take():
    lm = good_lm()
    assert fx.implemented(landmarks.capture_check(lm)) == []


def test_capture_check_flags_a_low_frame_rate():
    for fps in (24.0, 25.0):
        warns = fx.implemented(landmarks.capture_check(good_lm(60, fps)))
        assert len(warns) == 1 and "fps" in warns[0] and "30" in warns[0], warns
    assert landmarks.capture_check(good_lm(120, 60.0)) == []
    # the timestamps decide, not the nominal rate the container claims
    lm = good_lm(60, 24.0, fps_source=30.0)
    assert any("24" in w for w in landmarks.capture_check(lm))
    assert landmarks.container_warnings(24.0) and not landmarks.container_warnings(30.0)


def test_capture_check_flags_a_body_out_of_frame():
    lm = good_lm()
    lm.pose_image[:30, 27:33, 1] = 1.2  # the feet are below the picture for half the clip
    warns = fx.implemented(landmarks.capture_check(lm))
    assert len(warns) == 1 and "frame" in warns[0] and "50%" in warns[0], warns
    lm.pose_image[:] = 0.5
    lm.pose_image[:3, 11, 0] = -0.1  # three stray frames are not worth a warning
    assert landmarks.capture_check(lm) == []


def test_capture_check_flags_low_confidence_and_several_people():
    lm = good_lm()
    lm.pose_vis[:, 11:33] = 0.3
    warns = fx.implemented(landmarks.capture_check(lm))
    assert len(warns) == 1 and "confidence" in warns[0], warns
    lm = good_lm()
    lm.meta["people_seen"] = 3
    warns = landmarks.capture_check(lm)
    assert len(warns) == 1 and "3 people" in warns[0], warns
    lm = good_lm()
    lm.valid[:] = False  # frames held for lack of a person do not count towards the picture or the confidence
    lm.pose_vis[:] = 0.0
    assert landmarks.capture_check(lm) == [], "the gaps are reported separately"


def test_face_pixels_is_the_median_head_box_side():
    lm = good_lm()
    assert fx.implemented(getattr(landmarks, "face_pixels", None))(lm) is None, "no head box in the file"
    lm.head_box = np.tile(np.array([0.4, 0.1, 0.5, 0.15], np.float32), (60, 1))  # 0.1 * 1080 wide
    assert abs(landmarks.face_pixels(lm) - 108.0) < 1e-3
    assert landmarks.face_too_small(lm) is False
    lm.head_box = np.tile(np.array([0.4, 0.1, 0.45, 0.15], np.float32), (60, 1))  # 54 px: too small to track
    assert landmarks.face_too_small(lm) is True


if __name__ == "__main__":
    fx.run_all(globals())
