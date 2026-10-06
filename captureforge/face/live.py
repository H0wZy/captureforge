"""Live face capture: receive the 52 ARKit scores over localhost UDP and drive shape keys in real time.

The sender is helpers/webcam_stream.py (webcam + MediaPipe, started by Session.start) or anything that sends the
same JSON datagram: {"state": "live", "v": [52 floats in ARKit order]} or {"state": "live", "s": {"name": value}}.
Pure Python plus bpy data access; the modal operator in ops.py only calls Session.tick on a timer.
"""

import json
import os
import socket
import subprocess
import tempfile
import time

import bpy

from .presets import ARKIT_52

HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "helpers", "webcam_stream.py")
HOST = "127.0.0.1"


def parse_packet(data):
    """bytes -> (state, {name: value}) or None for anything that is not a valid packet."""
    try:
        msg = json.loads(data.decode("utf-8"))
        state = str(msg.get("state", "live"))
        if "v" in msg:
            if len(msg["v"]) != len(ARKIT_52):
                return None
            scores = {n: float(x) for n, x in zip(ARKIT_52, msg["v"])}
        elif "s" in msg:
            scores = {str(k): float(v) for k, v in msg["s"].items()}
        else:
            return None
    except (ValueError, AttributeError, TypeError, UnicodeDecodeError):
        return None
    return state, scores


class Receiver:
    """Non-blocking UDP socket on localhost. poll() drains everything pending; the newest valid packet wins."""

    def __init__(self, port=9876):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind((HOST, port))
        except OSError as e:
            self.sock.close()
            raise ValueError(f"Cannot listen on {HOST}:{port} ({e}); is another capture already running?") from e
        self.sock.setblocking(False)
        self.port = self.sock.getsockname()[1]

    def poll(self):
        """(state, scores, count) of the newest valid packet, or (None, None, 0); count = datagrams read."""
        newest, count = None, 0
        while True:
            try:
                data, _ = self.sock.recvfrom(65535)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:  # e.g. connection reset notices on Windows
                break
            count += 1
            parsed = parse_packet(data)
            if parsed:
                newest = parsed
        return (*newest, count) if newest else (None, None, count)

    def close(self):
        self.sock.close()


def apply_scores(targets, scores, record_frame=None, mapping=None):
    """Set shape key values on every target from {name: value} (case-insensitive, optional rename map).
    record_frame: also keyframe those values on that frame, into an action named <object>_livemocap.
    Returns the number of keys set."""
    mapping = mapping or {}
    n = 0
    for obj in targets:
        keys = obj.data.shape_keys
        if keys is None:
            continue
        by_lower = {kb.name.lower(): kb for kb in keys.key_blocks if kb != keys.reference_key}
        if record_frame is not None:
            ad = keys.animation_data or keys.animation_data_create()
            if ad.action is None or not ad.action.name.startswith(f"{obj.name}_livemocap"):
                ad.action = bpy.data.actions.new(f"{obj.name}_livemocap")
        for name, value in scores.items():
            kb = by_lower.get(mapping.get(name.lower(), name).lower())
            if kb is None:
                continue
            kb.value = min(max(value, kb.slider_min), kb.slider_max)
            if record_frame is not None:
                keys.keyframe_insert(data_path=f'key_blocks["{kb.name}"].value', frame=record_frame)
            n += 1
    return n


def helper_command(python, model, port, source=0, smooth=0.3, neutral_seconds=2.0, gain=1.0, hz=30.0, profile=""):
    cmd = [python, HELPER, "--model", model, "--source", str(source), "--port", str(port), "--hz", str(hz),
           "--smooth", str(smooth), "--neutral-seconds", str(neutral_seconds), "--gain", str(gain)]
    return cmd + (["--profile", profile] if profile else [])


class Session:
    """One live capture: a Receiver, optionally the helper process, and the recording state."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.receiver = self.process = self.errfile = None
        self.state, self.packets, self.error = "stopped", 0, ""
        self.record, self.rec_t0, self.start_frame = False, None, 1

    @property
    def active(self):
        return self.receiver is not None

    def start(self, port, command=None, record=False, start_frame=1):
        """Listen on port; with command (see helper_command) also launch the helper. ValueError on failure."""
        if self.active:
            raise ValueError("Live capture is already running")
        self.receiver = Receiver(port)
        self.record, self.start_frame, self.rec_t0 = record, start_frame, None
        self.state, self.packets, self.error = "waiting", 0, ""
        if command:
            self.errfile = tempfile.TemporaryFile()
            try:
                self.process = subprocess.Popen(
                    command, stdout=subprocess.DEVNULL, stderr=self.errfile,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError as e:
                self.stop()
                raise ValueError(f"Could not start '{command[0]}': {e}") from e

    def tick(self, targets, fps, mapping=None):
        """One timer step: read packets, drive the targets (and record). Returns the number of keys set."""
        if not self.active:
            return 0
        if self.process is not None and self.process.poll() is not None:
            self.errfile.seek(0)
            tail = self.errfile.read().decode("utf-8", "replace").strip().splitlines()[-4:]
            self.error = "\n".join(tail) or f"helper exited with code {self.process.returncode}"
            self.stop(keep_error=True)
            return 0
        state, scores, count = self.receiver.poll()
        self.packets += count
        if state is None:
            return 0
        self.state = state
        if state == "calibrating" or state == "noface":
            return 0  # hold the last pose; calibrating packets are zeros
        frame = None
        if self.record:
            self.rec_t0 = self.rec_t0 or time.monotonic()
            frame = self.start_frame + int(round((time.monotonic() - self.rec_t0) * fps))
        return apply_scores(targets, scores, frame, mapping)

    def stop(self, keep_error=False):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.receiver is not None:
            self.receiver.close()
        if self.errfile is not None:
            self.errfile.close()
        err = self.error if keep_error else ""
        self.reset()
        self.error = err


SESSION = Session()
