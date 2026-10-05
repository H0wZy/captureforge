"""The framed loopback protocol between Blender and the capture helper (specs/004-live-capture-panel, FR-003).

A message is [uint32 header length][uint32 payload length][JSON header, UTF-8][payload], little endian. The header is
an object with a "type". The helper connects to 127.0.0.1 on the port Blender chose and its first message is "hello"
with the per-session token; Blender drops the connection on a wrong token. Types from the helper: hello, state, frame,
error, bye; from Blender: config, stop. A reader ignores types it does not know, so the interface can grow; a change
that breaks old readers bumps INTERFACE.

Pure Python, standard library only. Like post.py it is imported by path by the helper and as
captureforge.face.capture.protocol by Blender.
"""

import hmac
import json
import secrets
import struct

INTERFACE = 1
PREFIX = struct.Struct("<II")
MAX_HEADER = 256 * 1024           # a frame header with 478 landmarks is about 15 KB
MAX_PAYLOAD = 8 * 1024 * 1024     # a preview frame, 1280 x 720 RGB is 2.7 MB; the helper sends 320 px wide
FROM_HELPER = frozenset({"hello", "state", "frame", "error", "bye"})
FROM_BLENDER = frozenset({"config", "stop"})


class ProtocolError(ValueError):
    """code: bad_message (framing or JSON), token_mismatch, version_mismatch."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def encode(header, payload=b""):
    """One message as bytes. ValueError when the header or the payload is over the bounds."""
    head = json.dumps(header, separators=(",", ":")).encode("utf-8")
    if len(head) > MAX_HEADER or len(payload) > MAX_PAYLOAD:
        raise ValueError(f"message too large ({len(head)} header bytes, {len(payload)} payload bytes)")
    return PREFIX.pack(len(head), len(payload)) + head + bytes(payload)


class Decoder:
    """Turns a byte stream into (header, payload) pairs; tolerates any split of the stream. known: the types to
    keep (None keeps all). ProtocolError on a broken stream, after which the connection should be closed."""

    def __init__(self, known=None):
        self.known, self.buf = known, bytearray()

    def pending(self):
        return len(self.buf)

    def feed(self, data):
        self.buf += data
        out = []
        while len(self.buf) >= PREFIX.size:
            n_head, n_pay = PREFIX.unpack_from(self.buf)
            if not 0 < n_head <= MAX_HEADER or n_pay > MAX_PAYLOAD:
                raise ProtocolError("bad_message", f"bad message lengths ({n_head}, {n_pay})")
            end = PREFIX.size + n_head + n_pay
            if len(self.buf) < end:
                break
            try:
                header = json.loads(bytes(self.buf[PREFIX.size:PREFIX.size + n_head]).decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as e:
                raise ProtocolError("bad_message", f"unreadable message header: {e}") from e
            if not isinstance(header, dict) or not isinstance(header.get("type"), str):
                raise ProtocolError("bad_message", "message header without a type")
            payload = bytes(self.buf[PREFIX.size + n_head:end])
            del self.buf[:end]
            if self.known is None or header["type"] in self.known:
                out.append((header, payload))
        return out


def new_token():
    return secrets.token_hex(16)


def hello(token):
    return encode({"type": "hello", "token": token, "interface": INTERFACE})


def check_hello(header, token):
    """The first message must be hello with this session's token and the same interface version."""
    if header.get("type") != "hello" or not hmac.compare_digest(str(header.get("token", "")), token):
        raise ProtocolError("token_mismatch", "the capture helper did not present this session's token")
    if header.get("interface") != INTERFACE:
        raise ProtocolError("version_mismatch", f"the capture helper speaks interface {header.get('interface')}, "
                                                f"this add-on speaks {INTERFACE}")


def _round(values, digits):
    return None if values is None else [round(float(x), digits) for x in values]


def frame(seq, t, raw, calibrated, landmarks, matrix, preview=None):
    """A frame message. raw and calibrated: 52 scores in ARKit order or None (no face); landmarks: 478 [x, y, z]
    or None, sent flat; matrix: 16 row-major floats or None; t: the helper's capture time in seconds;
    preview: (width, height, RGB bytes) or None."""
    flat = None if landmarks is None else [x for p in landmarks for x in p]
    header = {"type": "frame", "seq": seq, "t": t, "raw": _round(raw, 5), "cal": _round(calibrated, 5),
              "lm": _round(flat, 5), "m": _round(matrix, 6)}
    payload = b""
    if preview is not None:
        w, h, payload = preview
        if len(payload) != w * h * 3:
            raise ValueError(f"preview is {len(payload)} bytes, {w} x {h} RGB needs {w * h * 3}")
        header["pw"], header["ph"] = w, h
    return encode(header, payload)
