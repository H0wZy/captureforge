"""Video -> landmarks.npz by running helpers/pose_to_landmarks.py in the helper Python (MediaPipe and OpenCV live
there, never inside Blender). Plain subprocess with progress and cancel; no bpy. Mirrors face/video.py."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time

HELPERS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "helpers")
SCRIPT = os.path.join(HELPERS, "pose_to_landmarks.py")
SETUP_SCRIPT = os.path.join(HELPERS, "setup_env.py")
POSE_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/"
            "pose_landmarker_heavy.task")

SETUP_LINES = [
    "1. Preferences > Add-ons > CaptureForge > Install helper: it shows what it will download and asks first.",
    "2. Manual alternative: python -m venv .venv, then .venv/Scripts/python -m pip install mediapipe opencv-python",
    "   (Linux/macOS: .venv/bin/python), and download a pose model: " + POSE_URL,
    "3. Preferences > Add-ons > CaptureForge: set Python = the venv's python, Pose model = the pose_landmarker .task file.",
]
SETUP_TEXT = "Setup:\n" + "\n".join(SETUP_LINES)
NOISE = ("INFO:", "WARNING:", "W0000", "I0000", "E0000")  # MediaPipe's native logging on stderr

MESSAGES = {2: "The helper could not read its arguments or the video.",
            3: "The helper packages are not installed.",
            4: "The pose model file could not be read.",
            5: "No person found in any frame of the video."}


def check_setup(python, pose_model):
    """Raise ValueError (with setup instructions) unless python and the pose model point to real files."""
    if not python or not os.path.isfile(python):
        raise ValueError(f"Python for the pose helper not found: '{python}'.\n{SETUP_TEXT}")
    if not pose_model or not os.path.isfile(pose_model):
        raise ValueError(f"MediaPipe pose model file not found: '{pose_model}'.\n{SETUP_TEXT}")


def lite_next_to(pose_model):
    """The lite model that setup_env.py puts beside the heavy one, used as the automatic fallback."""
    lite = os.path.join(os.path.dirname(pose_model), "pose_landmarker_lite.task")
    return lite if os.path.isfile(lite) and os.path.abspath(lite) != os.path.abspath(pose_model) else None


class Job:
    """A running helper process. poll() is non-blocking: None while running, then the summary dict or ValueError."""

    def __init__(self, cmd, out_npz, python):
        self.out, self.progress, self.summary, self.cancelled, self.status = out_npz, 0.0, None, False, ""
        self._err = []
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as e:
            raise ValueError(f"Could not run '{python}': {e}") from e
        self._threads = [threading.Thread(target=self._read_out, daemon=True),
                         threading.Thread(target=self._read_err, daemon=True)]
        for t in self._threads:
            t.start()

    def _read_out(self):
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                self.status = line.strip() or self.status  # plain text: what the setup script is doing
                continue
            if isinstance(msg, dict):
                if "progress" in msg:
                    self.progress = float(msg["progress"])
                if msg.get("done") or "python" in msg:  # the helper's summary, or setup_env's final paths
                    self.summary, self.progress = msg, 1.0

    def _read_err(self):
        for line in self.proc.stderr:
            line = line.rstrip()
            if line and not line.startswith(NOISE):
                self._err.append(line)
                del self._err[:-12]

    @property
    def finished(self):
        return self.proc.poll() is not None

    def poll(self):
        code = self.proc.poll()
        if code is None:
            return None
        for t in self._threads:
            t.join(timeout=2)
        if self.cancelled:
            raise ValueError("Cancelled.")
        if code != 0 or self.summary is None:
            msg = "\n".join(self._err[-4:]) or MESSAGES.get(code, f"The helper exited with code {code}.")
            if code == 3 or "missing package" in msg or "No module named" in msg:
                msg += f"\n{SETUP_TEXT}"
            elif code == 5 and "No person" not in msg:
                msg = MESSAGES[5]
            raise ValueError(msg)
        return self.summary

    def cancel(self):
        """Stop the helper; it writes its file only at the very end, but remove any stray file anyway."""
        self.cancelled = True
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        for t in self._threads:
            t.join(timeout=2)
        if os.path.isfile(self.out):
            os.remove(self.out)


def start(python, pose_model, video, out_npz, hands_model=None, variant="heavy", head_box=False, max_seconds=None,
          script=None):
    """Start the helper on a video; returns a Job."""
    check_setup(python, pose_model)
    if not os.path.isfile(video):
        raise ValueError(f"Video not found: {video}")
    if hands_model and not os.path.isfile(hands_model):
        raise ValueError(f"MediaPipe hand model file not found: '{hands_model}'.\n{SETUP_TEXT}")
    cmd = [python, script or SCRIPT, video, "-o", out_npz, "--pose-model", pose_model, "--variant", variant]
    if hands_model:
        cmd += ["--hands-model", hands_model]
    if head_box:
        cmd.append("--head-box")
    if max_seconds:
        cmd += ["--max-seconds", str(max_seconds)]
    if variant == "heavy" and lite_next_to(pose_model):
        cmd += ["--fallback-model", lite_next_to(pose_model)]
    return Job(cmd, out_npz, python)


def run(python, pose_model, video, out_npz, hands_model=None, variant="heavy", head_box=False, on_progress=None,
        timeout=None, max_seconds=None, script=None):
    """Run the helper to the end (blocking). Returns its summary dict; ValueError carries the helper's last
    error lines (plus the setup text when packages are missing)."""
    job = start(python, pose_model, video, out_npz, hands_model, variant, head_box, max_seconds, script)
    t0, last = time.time(), -1.0
    while True:
        result = job.poll()
        if on_progress and job.progress != last:
            last = job.progress
            on_progress(last)
        if result is not None:
            return result
        if timeout is not None and time.time() - t0 > timeout:
            job.cancel()
            raise ValueError(f"The helper timed out after {timeout:g} s.")
        time.sleep(0.05)


# ------------------------------------------------------------------ one-time helper setup

def _setup_module():
    spec = importlib.util.spec_from_file_location("bodyforge_setup_env", SETUP_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def setup_plan(venv, hands=False):
    """What Install helper will do (text shown before anything happens): venv, packages, model URLs, sizes."""
    return _setup_module().plan_text(venv, hands)


def find_system_python():
    """A Python 3.10 or newer on the PATH to create the helper venv with, or '' if there is none."""
    for name in ("python3", "python", "py"):
        exe = shutil.which(name)
        if not exe:
            continue
        try:
            out = subprocess.run([exe, "-c", "import sys; print(sys.version_info >= (3, 10))"], capture_output=True,
                                 text=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out.stdout.strip() == "True":
            return exe
    return ""


def start_setup(system_python, venv, hands=False):
    """Run setup_env.py --yes with a system Python; returns a Job (its summary holds the paths for the preferences)."""
    if not system_python:
        raise ValueError("No Python 3.10 or newer was found on this computer. Install one from python.org "
                         "(tick 'Add python.exe to PATH') and press Install helper again.")
    cmd = [system_python, SETUP_SCRIPT, "--venv", venv, "--yes"] + (["--hands"] if hands else [])
    return Job(cmd, "", system_python)


def check_helper(python, pose_model, modules=("mediapipe", "cv2", "numpy")):
    """Verify the helper Python can import its packages and the pose model exists. Returns 'helper ready'."""
    check_setup(python, pose_model)
    try:
        p = subprocess.run([python, "-c", "import " + ", ".join(modules)], capture_output=True, text=True,
                           timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError(f"Could not run '{python}': {e}") from e
    if p.returncode:
        last = (p.stderr.strip().splitlines() or ["import failed"])[-1]
        raise ValueError(f"The helper Python cannot import its packages ({last}).\n{SETUP_TEXT}")
    return "helper ready"
