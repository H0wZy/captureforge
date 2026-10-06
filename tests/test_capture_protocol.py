"""Self-check for captureforge/face/capture/protocol.py, the framed loopback protocol between Blender and the capture
helper. Standard library only. Run: python tests/test_capture_protocol.py"""

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "captureforge" / "face" / "capture"))

import protocol as p  # noqa: E402


def expect_error(fn, code):
    try:
        fn()
    except p.ProtocolError as e:
        assert e.code == code, (e.code, code, str(e))
        return e
    raise AssertionError(f"expected ProtocolError {code}")


def test_round_trip_with_payload():
    data = (p.encode({"type": "state", "state": "live"}) + p.encode({"type": "frame", "seq": 3}, b"\x01\x02\x03")
            + p.encode({"type": "bye"}))
    msgs = p.Decoder().feed(data)
    assert [h["type"] for h, _ in msgs] == ["state", "frame", "bye"]
    assert msgs[1] == ({"type": "frame", "seq": 3}, b"\x01\x02\x03") and msgs[0][1] == b""


def test_partial_reads_byte_by_byte():
    data = p.encode({"type": "frame", "seq": 1}, bytes(range(256)) * 3) + p.encode({"type": "bye"})
    dec, out = p.Decoder(), []
    for i in range(len(data)):
        out += dec.feed(data[i:i + 1])
    assert [h["type"] for h, _ in out] == ["frame", "bye"] and out[0][1] == bytes(range(256)) * 3
    assert dec.pending() == 0


def test_absurd_lengths_are_rejected_before_reading_the_body():
    dec = p.Decoder()
    expect_error(lambda: dec.feed(struct.pack("<II", p.MAX_HEADER + 1, 0)), "bad_message")
    expect_error(lambda: p.Decoder().feed(struct.pack("<II", 10, p.MAX_PAYLOAD + 1)), "bad_message")
    expect_error(lambda: p.Decoder().feed(struct.pack("<II", 0, 0)), "bad_message")  # an empty header
    try:
        p.encode({"type": "frame", "junk": "x" * p.MAX_HEADER})
    except ValueError:
        pass
    else:
        raise AssertionError("encode must refuse an oversized header")


def test_bad_headers():
    bad = [b"not json", json.dumps([1, 2]).encode(), json.dumps({"no": "type"}).encode(), b"\xff\xfe"]
    for raw in bad:
        expect_error(lambda raw=raw: p.Decoder().feed(struct.pack("<II", len(raw), 0) + raw), "bad_message")


def test_unknown_types_are_ignored():
    data = p.encode({"type": "future_thing", "x": 1}) + p.encode({"type": "state", "state": "live"})
    msgs = p.Decoder(known=p.FROM_HELPER).feed(data)
    assert [h["type"] for h, _ in msgs] == ["state"]
    assert [h["type"] for h, _ in p.Decoder().feed(data)] == ["future_thing", "state"]  # no filter: all of them


def test_hello_and_token():
    token = p.new_token()
    assert len(token) >= 32 and token != p.new_token()
    (header, _), = p.Decoder().feed(p.hello(token))
    p.check_hello(header, token)  # no exception
    expect_error(lambda: p.check_hello(header, p.new_token()), "token_mismatch")
    expect_error(lambda: p.check_hello({"type": "frame", "token": token}, token), "token_mismatch")
    expect_error(lambda: p.check_hello({"type": "hello"}, token), "token_mismatch")
    e = expect_error(lambda: p.check_hello(dict(header, interface=p.INTERFACE + 1), token), "version_mismatch")
    assert str(p.INTERFACE + 1) in str(e)


def test_frame_message():
    raw, cal = [0.5] * 52, [0.25] * 52
    lm = [[0.1234567, 0.5, -0.01]] * 478
    m = [float(i) for i in range(16)]
    (h, payload), = p.Decoder().feed(p.frame(7, 1.5, raw, cal, lm, m, preview=(4, 2, bytes(24))))
    assert h["type"] == "frame" and h["seq"] == 7 and h["t"] == 1.5
    assert h["raw"] == raw and h["cal"] == cal and len(h["lm"]) == 478 * 3 and h["lm"][0] == 0.12346
    assert h["m"] == m and (h["pw"], h["ph"]) == (4, 2) and payload == bytes(24)
    (h, payload), = p.Decoder().feed(p.frame(8, 1.6, None, None, None, None))
    assert h["raw"] is None and h["lm"] is None and h["m"] is None and payload == b"" and "pw" not in h
    try:
        p.frame(9, 1.7, raw, cal, lm, m, preview=(4, 2, bytes(23)))
    except ValueError:
        pass
    else:
        raise AssertionError("a preview of the wrong size must be refused")


def test_typical_frame_fits_the_bounds():
    lm = [[0.123456, 0.654321, -0.0123456]] * 478
    data = p.frame(1, 12345.678, [0.123456] * 52, [0.123456] * 52, lm, [0.123456] * 16,
                   preview=(320, 240, bytes(320 * 240 * 3)))
    head_len, pay_len = struct.unpack("<II", data[:8])
    assert head_len < p.MAX_HEADER // 4 and pay_len < p.MAX_PAYLOAD


if __name__ == "__main__":
    tests = [f for k, f in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} passed")
