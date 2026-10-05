"""Create the helper environment: a private venv with the pinned packages and the face model, only after the user
confirms (specs/004-live-capture-panel, FR-010, FR-011, FR-013).

    python setup.py --venv DIR                        print the plan (what, from where, how big) and change nothing
    python setup.py --venv DIR --yes [--python P] [--wheels DIR] [--bundled-model FILE] [--dry-run]

Blender runs it with its own interpreter as a background process, so a machine without a Python of its own works;
a system Python is only the fallback. Packages come from helper-requirements.txt (exact pins, binary wheels only),
or with --wheels from a folder of wheels the user brought (no network). The face model is copied from the add-on
when the release zip carries it, or downloaded from the pinned URL; either way its SHA-256 is checked. The last
stdout line of a real run is JSON with the paths to store in the preferences. No admin rights, nothing outside DIR.
Standard library only.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2]  # the add-on folder (captureforge/)
LOCK = PACKAGE / "helper-requirements.txt"
HELPER = PACKAGE / "face" / "helpers" / "capture_helper.py"
MODEL = {"name": "face_landmarker.task",
         "url": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/"
                "face_landmarker.task",
         "size": 3758596, "sha256": "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"}
# Approximate wheel download sizes in MB (smallest and largest platform), PyPI 2026-10-05. Update with the pins.
SIZES = {"mediapipe": (18, 38), "opencv-contrib-python": (43, 82), "numpy": (5, 12), "cv2-enumerate-cameras": (0.1, 0.2)}
DEPENDENCIES = ("matplotlib, pillow, fonttools, contourpy, kiwisolver, absl-py, flatbuffers, sounddevice, certifi "
                "and a few small ones, about 15 to 30 MB")


def read_pins(lock):
    """[(name, version)] of the name==version lines of a requirements file."""
    pins = []
    for line in Path(lock).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" in line:
            name, version = line.split("==", 1)
            pins.append((name.strip(), version.strip()))
    return pins


def venv_python(venv):
    return os.path.join(venv, "Scripts", "python.exe") if os.name == "nt" else os.path.join(venv, "bin", "python")


def _size(name):
    lo, hi = SIZES.get(name, (None, None))
    return "size unknown" if lo is None else f"about {lo:g} to {hi:g} MB"


def plan_text(venv, python, lock=LOCK, bundled_model=None, wheels=None):
    source = f"the folder {wheels} (no network)" if wheels else "PyPI (https://pypi.org)"
    lines = ["FaceForge helper setup. Nothing is downloaded or installed until you press Install.",
             f"  Folder: {venv}",
             f"  Python used to create it: {python}",
             f"  Packages, exact versions, binary wheels only, from {source}:"]
    lines += [f"    {name}=={version}, {_size(name)}" for name, version in read_pins(lock)]
    lines += [f"    plus their dependencies: {DEPENDENCIES}.",
              "  Download in total about 100 to 160 MB depending on the platform; about 500 MB on disk."]
    mb = MODEL["size"] / 1e6
    if bundled_model:
        lines.append(f"  Face model {MODEL['name']} ({mb:.1f} MB, Apache-2.0): included in the add-on, copied.")
    else:
        lines.append(f"  Face model {MODEL['name']} ({mb:.1f} MB, Apache-2.0), downloaded from {MODEL['url']}")
    lines += [f"    SHA-256 {MODEL['sha256']} (checked)",
              "  It needs no admin rights and nothing system-wide is changed: delete the folder to remove it.",
              "  After setup, capture and video import work offline."]
    return "\n".join(lines)


def commands(python, venv, lock=LOCK, wheels=None):
    """The venv and pip command lines."""
    pip = [venv_python(venv), "-m", "pip", "install", "--disable-pip-version-check", "--only-binary=:all:"]
    if wheels:
        pip += ["--no-index", "--find-links", str(wheels)]
    return [[python, "-m", "venv", venv], pip + ["-r", str(lock)]]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def install_model(dest_dir, model=MODEL, bundled=None, fetch=urllib.request.urlretrieve):
    """Copy the bundled model or download it, check the SHA-256, then move it in place. ValueError on a mismatch
    (the partial file is deleted)."""
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, model["name"])
    part = dest + ".part"
    try:
        if bundled:
            shutil.copyfile(bundled, part)
        else:
            fetch(model["url"], part)
        digest = _sha256(part)
        if digest != model["sha256"]:
            raise ValueError(f"{model['name']}: checksum mismatch (got {digest}, expected {model['sha256']})")
        os.replace(part, dest)
    finally:
        if os.path.exists(part):
            os.remove(part)
    return dest


def pick_python(blender_python, candidates, works):
    """Blender's own interpreter when it can make a venv, else the first candidate that can, else None."""
    for p in [blender_python, *candidates]:
        if p and works(p):
            return p
    return None


def can_make_venv(python):
    exe = shutil.which(python) or python
    try:
        return subprocess.run([exe, "-c", "import venv, ensurepip"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def find_model(addon_dir, pref_path, venv):
    """The face model to use: the release zip's copy, else the path in the preferences, else the installer's."""
    for p in (os.path.join(addon_dir, "models", MODEL["name"]), pref_path,
              os.path.join(venv, "models", MODEL["name"]) if venv else ""):
        if p and os.path.isfile(p):
            return p
    return None


def main(argv=None, run=None, fetch=urllib.request.urlretrieve, model=MODEL, say=None):
    say = say or (lambda line: print(line, flush=True))
    run = run or (lambda cmd: subprocess.run(cmd).returncode)
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--venv", required=True)
    ap.add_argument("--yes", action="store_true", help="do it (without this only the plan is printed)")
    ap.add_argument("--dry-run", action="store_true", help="print the commands and do nothing")
    ap.add_argument("--python", help="interpreter that creates the venv (default: this one, else a system Python)")
    ap.add_argument("--wheels", help="install from this folder of wheels, without network")
    ap.add_argument("--bundled-model", help="the add-on's copy of the face model")
    ap.add_argument("--lock", default=str(LOCK))
    a = ap.parse_args(argv)
    venv = os.path.abspath(a.venv)
    python = a.python or pick_python(sys.executable, ["python3", "python", "py"], can_make_venv)
    if not a.yes:
        say(plan_text(venv, python or "(none found)", a.lock, a.bundled_model, a.wheels))
        return 0
    if python is None:
        say("error: no Python that can create a venv (Blender's own interpreter could not)")
        return 1
    steps = commands(python, venv, a.lock, a.wheels)
    models = os.path.join(venv, "models")
    model_path = os.path.join(models, model["name"])
    check = [venv_python(venv), str(HELPER), "--self-test", "--model", model_path]
    if a.dry_run:
        for cmd in steps + [check]:
            say("would run: " + " ".join(cmd))
        say(f"would {'copy ' + a.bundled_model if a.bundled_model else 'download ' + model['url']} -> {model_path}")
        return 0
    for i, cmd in enumerate(steps, 1):
        say(f"step {i}/4: {' '.join(cmd[:4])} ...")
        if run(cmd):
            say(f"error: step {i} failed: {' '.join(cmd)}")
            return 1
    say("step 3/4: face model ...")
    try:
        install_model(models, model, a.bundled_model, fetch)
    except (OSError, ValueError) as e:
        say(f"error: {e}")
        return 1
    say("step 4/4: self-test ...")
    if run(check):
        say("error: the helper self-test failed (see the lines above)")
        return 1
    say(json.dumps({"python": venv_python(venv), "model": model_path}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
