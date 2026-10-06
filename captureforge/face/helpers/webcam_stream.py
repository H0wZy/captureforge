"""Webcam (or video file) -> MediaPipe Face Landmarker, LIVE_STREAM mode -> the 52 ARKit scores over UDP.

Usage: python webcam_stream.py --model face_landmarker.task [--source 0] [--port 9876] [--hz 30]
       [--smooth 0.3] [--neutral-seconds 2] [--gain 1.0] [--loop]

Runs outside Blender (in the Python that has mediapipe and opencv). Packet, one UDP datagram of JSON to
127.0.0.1:port, about --hz times a second:
    {"t": seconds, "state": "calibrating" | "live" | "noface", "v": [52 floats in ARKit_52 order]}
The first --neutral-seconds are the neutral baseline (hold a still neutral face); during it the scores are zero.
Scores are baseline-subtracted, scaled by --gain, clamped to 0..1 and lightly smoothed. Stop with Ctrl+C or by
terminating the process. ponytail: it never learns the parent died; the add-on kills it on Stop.
"""

import argparse
import json
import socket
import time

from video_to_csv import ARKIT_52, _fail, _import_cv, open_tracker


class Stream:
    """Streaming version of video_to_csv's calibrate + smooth: feed (t, scores or None), get (state, vector)."""

    def __init__(self, neutral_seconds=2.0, gain=1.0, smooth=0.3, profile=None):
        self.neutral, self.gain, self.smooth = neutral_seconds, gain, min(max(smooth, 0.0), 0.99)
        self.profile = profile  # actor profile (spec 005): applied after the neutral, before the smoothing
        self.t0 = None
        self.sum, self.n = [0.0] * len(ARKIT_52), 0
        self.base = None
        self.prev = [0.0] * len(ARKIT_52)

    def update(self, t, scores):
        """scores: {name: value} for the frame, or None when no face was found."""
        if self.t0 is None:
            self.t0 = t
        if scores is None:
            return "noface", list(self.prev)
        raw = [scores.get(n, 0.0) for n in ARKIT_52]
        if self.base is None:
            if t - self.t0 < self.neutral:
                self.sum = [s + x for s, x in zip(self.sum, raw)]
                self.n += 1
                return "calibrating", [0.0] * len(raw)
            self.base = [s / self.n for s in self.sum] if self.n else [0.0] * len(raw)
        out = [min(1.0, max(0.0, (x - b) * self.gain)) for x, b in zip(raw, self.base)]
        if self.profile is not None:
            from calib import apply  # ../capture (on sys.path through video_to_csv), needs numpy
            out = apply(self.profile, ARKIT_52, [out])[0].tolist()
        self.prev = [self.smooth * p + (1 - self.smooth) * x for p, x in zip(self.prev, out)]
        return "live", list(self.prev)


def packet(t, state, vector):
    return json.dumps({"t": round(t, 4), "state": state, "v": [round(x, 4) for x in vector]}).encode()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="face_landmarker.task")
    ap.add_argument("--source", default="0", help="camera index, or a video file path")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9876)
    ap.add_argument("--hz", type=float, default=30.0)
    ap.add_argument("--smooth", type=float, default=0.3)
    ap.add_argument("--neutral-seconds", type=float, default=2.0)
    ap.add_argument("--gain", type=float, default=1.0)
    ap.add_argument("--loop", action="store_true", help="restart a video file when it ends")
    ap.add_argument("--profile", help="actor profile (.faceprofile.json, spec 005) that corrects the scores")
    a = ap.parse_args()
    profile = None
    if a.profile:
        from calib import CalibrationError, load_profile
        try:
            profile = load_profile(a.profile)
        except CalibrationError as e:
            _fail(str(e))

    cv2, _ = _import_cv()
    tracker = open_tracker("live", a.model)
    is_file = not a.source.isdigit()
    cap = cv2.VideoCapture(a.source if is_file else int(a.source))
    if not cap.isOpened():
        _fail(f"cannot open {'video' if is_file else 'camera'}: {a.source}")
    pace = (1.0 / (cap.get(cv2.CAP_PROP_FPS) or 30.0)) if is_file else 0.0  # a camera paces itself

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    stream = Stream(a.neutral_seconds, a.gain, a.smooth, profile)
    start = time.monotonic()
    next_send, period, last_ms = start, 1.0 / a.hz, -1
    print(f"streaming {a.source} to {a.host}:{a.port} at {a.hz:g} Hz", flush=True)
    try:
        with tracker:
            while True:
                t_frame = time.monotonic()
                ok, frame = cap.read()
                if not ok:
                    if is_file and a.loop:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    break
                now = time.monotonic()
                ms = max(int((now - start) * 1000), last_ms + 1)  # strictly increasing
                last_ms = ms
                latest = tracker.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), ms)
                if now >= next_send:
                    next_send = max(next_send + period, now)
                    state, vec = stream.update(now - start, latest.scores if latest is not None else None)
                    sock.sendto(packet(now - start, state, vec), (a.host, a.port))
                if pace:
                    time.sleep(max(0.0, pace - (time.monotonic() - t_frame)))
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        sock.close()


if __name__ == "__main__":
    main()
