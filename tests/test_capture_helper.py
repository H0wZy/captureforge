"""The capture helper (captureforge/face/helpers/capture_helper.py) end to end with a fake camera (synthetic frames)
and a fake tracker: this test plays Blender's side of the loopback protocol. Needs numpy (no OpenCV, no MediaPipe,
no camera). Run: python tests/test_capture_helper.py"""

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPERS = ROOT / "captureforge" / "face" / "helpers"
sys.path.insert(0, str(ROOT / "captureforge" / "face" / "capture"))
sys.path.insert(0, str(HELPERS))

import protocol  # noqa: E402

HELPER = HELPERS / "capture_helper.py"


class Blender:
    """The add-on's side: listen, start the helper with a stdin pipe, read messages."""

    def __init__(self, *args, token=None, connect=True):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.srv.settimeout(10)
        self.token = token or protocol.new_token()
        port = self.srv.getsockname()[1] if connect else 9
        self.proc = subprocess.Popen([sys.executable, str(HELPER), "--port", str(port), "--token", self.token, *args],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.conn, self.dec, self.msgs = None, protocol.Decoder(), []

    def accept(self):
        self.conn, _ = self.srv.accept()
        self.conn.settimeout(10)

    def read_until(self, pred, timeout=10.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for i, (h, _) in enumerate(self.msgs):
                if pred(h):
                    return self.msgs[i]
            try:
                data = self.conn.recv(1 << 16)
            except socket.timeout:
                continue
            if not data:
                break
            self.msgs += self.dec.feed(data)
        return next(((h, p) for h, p in self.msgs if pred(h)), None)

    def send(self, header):
        self.conn.sendall(protocol.encode(header))

    def wait_exit(self, timeout):
        start = time.monotonic()
        try:
            self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
            raise AssertionError(f"helper still running after {timeout} s")
        return time.monotonic() - start

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        for s in (self.conn, self.srv):
            if s is not None:
                s.close()
        for f in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            if f and not f.closed:
                f.close()


FAKE = ["--source", "synthetic", "--fake-tracker", "--neutral-seconds", "0.3"]


def test_hello_states_frames_and_preview():
    b = Blender(*FAKE)
    try:
        b.accept()
        first = b.read_until(lambda h: True)
        protocol.check_hello(first[0], b.token)
        assert b.read_until(lambda h: h.get("state") == "calibrating")
        assert b.read_until(lambda h: h.get("state") == "live")
        assert b.read_until(lambda h: h.get("state") == "noface", timeout=6), "the synthetic camera blanks once a while"
        assert b.read_until(lambda h: h["type"] == "frame" and h["raw"] is None), "no-face frames are sent too"
        frames = [(h, p) for h, p in b.msgs if h["type"] == "frame"]
        faces = [(h, p) for h, p in frames if h["raw"] is not None]
        h, _ = faces[-1]
        assert len(h["raw"]) == 52 and len(h["cal"]) == 52 and len(h["lm"]) == 478 * 3 and len(h["m"]) == 16
        assert all(h["lm"] is None and h["m"] is None for h, _ in frames if h["raw"] is None)
        seqs = [h["seq"] for h, _ in frames]
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
        assert all(abs(h["t"] - time.time()) < 30 for h, _ in frames), "times are on the host clock"
        previews = [(h, p) for h, p in frames if p]
        assert previews and all(len(p) == h["pw"] * h["ph"] * 3 and h["pw"] <= 320 for h, p in previews)
        span = frames[-1][0]["t"] - frames[0][0]["t"]
        assert len(previews) <= 15 * span + 3, (len(previews), span)  # capped at 15 Hz
        assert len(frames) >= 20 * span, (len(frames), span)  # about 30 fps from the fake camera
    finally:
        b.close()


def test_exits_when_blender_closes_stdin():
    b = Blender(*FAKE)
    try:
        b.accept()
        assert b.read_until(lambda h: h["type"] == "frame")
        b.proc.stdin.close()
        assert b.wait_exit(2.0) < 2.0
    finally:
        b.close()


def test_stop_message_says_bye():
    b = Blender(*FAKE)
    try:
        b.accept()
        assert b.read_until(lambda h: h["type"] == "frame")
        b.send({"type": "stop"})
        assert b.read_until(lambda h: h["type"] == "bye")
        b.wait_exit(3.0)
        assert b.proc.returncode == 0, b.proc.stderr.read()
    finally:
        b.close()


def test_config_changes_preview():
    b = Blender(*FAKE)
    try:
        b.accept()
        assert b.read_until(lambda h: h["type"] == "frame")
        b.send({"type": "config", "preview": False})
        time.sleep(0.5)
        n = len(b.msgs)
        b.read_until(lambda h: False, timeout=1.0)
        later = [p for h, p in b.msgs[n:] if h["type"] == "frame"]
        assert later and not any(later), "no preview after preview off"
    finally:
        b.close()


def test_fatal_error_is_sent_then_exit():
    b = Blender("--source", "synthetic", "--model", str(ROOT / "no_such_model.task"))
    try:
        b.accept()
        err = b.read_until(lambda h: h["type"] == "error")
        assert err and err[0]["code"] == "model_missing", b.msgs
        b.wait_exit(3.0)
        assert b.proc.returncode == 2 and "error_code: model_missing" in b.proc.stderr.read().decode()
    finally:
        b.close()


def test_no_listener_exits_quickly():
    b = Blender(*FAKE, connect=False)
    try:
        assert b.wait_exit(5.0) < 5.0 and b.proc.returncode != 0
    finally:
        b.close()


def run(*args):
    return subprocess.run([sys.executable, str(HELPER), *args], capture_output=True, text=True, timeout=30)


def test_list_cameras_prints_json():
    p = run("--list-cameras")
    assert p.returncode == 0, p.stderr
    cams = json.loads(p.stdout.strip().splitlines()[-1])
    assert isinstance(cams, list) and all({"index", "name", "backend"} <= set(c) for c in cams)


def test_probe_cameras_with_a_fake_opener():
    import capture_helper as ch
    opened = {0: True, 2: True}
    cams = ch.probe_cameras(lambda i: opened.get(i, False), max_index=5)
    assert cams == [{"index": 0, "name": "Camera 0", "backend": ""}, {"index": 2, "name": "Camera 2", "backend": ""}]


def test_self_test():
    p = run("--self-test", "--fake-tracker")
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout.strip().splitlines()[-1])["ok"] is True
    p = run("--self-test", "--model", str(ROOT / "no_such_model.task"))
    assert p.returncode == 2 and "error_code: model_missing" in p.stderr, p.stderr


def test_profile_in_the_live_stream():
    import os
    import tempfile
    prof = {"format": "faceforge-actor-profile", "version": 1, "mirrored": False, "gains": {"jawOpen": 4.0},
            "crosstalk": {}, "undetected": []}
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "me.faceprofile.json")
        with open(path, "w") as f:
            json.dump(prof, f)
        b = Blender(*FAKE, "--smooth", "0", "--neutral-seconds", "0", "--profile", path)
        try:
            b.accept()
            n = [0]

            def enough(h):  # 60 live frames with a face
                n[0] += h["type"] == "frame" and h["cal"] is not None and h["raw"] is not None
                return n[0] >= 60
            b.read_until(enough)
            cal = [h["cal"][17] for h, _ in b.msgs if h["type"] == "frame" and h["cal"] is not None]
            raw = [h["raw"][17] for h, _ in b.msgs if h["type"] == "frame" and h["raw"] is not None]
            assert max(raw) < 0.95 and max(cal) == 1.0, (max(raw), max(cal))  # gain 4 saturates; raw never does
        finally:
            b.close()
        with open(path, "w") as f:
            f.write("not json")
        b = Blender(*FAKE, "--profile", path)
        try:
            b.accept()
            err = b.read_until(lambda h: h["type"] == "error")
            assert err and err[0]["code"] == "profile_invalid", b.msgs
        finally:
            b.close()


if __name__ == "__main__":
    try:
        import numpy  # noqa: F401
    except ImportError:
        print("skipped: needs numpy")
        sys.exit(0)
    tests = [f for k, f in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
