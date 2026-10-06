# Research: go/no-go measurement for character-fitted weights (T001)

Measured 2026-10-05 on Linux x86-64, Blender 5.2.1, `mediapipe` 1.0.1, the pinned `face_landmarker.task`
(SHA-256 `64184e22...c9ff`). The spike scripts were throwaway (not committed, as T001 says); this note records what
they did and what they measured.

## Verdict

**No-go, on the synthetic proxy and on real footage. Implementation (T002 to T016) is on hold.** The real-clip check
(below, "Real footage") confirms the proxy: the fitted weights are worse than MediaPipe's own scores.

The fit lowers the landmark residual by 20 to 50 % in every configuration, so the first half of SC-004 passes. But
the fitted weights are further from the true weights than the generic MediaPipe scores in every configuration, so the
keyed result is worse, which fails the second half ("does not look worse"). The residual drop is not evidence of a
better result: the solver minimizes exactly that residual, so it drops whether or not the weights get closer to the
truth. SC-004's first criterion is circular and should be replaced if the feature is picked up again (below).

## Setup

No real face footage was available in the measuring environment, and the repository must not hold any. The proxy:

- **Actor**: a procedural head (one mesh, 73k vertices, features sculpted and painted as a color attribute) with all 52
  ARKit shape keys built from smooth regional deltas (jaw, lips, corners, lids, brows, cheeks, nose; the eight eye-look
  keys and `tongueOut` are empty on purpose). Animated with known weights: 2 s neutral, then 25 expressions of 0.8 s
  each (single keys, pairs and mixes), 660 frames at 30 fps, rendered with Workbench at 512 x 512. Two versions: with
  head motion (yaw up to 7 degrees, pitch 4, roll 2, small translation) and without.
- **Tracker**: MediaPipe Face Landmarker in VIDEO mode on the rendered frames; it found a face in 660 of 660 frames on
  both clips. Landmarks, raw scores, validity and times were written in the `.npz` layout of FR-001.
- **Characters**: three procedural heads of different styles with their own keys: `same` (the actor's own head, the
  control), `cartoon` (rounder head, bigger eyes, wider mouth, smile x1.8, jaw x1.5, brows x1.6, pucker x1.4, puff
  x2.0) and `narrow` (long head, small features, smile x0.7, jaw x0.8, funnel x1.3, and only a symmetric `eyeBlink`).
  MediaPipe found the face in each front render; the 478 points were pinned to the surface by ray cast (triangle plus
  barycentric) and every key was measured at weight 1 on the evaluated mesh, as in the plan.
- **Solver**: as in the plan (eye-distance units, depth weight 0.5, Umeyama alignment on 21 stable points, character
  rotation from the alignment points, projected FISTA, 300 iterations, unobservable keys kept generic). Generic
  weights: the CSV path's neutral calibration, gain 1.
- **Metrics**: residual drop = 1 - RMS(A w_fit - b) / RMS(A w_generic - b) (SC-004 first half). Weight error = RMS of
  (weights - true weights) over the observable keys; for `same` the truth is exact, for the other two it is the
  actor's weights (the absolute-matching truth would be lower where a key has a gain, which favours neither side
  consistently). "true/zero" = RMS(A w_true - b) / RMS(b): below 1 means the true weights explain the tracked
  landmark motion better than "nothing moved".

## Numbers

Residual drop (%) and weight error, for three prior strengths (`Sparsity` l1 = 0.02; `Generic prior` l2 = 0.1, 0.3,
1.0). "all 468" is the spec's point set; "contours" uses only the lip, eye and brow contour points (82 points).

With head motion:

| Character | Points | true/zero | Generic weight error | Drop l2=0.1 / 0.3 / 1.0 | Fitted weight error l2=0.1 / 0.3 / 1.0 |
|---|---|---|---|---|---|
| same | all 468 | 1.17 | 0.131 | 22.4 / 21.7 / 20.1 | 0.239 / 0.187 / 0.141 |
| same | contours | 0.95 | 0.132 | 38.8 / 36.9 / 33.3 | 0.234 / 0.180 / 0.133 |
| cartoon | all 468 | 1.23 | 0.131 | 23.8 / 23.1 / 21.6 | 0.282 / 0.223 / 0.158 |
| cartoon | contours | 1.04 | 0.132 | 36.7 / 35.7 / 32.3 | 0.286 / 0.236 / 0.160 |
| narrow | all 468 | 1.10 | 0.132 | 21.5 / 20.9 / 19.6 | 0.230 / 0.186 / 0.146 |
| narrow | contours | 0.91 | 0.133 | 33.9 / 32.3 / 29.3 | 0.233 / 0.182 / 0.139 |

Without head motion (rules out the alignment as the cause):

| Character | Points | true/zero | Generic weight error | Drop l2=0.1 / 0.3 / 1.0 | Fitted weight error l2=0.1 / 0.3 / 1.0 |
|---|---|---|---|---|---|
| same | all 468 | 1.32 | 0.118 | 22.2 / 21.4 / 19.3 | 0.206 / 0.168 / 0.127 |
| same | contours | 0.92 | 0.118 | 50.1 / 48.2 / 43.5 | 0.185 / 0.150 / 0.117 |
| cartoon | all 468 | 1.42 | 0.118 | 23.0 / 22.5 / 20.6 | 0.237 / 0.198 / 0.144 |
| cartoon | contours | 1.04 | 0.118 | 41.3 / 40.2 / 36.9 | 0.228 / 0.190 / 0.140 |
| narrow | all 468 | 1.21 | 0.118 | 20.3 / 19.6 / 17.9 | 0.196 / 0.164 / 0.130 |
| narrow | contours | 0.86 | 0.118 | 42.2 / 40.6 / 37.0 | 0.187 / 0.154 / 0.122 |

Other variants tried, same outcome: depth weight 0 instead of 0.5 (fitted error 0.13 to 0.24), the character rotation
taken from the character's MediaPipe landmarks instead of its surface points (2 to 4 degrees instead of 12 to 16,
results within 0.005), contours plus the lower face oval.

The solve itself is fast: 3000 frames x 52 keys, 300 iterations, 1.3 s on one core (SC-002 budget: 10 s).

## Why

The tracked landmark motion does not follow the surface motion closely enough. On the static clip the true weights
explain the landmarks no better than "nothing moved" (true/zero 0.86 to 1.42). On the clip with head motion, per expression, the
tracked displacement correlates well with the real one for the jaw (0.85 to 0.89) and moderately for the mouth corners and
lids (0.35 to 0.65), and hardly at all for the brows (0.18 to 0.21) and the cheek puff (0.05 to 0.11): MediaPipe places
the points between the visible features from its learned face prior, not from the skin. The fit then explains this
tracking noise with the character's keys, and the weights drift away from the truth. The prior toward the generic
weights limits the damage, and at l2 = 1.0 the fit is about as good as the generic scores, which means it adds
nothing.

## What would change the verdict

The proxy is pessimistic in one respect: the actor is a painted egg, and MediaPipe tracks a real human face (its
training domain) much more faithfully than this one. A real clip might give a true/zero ratio well under 1, and
then the fit could win. That cannot be measured on a real clip with the residual alone (it always drops); it needs
either known weights or a blind side-by-side review. Suggested protocol if the maintainer wants to retry:

1. Record a short clip of a consenting actor (POLICY.md) who acts scripted segments: jaw open, smile, pucker,
   blink, brows up, and so on. The script is the reference; no special device is needed.
2. Key one stylized character with the generic weights and with the fitted weights, render both, and have someone
   who did not run the fit pick the better one per segment. Go only if the fitted version wins most segments.
3. Replace SC-004's residual criterion with that review, or with the weight error on a synthetic clip whose actor is
   a realistic scanned head (freely licensed, consent documented), which is the closest thing to ground truth.

Two cheaper directions that keep the generic scores as the source of truth, recorded for a future spec:

- **Per-key gain calibration on the character**: render each character key at weight 1, run MediaPipe on the render,
  and read which generic score it produces; use that matrix to remap generic scores to the character's keys
  (addresses cross-talk such as "smile reads as dimple", which the proxy shows clearly, without trusting the
  landmark geometry).
- **Fit only the keys with strong landmark evidence** (jaw, lip corners, lids), keeping the rest generic.

## Side findings

- On Blender 5.2 a new shape key added with `shape_key_add(from_mix=False)` starts at value 1.0, not 0.0. Code that
  renders or measures "all keys at 0" must set the values explicitly.
- MediaPipe's generic scores on stylized renders show the cross-talk the spec describes: a smile on the procedural
  head reads mostly as `mouthDimpleRight` 0.89 and `mouthDimpleLeft` 0.66, a pucker also raises `mouthDimpleRight`
  0.73, and a neutral face reads `eyeLookDown` 0.6 on both eyes.

## Real footage (2026-10-05)

Two phone clips of a consenting adult (the maintainer), unscripted: 153 s of mixed expressions (854 x 480, 30 fps,
4590 of 4591 frames tracked) and 21 s of blinking (1920 x 1080, 60 fps, all 1273 frames tracked, 24 blinks). The clips
and their landmark files were processed in a temporary environment and deleted; nothing of them is in the repository.
Same three test characters and solver as above; the neutral face is a calm stretch at the start of each clip.

Because the performance was not scripted, 17 windows were labelled by looking at the frames (2 neutral, 3 smile,
3 jaw open, 2 pucker, 2 wink, 2 frown, 1 brows up, 2 sneer). Metric (not circular): in each expression window, is
one of the expected keys the strongest weight ("hit"), what share of the total weight it takes, and how much weight
the neutral windows carry.

| Weights | Hits (of 15) | Expected key share | Neutral weight sum |
|---|---|---|---|
| Generic MediaPipe scores | 7 | 0.21 to 0.22 | 0.34 to 0.35 |
| Fitted, spec defaults (l1 0.02, l2 0.1, gain 1) | 2 to 4 | 0.08 to 0.09 | 1.9 to 2.8 |
| Fitted, best of a sweep (gain 0.05 to 0.5, l2 0.1 to 10, all 468 or contour points, depth 0 or 0.5) | 5 to 8 (`same`), 1 (`cartoon`), 5 (`narrow`) | at most 0.17 | at least 0.6 at a matching hit count |

The residual still dropped 18 to 24 % (circular, as before).

Blinking clip, mean at the 24 blink peaks: generic `eyeBlink` 0.61 with 0.30 leaking into `eyeSquint`, `browDown` and
`cheekSquint`; fitted `eyeBlink` 0.07 to 0.40 with 0.40 to 1.00 leaking, and open-eye frames carry 0.24 to 1.65 of
weight instead of 0.16.

Two reasons show in the data:

- **Scale.** A real face moves its landmarks about ten times more (RMS 0.033 eye distances) than the test heads' keys
  move theirs (median 0.003). With absolute matching most weights saturate at 1. `Expression gain` fixes the scale but
  not the next point.
- **The tracked motion does not separate the keys.** With the scale fixed, the fit still spreads a smile or a blink over
  squint, sneer and shrug keys, which move nearby points the same way. MediaPipe's blendshape head was trained to make
  that separation and does it better than a geometric fit on its own landmarks.

A blind side-by-side (generic and fitted in random order, 9 moments, character `same`, gain 0.3, l2 1.0) was handed
to the maintainer; the result is recorded here when it comes back.
