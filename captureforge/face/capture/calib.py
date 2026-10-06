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


# ---- learning and applying -------------------------------------------------------------------------------------

FORMAT, VERSION = "faceforge-actor-profile", 1
GAIN_MIN, GAIN_MAX = 1.0, 4.0
DETECT = 0.1        # a target whose peak stays under this is "not detected for this actor"
MIN_LEAK = 0.05     # smaller cross-talk entries are noise and are dropped
HOLD = 0.5          # hold frames: activity at least half the segment's peak
VISIBLE = 0.05      # weights up to this are invisible on a character: the leak and neutral numbers ignore them


def mirror_name(name):
    """'eyeBlinkLeft' -> 'eyeBlinkRight', 'mouthLeft' -> 'mouthRight'; names without a side are unchanged."""
    if name.endswith("Left"):
        return name[:-4] + "Right"
    if name.endswith("Right"):
        return name[:-5] + "Left"
    return name


def gain_for(peak):
    """The gain that maps the actor's peak to 1.0, bounded to GAIN_MIN..GAIN_MAX."""
    return float(min(GAIN_MAX, max(GAIN_MIN, 1.0 / peak))) if peak > 0 else GAIN_MAX


def _swap(names, rows):
    col = {n: i for i, n in enumerate(names)}
    return rows[:, [col.get(mirror_name(n), i) for i, n in enumerate(names)]]


def _holds(act, pairs):
    out = []
    for entry, (a, b) in pairs:
        seg = np.asarray(act[a:b], float)
        out.append((entry, a + np.flatnonzero(seg >= HOLD * seg.max())))
    return out


def _is_mirrored(col, c, holds):
    """True when the one-sided expressions (left wink, left smile) read on the right side."""
    votes = []
    for entry, idx in holds:
        if entry["id"] in ("winkLeft", "smileLeft"):
            k = entry["targets"][0]
            if k in col and mirror_name(k) in col:
                votes.append(c[idx, col[mirror_name(k)]].mean() > c[idx, col[k]].mean())
    return bool(votes) and all(votes)


def _nnls(x, y, iterations=500):
    """min |x w - y|^2 with w >= 0 by projected gradient (small problems only)."""
    g = x.T @ x
    lip = float(np.linalg.eigvalsh(g)[-1]) if g.size else 0.0
    w = np.zeros(x.shape[1])
    if lip <= 0:
        return w
    xy = x.T @ y
    for _ in range(iterations):
        w = np.maximum(0.0, w - (g @ w - xy) / lip)
    return w


def _matrix(profile, names):
    """Cross-talk matrix L (K x K, L[j, i] = leak of source i into key j) and gains, for these column names."""
    col = {n: i for i, n in enumerate(names)}
    leak = np.zeros((len(names), len(names)))
    for j, row in profile["crosstalk"].items():
        for i, w in row.items():
            if j in col and i in col:
                leak[col[j], col[i]] = w
    gains = np.array([profile["gains"].get(n, 1.0) for n in names])
    return leak, gains


def learn(names, c, act, pairs, label="", tracker="mediapipe", tracker_version="", head_pitch_deg=None, created=""):
    """The actor profile from one scripted take. names: score columns; c: (n, K) neutral-subtracted scores clamped
    to 0..1 (the video path's calibration without smoothing); act: per-frame activity; pairs: match_script()."""
    names = list(names)
    col = {n: i for i, n in enumerate(names)}
    c = np.asarray(c, float)
    holds = _holds(act, pairs)
    mirrored = _is_mirrored(col, c, holds)
    if mirrored:
        c = _swap(names, c)
    crosstalk = {}
    for j, name in enumerate(names):
        segs = [(e, idx) for e, idx in holds if name not in e["targets"]]
        frames = np.concatenate([idx for _, idx in segs]) if segs else np.array([], int)
        sources = sorted({k for e, _ in segs for k in e["targets"] if k in col and k != name}, key=col.get)
        if not len(frames) or not sources or c[frames, j].max() < 2 * MIN_LEAK:
            continue
        w = _nnls(c[frames][:, [col[s] for s in sources]], c[frames, j])
        row = {s: round(float(v), 4) for s, v in zip(sources, w) if v >= MIN_LEAK}
        if row:
            crosstalk[name] = row
    profile = {"format": FORMAT, "version": VERSION, "label": label, "tracker": tracker,
               "tracker_version": tracker_version, "created": created, "mirrored": mirrored,
               "gains": {n: 1.0 for n in names}, "crosstalk": crosstalk, "undetected": [],
               "head_pitch_deg": head_pitch_deg}
    leak, _ = _matrix(profile, names)
    d = np.clip(c - c @ leak.T, 0.0, None)
    peaks = {}
    for entry, idx in holds:
        for k in entry["targets"]:
            if k in col:
                peaks[k] = max(peaks.get(k, 0.0), float(np.percentile(d[idx, col[k]], 90)))
    for k, peak in peaks.items():
        if peak < DETECT:
            profile["undetected"].append(k)
        else:
            profile["gains"][k] = round(gain_for(peak), 4)
    return profile


def apply(profile, names, rows):
    """Corrected scores: clamp(gain * (c - L c), 0, 1), after the left-right swap of a mirrored profile. No profile:
    a copy of rows. Columns the profile does not know pass through with gain 1 and no cross-talk."""
    rows = np.array(rows, dtype=float)
    if profile is None:
        return rows
    names = list(names)
    if profile.get("mirrored"):
        rows = _swap(names, rows)
    leak, gains = _matrix(profile, names)
    return np.clip(gains * np.clip(rows - rows @ leak.T, 0.0, None), 0.0, 1.0)


def save_profile(profile, path):
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=1, sort_keys=True)


def load_profile(path):
    """Read and check an actor profile. CalibrationError on another file type or version."""
    import json
    try:
        with open(path, encoding="utf-8") as f:
            profile = json.load(f)
    except (OSError, ValueError) as e:
        raise CalibrationError(f"cannot read the actor profile {path}: {e}") from e
    if not isinstance(profile, dict) or profile.get("format") != FORMAT:
        raise CalibrationError(f"{path} is not a FaceForge actor profile")
    if profile.get("version") != VERSION:
        raise CalibrationError(f"{path}: actor profile version {profile.get('version')}, this FaceForge reads {VERSION}")
    return profile


# ---- report and evaluation -------------------------------------------------------------------------------------

def _scores(names, w, holds, gaps, undetected):
    """Per-expression and per-take numbers of score table w (spec 005, SC-001 to SC-004)."""
    col = {n: i for i, n in enumerate(names)}
    vis = np.clip(w - VISIBLE, 0.0, None)
    rows = []
    for entry, idx in holds:
        tg = [col[k] for k in entry["targets"] if k in col]
        mean = w[idx].mean(axis=0)
        other = [i for i in range(len(names)) if i not in tg]
        rows.append({"id": entry["id"], "en": entry["en"],
                     "peak": float(np.mean([np.percentile(w[idx, i], 90) for i in tg])) if tg else 0.0,
                     "leak": float(vis[idx].mean(axis=0)[other].sum()), "hit": bool(tg) and int(np.argmax(mean)) in tg,
                     "undetected": all(k in undetected for k in entry["targets"])})
    detectable = [r["peak"] for r in rows if not r["undetected"]]
    return rows, {"hits": sum(r["hit"] for r in rows), "median_peak": float(np.median(detectable)) if detectable else 0.0,
                  "leak": float(np.mean([r["leak"] for r in rows])),
                  "neutral": float(vis[gaps].sum(axis=1).mean()) if len(gaps) else 0.0}


def evaluate(profile, names, c, act, pairs):
    """Before and after numbers of a take (the held-out take for the gate, the calibration take for the report):
    {"before": totals, "after": totals, "expressions": [per expression rows]}. Totals: hits (a target key is the
    strongest), median_peak (of the detectable expressions), leak (mean visible weight, above VISIBLE, on non-target
    keys), neutral (mean visible weight on the frames outside every expression)."""
    names = list(names)
    c = np.asarray(c, float)
    holds = _holds(act, pairs)
    inside = np.zeros(len(c), bool)
    for _, (a, b) in pairs:
        inside[max(0, a - 3):b + 3] = True
    gaps = np.flatnonzero(~inside)
    undetected = set(profile.get("undetected", ())) if profile else set()
    base = _swap(names, c) if profile and profile.get("mirrored") else c
    before_rows, before = _scores(names, base, holds, gaps, undetected)
    after_rows, after = _scores(names, apply(profile, names, c), holds, gaps, undetected)
    expressions = [{"id": b["id"], "en": b["en"], "peak_before": b["peak"], "peak_after": a["peak"],
                    "leak_before": b["leak"], "leak_after": a["leak"], "hit_before": b["hit"], "hit_after": a["hit"],
                    "undetected": b["undetected"]} for b, a in zip(before_rows, after_rows)]
    return {"before": before, "after": after, "expressions": expressions}


def report_lines(profile, ev):
    """Plain text lines for the panel and the operator report."""
    b, a = ev["before"], ev["after"]
    n = len(ev["expressions"])
    lines = [f"Actor profile '{profile.get('label', '')}': "
             + ("left and right were mirrored (corrected)" if profile.get("mirrored") else "not mirrored"),
             f"Target key strongest: {b['hits']} of {n} before, {a['hits']} after",
             f"Median target peak: {b['median_peak']:.2f} before, {a['median_peak']:.2f} after",
             f"Weight on other keys: {b['leak']:.2f} before, {a['leak']:.2f} after",
             f"Weight on a neutral face: {b['neutral']:.2f} before, {a['neutral']:.2f} after"]
    if profile.get("head_pitch_deg") is not None:
        lines.append(f"Mean head pitch during calibration: {profile['head_pitch_deg']:+.0f} degrees")
    for r in ev["expressions"]:
        state = "not detected" if r["undetected"] else f"{r['peak_before']:.2f} -> {r['peak_after']:.2f}"
        lines.append(f"  {r['en']}: {state}; others {r['leak_before']:.2f} -> {r['leak_after']:.2f}")
    if profile.get("undetected"):
        lines.append("Not detected for this actor (kept as tracked): " + ", ".join(profile["undetected"]))
    return lines


# ---- from a capture file to a profile --------------------------------------------------------------------------

def load_capture(path):
    """A capture file (interface 2, written by video_to_csv.py --capture) or a spec 003 landmark file (interface 1,
    no head matrices): times, valid, landmarks, scores (raw, NaN without a face), names, size, mats (or None)."""
    with np.load(path, allow_pickle=False) as d:
        try:
            out = {k: d[k] for k in ("interface", "times", "valid", "landmarks", "scores", "names", "size")}
        except KeyError as e:
            raise CalibrationError(f"{path} is not a FaceForge capture file (missing {e})") from e
        mats = d["mats"] if "mats" in d.files else None
    if int(out["interface"]) not in (1, 2):
        raise CalibrationError(f"{path}: capture file version {int(out['interface'])} is not supported")
    return {"times": out["times"].astype(float), "valid": out["valid"].astype(bool),
            "landmarks": out["landmarks"].astype(float), "scores": out["scores"].astype(float),
            "names": [str(n) for n in out["names"]], "size": tuple(int(x) for x in out["size"]),
            "mats": None if mats is None else mats.astype(float)}


def neutral_scores(cap, lead=LEAD_SECONDS):
    """(c, neutral frame indices): raw scores minus their mean over the valid frames of the first `lead` seconds,
    clamped to 0..1 (the video path's neutral calibration, gain 1); frames without a face are 0."""
    t, valid = np.asarray(cap["times"], float), np.asarray(cap["valid"], bool)
    raw = np.asarray(cap["scores"], float)
    neutral = np.flatnonzero(valid & (t - t[0] < lead))
    base = np.nanmean(raw[neutral], axis=0) if len(neutral) else np.zeros(raw.shape[1])
    c = np.clip(np.nan_to_num(raw - base), 0.0, 1.0)
    c[~valid] = 0.0
    return c, neutral


def head_pitch_deg(mats, valid):
    """Mean head pitch in degrees from the facial transformation matrices (None without matrices)."""
    if mats is None:
        return None
    m = np.asarray(mats, float)[np.asarray(valid, bool)]
    m = m[~np.isnan(m).any(axis=(1, 2))]
    if not len(m):
        return None
    r = m[:, :3, :3] / np.linalg.norm(m[:, :3, :3], axis=1, keepdims=True)
    return round(float(np.degrees(np.arcsin(np.clip(-r[:, 1, 2], -1, 1))).mean()), 1)


def calibrate(cap, label, lead=LEAD_SECONDS, tracker_version="", created=""):
    """The actor profile and its evaluation from one scripted take (load_capture). CalibrationError when the clip
    does not split into the script's expressions."""
    t = np.asarray(cap["times"], float)
    c, neutral = neutral_scores(cap, lead)
    lm = cap.get("landmarks")
    if lm is not None and np.asarray(cap["valid"]).any() and not np.isnan(lm[np.asarray(cap["valid"], bool)]).all():
        act = activity(lm, cap["size"], cap["valid"], neutral)
    else:
        act = score_activity(c)
    pairs = match_script(t, segment(t, act, lead))
    if not created:
        import datetime
        created = datetime.date.today().isoformat()
    profile = learn(cap["names"], c, act, pairs, label=label, tracker_version=tracker_version,
                    head_pitch_deg=head_pitch_deg(cap.get("mats"), cap["valid"]), created=created)
    ev = evaluate(profile, cap["names"], c, act, pairs)
    profile["report"] = {"before": ev["before"], "after": ev["after"], "expressions": ev["expressions"],
                         "segments": [[round(float(t[a]), 2), round(float(t[b - 1]), 2)] for _, (a, b) in pairs]}
    return profile, ev
