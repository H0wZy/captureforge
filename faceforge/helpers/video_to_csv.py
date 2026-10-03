"""Face video -> generic mocap CSV for FaceForge (time in seconds + ARKit-named shape columns).

Usage: python video_to_csv.py input.mp4 -o out.csv [--model face_landmarker.task]
       [--smooth 0..1] [--neutral-seconds 2] [--gain 1.0] [--preview out_preview.mp4]

The pure processing steps (hold_gaps, calibrate, smooth) need no third-party packages;
cv2/mediapipe are imported only when a video is actually processed.
"""

import argparse
import csv
import sys
from pathlib import Path

# Same names and case FaceForge expects (faceforge/presets.py ARKIT_52). MediaPipe returns 51 of
# them (no tongueOut) plus "_neutral", which is dropped. Columns are written in this order.
ARKIT_52 = [
    "eyeBlinkLeft", "eyeLookDownLeft", "eyeLookInLeft", "eyeLookOutLeft",
    "eyeLookUpLeft", "eyeSquintLeft", "eyeWideLeft",
    "eyeBlinkRight", "eyeLookDownRight", "eyeLookInRight", "eyeLookOutRight",
    "eyeLookUpRight", "eyeSquintRight", "eyeWideRight",
    "jawForward", "jawLeft", "jawRight", "jawOpen",
    "mouthClose", "mouthFunnel", "mouthPucker", "mouthLeft", "mouthRight",
    "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight",
    "mouthDimpleLeft", "mouthDimpleRight", "mouthStretchLeft", "mouthStretchRight",
    "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper",
    "mouthPressLeft", "mouthPressRight", "mouthLowerDownLeft", "mouthLowerDownRight",
    "mouthUpperUpLeft", "mouthUpperUpRight",
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight",
    "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
    "noseSneerLeft", "noseSneerRight",
    "tongueOut",
]
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")


# ---- pure processing (rows = list of per-frame lists, None = no face) -------------------------

def hold_gaps(rows):
    """Replace None rows with the last valid row (leading gap: the first valid row).
    Returns (filled_rows, missing_count). Raises ValueError if no frame has a face."""
    first = next((r for r in rows if r is not None), None)
    if first is None:
        raise ValueError("no face detected in any frame")
    out, last, missing = [], first, 0
    for r in rows:
        if r is None:
            missing += 1
            r = last
        out.append(list(r))
        last = r
    return out, missing


def calibrate(rows, times, neutral_seconds, gain=1.0, valid=None):
    """Subtract the per-channel mean of the first neutral_seconds, scale by gain, clamp to 0..1.
    valid: optional per-row bool (frames with a real detection) so held frames do not skew the mean."""
    n_cols = len(rows[0])
    t0 = times[0]
    idx = [i for i, t in enumerate(times)
           if t - t0 < neutral_seconds and (valid is None or valid[i])]
    if not idx:  # neutral_seconds == 0 or no detection in the window
        base = [0.0] * n_cols
    else:
        base = [sum(rows[i][c] for i in idx) / len(idx) for c in range(n_cols)]
    return [[min(1.0, max(0.0, (x - b) * gain)) for x, b in zip(r, base)] for r in rows]


def smooth(rows, amount):
    """Exponential moving average per channel. amount 0 = off, 1 = frozen (0.3 is light)."""
    if amount <= 0 or not rows:
        return [list(r) for r in rows]
    amount = min(amount, 0.99)
    out, prev = [], rows[0]
    for r in rows:
        prev = [amount * p + (1 - amount) * x for p, x in zip(prev, r)]
        out.append(prev)
    return out


def write_csv(path, names, times, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time"] + names)
        for t, r in zip(times, rows):
            w.writerow([f"{t:.6f}"] + [f"{x:.5f}" for x in r])


# ---- video / MediaPipe ------------------------------------------------------------------------

def _fail(msg):
    sys.exit(f"error: {msg}")


def _import_deps():
    try:
        import cv2
        import numpy as np
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
    except ImportError as e:
        _fail(f"missing package ({e.name}). Install with: pip install -r requirements.txt")
    return cv2, np, mp, mp_python, vision


def detect(video, model, want_landmarks):
    """Run Face Landmarker over every frame.
    Returns (times_s, rows, names, landmarks): rows[i] is None when no face; landmarks[i] is an
    (N, 2) array of normalized points or None (only filled when want_landmarks)."""
    cv2, np, mp, mp_python, vision = _import_deps()
    if not Path(model).is_file():
        _fail(f"model file not found: {model}\nDownload it (about 3.6 MB) from {MODEL_URL}")
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        _fail(f"cannot open video: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    opts = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.VIDEO, output_face_blendshapes=True, num_faces=1)
    times, scores, marks, last_ms, i = [], [], [], -1.0, 0
    with vision.FaceLandmarker.create_from_options(opts) as lm:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            if i > 0 and ms <= last_ms:  # container gave no usable timestamp: fall back to index/fps
                ms = i * 1000.0 / fps
            ms = max(ms, last_ms + 1)    # MediaPipe VIDEO mode needs strictly increasing ms
            last_ms = ms
            img = mp.Image(image_format=mp.ImageFormat.SRGB,
                           data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            res = lm.detect_for_video(img, int(ms))
            if res.face_blendshapes:
                scores.append({c.category_name: c.score for c in res.face_blendshapes[0]})
                marks.append(np.array([(p.x, p.y) for p in res.face_landmarks[0]], np.float32)
                             if want_landmarks else None)
            else:
                scores.append(None)
                marks.append(None)
            times.append(ms / 1000.0)
            i += 1
    cap.release()
    if not scores:
        _fail("video has no frames")
    seen = {k for r in scores if r for k in r}
    names = [n for n in ARKIT_52 if n in seen]
    unknown = sorted(seen - set(ARKIT_52) - {"_neutral"})
    if unknown:
        print(f"warning: ignoring unexpected shapes: {unknown}", file=sys.stderr)
    rows = [None if r is None else [r.get(n, 0.0) for n in names] for r in scores]
    return [t - times[0] for t in times], rows, names, marks


def write_preview(video, out, rows, names, marks):
    cv2, *_ = _import_deps()
    cap = cv2.VideoCapture(str(video))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(len(rows)):
        ok, frame = cap.read()
        if not ok:
            break
        if marks[i] is not None:
            for x, y in marks[i]:
                cv2.circle(frame, (int(x * w), int(y * h)), 1, (0, 255, 0), -1)
        top = sorted(zip(names, rows[i]), key=lambda p: -p[1])[:5]
        for k, (n, val) in enumerate(top):
            cv2.putText(frame, f"{n} {val:.2f}", (20, 40 + 36 * k), cv2.FONT_HERSHEY_SIMPLEX,
                        1.0, (0, 255, 255), 2, cv2.LINE_AA)
        vw.write(frame)
    cap.release()
    vw.release()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--model", default="face_landmarker.task")
    ap.add_argument("--smooth", type=float, default=0.3, help="0 = off .. 1 = frozen (default 0.3)")
    ap.add_argument("--neutral-seconds", type=float, default=2.0)
    ap.add_argument("--gain", type=float, default=1.0)
    ap.add_argument("--preview", help="write a debug video with landmarks and the top 5 shapes")
    a = ap.parse_args()
    if not 0 <= a.smooth <= 1:
        _fail("--smooth must be between 0 and 1")

    times, raw, names, marks = detect(a.video, a.model, bool(a.preview))
    valid = [r is not None for r in raw]
    try:
        rows, missing = hold_gaps(raw)
    except ValueError as e:
        _fail(str(e))
    if missing:
        print(f"warning: {missing} of {len(raw)} frames had no face (held last value)", file=sys.stderr)
    rows = smooth(calibrate(rows, times, a.neutral_seconds, a.gain, valid), a.smooth)
    write_csv(a.output, names, times, rows)
    print(f"wrote {a.output}: {len(rows)} frames, {times[-1]:.2f} s, {len(names)} shapes")
    if a.preview:
        write_preview(a.video, a.preview, rows, names, marks)
        print(f"wrote {a.preview}")


if __name__ == "__main__":
    main()
