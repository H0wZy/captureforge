"""Per-actor calibration of the face scores (specs/005-actor-calibration).

The actor records the scripted clip of SCRIPT once. From its scores (neutral-subtracted, as the video path does) and
landmarks this module learns a linear correction: a non-negative cross-talk matrix (how much each scripted target key
leaks into the other keys) and a gain per key so the actor's full expression reaches 1.0. apply() is what the video
path, the live capture and the CSV import call. The profile is a small JSON file of numbers.

Pure Python plus numpy, no bpy: importable by path from the helpers and as captureforge.face.capture.calib in Blender.
"""

import numpy as np

# The calibration script: order matters (segments are matched to it in order). Targets are ARKit names.
SCRIPT = [
    {"id": "jawOpen", "en": "Jaw open", "pt": "Boca aberta", "targets": ["jawOpen"]},
    {"id": "smile", "en": "Smile", "pt": "Sorriso", "targets": ["mouthSmileLeft", "mouthSmileRight"]},
    {"id": "smileLeft", "en": "Smile, left side only", "pt": "Sorriso só do lado esquerdo",
     "targets": ["mouthSmileLeft"]},
    {"id": "pucker", "en": "Pucker (kiss)", "pt": "Bico", "targets": ["mouthPucker"]},
    {"id": "funnel", "en": "Funnel (say 'O')", "pt": "Boca em 'O'", "targets": ["mouthFunnel"]},
    {"id": "blink", "en": "Blink both eyes", "pt": "Piscar os dois olhos", "targets": ["eyeBlinkLeft", "eyeBlinkRight"]},
    {"id": "winkLeft", "en": "Wink, left eye", "pt": "Piscar só o olho esquerdo", "targets": ["eyeBlinkLeft"]},
    {"id": "winkRight", "en": "Wink, right eye", "pt": "Piscar só o olho direito", "targets": ["eyeBlinkRight"]},
    {"id": "browsUp", "en": "Brows up", "pt": "Sobrancelhas pra cima",
     "targets": ["browInnerUp", "browOuterUpLeft", "browOuterUpRight"]},
    {"id": "browsDown", "en": "Brows down (frown the forehead)", "pt": "Sobrancelhas franzidas",
     "targets": ["browDownLeft", "browDownRight"]},
    {"id": "frown", "en": "Mouth corners down", "pt": "Boca triste (cantos pra baixo)",
     "targets": ["mouthFrownLeft", "mouthFrownRight"]},
    {"id": "stretch", "en": "Stretch the mouth sideways", "pt": "Esticar a boca pros lados",
     "targets": ["mouthStretchLeft", "mouthStretchRight"]},
    {"id": "mouthLeft", "en": "Mouth to the left", "pt": "Boca pra esquerda", "targets": ["mouthLeft"]},
    {"id": "mouthRight", "en": "Mouth to the right", "pt": "Boca pra direita", "targets": ["mouthRight"]},
    {"id": "cheekPuff", "en": "Puff the cheeks", "pt": "Bochecha inflada", "targets": ["cheekPuff"]},
    {"id": "sneer", "en": "Sneer (wrinkle the nose)", "pt": "Nariz franzido",
     "targets": ["noseSneerLeft", "noseSneerRight"]},
    {"id": "eyesWide", "en": "Eyes wide open", "pt": "Olhos arregalados", "targets": ["eyeWideLeft", "eyeWideRight"]},
    {"id": "press", "en": "Closed smile, lips pressed", "pt": "Sorriso de boca fechada, apertando os lábios",
     "targets": ["mouthPressLeft", "mouthPressRight"]},
]
LEAD_SECONDS = 3.0   # neutral at the start of the clip
HOLD_SECONDS = 1.0
PAUSE_SECONDS = 1.0

# Face mesh points that do not move with expressions (upper forehead, temples, nose bridge, face sides).
ALIGN_IDX = (10, 109, 338, 67, 297, 103, 332, 54, 284, 21, 251, 162, 389, 127, 356, 168, 6, 197, 195, 234, 454)
EYE_OUT = (33, 263)
FACE_POINTS = 468


class CalibrationError(ValueError):
    pass


# ---- activity and segmentation ---------------------------------------------------------------------------------

def _similarity(src, dst):
    """Batched Umeyama: s, R, t with dst ~ s R src + t; src (n, m, 3), dst (m, 3)."""
    mu_s, mu_d = src.mean(axis=1, keepdims=True), dst.mean(axis=0)
    xs, xd = src - mu_s, dst - mu_d
    cov = np.einsum("mi,nmj->nij", xd, xs) / src.shape[1]
    u, sig, vt = np.linalg.svd(cov)
    d = np.sign(np.linalg.det(u @ vt))
    fix = np.ones_like(sig)
    fix[:, 2] = d
    r = (u * fix[:, None, :]) @ vt
    s = (sig * fix).sum(axis=1) / np.maximum((xs ** 2).sum(axis=(1, 2)) / src.shape[1], 1e-12)
    t = mu_d - s[:, None] * np.einsum("nij,nj->ni", r, mu_s[:, 0])
    return s, r, t


def activity(landmarks, size, valid, neutral):
    """Expression activity per frame: RMS displacement of the face points from the neutral face after a similarity
    alignment (head motion removed), in outer-eye-distance units. landmarks (n, >=468, 3) normalized; size (w, h);
    neutral: index array of neutral frames. Frames without a face get 0."""
    w, h = size
    p = np.stack([landmarks[..., 0] * w, landmarks[..., 2] * w, -landmarks[..., 1] * h], axis=-1)[:, :FACE_POINTS]
    good = np.asarray(valid, bool) & ~np.isnan(p).any(axis=(1, 2))
    neutral = [i for i in np.atleast_1d(neutral) if good[i]] or list(np.flatnonzero(good)[:1])
    if not neutral:
        raise CalibrationError("no face in the clip")
    idx = list(ALIGN_IDX)
    ref = p[neutral[0]]
    s, r, t = _similarity(p[neutral][:, idx], ref[idx])
    neu = (s[:, None, None] * p[neutral] @ np.swapaxes(r, 1, 2) + t[:, None]).mean(axis=0)
    out = np.zeros(len(p))
    q = p[good]
    s, r, t = _similarity(q[:, idx], neu[idx])
    al = s[:, None, None] * q @ np.swapaxes(r, 1, 2) + t[:, None]
    eye = np.linalg.norm(neu[EYE_OUT[1]] - neu[EYE_OUT[0]])
    out[good] = np.sqrt(((al - neu) ** 2).sum(axis=2).mean(axis=1)) / eye
    return out


def score_activity(c):
    """Fallback activity when a clip has no landmarks: the sum of the neutral-subtracted scores per frame."""
    return np.clip(np.asarray(c, float), 0, None).sum(axis=1)


def _smooth(x, n):
    if n <= 1:
        return np.asarray(x, float)
    k = np.ones(n) / n
    return np.convolve(np.pad(x, (n // 2, n - 1 - n // 2), mode="edge"), k, mode="valid")


def segment(times, act, lead=LEAD_SECONDS, min_hold=0.25, merge_gap=0.2, window=0.15):
    """Expression segments as (start, end) frame indices (end exclusive): runs where the smoothed activity is above
    the neutral level plus 40 % of the way to its 95th percentile; runs shorter than min_hold seconds are dropped and
    runs closer than merge_gap seconds are merged. The neutral level is the median of the first `lead` seconds."""
    times = np.asarray(times, float)
    dt = float(np.median(np.diff(times))) if len(times) > 1 else 1 / 30
    a = _smooth(np.asarray(act, float), max(1, int(round(window / dt))))
    lead_mask = times - times[0] < lead
    level = float(np.median(a[lead_mask])) if lead_mask.any() else float(np.percentile(a, 30))
    on = a > level + 0.4 * (float(np.percentile(a, 95)) - level)
    runs, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            runs.append([i, j])
            i = j
        else:
            i += 1
    merged = []
    for r in runs:
        if merged and times[r[0]] - times[merged[-1][1] - 1] <= merge_gap + dt:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [(a_, b_) for a_, b_ in merged if times[b_ - 1] - times[a_] + dt >= min_hold]


def match_script(times, segments, script=SCRIPT):
    """[(script entry, (start, end))] in order; CalibrationError listing what was found when the count differs."""
    if len(segments) != len(script):
        found = ", ".join(f"{times[a]:.1f}-{times[b - 1]:.1f} s" for a, b in segments) or "none"
        raise CalibrationError(f"found {len(segments)} expressions, the script has {len(script)}: {found}. "
                               "Record the clip again with a clear pause of neutral face between expressions.")
    return list(zip(script, segments))
