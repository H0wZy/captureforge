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


def faceforge_mocap():
    """FaceForge's mocap module with bpy stubbed (its CSV readers need numpy only); None without numpy."""
    try:
        import numpy  # noqa: F401
    except ImportError:
        return None
    sys.modules.setdefault("bpy", types.ModuleType("bpy"))
    pkg = types.ModuleType("ffpkg")
    pkg.__path__ = [str(FF)]
    sys.modules["ffpkg"] = pkg
    return importlib.import_module("ffpkg.mocap")


def test_csv_roundtrip():
    names = v.ARKIT_52[:4]
    times = [0.0, 0.0334, 0.0667]
    rows = [[0.0, 0.1, 0.2, 0.3], [0.4, 0.5, 0.6, 0.7], [1.0, 0.9, 0.8, 0.0]]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "out.csv"
        v.write_csv(p, names, times, rows)
        mocap = faceforge_mocap()
        if mocap is None:
            print("  (numpy missing: skipping FaceForge reader round-trip)")
            return
        got_names, got_times, got_rows = mocap.read_csv(p)
    assert got_names == names, got_names
    assert all(close(a, b, 1e-5) for a, b in zip(got_times, times))
    assert all(close(a, b, 1e-5) for r1, r2 in zip(got_rows.tolist(), rows) for a, b in zip(r1, r2))


# ---- head pose (facial transformation matrix) -------------------------------------------------

import math  # noqa: E402


def mat4(rot, t=(0.0, 0.0, 0.0), scale=1.0):
    """Row-major 4x4 as 16 floats, like MediaPipe's facial_transformation_matrixes[0].flatten()."""
    return [scale * rot[0][0], scale * rot[0][1], scale * rot[0][2], t[0],
            scale * rot[1][0], scale * rot[1][1], scale * rot[1][2], t[1],
            scale * rot[2][0], scale * rot[2][1], scale * rot[2][2], t[2],
            0.0, 0.0, 0.0, 1.0]


def mat_close(a, b, eps=1e-6):
    return all(abs(a[i][j] - b[i][j]) < eps for i in range(3) for j in range(3))


def test_euler_roundtrip():
    grid = [math.radians(d) for d in (-80, -45, -10, 0, 10, 45, 80)]
    for x in grid:
        for y in grid + [math.radians(170), math.radians(-170)]:
            for z in grid:
                r = v.euler_to_matrix(x, y, z)
                got = v.matrix_to_euler(r)
                assert mat_close(v.euler_to_matrix(*got), r), (x, y, z, got)
                assert all(close(a, b, 1e-6) for a, b in zip(got, (x, y, z))), (x, y, z, got)
    # gimbal lock (pitch +-90): still a valid decomposition of the same rotation
    r = v.euler_to_matrix(math.pi / 2, 0.4, 0.0)
    assert mat_close(v.euler_to_matrix(*v.matrix_to_euler(r)), r, 1e-6)


def test_euler_axes():
    # +X rotation = pitch, +Y = yaw, +Z = roll, the documented order Ry * Rx * Rz
    a = 0.3
    assert mat_close(v.euler_to_matrix(a, 0, 0), [[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    assert mat_close(v.euler_to_matrix(0, a, 0), [[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    assert mat_close(v.euler_to_matrix(0, 0, a), [[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])


def test_orthonormalize_removes_scale():
    r = v.euler_to_matrix(0.2, -0.4, 0.1)
    m = mat4(r, t=(1, 2, -30), scale=1.07)
    got = v.orthonormalize([[m[0], m[1], m[2]], [m[4], m[5], m[6]], [m[8], m[9], m[10]]])
    assert mat_close(got, r)
    # near-rotation noise ends up orthonormal
    noisy = [[r[i][j] + 0.01 * (i - j) for j in range(3)] for i in range(3)]
    o = v.orthonormalize(noisy)
    for i in range(3):
        for j in range(3):
            dot = sum(o[k][i] * o[k][j] for k in range(3))
            assert close(dot, 1.0 if i == j else 0.0, 1e-9)


def test_unbreak():
    two = 2 * math.pi
    wrapped = [[0.0, 3.0, -3.0], [0.0, -3.1, 3.1], [0.0, -3.0, -3.1]]  # y and z jump by about 2 pi
    out = v.unbreak(wrapped)
    for i in range(1, 3):
        assert all(abs(out[i][c] - out[i - 1][c]) < math.pi for c in range(3)), out
    assert close(out[1][1], -3.1 + two) and close(out[1][2], 3.1 - two)
    assert out[0] == wrapped[0], "first frame is the reference"
    assert v.unbreak([]) == []


def test_head_pose_neutral_and_turn():
    times = [i / 10 for i in range(8)]  # 0 .. 0.7 s, neutral window = first 0.4 s
    tilt = v.euler_to_matrix(0.1, 0.0, 0.0)  # the head rests pitched by 0.1 rad
    turn = v.euler_to_matrix(0.0, 0.5, 0.0)  # then turns by 0.5 rad about its own Y
    mats = [mat4(tilt, (1, 2, -30))] * 4
    for _ in range(4):
        r = [[sum(tilt[i][k] * turn[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        mats.append(mat4(r, (3, 2, -32), scale=1.05))
    rot, pos = v.head_pose(mats, times, 0.4)
    assert all(abs(c) < 1e-9 for c in rot[0] + rot[3] + pos[0] + pos[3]), "neutral window is zero"
    assert all(close(a, b, 1e-6) for a, b in zip(rot[5], (0.0, 0.5, 0.0))), rot[5]
    assert all(close(a, b, 1e-9) for a, b in zip(pos[5], (2, 0, -2))), pos[5]
    # no neutral window: the identity is the neutral (rotation zero = facing the camera)
    rot0, pos0 = v.head_pose(mats, times, 0.0)
    assert close(rot0[0][0], 0.1, 1e-6) and pos0[0] == [1, 2, -30]


def test_head_pose_continuous_across_a_full_turn():
    n = 40
    times = [i / 10 for i in range(n)]
    mats = [mat4(v.euler_to_matrix(0.0, i * 0.2, 0.0)) for i in range(n)]  # 0 .. 7.8 rad of yaw
    rot, _ = v.head_pose(mats, times, 0.0)
    ys = [r[1] for r in rot]
    assert all(abs(b - a) < 0.3 for a, b in zip(ys, ys[1:])), "no 2 pi jumps"
    assert close(ys[-1], (n - 1) * 0.2, 1e-6)


def test_csv_head_columns_and_old_format():
    names = v.ARKIT_52[:2]
    times, rows = [0.0, 0.1], [[0.1, 0.2], [0.3, 0.4]]
    rot, pos = [[0.0, 0.1, -0.1], [0.01, 0.02, 0.03]], [[0.0, 0.0, 0.0], [1.5, -2.0, 0.5]]
    with tempfile.TemporaryDirectory() as d:
        old, new = Path(d) / "old.csv", Path(d) / "new.csv"
        v.write_csv(old, names, times, rows)
        assert old.read_text().splitlines()[0] == "time," + ",".join(names), "old format unchanged"
        v.write_csv(new, names, times, rows, rot, pos)
        head = new.read_text().splitlines()[0].split(",")
        assert head == ["time"] + names + ["headRotX", "headRotY", "headRotZ", "headPosX", "headPosY", "headPosZ"], head
        assert new.read_text().splitlines()[2].split(",")[-6:] == ["0.01000", "0.02000", "0.03000", "1.50000", "-2.00000", "0.50000"]


def test_head_columns_roundtrip():
    mocap = faceforge_mocap()
    if mocap is None:
        print("  (numpy missing: skipping FaceForge reader round-trip)")
        return
    names, times, rows = v.ARKIT_52[:2], [0.0, 0.1, 0.2], [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
    rot, pos = [[0.0, 0.1, -0.1], [0.01, 0.02, 0.03], [0.5, 0.0, 0.0]], [[0, 0, 0], [1.5, -2.0, 0.5], [0, 0, 0]]
    with tempfile.TemporaryDirectory() as d:
        p, old = Path(d) / "new.csv", Path(d) / "old.csv"
        v.write_csv(p, names, times, rows, rot, pos)
        v.write_csv(old, names, times, rows)
        got_names, got_times, got_rows = mocap.read_csv(p)
        assert got_names == names and got_rows.shape == (3, 2), "head columns must not become shapes"
        t, r, q = mocap.read_head_pose(p)
        assert all(close(a, b, 1e-5) for x, y in zip(r.tolist(), rot) for a, b in zip(x, y))
        assert all(close(a, b, 1e-5) for x, y in zip(q.tolist(), pos) for a, b in zip(x, y))
        assert all(close(a, b, 1e-5) for a, b in zip(t, times))
        assert mocap.read_head_pose(old) is None
        assert mocap.read_csv(old)[0] == names


def test_names_match_faceforge():
    src = (FF / "presets.py").read_text(encoding="utf-8")
    assert all(f'"{n}"' in src for n in v.ARKIT_52), "ARKIT_52 drifted from presets.py"


if __name__ == "__main__":
    tests = [f for k, f in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
