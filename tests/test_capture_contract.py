"""The tracker contract (docs/TRACKER-CONTRACT.md): only captureforge/face/helpers/tracker.py may import MediaPipe, and
its Result has fixed shapes with None for "no face". The grep needs nothing; the Result checks need numpy and stub
MediaPipe-like objects (no mediapipe). Run: python tests/test_capture_contract.py"""

import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
HELPERS = ROOT / "captureforge" / "face" / "helpers"
sys.path.insert(0, str(HELPERS))

IMPORT = re.compile(r"^\s*(import\s+mediapipe|from\s+mediapipe[\s.])", re.M)


def test_only_the_tracker_imports_mediapipe():
    found = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "captureforge" / "face").rglob("*.py")
                   if IMPORT.search(p.read_text(encoding="utf-8")))
    assert found == ["captureforge/face/helpers/tracker.py"], found


def test_one_list_of_the_52_names():
    """The ARKit names live in captureforge/face/presets.py only; the tracker reads that file."""
    import tracker
    src = (HELPERS / "tracker.py").read_text(encoding="utf-8")
    assert '"eyeBlinkLeft", "eyeLookDownLeft"' not in src, "tracker.py must not keep its own copy"
    sys.path.insert(0, str(ROOT / "captureforge" / "face"))
    import presets
    assert tracker.ARKIT_52 == presets.ARKIT_52 and len(tracker.ARKIT_52) == 52


def test_tracker_imports_without_mediapipe():
    import tracker
    assert "mediapipe" not in sys.modules
    assert tracker.LANDMARKS == 478 and len(tracker.ARKIT_52) == 52


def numpy_or_skip():
    try:
        import numpy
    except ImportError:
        print("  (skipped: needs numpy)")
        return None
    return numpy


def stub_blendshapes(**scores):
    return [SimpleNamespace(category_name=k, score=v) for k, v in scores.items()]


def stub_points(n=478):
    return [SimpleNamespace(x=i / n, y=1 - i / n, z=-0.01 * i / n) for i in range(n)]


def test_result_with_a_face():
    np = numpy_or_skip()
    if np is None:
        return
    import tracker
    m = np.arange(16, dtype=np.float64).reshape(4, 4)
    r = tracker.to_result(40, [stub_blendshapes(_neutral=0.9, jawOpen=0.5, tongueOut=0.1)], [stub_points()], [m])
    assert r.timestamp_ms == 40 and r.face
    assert r.scores == {"jawOpen": 0.5, "tongueOut": 0.1}, r.scores  # _neutral is dropped
    assert r.landmarks.shape == (478, 3) and r.landmarks.dtype == np.float32
    assert abs(r.landmarks[239, 0] - 0.5) < 1e-6 and abs(r.landmarks[239, 2] + 0.005) < 1e-6
    assert r.matrix.shape == (4, 4) and r.matrix.dtype == np.float32 and r.matrix[1, 2] == 6


def test_result_without_a_face_or_matrix():
    np = numpy_or_skip()
    if np is None:
        return
    import tracker
    r = tracker.to_result(7, [], [], [])
    assert not r.face and r.scores is None and r.landmarks is None and r.matrix is None
    r = tracker.to_result(8, [stub_blendshapes(jawOpen=0.2)], [stub_points()], None)  # matrices not requested
    assert r.face and r.matrix is None and r.landmarks.shape == (478, 3)


def test_missing_model_is_a_coded_error():
    import tracker
    try:
        tracker.Tracker.video(str(ROOT / "no_such_model.task"))
    except tracker.TrackerError as e:
        assert e.code == "model_missing" and "no_such_model.task" in str(e), (e.code, str(e))
    else:
        raise AssertionError("expected TrackerError")


if __name__ == "__main__":
    tests = [f for k, f in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
