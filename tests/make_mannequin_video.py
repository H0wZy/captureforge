"""Render a synthetic test video: a flat-colour mannequin (no real person) standing still, then raising both arms.

Usage: python tests/make_mannequin_video.py OUT.mp4 [--frames-neutral N] [--fps F]
Needs opencv-python and numpy (run it with the helper venv's Python). The motion comes from the same skeleton
oracle the unit tests use (tests/fixtures_body.py), so the true joint angles are known.
"""

import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures_body as fx  # noqa: E402

W, H, PX_PER_M = 540, 960, 420.0


def draw_frame(pts):
    img = np.full((H, W, 3), (200, 205, 210), np.uint8)
    cv2.rectangle(img, (0, int(H * 0.88)), (W, H), (120, 125, 130), -1)
    lm = fx.char_to_landmark(pts)

    def p(i):
        return int(W / 2 + lm[i][0] * PX_PER_M), int(H * 0.88 - lm[i][1] * PX_PER_M)

    skin, shirt, jeans = (150, 175, 225), (60, 90, 200), (110, 70, 40)

    def limb(a, b, col, thick):
        cv2.line(img, p(a), p(b), col, thick, cv2.LINE_AA)

    for a, b in ((23, 25), (25, 27), (24, 26), (26, 28)):
        limb(a, b, jeans, 38)
    for a, b in ((27, 31), (28, 32)):
        limb(a, b, (30, 30, 30), 24)
    cv2.fillConvexPoly(img, np.array([p(11), p(12), p(24), p(23)]), shirt)
    for a, b in ((11, 13), (13, 15), (12, 14), (14, 16)):
        limb(a, b, shirt if b in (13, 14) else skin, 30)
    for wrist in (15, 16):
        cv2.circle(img, p(wrist), 22, skin, -1, cv2.LINE_AA)
    ears = (np.array(p(7)) + np.array(p(8))) // 2
    head = (int(ears[0]), int(ears[1]))
    cv2.circle(img, head, 48, skin, -1, cv2.LINE_AA)
    cv2.ellipse(img, (head[0], head[1] - 8), (48, 44), 0, 180, 360, (40, 30, 30), -1, cv2.LINE_AA)
    for eye in (2, 5):
        cv2.circle(img, p(eye), 5, (30, 30, 30), -1, cv2.LINE_AA)
    cv2.line(img, p(0), (p(0)[0], p(0)[1] + 16), (110, 120, 190), 3, cv2.LINE_AA)
    cv2.line(img, p(9), p(10), (60, 60, 160), 4, cv2.LINE_AA)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--frames-neutral", type=int, default=45)
    ap.add_argument("--fps", type=float, default=30.0)
    a = ap.parse_args()
    clip = fx.hands_up_clip(neutral=a.frames_neutral, raise_=30, hold=30, fps=a.fps)
    vw = cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"mp4v"), a.fps, (W, H))
    for euler in clip.euler:
        vw.write(draw_frame(fx.skeleton(euler)[0]))
    vw.release()


if __name__ == "__main__":
    main()
