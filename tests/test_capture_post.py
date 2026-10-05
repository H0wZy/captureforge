"""Self-check for captureforge/face/capture/post.py, the post-processing shared by the video helper, the live bake and
the tests. Golden values were computed with video_to_csv.py's own steps before they moved into post.py, so the move
changes no number. Pure Python (no numpy, mediapipe or Blender). Run: python tests/test_capture_post.py"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "captureforge" / "face" / "capture"))
sys.path.insert(0, str(ROOT / "captureforge" / "face" / "helpers"))

import post  # noqa: E402
import video_to_csv as v  # noqa: E402

TIMES = [i / 10 for i in range(8)]
RAW = [None, [0.1, 0.2], [0.1, 0.3], None, [0.6, 0.2], [0.9, 0.0], None, [0.4, 0.8]]
GOLDEN_ROWS = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0525], [0.0, 0.06825], [0.525, 0.020475], [0.8575, 0.006142],
               [0.95725, 0.001843], [0.602175, 0.578053]]
GOLDEN_ROT = [[0.0, -0.01, 0.0], [0.0, -0.01, 0.0], [0.0, 0.004, 0.0], [0.0, 0.0082, 0.0], [0.07, 0.20546, 0.0],
              [-0.049, 0.404638, 0.035], [-0.0847, 0.464391, 0.0455], [-0.02541, -0.007683, 0.08365]]
GOLDEN_POS = [[0.0, 0.0, 0.0]] * 4 + [[0.7, 1.4, 1.4], [1.61, 1.12, 2.52], [1.883, 1.036, 2.856],
                                      [0.5649, 0.3108, 0.8568]]


def mat(yaw, pitch, roll, t):
    r = post.euler_to_matrix(pitch, yaw, roll)
    return [r[0][0], r[0][1], r[0][2], t[0], r[1][0], r[1][1], r[1][2], t[1],
            r[2][0], r[2][1], r[2][2], t[2], 0, 0, 0, 1]


MATS = [None, mat(0.0, 0.0, 0.0, (0, 0, -50)), mat(0.02, 0.0, 0.0, (0, 0, -50)), None,
        mat(0.3, 0.1, 0.0, (1, 2, -48)), mat(0.5, -0.1, 0.05, (2, 1, -47)), None, mat(-0.2, 0.0, 0.1, (0, 0, -50))]


def same(a, b, eps=1e-6):
    return len(a) == len(b) and all(len(r) == len(s) and all(abs(x - y) < eps for x, y in zip(r, s))
                                    for r, s in zip(a, b))


def test_process_matches_the_video_path():
    out = post.process(TIMES, RAW, MATS, neutral_seconds=0.35, gain=1.5, smoothing=0.3)
    assert out["missing"] == 3
    assert same(out["rows"], GOLDEN_ROWS), out["rows"]
    assert same(out["rot"], GOLDEN_ROT), out["rot"]
    assert same(out["pos"], GOLDEN_POS), out["pos"]


def test_process_without_head_pose():
    out = post.process(TIMES, RAW, MATS, 0.35, 1.5, 0.3, head=False)
    assert out["rot"] is None and out["pos"] is None and same(out["rows"], GOLDEN_ROWS)
    out = post.process(TIMES, RAW, [None] * len(RAW), 0.35, 1.5, 0.3)  # a tracker without matrices
    assert out["rot"] is None and out["pos"] is None


def test_process_without_any_face():
    try:
        post.process(TIMES[:2], [None, None], [None, None])
    except ValueError as e:
        assert "no face" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_video_helper_uses_the_shared_steps():
    for name in ("hold_gaps", "calibrate", "smooth", "head_pose", "orthonormalize", "euler_to_matrix",
                 "matrix_to_euler", "unbreak"):
        assert getattr(v, name) is getattr(post, name), name
    assert v.HEAD_COLUMNS == post.HEAD_COLUMNS


if __name__ == "__main__":
    tests = [f for k, f in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
