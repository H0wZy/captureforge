"""Create the shared helper venv and download the MediaPipe models (BodyForge, also usable by FaceForge).

Usage: python setup_env.py --venv DIR [--hands] [--yes] [--dry-run]

Without --yes it only prints the plan (the venv, the packages and the model URLs with their sizes) and exits 0;
the add-on shows that text, asks the user to confirm, and runs it again with --yes. It needs no admin rights and
writes only inside DIR. The packages are the exact pins of captureforge/helper-requirements.txt (binary wheels only).
The add-on runs it with Blender's own Python when that one can create a venv. The last stdout line of a real run is a
JSON object with the paths to store in the add-on preferences.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = "https://storage.googleapis.com/mediapipe-models/"
LOCK = Path(__file__).resolve().parents[2] / "helper-requirements.txt"  # the add-on's lock file


def pins(lock=LOCK):
    """The name==version lines of the lock file (the same pins as the face helper installer)."""
    out = []
    for line in Path(lock).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" in line:
            out.append(line)
    return out



# name: (url, size in MB, sha256, optional)
MODELS = {
    "pose_landmarker_heavy.task": (BASE + "pose_landmarker/pose_landmarker_heavy/float16/latest/"
                                   "pose_landmarker_heavy.task", 30.7,
                                   "64437af838a65d18e5ba7a0d39b465540069bc8aae8308de3e318aad31fcbc7b", False),
    "pose_landmarker_lite.task": (BASE + "pose_landmarker/pose_landmarker_lite/float16/latest/"
                                  "pose_landmarker_lite.task", 5.8,
                                  "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a", False),
    "hand_landmarker.task": (BASE + "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task", 7.8,
                             "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1", True),
}


def venv_python(venv):
    return os.path.join(venv, "Scripts", "python.exe") if os.name == "nt" else os.path.join(venv, "bin", "python")


def plan_text(venv, hands=False):
    lines = ["BodyForge helper setup. This will:",
             f"  1. create a Python environment in: {venv}",
             f"  2. install with pip (exact versions, binary wheels only): {', '.join(pins())}",
             "  3. download these model files (Apache-2.0, from Google's MediaPipe storage) into "
             f"{os.path.join(venv, 'models')}:"]
    for name, (url, mb, _, optional) in MODELS.items():
        tag = "  (only with --hands)" if optional and not hands else ""
        lines.append(f"       {name}, about {mb:g} MB{tag}\n       {url}")
    lines += ["Nothing is installed system-wide and no admin rights are needed.",
              "Run it again with --yes to go ahead."]
    return "\n".join(lines)


def _download(url, dest, sha256):
    tmp = dest + ".part"
    urllib.request.urlretrieve(url, tmp)
    digest = hashlib.sha256(open(tmp, "rb").read()).hexdigest()
    if sha256 and digest != sha256:
        os.remove(tmp)
        raise RuntimeError(f"{os.path.basename(dest)}: checksum mismatch (got {digest})")
    os.replace(tmp, dest)
    return digest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--venv", required=True, help="folder for the shared helper environment")
    ap.add_argument("--hands", action="store_true", help="also download the hand model (fingers)")
    ap.add_argument("--yes", action="store_true", help="do it (without this only the plan is printed)")
    ap.add_argument("--dry-run", action="store_true", help="print what would run and do nothing")
    a = ap.parse_args(argv)
    venv = os.path.abspath(a.venv)
    models = os.path.join(venv, "models")
    wanted = {n: m for n, m in MODELS.items() if not m[3] or a.hands}
    if not a.yes:
        print(plan_text(venv, a.hands))
        return 0
    steps = [([sys.executable, "-m", "venv", venv], "create the environment"),
             ([venv_python(venv), "-m", "pip", "install", "--only-binary=:all:", "-r", str(LOCK)],
              f"pip install --only-binary=:all: -r {LOCK}")]
    if a.dry_run:
        for cmd, what in steps:
            print(f"would run ({what}): {' '.join(cmd)}")
        for name, (url, mb, _, _) in wanted.items():
            print(f"would download {url} -> {os.path.join(models, name)} (about {mb:g} MB)")
        return 0
    for cmd, what in steps:
        print(f"{what} ...", flush=True)
        if subprocess.run(cmd).returncode:
            print(f"error: failed to {what}", file=sys.stderr)
            return 1
    os.makedirs(models, exist_ok=True)
    paths = {}
    for name, (url, mb, sha, _) in wanted.items():
        dest = os.path.join(models, name)
        print(f"downloading {name} (about {mb:g} MB) from {url} ...", flush=True)
        try:
            _download(url, dest, sha)
        except (OSError, RuntimeError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        paths[name] = dest
    print(json.dumps({"python": venv_python(venv), "pose_model": paths["pose_landmarker_heavy.task"],
                      "lite_model": paths["pose_landmarker_lite.task"], "hand_model": paths.get("hand_landmarker.task", "")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
