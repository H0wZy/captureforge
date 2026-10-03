"""Video -> mocap CSV by running helpers/video_to_csv.py in a separate Python (MediaPipe + OpenCV live
there, never inside Blender). Plain subprocess; no bpy."""

import os
import subprocess

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "helpers", "video_to_csv.py")
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
        script=None, timeout=None):
    """Run the helper on a video and write out_csv. Returns the helper's last stdout line.
    Blocks until done. ponytail: no progress bar or cancel; a modal Popen poll if videos get long."""
    check_setup(python, model)
    if not os.path.isfile(video):
        raise ValueError(f"Video not found: {video}")
    cmd = [python, script or SCRIPT, video, "-o", out_csv, "--model", model, "--smooth", str(smooth),
           "--neutral-seconds", str(neutral_seconds), "--gain", str(gain)]
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
    if not os.path.isfile(out_csv):
        raise ValueError("The helper finished but wrote no CSV")
    return (p.stdout.strip().splitlines() or [""])[-1]
