"""Post-processing of tracked faces, shared by the video helper (helpers/video_to_csv.py), the live capture bake and
the tests: fill gaps, neutral calibration, gain, smoothing and the head pose from the facial transformation matrices.

Pure Python, standard library only. It is a plain module, not only a package member: the helpers run in their own
Python and import it by path (they put this folder on sys.path), Blender imports it as
captureforge.face.capture.post.
"""

import math

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


def process(times, raw_rows, mats, neutral_seconds=2.0, gain=1.0, smoothing=0.3, head=True):
    """The video path's steps on one take. raw_rows: per frame a list of scores or None (no face); mats: per frame
    the facial transformation matrix (16 row-major floats) or None. Returns {"rows", "missing", "rot", "pos"}:
    calibrated and smoothed rows, the count of frames without a face, and the head pose rows (None when head is off
    or the tracker gave no matrix). ValueError when no frame has a face."""
    valid = [r is not None for r in raw_rows]
    rows, missing = hold_gaps(raw_rows)
    rows = smooth(calibrate(rows, times, neutral_seconds, gain, valid), smoothing)
    rot = pos = None
    if head and any(m is not None for m in mats):
        filled, _ = hold_gaps(mats)
        rot, pos = head_pose(filled, times, neutral_seconds, valid)
        rot, pos = smooth(rot, smoothing), smooth(pos, smoothing)
    return {"rows": rows, "missing": missing, "rot": rot, "pos": pos}

