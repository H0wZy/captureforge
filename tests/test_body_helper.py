"""Pure tests for the BodyForge helper scripts (no mediapipe or opencv needed). Run: python tests/test_body_helper.py

The scripts live in captureforge/body/helpers and run in the helper venv; the real MediaPipe path is covered by
tests/test_body_helper_real.py, which is skipped unless BODYFORGE_PYTHON and BODYFORGE_POSE_MODEL are set.
"""

import os
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures_body as fx  # noqa: E402

HELPERS = os.path.join(fx.ROOT, "captureforge", "body", "helpers")
sys.path.insert(0, HELPERS)
import pose_to_landmarks as ptl  # noqa: E402
import setup_env  # noqa: E402

fx.pure_import()
from captureforge.body import landmarks  # noqa: E402

TMP = tempfile.mkdtemp()


def run_script(name, *args):
    return subprocess.run([sys.executable, os.path.join(HELPERS, name), *args], capture_output=True, text=True)


def test_parser_works_without_mediapipe():
    p = fx.implemented(getattr(ptl, "build_parser", lambda: None)())
    a = p.parse_args(["clip.mp4", "-o", "out.npz", "--pose-model", "pose.task"])
    assert a.video == "clip.mp4" and a.out == "out.npz" and a.pose_model == "pose.task"
    assert a.variant == "heavy" and a.hands_model is None and a.head_box is False and a.max_seconds is None
    a = p.parse_args(["v.mp4", "-o", "o.npz", "--pose-model", "p.task", "--variant", "lite", "--head-box",
                      "--max-seconds", "5"])
    assert a.variant == "lite" and a.head_box is True and a.max_seconds == 5
    r = run_script("pose_to_landmarks.py", "--help")
    assert r.returncode == 0 and "--pose-model" in r.stdout


def test_exit_codes():
    missing_video = fx.implemented(getattr(ptl, "main", lambda *a, **k: None)(
        ["nope.mp4", "-o", os.path.join(TMP, "x.npz"), "--pose-model", "p.task"]))
    assert missing_video == 2
    video = os.path.join(TMP, "dummy.mp4")
    open(video, "wb").write(b"not a video")
    model = os.path.join(TMP, "pose.task")
    open(model, "wb").write(b"x")

    def no_package(name):
        raise ImportError(f"No module named {name!r}")

    import io
    import contextlib
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code = ptl.main([video, "-o", os.path.join(TMP, "x.npz"), "--pose-model", model], _import=no_package)
    assert code == 3 and "missing package" in err.getvalue(), (code, err.getvalue())
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code = ptl.main([video, "-o", os.path.join(TMP, "x.npz"), "--pose-model", os.path.join(TMP, "none.task")],
                        _import=lambda n: object())
    assert code == 4 and "model" in err.getvalue().lower(), (code, err.getvalue())
    assert not os.path.exists(os.path.join(TMP, "x.npz")), "a failed run leaves no file"
    r = run_script("pose_to_landmarks.py", video, "-o", os.path.join(TMP, "y.npz"), "--pose-model", model)
    assert r.returncode in (3, 4, 5), "missing packages or an unreadable stand-in model, never a traceback exit"
    assert "Traceback" not in r.stderr


def test_setup_env_plan_and_dry_run():
    venv = os.path.join(TMP, "helper-venv")
    r = run_script("setup_env.py", "--venv", venv)
    assert r.returncode == 0 and not os.path.exists(venv), "without --yes it only prints the plan"
    out = r.stdout
    for needle in (venv, "mediapipe", "opencv-python", "storage.googleapis.com", "pose_landmarker_heavy",
                   "pose_landmarker_lite", "hand_landmarker", "--yes"):
        assert needle in out, f"plan text should mention {needle}"
    r2 = run_script("setup_env.py", "--venv", venv, "--yes", "--dry-run")
    assert r2.returncode == 0 and not os.path.exists(venv), "--dry-run does nothing"
    assert "pip install" in r2.stdout and "venv" in r2.stdout and "download" in r2.stdout.lower()
    plan = fx.implemented(getattr(setup_env, "plan_text", lambda *a: None)(venv))
    assert venv in plan


def test_native_axes_conversion():
    native = np.array([[[0.1, 0.5, -0.2]]], np.float32)  # MediaPipe: x right, y down, z away from the camera
    out = fx.implemented(getattr(ptl, "to_landmark_axes", lambda a: None)(native))
    assert np.allclose(out, [[[0.1, -0.5, 0.2]]]), "to +X right, +Y up, +Z toward the camera"


def test_most_prominent_person():
    small = np.array([[0.1, 0.1, 0], [0.2, 0.3, 0]])
    big = np.array([[0.4, 0.1, 0], [0.9, 0.95, 0]])
    pick = fx.implemented(getattr(ptl, "most_prominent", lambda poses: None)([small, big]))
    assert pick == 1 and ptl.most_prominent([small]) == 0


def test_writer_roundtrips_through_the_reader():
    n = 12
    rng = np.random.default_rng(1)
    rec = fx.implemented(getattr(ptl, "Recorder", lambda: None)())
    for i in range(n):
        if i in (3, 4):
            rec.add(i / 30.0, None, None, None)
        else:
            rec.add(i / 30.0, rng.normal(size=(33, 3)), rng.uniform(size=(33, 3)), rng.uniform(size=33))
    path = os.path.join(TMP, "rt.npz")
    rec.write(path, size=(720, 1280), fps_source=30.0, model="pose_landmarker_heavy.task", model_sha256="ab" * 32,
              variant="heavy", people_seen=2, rotation=90, warnings=["w"])
    lm = fx.implemented(landmarks.read(path))
    assert lm.pose_world.shape == (n, 33, 3) and lm.size == (720, 1280) and lm.gaps == [(3, 5)]
    assert lm.meta["people_seen"] == 2 and lm.meta["frames_without_person"] == 2
    assert lm.meta["model_variant"] == "heavy" and lm.meta["rotation_applied"] == 90 and lm.meta["hands"] is False
    assert lm.meta["warnings"] == ["w"] and lm.meta["model"] == "pose_landmarker_heavy.task"
    assert np.allclose(np.diff(lm.times), 1 / 30.0) and abs(lm.fps_source - 30.0) < 1e-9
    assert np.isnan(np.load(path)["pose_world"][3]).all(), "no-person frames are written as NaN"
    raw = np.load(path, allow_pickle=False)
    assert int(raw["version"]) == 1 and raw["pose_vis"][3].sum() == 0


def test_strictly_increasing_timestamps():
    rec = fx.implemented(getattr(ptl, "Recorder", lambda: None)())
    for t in (0.0, 0.033, 0.033, 0.033, 0.1):  # a container that repeats timestamps
        rec.add(t, np.zeros((33, 3)), np.zeros((33, 3)), np.ones(33))
    path = os.path.join(TMP, "ts.npz")
    rec.write(path, size=(10, 10), fps_source=30.0, model="m", model_sha256="", variant="lite", people_seen=1,
              rotation=0, warnings=[])
    t = np.load(path)["times"]
    assert (np.diff(t) > 0).all() and t[0] == 0 and abs(t[-1] - 0.1) < 1e-6


if __name__ == "__main__":
    fx.run_all(globals())
