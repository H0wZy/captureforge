"""Clip operations on a MotionClip (pure numpy): clean-up pipeline, in place, trim, loop closer, mirror.
Every function returns a new clip."""

import numpy as np

from . import contact, filters, profile, quat, solve

M = np.diag([-1.0, 1.0, 1.0])  # mirror across the character's YZ plane (left is +X)


def _partner():
    """Profile index of each bone's mirror partner (Left <-> Right; the centre bones map to themselves)."""
    out = []
    for name in profile.NAMES:
        other = name.replace("Left", "Right") if name.startswith("Left") else (
            name.replace("Right", "Left") if name.startswith("Right") else name)
        out.append(profile.INDEX[other])
    return np.array(out)


def _ankles(clip):
    _, head = solve.fk(clip.rot, clip.hips_pos)
    return head[:, [profile.INDEX["LeftFoot"], profile.INDEX["RightFoot"]]]


def cleanup(clip, mode="FINAL", strength=1.0, lock_left=True, lock_right=True, off_ranges=(), in_place_=False):
    """Smooth, find the planted feet, lock them, and optionally make the clip in place. `mode` FINAL is the
    zero-phase low-pass (no lag), PREVIEW the causal One Euro filter; `strength` > 1 smooths more."""
    if mode == "PREVIEW":
        rot = np.stack([filters.one_euro_quat(clip.rot[:, i], clip.fps) for i in range(clip.rot.shape[1])], axis=1)
        hips = filters.one_euro(clip.hips_pos, clip.fps)
    else:
        rot = filters.smooth_quat(clip.rot, clip.fps, filters.ROT_CUTOFF / strength)
        hips = filters.zero_phase(clip.hips_pos, clip.fps, filters.POS_CUTOFF / strength)
    out = clip.replace(rot=rot, hips_pos=hips)
    out = out.replace(contact=contact.detect(_ankles(out), out.fps))
    out = contact.lock(out, lock_left, lock_right, off_ranges)
    return in_place(out) if in_place_ else out


def in_place(clip):
    """Remove horizontal hip drift; the height and every limb rotation stay."""
    hips = clip.hips_pos.copy()
    hips[:, :2] = hips[0, :2]
    return clip.replace(hips_pos=hips, flags=dict(clip.flags, in_place=True))


def trim(clip, start=0, end=None):
    """Keep frames start..end inclusive (end None or 0 = the last frame); the new clip starts at time 0."""
    last = len(clip.times) - 1
    end = last if not end else min(end, last)
    s = slice(start, end + 1)
    n = end + 1 - start
    return clip.replace(times=np.arange(n) / clip.fps, rot=clip.rot[s], hips_pos=clip.hips_pos[s],
                        contact=clip.contact[s], conf=clip.conf[s])


def loop(clip, blend=8):
    """Make the last frame equal the first: the last `blend` frames cross-fade (smoothstep) into frame 0."""
    m = len(clip.times)
    blend = max(1, min(blend, m - 1))
    t = np.arange(1, blend + 1) / blend
    s = t * t * (3 - 2 * t)
    rot, hips = clip.rot.copy(), clip.hips_pos.copy()
    idx = np.arange(m - blend, m)
    rot[idx] = quat.slerp(rot[idx], np.broadcast_to(rot[0], rot[idx].shape), s[:, None])
    hips[idx] = hips[idx] * (1 - s[:, None]) + hips[0] * s[:, None]
    return clip.replace(rot=rot, hips_pos=hips, flags=dict(clip.flags, looped=True))


def mirror(clip):
    """Swap left and right: every bone takes its partner's pose reflected across the YZ plane."""
    G, _ = solve.fk(clip.rot, clip.hips_pos)
    swap = _partner()
    rot = solve.to_local(M @ G[:, swap] @ M)
    for i in range(rot.shape[1]):
        rot[:, i] = quat.continuity(rot[:, i])
    hips = clip.hips_pos.copy()
    hips[:, 0] = 2 * profile.HEAD[0, 0] - hips[:, 0]
    f = clip.flags
    flags = dict(f, mirrored=not f["mirrored"], lock_left=f["lock_right"], lock_right=f["lock_left"])
    return clip.replace(rot=rot, hips_pos=hips, contact=clip.contact[:, ::-1].copy(), conf=clip.conf[:, swap],
                        flags=flags)
