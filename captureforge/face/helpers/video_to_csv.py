"""Face video -> generic mocap CSV for FaceForge (time in seconds + ARKit-named shape columns).

Usage: python video_to_csv.py input.mp4 -o out.csv [--model face_landmarker.task]
       [--smooth 0..1] [--neutral-seconds 2] [--gain 1.0] [--preview out_preview.mp4] [--no-head-pose]
       [--capture take.capture.npz] [--profile me.faceprofile.json]

Besides the shape columns the CSV gets the head pose: headRotX/Y/Z (radians, relative to the neutral head,
Euler order Ry * Rx * Rz = yaw, pitch, roll in the head frame: X = the person's left, Y up, Z out of the face)
and headPosX/Y/Z (centimeters, relative to the neutral position). Readers that only know shapes ignore them.

The pure processing steps (hold_gaps, calibrate, smooth, head_pose, in ../capture/post.py) need no third-party packages;
cv2 and the tracker (helpers/tracker.py, the only MediaPipe user) load only when a video is processed.
"""

import argparse
import csv
import sys
from pathlib import Path

# The shared post-processing lives in ../capture/post.py (also used by the live capture bake in Blender).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "capture"))
from tracker import ARKIT_52, MODEL_URL, Tracker, TrackerError  # noqa: E402,F401  (same folder)
from post import (HEAD_COLUMNS, calibrate, euler_to_matrix, head_pose, hold_gaps, matrix_to_euler,  # noqa: E402,F401
                  orthonormalize, process, smooth, unbreak)


def write_csv(path, names, times, rows, head_rot=None, head_pos=None):
    """time + shape columns; with head_rot and head_pos (one [x, y, z] per frame) the six HEAD_COLUMNS follow."""
    head = head_rot is not None and head_pos is not None
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time"] + names + (HEAD_COLUMNS if head else []))
        for i, (t, r) in enumerate(zip(times, rows)):
            extra = list(head_rot[i]) + list(head_pos[i]) if head else []
            w.writerow([f"{t:.6f}"] + [f"{x:.5f}" for x in list(r) + extra])


def write_capture(path, times, raw, marks, mats, size):
    """The capture file of one take (spec 004 capture file, interface 2; spec 005 calibrates from it): per frame
    the raw scores in ARKIT_52 order (absent names 0), the 478 normalized landmarks and the 4x4 head matrix, NaN
    where there is no face. raw[i]: {name: score} or None. It is face data: written only when asked (--capture)."""
    import numpy as np
    n = len(times)
    scores = np.full((n, len(ARKIT_52)), np.nan, np.float32)
    landmarks = np.full((n, 478, 3), np.nan, np.float32)
    matrices = np.full((n, 4, 4), np.nan, np.float32)
    for i in range(n):
        if raw[i] is not None:
            scores[i] = [raw[i].get(k, 0.0) for k in ARKIT_52]
        if marks[i] is not None:
            landmarks[i] = marks[i]
        if mats[i] is not None:
            matrices[i] = np.asarray(mats[i], np.float32).reshape(4, 4)
    np.savez_compressed(path, interface=2, times=np.asarray(times, np.float64), valid=~np.isnan(scores).any(axis=1),
                        landmarks=landmarks, scores=scores, names=np.array(ARKIT_52), size=np.array(size),
                        mats=matrices)


# ---- video / MediaPipe ------------------------------------------------------------------------

def _fail(msg):
    sys.exit(f"error: {msg}")


def _import_cv():
    try:
        import cv2
        import numpy as np
    except ImportError as e:
        _fail(f"missing package ({e.name}). Install with: pip install -r requirements.txt")
    return cv2, np


def open_tracker(mode, model):
    """Tracker.image / video / live on the model, or exit with the tracker's message."""
    try:
        return getattr(Tracker, mode)(model)
    except TrackerError as e:
        _fail(str(e))


def detect(video, model, want_landmarks, boxes=None):
    """Run the face tracker over every frame (inside the per-frame normalized box when `boxes` is given).
    Returns (times_s, rows, names, landmarks, mats): rows[i] is None when no face; landmarks[i] is the (478, 3)
    array of normalized points or None (only filled when want_landmarks); mats[i] is the facial
    transformation matrix as 16 row-major floats, or None."""
    cv2, np = _import_cv()
    tracker = open_tracker("video", model)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        tracker.close()
        _fail(f"cannot open video: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    times, scores, marks, mats, last_ms, i = [], [], [], [], -1.0, 0
    with tracker:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            if i > 0 and ms <= last_ms:  # container gave no usable timestamp: fall back to index/fps
                ms = i * 1000.0 / fps
            ms = max(ms, last_ms + 1)    # video mode needs strictly increasing ms
            last_ms = ms
            if boxes is not None:
                frame = crop_frame(frame, box_at(boxes, i))
            res = tracker.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), int(ms))
            scores.append(res.scores)
            marks.append(res.landmarks if res.face and want_landmarks else None)
            mats.append([float(x) for x in res.matrix.ravel()] if res.matrix is not None else None)
            times.append(ms / 1000.0)
            i += 1
    cap.release()
    if not scores:
        _fail("video has no frames")
    seen = {k for r in scores if r for k in r}
    names = [n for n in ARKIT_52 if n in seen]
    unknown = sorted(seen - set(ARKIT_52))
    if unknown:
        print(f"warning: ignoring unexpected shapes: {unknown}", file=sys.stderr)
    rows = [None if r is None else [r.get(n, 0.0) for n in names] for r in scores]
    return [t - times[0] for t in times], rows, names, marks, mats


def write_preview(video, out, rows, names, marks):
    cv2, _ = _import_cv()
    cap = cv2.VideoCapture(str(video))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(len(rows)):
        ok, frame = cap.read()
        if not ok:
            break
        if marks[i] is not None:
            for x, y in marks[i][:, :2]:
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
    ap.add_argument("--profile", help="actor profile (.faceprofile.json, spec 005) that corrects the scores")
    ap.add_argument("--capture", help="also write the per-frame raw scores, landmarks and head matrices to this .npz "
                                      "(face data; the actor calibration reads it)")
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
        if a.capture:
            _fail("--capture needs the whole frame: it cannot be combined with --crop")

    profile = None
    if a.profile:
        from calib import CalibrationError, load_profile  # ../capture, needs numpy
        try:
            profile = load_profile(a.profile)
        except CalibrationError as e:
            _fail(str(e))
    times, raw, names, marks, mats = detect(a.video, a.model, bool(a.preview or a.capture), boxes)
    try:
        out = process(times, raw, mats, a.neutral_seconds, a.gain, a.smooth, head=not a.no_head_pose,
                      names=names, profile=profile)
    except ValueError as e:
        _fail(str(e))
    if out["missing"]:
        print(f"warning: {out['missing']} of {len(raw)} frames had no face (held last value)", file=sys.stderr)
    rows, rot, pos = out["rows"], out["rot"], out["pos"]
    write_csv(a.output, names, times, rows, rot, pos)
    print(f"wrote {a.output}: {len(rows)} frames, {times[-1]:.2f} s, {len(names)} shapes"
          + (", head pose" if rot else ""))
    if a.capture:
        cv2, _ = _import_cv()
        cap = cv2.VideoCapture(str(a.video))
        size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        cap.release()
        write_capture(a.capture, times, [None if r is None else dict(zip(names, r)) for r in raw], marks, mats, size)
        print(f"wrote {a.capture}")
    if a.preview:
        write_preview(a.video, a.preview, rows, names, marks)
        print(f"wrote {a.preview}")


if __name__ == "__main__":
    main()
