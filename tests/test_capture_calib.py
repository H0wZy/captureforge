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


# ---- learning and applying -----------------------------------------------------------------------------------

TRUE_PEAK = {"eyeBlinkLeft": 0.6, "eyeBlinkRight": 0.6, "mouthFrownLeft": 0.33, "mouthFrownRight": 0.33,
             "browInnerUp": 0.5, "cheekPuff": 0.0, "noseSneerLeft": 0.0, "noseSneerRight": 0.0}
TRUE_LEAK = {("eyeSquintLeft", "mouthSmileLeft"): 0.4, ("eyeSquintRight", "mouthSmileRight"): 0.4,
             ("eyeLookDownLeft", "eyeBlinkLeft"): 0.5, ("eyeLookDownRight", "eyeBlinkRight"): 0.5,
             ("mouthUpperUpLeft", "mouthSmileLeft"): 0.6, ("mouthDimpleRight", "mouthPucker"): 0.3}


def synthetic_take(seed=0, noise=0.01, mirrored=False):
    """(names, times, c, act) of a scripted take: each expression drives its targets to TRUE_PEAK (default 0.9)
    times a hold-shaped envelope; TRUE_LEAK copies a share of a target into a key that is never a target."""
    import calib
    import numpy as np
    from tracker import ARKIT_52
    names = list(ARKIT_52)
    col = {n: i for i, n in enumerate(names)}
    t, act, starts = scripted_activity(seed=seed)
    c = np.zeros((len(t), len(names)))
    for entry, s0 in zip(calib.SCRIPT, starts):
        env = np.clip(np.minimum(t - s0, s0 + 1.0 - t) / 0.15, 0, 1)
        for k in entry["targets"]:
            c[:, col[k]] += TRUE_PEAK.get(k, 0.9) * env
    for (j, i), w in TRUE_LEAK.items():
        c[:, col[j]] += w * c[:, col[i]]
    c = np.clip(c + noise * np.random.default_rng(seed + 7).standard_normal(c.shape), 0, 1)
    if mirrored:
        c = c[:, [col[calib.mirror_name(n)] for n in names]]
    return names, t, c, act


def learned(seed=0, mirrored=False):
    import calib
    names, t, c, act = synthetic_take(seed, mirrored=mirrored)
    pairs = calib.match_script(t, calib.segment(t, act))
    return calib.learn(names, c, act, pairs, label="test actor"), names, t, c, act


def test_learn_recovers_gains_and_crosstalk():
    prof, *_ = learned()
    g = prof["gains"]
    for k, peak in TRUE_PEAK.items():
        if peak:
            assert abs(g[k] - 1 / peak) / (1 / peak) < 0.05 or (1 / peak > 4 and g[k] == 4.0), (k, g[k])
    assert abs(g["jawOpen"] - 1 / 0.9) < 0.06 and abs(g["mouthSmileLeft"] - 1 / 0.9) < 0.06
    for (j, i), w in TRUE_LEAK.items():
        assert abs(prof["crosstalk"].get(j, {}).get(i, 0.0) - w) < 0.05, (j, i, prof["crosstalk"].get(j))
    spurious = [(j, i, w) for j, row in prof["crosstalk"].items() for i, w in row.items() if (j, i) not in TRUE_LEAK]
    assert not spurious, spurious
    assert set(prof["undetected"]) == {"cheekPuff", "noseSneerLeft", "noseSneerRight"}
    assert all(prof["gains"][k] == 1.0 for k in prof["undetected"])
    assert prof["mirrored"] is False and prof["label"] == "test actor" and prof["version"] == 1


def test_gain_bounds():
    import calib
    assert calib.gain_for(0.1) == 4.0 and calib.gain_for(0.95) == 1.0 / 0.95 and calib.gain_for(1.2) == 1.0


def test_apply_corrects_a_held_out_take():
    import calib
    import numpy as np
    prof, names, *_ = learned(seed=0)
    names, t, c, act = synthetic_take(seed=3)  # another take, other noise
    y = calib.apply(prof, names, c)
    col = {n: i for i, n in enumerate(names)}
    for entry, (a, b) in calib.match_script(t, calib.segment(t, act)):
        hold = slice(a + 5, b - 5)
        for k in entry["targets"]:
            if k not in prof["undetected"]:
                assert y[hold, col[k]].max() > 0.9, (entry["id"], k, y[hold, col[k]].max())
    for j, _ in TRUE_LEAK:
        assert y[:, col[j]].max() < 0.1, (j, y[:, col[j]].max())
    assert np.all((y >= 0) & (y <= 1))


def test_apply_without_profile_and_absent_columns():
    import calib
    import numpy as np
    prof, names, t, c, _ = learned()
    assert np.array_equal(calib.apply(None, names, c), c)
    keep = [n for n in names if n not in ("eyeSquintLeft", "mouthSmileRight")]
    sub = c[:, [names.index(n) for n in keep]]
    y = calib.apply(prof, keep, sub)
    assert y.shape == sub.shape
    full = calib.apply(prof, names, c)
    j = keep.index("eyeBlinkLeft")
    assert np.allclose(y[:, j], full[:, names.index("eyeBlinkLeft")], atol=1e-9)


def test_mirrored_recording():
    import calib
    import numpy as np
    prof, names, *_ = learned()
    mprof, *_ = learned(mirrored=True)
    assert mprof["mirrored"] is True
    for k in ("eyeBlinkLeft", "mouthSmileLeft", "mouthFrownRight"):
        assert abs(mprof["gains"][k] - prof["gains"][k]) < 0.05, k
    _, _, c, _ = synthetic_take(seed=3)
    _, _, cm, _ = synthetic_take(seed=3, mirrored=True)
    assert np.allclose(calib.apply(mprof, names, cm), calib.apply(prof, names, c), atol=0.03)
    assert calib.mirror_name("mouthLeft") == "mouthRight" and calib.mirror_name("jawOpen") == "jawOpen"


def test_profile_file_round_trip():
    import calib
    import json
    import os
    import tempfile
    prof, *_ = learned()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "me.faceprofile.json")
        calib.save_profile(prof, path)
        assert calib.load_profile(path) == json.loads(json.dumps(prof))
        bad = dict(prof, version=99)
        with open(path, "w") as f:
            json.dump(bad, f)
        expect_error(lambda: calib.load_profile(path), "version")
        with open(path, "w") as f:
            json.dump({"format": "something else"}, f)
        expect_error(lambda: calib.load_profile(path), "profile")


# ---- report and evaluation -------------------------------------------------------------------------------------

def test_evaluate_on_a_held_out_take():
    import calib
    prof, *_ = learned(seed=0)
    names, t, c, act = synthetic_take(seed=3)
    pairs = calib.match_script(t, calib.segment(t, act))
    ev = calib.evaluate(prof, names, c, act, pairs)
    b, a = ev["before"], ev["after"]
    assert len(ev["expressions"]) == 18
    assert a["hits"] >= 15 and a["hits"] >= b["hits"], (b["hits"], a["hits"])
    assert a["median_peak"] >= 0.85 > b["median_peak"] - 0.3, (b["median_peak"], a["median_peak"])
    assert a["leak"] <= 0.5 * b["leak"], (b["leak"], a["leak"])
    assert a["neutral"] <= b["neutral"] + 0.05
    row = next(r for r in ev["expressions"] if r["id"] == "blink")
    assert row["peak_before"] < 0.7 and row["peak_after"] > 0.9 and row["leak_after"] < row["leak_before"]
    assert next(r for r in ev["expressions"] if r["id"] == "cheekPuff")["undetected"]


def test_report_lines():
    import calib
    prof, names, t, c, act = learned()
    ev = calib.evaluate(prof, names, c, act, calib.match_script(t, calib.segment(t, act)))
    lines = calib.report_lines(prof, ev)
    text = "\n".join(lines)
    assert "Blink both eyes" in text and "not detected" in text and "cheekPuff" in text
    assert any(l.startswith("Target key strongest") for l in lines)
    assert "mirrored" not in text.lower() or "not mirrored" in text.lower()


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
