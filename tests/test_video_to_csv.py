"""Self-check for the pure parts of video_to_csv.py. Run: python tests/test_video_to_csv.py
Needs no mediapipe/opencv. The CSV round-trip uses FaceForge's own mocap.read_csv when numpy is
available (bpy is stubbed), otherwise that step is skipped."""

import importlib
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FF = ROOT / "captureforge" / "face"
sys.path.insert(0, str(FF / "helpers"))

import video_to_csv as v  # noqa: E402


def close(a, b, eps=1e-6):
    return abs(a - b) < eps


def test_hold_gaps():
    rows, missing = v.hold_gaps([None, [1.0], None, [3.0], None])
    assert missing == 3 and rows == [[1.0], [1.0], [1.0], [3.0], [3.0]], rows
    try:
        v.hold_gaps([None, None])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_calibrate():
    times = [0, 0.5, 1.0, 1.5, 2.0, 2.5]
    rows = [[0.2, 0.0], [0.2, 0.0], [0.2, 0.0], [0.2, 0.0], [0.7, 0.9], [0.1, 1.0]]
    out = v.calibrate(rows, times, 2.0)  # baseline = first 4 rows -> [0.2, 0]
    assert all(close(x, 0) for x in out[0] + out[3]), out
    assert close(out[4][0], 0.5) and close(out[4][1], 0.9)
    assert out[5][0] == 0.0, "negative must clamp to 0"
    assert v.calibrate(rows, times, 2.0, gain=3.0)[4][0] == 1.0, "gain then clamp to 1"
    # held frames must not skew the baseline
    held = [[9.0, 9.0]] + rows[1:]
    out = v.calibrate(held, times, 2.0, valid=[False] + [True] * 5)
    assert close(out[1][0], 0.0)


def test_smooth():
    rows = [[0.0], [1.0], [1.0], [1.0]]
    assert v.smooth(rows, 0) == rows
    s = v.smooth(rows, 0.5)
    assert close(s[0][0], 0.0) and close(s[1][0], 0.5) and close(s[2][0], 0.75), s
    assert s[0][0] <= s[1][0] <= s[2][0] <= s[3][0] <= 1.0


def test_csv_roundtrip():
    names = v.ARKIT_52[:4]
    times = [0.0, 0.0334, 0.0667]
    rows = [[0.0, 0.1, 0.2, 0.3], [0.4, 0.5, 0.6, 0.7], [1.0, 0.9, 0.8, 0.0]]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "out.csv"
        v.write_csv(p, names, times, rows)
        try:
            import numpy  # noqa: F401
        except ImportError:
            print("  (numpy missing: skipping FaceForge reader round-trip)")
            return
        sys.modules.setdefault("bpy", types.ModuleType("bpy"))
        pkg = types.ModuleType("ffpkg")
        pkg.__path__ = [str(FF)]
        sys.modules["ffpkg"] = pkg
        mocap = importlib.import_module("ffpkg.mocap")
        got_names, got_times, got_rows = mocap.read_csv(p)
    assert got_names == names, got_names
    assert all(close(a, b, 1e-5) for a, b in zip(got_times, times))
    assert all(close(a, b, 1e-5) for r1, r2 in zip(got_rows.tolist(), rows) for a, b in zip(r1, r2))


def test_names_match_faceforge():
    src = (FF / "presets.py").read_text(encoding="utf-8")
    assert all(f'"{n}"' in src for n in v.ARKIT_52), "ARKIT_52 drifted from presets.py"


if __name__ == "__main__":
    tests = [f for k, f in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
