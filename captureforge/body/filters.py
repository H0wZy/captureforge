"""Smoothing filters (pure numpy): One Euro for the causal preview, a zero-phase Butterworth for the final clip.

Credits (Constitution I): the One Euro filter is Casiez, Roussel and Vogel (CHI 2012); the Butterworth low-pass is
the standard bilinear-transform design, run forward and backward so it has no lag. Rotations are filtered as
quaternions after sign continuity, never as Euler angles (research D5).
"""

import numpy as np

from . import quat

ROT_CUTOFF = 6.0   # Hz, zero-phase low-pass on bone rotations
POS_CUTOFF = 3.0   # Hz, on the hips translation


def _biquad(cutoff, fps):
    """Second-order Butterworth low-pass coefficients (b0, b1, b2, a1, a2) by the bilinear transform."""
    cutoff = min(cutoff, 0.45 * fps)
    k = np.tan(np.pi * cutoff / fps)
    r2 = np.sqrt(2.0)
    norm = 1.0 / (1.0 + r2 * k + k * k)
    b0 = k * k * norm
    return b0, 2 * b0, b0, 2 * (k * k - 1) * norm, (1.0 - r2 * k + k * k) * norm


def _pass(b, x):
    """One direction of the biquad over axis 0, started in its steady state for a constant input x[0]."""
    b0, b1, b2, a1, a2 = b
    y = np.empty_like(x)
    z2 = (b2 - a2) * x[0]
    z1 = (b1 + b2 - a1 - a2) * x[0]
    for n in range(len(x)):
        y[n] = b0 * x[n] + z1
        z1 = b1 * x[n] - a1 * y[n] + z2
        z2 = b2 * x[n] - a2 * y[n]
    return y


def zero_phase(x, fps, cutoff):
    """Low-pass `x` (frames first, any trailing shape) with a 4th-order zero-phase Butterworth at `cutoff` Hz:
    a 2nd-order section forward then backward, on an odd-extended signal so the ends do not ring."""
    x = np.asarray(x, float)
    if len(x) < 3:
        return x.copy()
    b = _biquad(cutoff, fps)
    pad = min(len(x) - 1, max(3, int(3 * fps / cutoff)))
    head = 2 * x[0] - x[pad:0:-1]
    tail = 2 * x[-1] - x[-2:-pad - 2:-1]
    y = _pass(b, np.concatenate([head, x, tail]))
    y = _pass(b, y[::-1])[::-1]
    return y[pad:pad + len(x)]


def smooth_quat(q, fps, cutoff):
    """Zero-phase smoothing of quaternions (frames first): sign continuity, filter the components, renormalise."""
    return quat.normalize(zero_phase(quat.continuity(q, axis=0), fps, cutoff))


def _alpha(cutoff, fps):
    return 1.0 / (1.0 + fps / (2 * np.pi * cutoff))


def one_euro(x, fps, min_cutoff=1.5, beta=1.0, d_cutoff=1.0):
    """Causal One Euro filter over axis 0 of `x` (any trailing shape): smooth when still, follow when fast."""
    x = np.asarray(x, float)
    out = np.empty_like(x)
    out[0], edx = x[0], np.zeros_like(x[0])
    for t in range(1, len(x)):
        dx = (x[t] - x[t - 1]) * fps
        edx = edx + _alpha(d_cutoff, fps) * (dx - edx)
        a = _alpha(min_cutoff + beta * np.abs(edx), fps)
        out[t] = out[t - 1] + a * (x[t] - out[t - 1])
    return out


def one_euro_quat(q, fps, min_cutoff=1.5, beta=1.0, d_cutoff=1.0):
    """Causal One Euro filter for quaternions (frames first): the speed is the angle turned per second and the
    smoothing is a SLERP towards each new sample."""
    q = quat.continuity(np.asarray(q, float), axis=0)
    out = np.empty_like(q)
    out[0], edx = q[0], np.zeros(q.shape[1:-1])
    for t in range(1, len(q)):
        speed = quat.angle(quat.mul(q[t], quat.conj(q[t - 1]))) * fps
        edx = edx + _alpha(d_cutoff, fps) * (speed - edx)
        a = _alpha(min_cutoff + beta * edx, fps)
        out[t] = quat.slerp(out[t - 1], q[t], a)
    return out
