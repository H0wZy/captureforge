"""One image -> MediaPipe Face Landmarker landmarks as JSON (normalized x, y, z for each of the 478 points).

Usage: python face_landmarks.py image.png -o landmarks.json --model face_landmarker.task
Runs outside Blender, in the Python that has mediapipe and opencv. Tracking goes through tracker.py, like the other helpers.
"""

import argparse
import json

from video_to_csv import _fail, _import_cv, open_tracker  # same folder; python puts the script folder on sys.path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("image")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--model", default="face_landmarker.task")
    a = ap.parse_args()
    cv2, _ = _import_cv()
    frame = cv2.imread(a.image)
    if frame is None:
        _fail(f"cannot read image: {a.image}")
    with open_tracker("image", a.model) as tracker:
        res = tracker.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), 0)
    if not res.face:
        _fail("no face detected in the render (needs a clear front view with visible eyes and mouth)")
    h, w = frame.shape[:2]
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump({"width": w, "height": h,
                   "landmarks": res.landmarks.tolist()}, f)
    print(f"wrote {a.output}: {len(res.landmarks)} landmarks")


if __name__ == "__main__":
    main()
