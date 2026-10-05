"""Self-check for captureforge/face/capture/calib.py, the per-actor calibration (spec 005). Synthetic score and
activity tables only: no video, tracker, camera or Blender. Needs numpy. Run: python tests/test_capture_calib.py"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "captureforge" / "face" / "capture"))
sys.path.insert(0, str(ROOT / "captureforge" / "face" / "helpers"))

FPS = 30.0


def expect_error(fn, *needles):
    import calib
    try:
        fn()
    except calib.CalibrationError as e:
        for n in needles:
            assert n in str(e), (n, str(e))
        return e
    raise AssertionError("expected CalibrationError")


# ---- script and segmentation ---------------------------------------------------------------------------------

def test_script():
    import calib
    from tracker import ARKIT_52
    ids = [s["id"] for s in calib.SCRIPT]
    assert len(ids) == 18 and len(set(ids)) == 18
    assert ids[:3] == ["jawOpen", "smile", "smileLeft"] and ids[-1] == "press"
    for s in calib.SCRIPT:
        assert s["en"] and s["pt"] and s["targets"] and set(s["targets"]) <= set(ARKIT_52), s
    by = {s["id"]: s["targets"] for s in calib.SCRIPT}
    assert by["winkLeft"] == ["eyeBlinkLeft"] and by["winkRight"] == ["eyeBlinkRight"]
    assert set(by["blink"]) == {"eyeBlinkLeft", "eyeBlinkRight"} and by["cheekPuff"] == ["cheekPuff"]


def scripted_activity(n_expr=18, hold=1.0, gap=1.0, lead=3.0, level=0.1, noise=0.002, seed=0, extra=None):
    """Times and an activity curve: `lead` s neutral, then n_expr bumps of `hold` s with `gap` s of neutral."""
    import numpy as np
    rng = np.random.default_rng(seed)
    n = int((lead + n_expr * (hold + gap) + 1.0) * FPS)
    t = np.arange(n) / FPS
    act = 0.01 + noise * rng.standard_normal(n)
    starts = [lead + k * (hold + gap) for k in range(n_expr)]
    for s in starts:
        act[(t >= s) & (t < s + hold)] += level
    for s, e in extra or ():
        act[(t >= s) & (t < e)] += level
    return t, act, starts


def test_segment_finds_each_expression():
    import calib
    t, act, starts = scripted_activity()
    segs = calib.segment(t, act)
    assert len(segs) == 18, segs
    for (a, b), s in zip(segs, starts):
        assert abs(t[a] - s) < 0.2 and abs(t[b - 1] - (s + 1.0)) < 0.2, (t[a], t[b - 1], s)


def test_segment_drops_blips_and_merges_close_runs():
    import calib
    import numpy as np
    t, act, starts = scripted_activity(extra=[(1.0, 1.08)])          # a 0.08 s twitch in the neutral lead
    gap = (t >= starts[4] + 0.45) & (t < starts[4] + 0.55)            # a 0.1 s dip inside expression 5
    act[gap] = 0.01
    segs = calib.segment(t, act)
    assert len(segs) == 18, [(round(t[a], 2), round(t[b - 1], 2)) for a, b in segs]
    assert np.isclose(t[segs[4][0]], starts[4], atol=0.2)


def test_match_script_count_mismatch_lists_segments():
    import calib
    t, act, starts = scripted_activity(n_expr=17)
    segs = calib.segment(t, act)
    e = expect_error(lambda: calib.match_script(t, segs), "17", "18")
    assert f"{starts[0]:.1f}" in str(e), str(e)  # the times of what was found
    t, act, _ = scripted_activity()
    pairs = calib.match_script(t, calib.segment(t, act))
    assert [s["id"] for s, _ in pairs] == [s["id"] for s in calib.SCRIPT]


def test_activity_ignores_head_motion():
    import calib
    import numpy as np
    rng = np.random.default_rng(1)
    base = rng.uniform(0.3, 0.7, (478, 3))
    base[:, 2] = rng.uniform(-0.05, 0.05, 478)
    n = 40
    lm = np.repeat(base[None], n, axis=0)
    for i in range(n):  # the head turns and moves in the image: no expression
        a = 0.2 * np.sin(i / 5)
        r = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        lm[i] = (base - 0.5) @ r.T * (1 + 0.1 * np.sin(i / 7)) + 0.5 + [0.02 * np.sin(i / 3), 0.01, 0]
    mouth = [0, 13, 14, 17, 61, 291]
    lm[30:, mouth, 1] += 0.03  # the jaw drops in the last 10 frames
    act = calib.activity(lm, (640, 480), np.ones(n, bool), np.arange(5))
    assert act[:30].max() < 1e-6, act[:30].max()
    assert act[30:].min() > 10 * max(act[:30].max(), 1e-9) and act[30:].min() > 0.001


def test_score_activity_fallback():
    import calib
    import numpy as np
    c = np.zeros((10, 52))
    c[3:6, 17] = 0.8
    c[4, 0] = 0.3
    a = calib.score_activity(c)
    assert a.shape == (10,) and a[0] == 0 and a[4] > a[3] > 0


if __name__ == "__main__":
    try:
        import numpy  # noqa: F401
    except ImportError:
        print("skipped: needs numpy")
        sys.exit(0)
    tests = [f for k, f in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
