"""One image -> MediaPipe Face Landmarker landmarks as JSON (normalized x, y, z for each of the 478 points).

Usage: python face_landmarks.py image.png -o landmarks.json --model face_landmarker.task
Runs outside Blender, in the Python that has mediapipe and opencv. Shares its import check with video_to_csv.py.
"""

import argparse
import json

from video_to_csv import _fail, _import_deps  # same folder; python puts the script folder on sys.path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("image")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--model", default="face_landmarker.task")
    a = ap.parse_args()
    cv2, np, mp, mp_python, vision = _import_deps()
    frame = cv2.imread(a.image)
    if frame is None:
        _fail(f"cannot read image: {a.image}")
    opts = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=a.model),
        running_mode=vision.RunningMode.IMAGE, num_faces=1)
    with vision.FaceLandmarker.create_from_options(opts) as lm:
        res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    if not res.face_landmarks:
        _fail("no face detected in the render (needs a clear front view with visible eyes and mouth)")
    h, w = frame.shape[:2]
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump({"width": w, "height": h,
                   "landmarks": [[p.x, p.y, p.z] for p in res.face_landmarks[0]]}, f)
    print(f"wrote {a.output}: {len(res.face_landmarks[0])} landmarks")


if __name__ == "__main__":
    main()
