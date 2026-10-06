"""Live capture sidecar: camera (or a fake camera) -> face tracker -> framed messages to Blender over loopback TCP.

Blender starts it on Capture and owns its life (specs/004-live-capture-panel):
    python capture_helper.py --port N --token T [--camera 0 | --source FILE | --source synthetic] [--model M]
           [--smooth 0.3] [--neutral-seconds 2] [--gain 1] [--profile P] [--preview-width 320] [--max-width 1280]
           [--fake-tracker]
    python capture_helper.py --list-cameras      JSON list of {index, name, backend} (opens devices: only on request)
    python capture_helper.py --self-test         imports, model load, one synthetic frame; JSON {"ok": ...}

It connects to 127.0.0.1:N, says hello with the token (protocol.py), streams state and frame messages, and exits on
end of file on stdin (Blender closed the pipe, quit or died), on a "stop" message (after "bye"), when Blender closes
the connection, or on a fatal error after an "error" message. Errors also end stderr with "error_code: <code>"
(capture/errors.py). Frames carry the helper's capture time on the host clock, the raw and the calibrated scores,
the 478 landmarks, the head matrix and, at most 15 times a second, a small RGB preview.

`--source synthetic` and `--fake-tracker` are the fake camera and tracker of the tests and of CI: they need numpy
only. A real camera or video file needs OpenCV; the real tracker needs MediaPipe (tracker.py).
"""

import argparse
import json
import math
import os
import socket
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "capture"))
import protocol  # noqa: E402
from tracker import ARKIT_52, LANDMARKS, Result, Tracker, TrackerError  # noqa: E402
from webcam_stream import Stream  # noqa: E402

PREVIEW_HZ = 15.0
NO_FRAMES_SECONDS = 3.0


class HelperError(Exception):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code


# ---- fake camera and fake tracker (tests, CI, --self-test without a model) ------------------------------------

class SyntheticCamera:
    """30 fps frames whose brightness swings slowly; every fourth second is black (the fake tracker sees no face)."""

    def __init__(self, width=640, height=480, fps=30.0):
        import numpy as np
        self.np, self.w, self.h, self.period = np, width, height, 1.0 / fps
        self.i, self.next = 0, time.monotonic()

    def read(self):
        wait = self.next - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.next = max(self.next + self.period, time.monotonic() - self.period)
        i, self.i = self.i, self.i + 1
        level = 0 if (i // 30) % 4 == 3 else int(128 + 100 * math.sin(i / 10.0))
        frame = self.np.full((self.h, self.w, 3), level, self.np.uint8)
        if level:
            frame[:, : self.w // 8] = 255  # a bright bar so the preview is not flat
        return frame

    def release(self):
        pass


class FakeTracker:
    """Same interface as tracker.Tracker: jawOpen follows the frame brightness, no face on a black frame."""

    def __init__(self):
        import numpy as np
        self.np = np
        g = np.linspace(0.2, 0.8, 22)
        pts = np.array([(x, y, 0.0) for y in g for x in g][:LANDMARKS - 2] + [(0.5, 0.5, 0.0)] * 2, np.float32)
        self.landmarks, self.matrix = pts[:LANDMARKS], np.eye(4, dtype=np.float32)

    def process(self, frame_rgb, timestamp_ms):
        level = float(frame_rgb.mean()) / 255.0
        if level < 0.02:
            return Result(int(timestamp_ms), None, None, None)
        scores = {n: 0.0 for n in ARKIT_52[:-1]}
        scores["jawOpen"] = level
        return Result(int(timestamp_ms), scores, self.landmarks, self.matrix)

    def close(self):
        pass


# ---- camera ------------------------------------------------------------------------------------------------------

def _cv2():
    try:
        import cv2
    except ImportError as e:
        raise HelperError("helper_missing", f"missing package ({e.name}). Install with: pip install -r requirements.txt")
    return cv2


def probe_cameras(opens, max_index=10):
    """Indices 0..max_index-1 that open, as camera entries; opens(i) -> bool."""
    return [{"index": i, "name": f"Camera {i}", "backend": ""} for i in range(max_index) if opens(i)]


def list_cameras():
    """Names from the optional cv2-enumerate-cameras package (MIT), else a probe of indices 0 to 9 with OpenCV."""
    try:
        from cv2_enumerate_cameras import enumerate_cameras
        return [{"index": c.index, "name": c.name, "backend": str(getattr(c, "backend", ""))}
                for c in enumerate_cameras()]
    except ImportError:
        pass
    try:
        cv2 = _cv2()
    except HelperError:
        return []

    def opens(i):
        cap = cv2.VideoCapture(i)
        try:
            return cap.isOpened() and cap.read()[0]
        finally:
            cap.release()
    return probe_cameras(opens)


class Camera:
    """An OpenCV camera index or video file returning RGB frames; a video file plays at its own frame rate."""

    def __init__(self, source, loop=False):
        cv2 = self.cv2 = _cv2()
        self.is_file, self.loop = not str(source).isdigit(), loop
        self.cap = cv2.VideoCapture(str(source) if self.is_file else int(source))
        if not self.cap.isOpened():
            self.cap.release()
            raise HelperError(*_open_failure(source, self.is_file))
        self.period = 1.0 / (self.cap.get(cv2.CAP_PROP_FPS) or 30.0) if self.is_file else 0.0
        self.next, self.last_ok = time.monotonic(), time.monotonic()

    def read(self):
        """An RGB frame, None at the end of a file. HelperError when a camera stops delivering frames."""
        while True:
            ok, frame = self.cap.read()
            if ok:
                break
            if self.is_file:
                if not self.loop:
                    return None
                self.cap.set(self.cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            if time.monotonic() - self.last_ok > NO_FRAMES_SECONDS:
                raise HelperError("no_frames", "the camera delivered no frame for 3 s (unplugged or in use)")
            time.sleep(0.01)
        self.last_ok = time.monotonic()
        if self.period:
            wait = self.next - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.next = max(self.next + self.period, time.monotonic() - self.period)
        return self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)

    def release(self):
        self.cap.release()


def _open_failure(source, is_file):
    """(code, detail) for a camera or file that does not open."""
    if is_file:
        return "no_camera", f"cannot open video file: {source}"
    if sys.platform.startswith("linux"):
        dev = f"/dev/video{source}"
        if not os.path.exists(dev):
            return "no_camera", f"{dev} does not exist"
        if not os.access(dev, os.R_OK | os.W_OK):
            return "permission_denied", f"no read/write access to {dev}"
        return "camera_busy", f"{dev} exists but does not open"
    if sys.platform == "darwin":
        return "permission_denied", f"camera {source} does not open (macOS camera permission for Blender?)"
    return "camera_busy", f"camera {source} does not open (missing, in use, or blocked by Privacy settings)"


def downscale(frame, width):
    """frame scaled to at most `width` pixels wide (aspect kept); OpenCV when present, else every n-th pixel."""
    h, w = frame.shape[:2]
    if w <= width:
        return frame
    try:
        import cv2
        return cv2.resize(frame, (width, max(1, round(h * width / w))), interpolation=cv2.INTER_AREA)
    except ImportError:
        step = math.ceil(w / width)
        return frame[::step, ::step]


# ---- session -------------------------------------------------------------------------------------------------------

class Link:
    """The connection to Blender: send from the main thread, a reader thread for config and stop."""

    def __init__(self, port, token):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.stop, self.config, self.lock = threading.Event(), {}, threading.Lock()
        self.send_raw(protocol.hello(token))
        threading.Thread(target=self._read, daemon=True).start()

    def send_raw(self, data):
        try:
            self.sock.sendall(data)
        except OSError:
            self.stop.set()  # Blender is gone or not reading: end

    def _read(self):
        dec = protocol.Decoder(known=protocol.FROM_BLENDER)
        self.sock.settimeout(None)
        while not self.stop.is_set():
            try:
                data = self.sock.recv(1 << 16)
                if not data:
                    raise ConnectionError("Blender closed the connection")
                msgs = dec.feed(data)
            except (OSError, protocol.ProtocolError):
                self.stop.set()
                return
            for header, _ in msgs:
                if header["type"] == "stop":
                    self.stop.set()
                elif header["type"] == "config":
                    with self.lock:
                        self.config.update(header)

    def take_config(self):
        with self.lock:
            cfg, self.config = self.config, {}
        return cfg

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def watch_stdin(stop):
    """End the capture when Blender closes our stdin (normal stop, quit, crash or kill: the pipe closes)."""
    def run():
        try:  # os.read, not sys.stdin: a buffered reader blocked in a daemon thread aborts the interpreter's exit
            fd = sys.stdin.fileno()
            while os.read(fd, 1024):
                pass
        except (OSError, ValueError):
            pass
        stop.set()
    threading.Thread(target=run, daemon=True).start()


def open_tracker(args):
    if args.fake_tracker:
        return FakeTracker()
    try:
        return Tracker.live(args.model)
    except TrackerError as e:
        raise HelperError(e.code, str(e))


def open_source(args):
    if args.source == "synthetic":
        return SyntheticCamera()
    return Camera(args.source if args.source else args.camera, loop=args.loop)


def load_actor_profile(path):
    if not path:
        return None
    from calib import CalibrationError, load_profile  # ../capture, needs numpy
    try:
        return load_profile(path)
    except CalibrationError as e:
        raise HelperError("profile_invalid", str(e))


def capture(args, link):
    profile = load_actor_profile(args.profile)
    tracker = open_tracker(args)
    cam = open_source(args)
    stream = Stream(args.neutral_seconds, args.gain, args.smooth, profile)
    start_mono, start_wall = time.monotonic(), time.time()
    preview_on, preview_every, next_preview = True, 1.0 / PREVIEW_HZ, 0.0
    state, last_ts, last_ms, seq, small = "starting", None, -1, 0, None
    link.send_raw(protocol.encode({"type": "state", "state": state}))
    try:
        while not link.stop.is_set():
            cfg = link.take_config()
            if cfg:
                preview_on = bool(cfg.get("preview", preview_on))
                if cfg.get("recalibrate"):
                    stream = Stream(cfg.get("neutral_seconds", stream.neutral), stream.gain, stream.smooth, profile)
                stream.gain = float(cfg.get("gain", stream.gain))
                stream.smooth = min(max(float(cfg.get("smooth", stream.smooth)), 0.0), 0.99)
            frame = cam.read()
            if frame is None:
                break
            ms = max(int((time.monotonic() - start_mono) * 1000), last_ms + 1)
            last_ms = ms
            small = downscale(frame, args.max_width)
            res = tracker.process(small, ms)
            if res is None or res.timestamp_ms == last_ts:
                continue  # live mode: nothing new finished yet
            last_ts = res.timestamp_ms
            new_state, cal = stream.update(res.timestamp_ms / 1000.0, res.scores)
            if new_state != state:
                state = new_state
                link.send_raw(protocol.encode({"type": "state", "state": state}))
            raw = [res.scores.get(n, 0.0) for n in ARKIT_52] if res.face else None
            preview = None
            now = time.monotonic()
            if preview_on and now >= next_preview:
                next_preview = now + preview_every
                p = downscale(small, args.preview_width)
                preview = (p.shape[1], p.shape[0], p.tobytes())
            link.send_raw(protocol.frame(
                seq, round(start_wall + res.timestamp_ms / 1000.0, 4), raw, cal if res.face else None,
                res.landmarks.tolist() if res.landmarks is not None else None,
                res.matrix.ravel().tolist() if res.matrix is not None else None, preview))
            seq += 1
    finally:
        cam.release()
        tracker.close()
    link.send_raw(protocol.encode({"type": "bye"}))


def fail(code, detail, link=None):
    if link is not None:
        link.send_raw(protocol.encode({"type": "error", "code": code, "detail": detail}))
    print(f"error: {detail}\nerror_code: {code}", file=sys.stderr, flush=True)
    sys.exit(2)


def self_test(args):
    import numpy as np
    try:
        tracker = open_tracker(args)
        res = tracker.process(np.full((480, 640, 3), 128, np.uint8), 0)
        tracker.close()
    except HelperError as e:
        fail(e.code, str(e))
    print(json.dumps({"ok": True, "face": bool(res and res.face), "python": sys.version.split()[0]}))


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int)
    ap.add_argument("--token", default="")
    ap.add_argument("--camera", default="0", help="camera index")
    ap.add_argument("--source", default="", help="a video file, or 'synthetic' (fake camera); overrides --camera")
    ap.add_argument("--loop", action="store_true", help="restart a video file when it ends")
    ap.add_argument("--model", default="face_landmarker.task")
    ap.add_argument("--smooth", type=float, default=0.3)
    ap.add_argument("--neutral-seconds", type=float, default=2.0)
    ap.add_argument("--gain", type=float, default=1.0)
    ap.add_argument("--profile", default="", help="actor profile (.faceprofile.json, spec 005) for the calibrated scores")
    ap.add_argument("--preview-width", type=int, default=320)
    ap.add_argument("--max-width", type=int, default=1280, help="frames wider than this are scaled down first")
    ap.add_argument("--fake-tracker", action="store_true", help="tests: a fake tracker that needs numpy only")
    ap.add_argument("--list-cameras", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    return ap


def main():
    args = build_parser().parse_args()
    if args.list_cameras:
        print(json.dumps(list_cameras()))
        return
    if args.self_test:
        self_test(args)
        return
    if args.port is None:
        fail("helper_missing", "--port is required")
    try:
        link = Link(args.port, args.token)
    except OSError as e:
        print(f"error: cannot connect to Blender on 127.0.0.1:{args.port}: {e}", file=sys.stderr)
        sys.exit(3)
    watch_stdin(link.stop)
    try:
        capture(args, link)
    except HelperError as e:
        fail(e.code, str(e), link)
    finally:
        link.close()


if __name__ == "__main__":
    main()
