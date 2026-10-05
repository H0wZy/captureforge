"""Live capture failures as a fixed set of codes, each with a one-line message and a fix per operating system
(specs/004-live-capture-panel, FR-012). The helper sends the codes it can see (HELPER_CODES) in an "error" message,
or as a last "error_code: <code>" line on stderr; Blender derives the others from the helper's exit and socket errors.
Pure Python, standard library only.
"""

import errno
import re
import sys

_ANY = "any"
# code: (message, {os: fix}); "any" is the fix on every OS without its own line.
CODES = {
    "no_camera": ("No camera found at this index.", {
        _ANY: "Plug the camera in, press Refresh cameras and pick it from the list."}),
    "camera_busy": ("The camera is in use by another app.", {
        _ANY: "Close the other app that uses the camera (video call, browser tab, OBS), then press Capture again."}),
    "permission_denied": ("The operating system denied access to the camera.", {
        "windows": "Settings > Privacy & security > Camera: turn on camera access and 'Let desktop apps access "
                   "your camera'.",
        "darwin": "System Settings > Privacy & Security > Camera: enable Blender, then restart Blender.",
        "linux": "Add your user to the 'video' group (sudo usermod -aG video $USER), log out and in, and check that "
                 "/dev/video* exists."}),
    "no_frames": ("The camera opened but delivered no frames.", {
        _ANY: "Pick another camera; some virtual cameras deliver nothing until their app is running."}),
    "helper_missing": ("The capture helper is not installed or cannot start.", {
        _ANY: "Press Install helper in the FaceForge panel (or the add-on preferences) and confirm."}),
    "model_missing": ("The face model file is missing.", {
        _ANY: "Press Install helper again, or set Face model in the add-on preferences to face_landmarker.task."}),
    "model_corrupt": ("The face model file does not load.", {
        _ANY: "Delete the model file and press Install helper again; it checks the download's SHA-256."}),
    "helper_crashed": ("The capture helper stopped unexpectedly.", {
        _ANY: "The part recorded so far is kept. Press Capture to start again; the helper's last error lines are "
              "shown below."}),
    "port_busy": ("No free local port for the capture connection.", {
        _ANY: "Press Capture again (a new port is chosen); if it keeps failing, check local firewall software."}),
    "token_mismatch": ("Another program answered on the capture port.", {
        _ANY: "Press Capture again; the connection is local and refuses programs without this session's key."}),
    "version_mismatch": ("The capture helper does not match this add-on version.", {
        _ANY: "Reinstall or update the add-on so the helper script and the add-on come from the same release."}),
}
HELPER_CODES = ("no_camera", "camera_busy", "permission_denied", "no_frames", "helper_missing", "model_missing",
                "model_corrupt")


def os_key(platform=None):
    platform = platform or sys.platform
    if platform.startswith("win"):
        return "windows"
    return "darwin" if platform == "darwin" else "linux"


def message(code, platform=None, detail=""):
    """'<message>\\n[<detail>\\n]Fix: <fix for this OS>'."""
    if code not in CODES:
        return f"Live capture failed ({code})." + (f"\n{detail}" if detail else "")
    text, fixes = CODES[code]
    fix = fixes.get(os_key(platform), fixes.get(_ANY, ""))
    return text + (f"\n{detail}" if detail else "") + f"\nFix: {fix}"


def from_exit(returncode, stderr_text):
    """The code for a helper that exited during a capture, from its exit code and the end of its stderr."""
    found = re.findall(r"^error_code: ([a-z_]+)\s*$", stderr_text or "", re.M)
    if found:
        return found[-1] if found[-1] in HELPER_CODES else "helper_crashed"
    if "missing package" in (stderr_text or "") or "No module named" in (stderr_text or ""):
        return "helper_missing"
    if "model file not found" in (stderr_text or ""):
        return "model_missing"
    return "helper_crashed"


_ADDR_IN_USE = {errno.EADDRINUSE, 10048}  # 10048 = WSAEADDRINUSE on Windows


def from_os_error(exc):
    """The code for an OSError from starting the helper (missing or not executable) or from the socket."""
    if isinstance(exc, (FileNotFoundError, PermissionError)):
        return "helper_missing"
    if exc.errno in _ADDR_IN_USE or getattr(exc, "winerror", None) in _ADDR_IN_USE:
        return "port_busy"
    return "helper_crashed"
