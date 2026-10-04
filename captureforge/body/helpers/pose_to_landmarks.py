"""Video -> landmarks.npz for BodyForge (MediaPipe Pose, optionally Hands). Runs in the helper venv, never in Blender.

Usage: python pose_to_landmarks.py VIDEO -o OUT.npz --pose-model POSE.task
       [--hands-model HANDS.task] [--variant heavy|lite] [--head-box] [--max-seconds N]
       [--fallback-model LITE.task] [--time-budget SECONDS]

Contract: specs/001-bodyforge-v1/contracts/helper-cli.md and landmarks-file.md. Progress and the final summary are
JSON lines on stdout; errors go to stderr. Exit codes: 0 ok, 2 bad arguments or missing file, 3 missing package,
4 model file unreadable, 5 no person in any frame. The file is written only at the end, so a cancel leaves none.
Only argparse, json and hashlib are needed to read --help; cv2, mediapipe and numpy are imported when work starts.
"""

import argparse
import hashlib
import importlib
import json
import os
import sys
import time

try:
    import numpy as np
except ImportError:  # reported as "missing package" when work starts; --help still works
    np = None

HELPER_VERSION = "1"
BOX_MARGIN = 0.6        # head box grows by this fraction of its size on every side
LEFT_WRIST, RIGHT_WRIST = 15, 16
HAND_MATCH = 0.2        # normalized image distance within which a detected hand belongs to a pose wrist
SLOW_AFTER = 15         # frames timed before deciding whether the heavy model is too slow


def build_parser():
    ap = argparse.ArgumentParser(description="Video to landmarks.npz with MediaPipe Pose")
    ap.add_argument("video")
    ap.add_argument("-o", "--out", required=True, help="output .npz")
    ap.add_argument("--pose-model", required=True, help="pose_landmarker .task file")
    ap.add_argument("--hands-model", default=None, help="hand_landmarker .task file (optional, for fingers)")
    ap.add_argument("--variant", choices=("heavy", "lite"), default="heavy", help="recorded in the file")
    ap.add_argument("--head-box", action="store_true", help="also write a per-frame head box (for the face crop)")
    ap.add_argument("--max-seconds", type=float, default=None, help="process only the first N seconds")
    ap.add_argument("--fallback-model", default=None,
                    help="lighter pose model used instead when the first model is too slow for --time-budget")
    ap.add_argument("--time-budget", type=float, default=150.0, help="seconds the pose pass may take (default 150)")
    return ap


# ---- pure helpers -------------------------------------------------------------------------------

def to_landmark_axes(native):
    """MediaPipe world axes (x right, y down, z away from the camera) to the file's +X right, +Y up, +Z toward
    the camera, so no reader depends on MediaPipe conventions."""
    native = np.asarray(native)
    return native * np.array([1, -1, -1], native.dtype)


def most_prominent(poses):
    """Index of the person whose landmarks span the largest image box (poses: list of (33, >=2) arrays)."""
    def area(p):
        p = np.asarray(p)[:, :2]
        return float(np.prod(p.max(axis=0) - p.min(axis=0)))
    return max(range(len(poses)), key=lambda i: area(poses[i]))


def head_box(image33):
    """[x0, y0, x1, y1] (normalized, clipped to the frame) around the face landmarks 0..10, with margin."""
    p = np.asarray(image33)[:11, :2]
    lo, hi = p.min(axis=0), p.max(axis=0)
    pad = (hi - lo) * BOX_MARGIN
    lo, hi = np.clip(lo - pad, 0, 1), np.clip(hi + pad, 0, 1)
    return np.array([lo[0], lo[1], hi[0], hi[1]], np.float32)


class Recorder:
    """Collects one row per frame and writes the landmark file (contracts/landmarks-file.md)."""

    def __init__(self):
        self.t, self.world, self.image, self.vis, self.hands, self.hands_vis, self.box = [], [], [], [], [], [], []

    def add(self, t, world, image, vis, hands=None, hands_vis=None, box=None):
        """One frame. world/image/vis are None when no person was found (written as NaN and 0)."""
        self.t.append(float(t))
        self.world.append(np.full((33, 3), np.nan) if world is None else np.asarray(world))
        self.image.append(np.full((33, 3), np.nan) if image is None else np.asarray(image))
        self.vis.append(np.zeros(33) if vis is None else np.asarray(vis))
        self.hands.append(np.full((2, 21, 3), np.nan) if hands is None else np.asarray(hands))
        self.hands_vis.append(np.zeros(2) if hands_vis is None else np.asarray(hands_vis))
        self.box.append(np.full(4, np.nan) if box is None else np.asarray(box))

    def write(self, path, size, fps_source, model, model_sha256, variant, people_seen, rotation, warnings,
              hands=False, head_box=False):
        t = np.array(self.t, np.float64)
        t -= t[0]
        for i in range(1, len(t)):  # strictly increasing, whatever the container reported
            t[i] = max(t[i], t[i - 1] + 1e-6)
        gone = int(np.isnan(np.array(self.world)[:, 0, 0]).sum())
        meta = {"helper_version": HELPER_VERSION, "model": os.path.basename(model), "model_sha256": model_sha256,
                "model_variant": variant, "hands": bool(hands), "people_seen": int(people_seen),
                "frames_without_person": gone, "rotation_applied": int(rotation), "warnings": list(warnings)}
        data = dict(version=np.int64(1), times=t, fps_source=np.float64(fps_source), size=np.array(size, np.int64),
                    pose_world=np.array(self.world, np.float32), pose_image=np.array(self.image, np.float32),
                    pose_vis=np.array(self.vis, np.float32), meta=np.str_(json.dumps(meta)))
        if hands:
            data["hands_world"] = np.array(self.hands, np.float32)
            data["hands_vis"] = np.array(self.hands_vis, np.float32)
        if head_box:
            data["head_box"] = np.array(self.box, np.float32)
        with open(path, "wb") as f:  # a file object: numpy would append .npz to a bare name
            np.savez_compressed(f, **data)
        return gone


# ---- MediaPipe work -----------------------------------------------------------------------------

def _say(obj):
    print(json.dumps(obj), flush=True)


def _fail(code, msg):
    print(f"error: {msg}", file=sys.stderr)
    return code


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class SlowModel(Exception):
    pass


def _assign_hands(res, pose_image, hands_out, vis_out):
    """Give each detected hand to the nearer pose wrist (MediaPipe's handedness label assumes a mirrored image)."""
    wrists = [pose_image[LEFT_WRIST][:2], pose_image[RIGHT_WRIST][:2]]
    cands = []
    for img, world in zip(res.hand_landmarks, res.hand_world_landmarks):
        wr = np.array([img[0].x, img[0].y])
        for side in (0, 1):
            d = float(np.linalg.norm(wr - wrists[side]))
            if d < HAND_MATCH:
                cands.append((d, side, np.array([(p.x, p.y, p.z) for p in world])))
    for d, side, world in sorted(cands, key=lambda c: c[0]):
        if vis_out[side] == 0:
            hands_out[side], vis_out[side] = to_landmark_axes(world), 1.0


def _run_pass(a, deps, model, rec_hands, can_fall_back):
    cv2, mp, mp_python, vision = deps
    cap = cv2.VideoCapture(a.video)
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {a.video}")
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)  # honor the phone's rotation metadata
    rotation = int(cap.get(cv2.CAP_PROP_ORIENTATION_META) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if a.max_seconds and total:
        total = min(total, int(a.max_seconds * fps))
    limit = int(a.max_seconds * fps) if a.max_seconds else None
    _say({"info": {"fps": round(fps, 3), "frames": total, "rotation": rotation}})  # early, for capture warnings
    try:
        pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model),
            running_mode=vision.RunningMode.VIDEO, num_poses=2))
        hands = (vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=a.hands_model),
            running_mode=vision.RunningMode.VIDEO, num_hands=2)) if a.hands_model else None)
    except Exception as e:  # noqa: BLE001
        raise OSError(f"cannot load a model: {e}") from e
    rec, people, size, last_ms, i, t0 = Recorder(), 1, None, -1.0, 0, time.time()
    try:
        while limit is None or i < limit:
            ok, frame = cap.read()
            if not ok:
                break
            size = (frame.shape[1], frame.shape[0])
            ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            if i > 0 and ms <= last_ms:  # no usable timestamp from the container: index / fps
                ms = i * 1000.0 / fps
            ms = max(ms, last_ms + 1)    # MediaPipe video mode needs strictly increasing milliseconds
            last_ms = ms
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            res = pose.detect_for_video(img, int(ms))
            world = image = vis = box = None
            hw, hv = np.full((2, 21, 3), np.nan), np.zeros(2)
            if res.pose_world_landmarks:
                imgs = [np.array([(p.x, p.y, p.z) for p in person]) for person in res.pose_landmarks]
                k = most_prominent(imgs) if len(imgs) > 1 else 0
                people = max(people, len(imgs))
                image = imgs[k]
                world = to_landmark_axes(np.array([(p.x, p.y, p.z) for p in res.pose_world_landmarks[k]]))
                vis = np.array([p.visibility if p.visibility is not None else 1.0 for p in res.pose_landmarks[k]])
                box = head_box(image) if a.head_box else None
                if hands:
                    _assign_hands(hands.detect_for_video(img, int(ms)), image, hw, hv)
            rec.add(ms / 1000.0, world, image, vis, hw, hv, box)
            i += 1
            if can_fall_back and i == SLOW_AFTER and total and (time.time() - t0) / i * total > a.time_budget:
                raise SlowModel()
            if i % 5 == 0:
                _say({"progress": round(min(i / total, 1.0), 3) if total else 0.0, "frame": i, "frames": total})
    finally:
        cap.release()
        pose.close()
        if hands:
            hands.close()
    return rec, people, size, fps, rotation


def main(argv=None, _import=importlib.import_module):
    a = build_parser().parse_args(argv)
    if not os.path.isfile(a.video):
        return _fail(2, f"video not found: {a.video}")
    if a.hands_model and not os.path.isfile(a.hands_model):
        return _fail(4, f"hand model file not found: {a.hands_model}")
    try:
        if np is None:
            raise ImportError("numpy", name="numpy")
        deps = (_import("cv2"), _import("mediapipe"), _import("mediapipe.tasks.python"),
                _import("mediapipe.tasks.python.vision"))
    except ImportError as e:
        return _fail(3, f"missing package ({getattr(e, 'name', None) or e}). Run setup_env.py to install the helper.")
    if not os.path.isfile(a.pose_model):
        return _fail(4, f"pose model file not found or unreadable: {a.pose_model}")
    model, variant, warnings = a.pose_model, a.variant, []
    try:
        for attempt in (0, 1):
            fallback = a.fallback_model if os.path.isfile(a.fallback_model or "") else None
            try:
                rec, people, size, fps, rotation = _run_pass(a, deps, model, bool(a.hands_model),
                                                             attempt == 0 and fallback is not None)
                break
            except SlowModel:
                model, variant = fallback, "lite"
                warnings.append("The pose model was too slow for the time budget; used the lite model.")
    except OSError as e:
        return _fail(4, str(e))
    except ValueError as e:
        return _fail(2, str(e))
    if np.isnan(np.array(rec.world)[:, 0, 0]).all():
        return _fail(5, "no person found in any frame")
    if people > 1:
        warnings.append(f"{people} people were seen in one frame; the most prominent one is used.")
    gone = rec.write(a.out, size, fps, model, _sha256(model), variant, people, rotation, warnings,
                     hands=bool(a.hands_model), head_box=a.head_box)
    _say({"done": True, "frames": len(rec.t), "frames_without_person": gone, "path": a.out})
    return 0


if __name__ == "__main__":
    sys.exit(main())
