"""Self-check for captureforge/face/capture/setup.py, the helper environment installer: the consent text, the exact
commands, nothing run without --yes, the model checksum and the model lookup order. Nothing is downloaded or
installed: the runner and the downloader are fakes. Standard library only. Run: python tests/test_capture_setup.py"""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "captureforge" / "face" / "capture"))

import setup as s  # noqa: E402

LOCK = ROOT / "captureforge" / "helper-requirements.txt"


class Runner:
    """Records commands instead of running them; fails the ones whose label contains `fail`."""

    def __init__(self, fail=""):
        self.calls, self.fail = [], fail

    def __call__(self, cmd):
        self.calls.append(cmd)
        return 1 if self.fail and self.fail in " ".join(cmd) else 0


def test_pins_are_exact_and_cover_the_tracker():
    pins = dict(s.read_pins(LOCK))
    assert {"mediapipe", "opencv-contrib-python", "numpy"} <= set(pins), pins
    assert all(v and v[0].isdigit() for v in pins.values()), pins
    assert "opencv-python" not in pins  # mediapipe brings contrib; two cv2 packages would clash
    assert (ROOT / "requirements-mocap.txt").read_text().strip().endswith("-r captureforge/helper-requirements.txt")


def test_plan_text_says_everything_before_anything_runs():
    text = s.plan_text("/x/helper", "/blender/python/bin/python3.13", LOCK)
    for pin in s.read_pins(LOCK):
        assert f"{pin[0]}=={pin[1]}" in text, pin
    for needle in ("/x/helper", "/blender/python/bin/python3.13", "pypi.org", "MB", s.MODEL["sha256"],
                   s.MODEL["url"], "no admin rights", "nothing system-wide", "Install"):
        assert needle in text, needle
    bundled = s.plan_text("/x/helper", "py", LOCK, bundled_model="/addon/models/face_landmarker.task")
    assert "included in the add-on" in bundled and "storage.googleapis.com" not in bundled
    offline = s.plan_text("/x/helper", "py", LOCK, wheels="/media/usb/wheels")
    assert "/media/usb/wheels" in offline and "pypi.org" not in offline


def test_commands_use_pins_and_binary_wheels():
    venv = os.path.join("x", "helper")
    cmds = s.commands("/bl/python", venv, LOCK)
    assert cmds[0] == ["/bl/python", "-m", "venv", venv]
    pip = cmds[1]
    assert pip[:4] == [s.venv_python(venv), "-m", "pip", "install"]
    assert "--only-binary=:all:" in pip and pip[-2:] == ["-r", str(LOCK)]
    assert "--no-index" not in pip
    off = s.commands("/bl/python", venv, LOCK, wheels="/w")[1]
    assert "--no-index" in off and off[off.index("--find-links") + 1] == "/w" and "--only-binary=:all:" in off


def test_nothing_runs_without_yes():
    run, fetched = Runner(), []
    with tempfile.TemporaryDirectory() as d:
        rc = s.main(["--venv", os.path.join(d, "h")], run=run, fetch=lambda url, dest: fetched.append(url))
        assert rc == 0 and run.calls == [] and fetched == [] and os.listdir(d) == []
        rc = s.main(["--venv", os.path.join(d, "h"), "--yes", "--dry-run"], run=run, fetch=lambda u, p: fetched.append(u))
        assert rc == 0 and run.calls == [] and fetched == [] and os.listdir(d) == []


def fake_model(content=b"model bytes"):
    return {"name": "face_landmarker.task", "url": "https://example.invalid/m.task", "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest()}


def test_install_runs_the_steps_and_checks_the_model():
    content = b"model bytes"

    def fetch(url, dest):
        Path(dest).write_bytes(content)

    with tempfile.TemporaryDirectory() as d:
        venv, run = os.path.join(d, "h"), Runner()
        out = []
        rc = s.main(["--venv", venv, "--yes", "--python", "/bl/python"], run=run, fetch=fetch, model=fake_model(),
                    say=out.append)
        assert rc == 0, out
        assert run.calls[0][:3] == ["/bl/python", "-m", "venv"] and "pip" in run.calls[1]
        assert run.calls[-1][-3:] == ["--self-test", "--model", os.path.join(venv, "models", "face_landmarker.task")]
        result = json.loads(out[-1])
        assert result == {"python": s.venv_python(venv), "model": os.path.join(venv, "models", "face_landmarker.task")}
        assert Path(result["model"]).read_bytes() == content
        assert not list(Path(venv, "models").glob("*.part"))


def test_checksum_mismatch_deletes_the_partial_file():
    def fetch(url, dest):
        Path(dest).write_bytes(b"tampered")

    with tempfile.TemporaryDirectory() as d:
        venv, out = os.path.join(d, "h"), []
        rc = s.main(["--venv", venv, "--yes", "--python", "py"], run=Runner(), fetch=fetch, model=fake_model(),
                    say=out.append)
        assert rc == 1 and any("checksum" in line for line in out), out
        assert not any(Path(venv, "models").iterdir())


def test_bundled_model_is_copied_after_its_checksum():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d, "bundled.task")
        src.write_bytes(b"model bytes")
        venv, fetched, out = os.path.join(d, "h"), [], []
        rc = s.main(["--venv", venv, "--yes", "--python", "py", "--bundled-model", str(src)], run=Runner(),
                    fetch=lambda u, p: fetched.append(u), model=fake_model(), say=out.append)
        assert rc == 0 and fetched == [], out
        assert Path(json.loads(out[-1])["model"]).read_bytes() == b"model bytes"


def test_a_failing_step_stops_the_install():
    with tempfile.TemporaryDirectory() as d:
        run, out = Runner(fail="pip"), []
        rc = s.main(["--venv", os.path.join(d, "h"), "--yes", "--python", "py"], run=run,
                    fetch=lambda u, p: None, model=fake_model(), say=out.append)
        assert rc == 1 and len(run.calls) == 2 and any("pip" in line for line in out), out


def test_pick_python_prefers_blender():
    works = {"/blender/py": True, "/usr/bin/python3": True}
    assert s.pick_python("/blender/py", ["/usr/bin/python3"], lambda p: works.get(p, False)) == "/blender/py"
    works["/blender/py"] = False
    assert s.pick_python("/blender/py", ["/nope", "/usr/bin/python3"], lambda p: works.get(p, False)) == "/usr/bin/python3"
    assert s.pick_python("/blender/py", ["/nope"], lambda p: False) is None


def test_model_lookup_order():
    with tempfile.TemporaryDirectory() as d:
        addon, venv = Path(d, "addon"), Path(d, "venv")
        (addon / "models").mkdir(parents=True)
        (venv / "models").mkdir(parents=True)
        pref = Path(d, "mine.task")
        assert s.find_model(str(addon), "", str(venv)) is None
        (venv / "models" / "face_landmarker.task").write_bytes(b"x")
        assert s.find_model(str(addon), "", str(venv)) == str(venv / "models" / "face_landmarker.task")
        pref.write_bytes(b"x")
        assert s.find_model(str(addon), str(pref), str(venv)) == str(pref)
        (addon / "models" / "face_landmarker.task").write_bytes(b"x")  # the release zip's copy wins
        assert s.find_model(str(addon), str(pref), str(venv)) == str(addon / "models" / "face_landmarker.task")


if __name__ == "__main__":
    tests = [f for k, f in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
