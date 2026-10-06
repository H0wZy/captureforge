"""Quaternion helpers on numpy arrays (pure). Quaternions are (..., 4) as (w, x, y, z); every function
broadcasts over the leading dimensions, so a whole clip (frames x bones) is one call."""

import numpy as np

IDENTITY = np.array([1.0, 0.0, 0.0, 0.0])


def normalize(q):
    q = np.asarray(q, float)
    n = np.linalg.norm(q, axis=-1, keepdims=True)
    return q / np.where(n < 1e-12, 1.0, n)


def mul(a, b):
    aw, ax, ay, az = np.moveaxis(np.asarray(a, float), -1, 0)
    bw, bx, by, bz = np.moveaxis(np.asarray(b, float), -1, 0)
    return np.stack([aw * bw - ax * bx - ay * by - az * bz,
                     aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw], axis=-1)


def conj(q):
    return np.asarray(q, float) * np.array([1.0, -1.0, -1.0, -1.0])


def from_matrix(m):
    """Rotation matrices (..., 3, 3) to unit quaternions (Shepperd's method, stable for every rotation)."""
    m = np.asarray(m, float)
    m00, m01, m02 = m[..., 0, 0], m[..., 0, 1], m[..., 0, 2]
    m10, m11, m12 = m[..., 1, 0], m[..., 1, 1], m[..., 1, 2]
    m20, m21, m22 = m[..., 2, 0], m[..., 2, 1], m[..., 2, 2]
    cand = np.stack([
        np.stack([1 + m00 + m11 + m22, m21 - m12, m02 - m20, m10 - m01], -1),
        np.stack([m21 - m12, 1 + m00 - m11 - m22, m01 + m10, m02 + m20], -1),
        np.stack([m02 - m20, m01 + m10, 1 - m00 + m11 - m22, m12 + m21], -1),
        np.stack([m10 - m01, m02 + m20, m12 + m21, 1 - m00 - m11 + m22], -1)], axis=-2)
    best = np.argmax(np.stack([1 + m00 + m11 + m22, 1 + m00 - m11 - m22,
                               1 - m00 + m11 - m22, 1 - m00 - m11 + m22], -1), axis=-1)
    q = np.take_along_axis(cand, best[..., None, None], axis=-2)[..., 0, :]
    return normalize(q)


def to_matrix(q):
    w, x, y, z = np.moveaxis(normalize(q), -1, 0)
    return np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
        np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
        np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], axis=-2)


def slerp(a, b, t):
    """Spherical interpolation along the short arc; t broadcasts against the leading dimensions."""
    a, b = normalize(a), normalize(b)
    t = np.asarray(t, float)[..., None]
    d = np.sum(a * b, axis=-1, keepdims=True)
    b = np.where(d < 0, -b, b)
    d = np.abs(d)
    theta = np.arccos(np.clip(d, -1, 1))
    s = np.sin(theta)
    near = s < 1e-6
    wa = np.where(near, 1 - t, np.sin((1 - t) * theta) / np.where(near, 1, s))
    wb = np.where(near, t, np.sin(t * theta) / np.where(near, 1, s))
    return normalize(wa * a + wb * b)


def continuity(q, axis=0):
    """Flip signs along `axis` (time) so consecutive quaternions are in the same hemisphere (q and -q are
    the same rotation; a sign jump would make any filter or interpolation swing the long way round)."""
    q = np.moveaxis(np.array(q, float), axis, 0)
    if len(q) > 1:
        dots = np.sum(q[1:] * q[:-1], axis=-1)
        flip = np.cumprod(np.where(dots < 0, -1.0, 1.0), axis=0)
        q[1:] *= flip[..., None]
    return np.moveaxis(q, 0, axis)


def mean(q, axis=0):
    """Mean rotation of quaternions along `axis` (signs aligned to the first, then normalised)."""
    q = np.moveaxis(np.asarray(q, float), axis, 0)
    ref = q[0]
    sign = np.where(np.sum(q * ref, axis=-1, keepdims=True) < 0, -1.0, 1.0)
    return normalize(np.mean(q * sign, axis=0))


def angle(q):
    """Rotation angle in radians (0..pi) of unit quaternions."""
    return 2 * np.arccos(np.clip(np.abs(normalize(q)[..., 0]), 0, 1))


def to_euler(q):
    """Euler XYZ in radians with Blender's convention: R = Rz(c) Ry(b) Rx(a); returns (..., 3) as (a, b, c)."""
    m = to_matrix(q)
    b = np.arcsin(np.clip(-m[..., 2, 0], -1, 1))
    a = np.arctan2(m[..., 2, 1], m[..., 2, 2])
    c = np.arctan2(m[..., 1, 0], m[..., 0, 0])
    return np.stack([a, b, c], axis=-1)


def from_euler(e):
    """Inverse of to_euler."""
    a, b, c = np.moveaxis(np.asarray(e, float), -1, 0)
    qx = np.stack([np.cos(a / 2), np.sin(a / 2), 0 * a, 0 * a], -1)
    qy = np.stack([np.cos(b / 2), 0 * b, np.sin(b / 2), 0 * b], -1)
    qz = np.stack([np.cos(c / 2), 0 * c, 0 * c, np.sin(c / 2)], -1)
    return normalize(mul(qz, mul(qy, qx)))


def rotate(q, v):
    """Rotate vectors v (..., 3) by quaternions q (..., 4)."""
    return np.einsum("...ij,...j->...i", to_matrix(q), np.asarray(v, float))
