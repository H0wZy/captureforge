# Implementation Plan: FaceForge weights fitted to the character

**Branch**: `003-character-fitted-weights` (stacked on `002-face-head-pose`, which is stacked on `001-bodyforge-v1`; rebase when those merge) | **Date**: 2026-10-05 | **Spec**: [spec.md](spec.md)

## Summary

The video helper optionally keeps the 478 landmarks and the raw generic scores of every frame in a `.npz`. In
Blender, FaceForge renders the character from the front (the auto rig fit camera), finds its neutral landmarks,
pins them to the surface as triangle plus barycentric coordinates, and measures what each shape key does to those
points. The actor's frames are aligned to the neutral face and expressed in the same normalized units. A bounded,
sparse, prior-regularized least squares (FISTA, all frames at once, numpy) turns the actor's landmark motion into
weights of the character's own keys; unobservable keys keep the generic score. The weights go through the existing
mocap import. Everything is off by default.

## Technical Context

- Language: Python 3.11+ (numpy in the pure module; `bpy`, `mathutils` in the Blender module); helper unchanged except one optional output.
- Interface: `landmarks.npz` (spec FR-001), the only new file format. The CSV stays as is.
- Testing: pure numpy tests (`tests/test_fit_*.py`, the CI unit stage already creates a numpy venv for the BodyForge ones, extend its loop), headless Blender tests on a procedural head with fabricated landmarks, one optional real-MediaPipe test gated by the existing `FACEFORGE_PYTHON` / `FACEFORGE_MODEL`.
- Performance: the solve is `(K x K)` matrix products on a `(frames x K)` matrix, 300 iterations: 3000 x 52 well under a second in numpy; the budget in SC-002 is 10 s.
- Open technical risk (the reason for task T001): landmarks detected on a stylized render may be off the true face geometry, and an exaggerated key may saturate. Mitigations: the prior toward the generic weights, `Fit strength`, `Expression gain`, the report.

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Clean room | Pass | Ideas: least-squares blendshape fitting, Procrustes alignment, FISTA (Beck and Teboulle 2009), all textbook; the research note credits the idea of converting tracked geometry to blendshapes; nothing copied from any tool. |
| II. Blender API only inside the extension, ML outside | Pass | MediaPipe stays in `helpers/`; the solver module is numpy only; Blender code only reads the `.npz`. |
| III. Headless-testable, test first | Pass | The math is in a pure module with plain tests; the Blender part takes explicit objects; test tasks precede code tasks. |
| IV. CI green on 4.4 and 5.2 | Pass | New Blender tests join `run_tests.py`; only API already used elsewhere (`BVHTree`, shape key `data`, `foreach_get`). |
| V. GPL-compatible dependencies | Pass | numpy (bundled) only; no scipy; no new weights or models. |
| VI. Privacy and responsible use | Pass | The landmark file is face data: opt-in (`Keep landmarks`), documented, `*.landmarks.npz` in `.gitignore`, a delete button; tests use fabricated landmarks; POLICY.md applies. |
| VII. English first, pt-BR for users | Pass | README and README.pt-BR updated in the same change. |
| VIII. Lean code | Pass, one note | Two new modules (`fitsolve.py` pure, `fitweights.py` Blender), no classes beyond a dataclass-free dict report; settings join `scene.faceforge`. |
| IX. Android friendly | Pass | Same phone video; nothing platform-specific. |
| X. Semantic versioning | Pass | New optional file format and settings; the manifest version moves at release. |

## Project Structure

```text
specs/003-character-fitted-weights/    spec.md, plan.md, tasks.md
captureforge/face/helpers/video_to_csv.py   --landmarks PATH writes the .npz (FR-001)
captureforge/face/fitsolve.py          pure numpy: load_landmarks, align, normalize, solve, report numbers
captureforge/face/fitweights.py        bpy: character basis, fit orchestration, report text
captureforge/face/video.py             passes --landmarks when asked
captureforge/face/ops.py, ui.py        faceforge.fit_weights, faceforge.delete_landmarks, box 4d
tests/test_fit_solve.py                pure tests
tests/run_tests.py                     Blender tests (basis, end to end with fabricated landmarks)
.gitignore                             *.landmarks.npz
.github/workflows/ci.yml               unit stage runs tests/test_fit_*.py in the numpy venv
README.md, README.pt-BR.md
```

## Design

### Landmark file (helper)

`video_to_csv.py --landmarks PATH` collects what `detect()` already sees per frame (the 478 points, the matrix
is not needed) and the raw 52 generic scores before calibration, and writes the arrays of FR-001 with
`numpy.savez_compressed`. `detect()` already builds `marks` only for `--preview`; it gets a flag for all frames.
Frames without a face are NaN with `valid` false.

### Coordinates

Everything is in a character-like frame: X = the person's left (image right), Y = depth with the camera side
negative (the character looks toward -Y, so a point closer to the camera has the smaller Y, which is MediaPipe's z
sign), Z = up. A landmark `(u, v, zn)` becomes `(u * W, zn * W, -v * H)` in pixels (MediaPipe's z uses the x scale),
then is divided by the outer eye-corner distance of the same face (landmarks 33 and 263) so that the actor and the
character are in the same unit.

### Character basis (Blender)

1. `autofit.front_camera`, `render_front`, `video.landmarks` on the target with every key at 0 give the 478 neutral
   landmarks (reused code; failure message from the spec's edge cases).
2. Each landmark is ray-cast onto the evaluated target as `autofit.map_landmarks` does for its 30 points, but all
   468 points keep `(triangle, barycentric)` from the BVH hit (`ray_cast` returns the face index), or the nearest
   surface point when the ray misses.
3. For every shape key of the target whose name is an ARKit name (case-insensitive; the symmetric fallback of the
   spec), the displaced point is the barycentric interpolation of the key's corner positions minus the basis ones.
   Stack as `A` with shape `(3 * 468, K)` after dividing by the character's outer eye-corner distance.
4. Sensitivity `s_k = |A[:, k]|`; keys below 5 % of the median are unobservable.

### Frame data (pure)

1. Neutral face = mean of the valid frames in the first `neutral_seconds`, computed like the generic path.
2. Per frame: similarity transform (Umeyama) of the alignment subset onto the neutral subset, applied to all 468
   points; residual `b = aligned - neutral`, flattened, with the depth axis weighted by 0.5 (also in `A`).
3. Frames without a face are removed from the solve and filled by hold afterwards, as `hold_gaps` does.

### Solver

Minimize over `W` (frames x K), `0 <= W <= 1`:
`|A W^T - B|^2 + l1 * sum(W) + l2 * |W - W_g|^2`, restricted to observable keys; the unobservable ones are set to
`W_g`. FISTA with step `1 / L`, `L = 2 * (lambda_max(A^T A) + l2)`, 300 iterations, starting at `W_g`, clamped each
step. Then `Fit strength` mixes `W = (1 - s) * W_g + s * W`, smoothing uses the existing `smooth`, and the result
goes through `calibrate`-free clamping to 0..1 (the generic path's neutral calibration is already inside `W_g`
and inside the neutral face).

`W_g` here is the generic score after the same neutral calibration and gain the CSV path uses, so that an
unobservable key is exactly what it would have been.

### Report

Per key: observable or not, mean and max fitted weight, mean absolute change versus generic. Per clip: the landmark
residual `|A W_g - B|` and `|A W - B|` (RMS in normalized units) and the relative drop. Text in the operator's
info line and the report area, JSON optional like the quality report.

### Panel and operators

Box `4d. Fit to character` after `Video to face`: landmark file path (filled by `Video to face` when `Keep
landmarks` is on), target comes from the pairs list like every other step, `Fit strength` (default 1.0),
`Expression gain` (1.0), advanced fold with `Sparsity` and `Generic prior`, buttons `Fit to character` and `Delete
landmark file`. The operators are thin wrappers over `fitweights`.

## Risks and the gate

- Landmarks on a stylized render may be wrong or missing. T001 measures this on the real clip and on a few
  characters of different styles before any UI is written; SC-004 is the gate.
- Absolute matching can ask a cartoony mouth for less than the artist wants. `Expression gain` is the lever; a
  per-actor range calibration is out of scope.
- Correlated keys: the prior and the sparsity term resolve it; the report shows keys pinned at 0 or 1.
- Depth noise: half weight for the depth axis, and a test with noise on depth only.

## Complexity Tracking

No violations. The one thing to watch: two modules are the minimum that keeps the math testable without Blender
(Principle III), so they stay.
