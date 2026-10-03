"""Self-check for the pure parts of helpers/webcam_stream.py (Stream, packet). Needs no mediapipe/opencv/Blender.
Run: python tests/test_webcam_stream.py"""

import json
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent.parent / "captureforge" / "face" / "helpers"
sys.path.insert(0, str(HELPERS))

import video_to_csv as v  # noqa: E402
import webcam_stream as w  # noqa: E402


def close(a, b, eps=1e-6):
    return abs(a - b) < eps


def test_calibrate_then_live():
    s = w.Stream(neutral_seconds=1.0, gain=2.0, smooth=0.0)
    jaw = v.ARKIT_52.index("jawOpen")
    for i in range(4):  # neutral window: a jaw resting at 0.1, no output yet
        state, vec = s.update(i * 0.25, {"jawOpen": 0.1})
        assert state == "calibrating" and max(vec) == 0.0
    state, vec = s.update(1.0, {"jawOpen": 0.4})  # baseline 0.1 -> (0.4 - 0.1) * 2 = 0.6
    assert state == "live" and close(vec[jaw], 0.6), vec[jaw]
    assert s.update(1.1, {"jawOpen": 0.0})[1][jaw] == 0.0, "below baseline clamps to 0"
    assert s.update(1.2, {"jawOpen": 5.0})[1][jaw] == 1.0, "clamps to 1"


def test_noface_holds_last_value():
    s = w.Stream(neutral_seconds=0.0, gain=1.0, smooth=0.0)
    jaw = v.ARKIT_52.index("jawOpen")
    assert s.update(0.0, {"jawOpen": 0.5})[1][jaw] == 0.5
    state, vec = s.update(0.1, None)
    assert state == "noface" and vec[jaw] == 0.5


def test_smoothing_is_an_ema():
    s = w.Stream(neutral_seconds=0.0, gain=1.0, smooth=0.5)
    jaw = v.ARKIT_52.index("jawOpen")
    out = [s.update(i * 0.1, {"jawOpen": 1.0})[1][jaw] for i in range(3)]
    assert close(out[0], 0.5) and close(out[1], 0.75) and close(out[2], 0.875), out


def test_packet_format():
    msg = json.loads(w.packet(1.23456789, "live", [0.123456] * 52))
    assert msg["state"] == "live" and len(msg["v"]) == 52 and msg["v"][0] == 0.1235 and msg["t"] == 1.2346


if __name__ == "__main__":
    tests = [f for k, f in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
