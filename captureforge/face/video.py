"""Video -> mocap CSV by running helpers/video_to_csv.py in a separate Python (MediaPipe + OpenCV live
there, never inside Blender). Plain subprocess; no bpy."""

import json
import os
import subprocess

HELPERS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "helpers")
SCRIPT = os.path.join(HELPERS, "video_to_csv.py")
LANDMARKS_SCRIPT = os.path.join(HELPERS, "face_landmarks.py")
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")

SETUP_LINES = [
    "1. python -m venv .venv",
    "2. .venv/Scripts/python -m pip install mediapipe opencv-python   (Linux/macOS: .venv/bin/python)",
    "3. Download the model (about 3.6 MB): " + MODEL_URL,
    "4. Preferences > Add-ons > FaceForge: set Python = the venv's python, Model = the .task file.",
]
SETUP_TEXT = "Setup:\n" + "\n".join(SETUP_LINES)


def check_setup(python, model):
    """Raise ValueError (with setup instructions) unless python and model point to real files."""
    if not python or not os.path.isfile(python):
        raise ValueError(f"Python for MediaPipe not found: '{python}'.\n{SETUP_TEXT}")
    if not model or not os.path.isfile(model):
        raise ValueError(f"MediaPipe model file not found: '{model}'.\n{SETUP_TEXT}")


def run(python, model, video, out_csv, smooth=0.3, neutral_seconds=2.0, gain=1.0,
        script=None, timeout=None, crop=None):
    """Run the helper on a video and write out_csv. Returns the helper's last stdout line.
    `crop`: a BodyForge landmarks.npz whose per-frame head box limits the face tracker to the head (body + face).
    Blocks until done. ponytail: no progress bar or cancel; a modal Popen poll if videos get long."""
    check_setup(python, model)
    if not os.path.isfile(video):
        raise ValueError(f"Video not found: {video}")
    cmd = [python, script or SCRIPT, video, "-o", out_csv, "--model", model, "--smooth", str(smooth),
           "--neutral-seconds", str(neutral_seconds), "--gain", str(gain)]
    if crop:
        cmd += ["--crop", crop]
    last = _exec(cmd, python, timeout)
    if not os.path.isfile(out_csv):
        raise ValueError("The helper finished but wrote no CSV")
    return last


def landmarks(python, model, image, script=None, timeout=None):
    """Run helpers/face_landmarks.py on one image. Returns {"width", "height", "landmarks": [[x, y, z]]}
    with normalized coordinates (x right, y down, origin top-left)."""
    check_setup(python, model)
    if not os.path.isfile(image):
        raise ValueError(f"Image not found: {image}")
    out = image + ".landmarks.json"
    _exec([python, script or LANDMARKS_SCRIPT, image, "-o", out, "--model", model], python, timeout)
    try:
        with open(out, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(f"The helper wrote no readable landmarks: {e}") from e


def _exec(cmd, python, timeout):
    """Run a helper command; ValueError with its last error lines (plus setup help) on failure."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError(f"Could not run '{python}': {e}") from e
    if p.returncode != 0:
        err = (p.stderr or p.stdout).strip().splitlines()
        msg = "\n".join(err[-4:]) or f"helper exited with code {p.returncode}"
        if "missing package" in msg or "No module named" in msg:
            msg += f"\n{SETUP_TEXT}"
        raise ValueError(msg)
    return (p.stdout.strip().splitlines() or [""])[-1]
