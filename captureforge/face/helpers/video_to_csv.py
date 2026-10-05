"""Face video -> generic mocap CSV for FaceForge (time in seconds + ARKit-named shape columns).

Usage: python video_to_csv.py input.mp4 -o out.csv [--model face_landmarker.task]
       [--smooth 0..1] [--neutral-seconds 2] [--gain 1.0] [--preview out_preview.mp4] [--no-head-pose]

Besides the shape columns the CSV gets the head pose: headRotX/Y/Z (radians, relative to the neutral head,
Euler order Ry * Rx * Rz = yaw, pitch, roll in the head frame: X = the person's left, Y up, Z out of the face)
and headPosX/Y/Z (centimeters, relative to the neutral position). Readers that only know shapes ignore them.

The pure processing steps (hold_gaps, calibrate, smooth, head_pose) need no third-party packages;
cv2/mediapipe are imported only when a video is actually processed.
"""

import argparse
import csv
import math
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


HEAD_COLUMNS = ["headRotX", "headRotY", "headRotZ", "headPosX", "headPosY", "headPosZ"]


# ---- head pose: 3x3 rotations are lists of rows, 4x4 matrices are 16 floats, row-major ---------

def orthonormalize(m):
    """The rotation closest to the 3x3 matrix m (Gram-Schmidt on the columns): drops a uniform scale."""
    cols = []
    for j in range(3):
        c = [m[0][j], m[1][j], m[2][j]]
        for u in cols:
            d = sum(a * b for a, b in zip(c, u))
            c = [a - d * b for a, b in zip(c, u)]
        n = math.sqrt(sum(a * a for a in c)) or 1.0
        cols.append([a / n for a in c])
    x, y = cols[0], cols[1]
    cols[2] = [x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2], x[0] * y[1] - x[1] * y[0]]  # right-handed
    return [[cols[j][i] for j in range(3)] for i in range(3)]


def euler_to_matrix(x, y, z):
    """R = Ry(y) * Rx(x) * Rz(z): yaw about Y, then pitch about X, then roll about Z (intrinsic)."""
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    return [[cy * cz + sy * sx * sz, -cy * sz + sy * sx * cz, sy * cx],
            [cx * sz, cx * cz, -sx],
            [-sy * cz + cy * sx * sz, sy * sz + cy * sx * cz, cy * cx]]


def matrix_to_euler(r):
    """Inverse of euler_to_matrix: (x, y, z) radians, x in -90..90. At +-90 (gimbal lock) roll is set to 0."""
    x = math.asin(max(-1.0, min(1.0, -r[1][2])))
    if abs(r[1][2]) < 1.0 - 1e-9:
        return x, math.atan2(r[0][2], r[2][2]), math.atan2(r[1][0], r[1][1])
    return x, math.atan2(-r[2][0], r[0][0]), 0.0


def unbreak(rows):
    """Make per-frame angles continuous: shift each by a multiple of 2 pi so it is within pi of the previous one."""
    out = []
    for r in rows:
        if out:
            r = [a - 2 * math.pi * round((a - p) / (2 * math.pi)) for a, p in zip(r, out[-1])]
        out.append(list(r))
    return out


def head_pose(mats, times, neutral_seconds, valid=None):
    """Facial transformation matrices (16 floats each, no gaps: see hold_gaps) -> (rot, pos) rows.

    rot: Euler angles of R_neutral^T * R_frame, continuous across frames; pos: translation minus the neutral one.
    The neutral is the mean over the first neutral_seconds (valid frames only), like calibrate(); without such
    frames it is the identity rotation and the origin."""
    rots = [orthonormalize([[m[0], m[1], m[2]], [m[4], m[5], m[6]], [m[8], m[9], m[10]]]) for m in mats]
    ts = [[m[3], m[7], m[11]] for m in mats]
    idx = [i for i, t in enumerate(times)
           if t - times[0] < neutral_seconds and (valid is None or valid[i])]
    if idx:
        mean = orthonormalize([[sum(rots[i][a][b] for i in idx) / len(idx) for b in range(3)] for a in range(3)])
        t0 = [sum(ts[i][c] for i in idx) / len(idx) for c in range(3)]
    else:
        mean, t0 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], [0.0, 0.0, 0.0]
    rel = [[[sum(mean[k][a] * r[k][b] for k in range(3)) for b in range(3)] for a in range(3)] for r in rots]
    return unbreak([list(matrix_to_euler(r)) for r in rel]), [[a - b for a, b in zip(t, t0)] for t in ts]


def write_csv(path, names, times, rows, head_rot=None, head_pos=None):
    """time + shape columns; with head_rot and head_pos (one [x, y, z] per frame) the six HEAD_COLUMNS follow."""
    head = head_rot is not None and head_pos is not None
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time"] + names + (HEAD_COLUMNS if head else []))
        for i, (t, r) in enumerate(zip(times, rows)):
            extra = list(head_rot[i]) + list(head_pos[i]) if head else []
            w.writerow([f"{t:.6f}"] + [f"{x:.5f}" for x in list(r) + extra])


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


def detect(video, model, want_landmarks, boxes=None):
    """Run Face Landmarker over every frame (inside the per-frame normalized box when `boxes` is given).
    Returns (times_s, rows, names, landmarks, mats): rows[i] is None when no face; landmarks[i] is an
    (N, 2) array of normalized points or None (only filled when want_landmarks); mats[i] is the facial
    transformation matrix as 16 row-major floats, or None."""
    cv2, np, mp, mp_python, vision = _import_deps()
    if not Path(model).is_file():
        _fail(f"model file not found: {model}\nDownload it (about 3.6 MB) from {MODEL_URL}")
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        _fail(f"cannot open video: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    opts = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.VIDEO, output_face_blendshapes=True,
        output_facial_transformation_matrixes=True, num_faces=1)
    times, scores, marks, mats, last_ms, i = [], [], [], [], -1.0, 0
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
            if boxes is not None:
                frame = crop_frame(frame, box_at(boxes, i))
            img = mp.Image(image_format=mp.ImageFormat.SRGB,
                           data=np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
            res = lm.detect_for_video(img, int(ms))
            if res.face_blendshapes:
                scores.append({c.category_name: c.score for c in res.face_blendshapes[0]})
                marks.append(np.array([(p.x, p.y) for p in res.face_landmarks[0]], np.float32)
                             if want_landmarks else None)
                mats.append([float(x) for x in np.asarray(res.facial_transformation_matrixes[0]).ravel()]
                            if res.facial_transformation_matrixes else None)
            else:
                scores.append(None)
                marks.append(None)
                mats.append(None)
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
    return [t - times[0] for t in times], rows, names, marks, mats


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


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--model", default="face_landmarker.task")
    ap.add_argument("--smooth", type=float, default=0.3, help="0 = off .. 1 = frozen (default 0.3)")
    ap.add_argument("--neutral-seconds", type=float, default=2.0)
    ap.add_argument("--gain", type=float, default=1.0)
    ap.add_argument("--preview", help="write a debug video with landmarks and the top 5 shapes")
    ap.add_argument("--no-head-pose", action="store_true", help="do not write the headRot/headPos columns")
    ap.add_argument("--crop", help="BodyForge landmarks.npz with a per-frame head box: track the face inside that "
                                   "crop (a face in a full-body frame is small)")
    return ap


def box_at(boxes, i):
    """The head box of frame i (the last one when the video has more frames than boxes)."""
    return boxes[min(i, len(boxes) - 1)]


def read_boxes(path):
    """Per-frame head boxes (n, 4) of a BodyForge landmark file, gaps filled with the last box (leading gap: the
    first box). ValueError when the file has no head box."""
    import numpy as np
    with np.load(path, allow_pickle=False) as d:
        if "head_box" not in d.files:
            raise ValueError(f"{path} has no head box: run the BodyForge helper with --head-box")
        boxes = d["head_box"].astype(np.float32)
    good = ~np.isnan(boxes).any(axis=1)
    if not good.any():
        raise ValueError(f"{path} has no head box in any frame")
    idx = np.maximum.accumulate(np.where(good, np.arange(len(boxes)), -1))
    idx[idx < 0] = int(np.argmax(good))
    return boxes[idx]


def crop_frame(frame, box):
    """The part of an image (rows, columns, ...) inside a normalized (x0, y0, x1, y1) box, at least 1 pixel."""
    h, w = frame.shape[:2]
    x0, y0 = int(round(box[0] * w)), int(round(box[1] * h))
    x1, y1 = max(int(round(box[2] * w)), x0 + 1), max(int(round(box[3] * h)), y0 + 1)
    return frame[y0:y1, x0:x1]


def main():
    a = build_parser().parse_args()
    if not 0 <= a.smooth <= 1:
        _fail("--smooth must be between 0 and 1")
    boxes = None
    if a.crop:
        try:
            boxes = read_boxes(a.crop)
        except (OSError, ValueError) as e:
            _fail(str(e))
        if a.preview:
            print("warning: --preview is not drawn with --crop", file=sys.stderr)
            a.preview = None

    times, raw, names, marks, mats = detect(a.video, a.model, bool(a.preview), boxes)
    valid = [r is not None for r in raw]
    try:
        rows, missing = hold_gaps(raw)
    except ValueError as e:
        _fail(str(e))
    if missing:
        print(f"warning: {missing} of {len(raw)} frames had no face (held last value)", file=sys.stderr)
    rows = smooth(calibrate(rows, times, a.neutral_seconds, a.gain, valid), a.smooth)
    rot = pos = None
    if not a.no_head_pose and any(m is not None for m in mats):
        mats, _ = hold_gaps(mats)
        rot, pos = head_pose(mats, times, a.neutral_seconds, valid)
        rot, pos = smooth(rot, a.smooth), smooth(pos, a.smooth)
    write_csv(a.output, names, times, rows, rot, pos)
    print(f"wrote {a.output}: {len(rows)} frames, {times[-1]:.2f} s, {len(names)} shapes"
          + (", head pose" if rot else ""))
    if a.preview:
        write_preview(a.video, a.preview, rows, names, marks)
        print(f"wrote {a.preview}")


if __name__ == "__main__":
    main()
