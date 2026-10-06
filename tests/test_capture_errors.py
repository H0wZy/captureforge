"""Self-check for captureforge/face/capture/errors.py: every error code of FR-012 has a message and a fix on each
operating system, and helper exits and socket errors map to codes. Standard library only.
Run: python tests/test_capture_errors.py"""

import errno
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "captureforge" / "face" / "capture"))

import errors as e  # noqa: E402

FR_012 = {"no_camera", "camera_busy", "permission_denied", "no_frames", "helper_missing", "model_missing",
          "model_corrupt", "helper_crashed", "port_busy", "token_mismatch"}


def test_every_code_has_a_message_and_a_fix_per_os():
    assert FR_012 <= set(e.CODES), FR_012 - set(e.CODES)
    for code in e.CODES:
        for plat in ("win32", "darwin", "linux"):
            text = e.message(code, plat)
            assert text.startswith(e.CODES[code][0]) and "\nFix: " in text and len(text.split("\nFix: ")[1]) > 10, \
                (code, plat, text)


def test_fixes_name_the_os_setting():
    assert "Privacy" in e.message("permission_denied", "win32")
    assert "Privacy & Security" in e.message("permission_denied", "darwin")
    assert "video" in e.message("permission_denied", "linux")
    assert e.message("permission_denied", "win32") != e.message("permission_denied", "linux")


def test_detail_and_unknown_code():
    assert e.message("no_camera", "linux", "index 3").splitlines()[1] == "index 3"
    assert e.message("what_is_this", "linux").startswith("Live capture failed (what_is_this)")


def test_helper_exit_maps_to_codes():
    assert e.from_exit(1, "Traceback ...\nerror: missing package (mediapipe). Install with: pip ...") == "helper_missing"
    assert e.from_exit(1, "error: model file not found: x.task") == "model_missing"
    assert e.from_exit(1, "error_code: camera_busy\n") == "camera_busy"  # the helper's own last word wins
    assert e.from_exit(-9, "") == "helper_crashed"
    assert e.from_exit(0, "") == "helper_crashed"  # it should not end on its own during a capture
    assert e.from_exit(1, "error_code: something_new") == "helper_crashed"


def test_os_errors_map_to_codes():
    assert e.from_os_error(FileNotFoundError(errno.ENOENT, "no such file")) == "helper_missing"
    assert e.from_os_error(PermissionError(errno.EACCES, "denied")) == "helper_missing"
    assert e.from_os_error(OSError(errno.EADDRINUSE, "in use")) == "port_busy"
    assert e.from_os_error(OSError(10048, "WSAEADDRINUSE")) == "port_busy"
    assert e.from_os_error(ConnectionResetError(errno.ECONNRESET, "reset")) == "helper_crashed"


def test_helper_codes_are_known():
    assert set(e.HELPER_CODES) <= set(e.CODES)
    helper = (ROOT / "captureforge" / "face" / "helpers" / "capture_helper.py")
    if helper.is_file():  # every code the helper can send is one Blender can explain
        import re
        sent = set(re.findall(r'(?:HelperError|fail)\(\s*"([a-z_]+)"', helper.read_text(encoding="utf-8")))
        assert sent and sent <= set(e.HELPER_CODES), sent - set(e.HELPER_CODES)


if __name__ == "__main__":
    tests = [f for k, f in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
