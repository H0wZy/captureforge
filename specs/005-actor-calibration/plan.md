# Implementation Plan: FaceForge per-actor calibration of the face scores

**Branch**: `005-actor-calibration` (stacked on `004-live-capture-panel`) | **Date**: 2026-10-05 | **Spec**: [spec.md](spec.md)

## Summary

The video helper can already track a clip; it gains an option to keep a capture file (times, raw scores, landmarks,
head matrices). A pure numpy module, `capture/calib.py`, reads that file, splits the scripted clip into expression
segments from the landmark motion (so expressions that the scores miss, like a cheek puff, still count), and learns a
linear correction on top of the existing neutral calibration: a non-negative cross-talk matrix (how much of each
scripted target key leaks into every other key) fitted by least squares, then a gain per key so that the actor's peak
reaches 1.0. The profile is a small JSON file. Applying it is one function, `apply(profile, names, rows)`, called from
the shared post-processing between the neutral calibration and the smoothing, so the video path, the live capture and
an opt-in CSV import all use the same code. Off by default; with no profile the output is unchanged.

## Technical Context

- Language: Python 3.11+ (Blender 4.4 and 5.2, the helper venv). `calib.py` needs numpy (bundled with Blender, pinned
  in the helper lock); it imports nothing from Blender and is importable by path like `post.py`.
- Inputs: a capture file `.npz` (interface 2 of the spec 004 capture file: spec 003's landmark file plus the head
  matrices) written by `video_to_csv.py --capture PATH`.
- Output: `<label>.faceprofile.json`.
- Testing: pure tests with synthetic score tables (`tests/test_capture_calib.py`), a helper test for `--capture`,
  Blender tests for the operators and the panel; the go/no-go measurement on two real scripted takes (not committed).
- Performance: a 40 s clip at 30 fps is 1200 frames x 52 keys; learning is a handful of small least-squares problems
  (well under a second); applying is one matrix product per frame.

## Constitution Check

| Principle | Status | How |
|---|---|---|
| I. Clean room | Pass | Linear cross-talk removal and per-channel gains are textbook signal calibration; the idea comes from the project's own measurements (spec 003 research). |
| II. Blender API only inside the extension, ML outside | Pass | MediaPipe stays in `helpers/tracker.py`; the calibration only reads scores and landmarks from a file. |
| III. Headless-testable, test first | Pass | The whole method is a pure module tested on synthetic tables first; operators are thin. |
| IV. CI green on 4.4 and 5.2 | Pass | No new Blender API beyond operators, properties and a panel box. |
| V. GPL-compatible dependencies | Pass | numpy only. |
| VI. Privacy | Pass | The calibration clip and capture file are opt-in and documented as face data; the profile holds numbers and a user label only; `*.faceprofile.json` and capture files are git-ignored; tests use synthetic data. |
| VII. English first, pt-BR for users | Pass | The script and the docs in both languages. |
| VIII. Lean code | Pass | One pure module, one apply call in the shared post-processing, thin operators. |
| IX. Android friendly | Pass | Any phone or webcam; the reference recordings were made with an Android phone. |
| X. Semantic versioning | Pass | New optional file formats with a version field. |

## Project Structure

```text
specs/005-actor-calibration/            spec.md, plan.md, tasks.md, research.md (gate numbers)
captureforge/face/capture/calib.py      pure numpy: SCRIPT, load_capture, activity, segment, learn, apply, report, evaluate, save/load profile
captureforge/face/capture/post.py       process(..., profile=None): apply between calibrate and smooth
captureforge/face/helpers/video_to_csv.py   --capture PATH (capture file), --profile PATH
captureforge/face/ops.py, ui.py, video.py   faceforge.calibrate, faceforge.profile_report, profile path, CSV option, script text
tests/test_capture_calib.py              pure tests
tests/test_video_to_csv.py               --capture writer round trip
tests/run_tests.py                       operators and panel
.gitignore                               *.faceprofile.json, *.capture.npz
README.md, README.pt-BR.md, docs/pt-BR/CALIBRACAO.md
```

## Design

### Script

`SCRIPT` is the ordered list of the spec's 18 expressions, each with an id, an English and a Portuguese label and its
target keys (for example `smile` -> `mouthSmileLeft`, `mouthSmileRight`; `winkLeft` -> `eyeBlinkLeft`). The panel text,
the docs and the segment matching all read it.

### Segmentation

Expression activity per frame = RMS displacement of the 468 face points after a similarity alignment to the neutral
face (the same approach measured in spec 003), in eye-distance units, lightly smoothed. A frame is active above
`neutral level + 40 %` of the gap between the neutral level and the 95th percentile; active runs shorter than 0.25 s
are dropped and runs closer than 0.2 s are merged. When the clip has no landmarks, the activity falls back to the sum of
the neutral-subtracted scores. Each segment's "hold" is its frames above half its own peak activity.

### Learning (on neutral-subtracted, clamped scores `c`, mirror fixed first)

1. Mirror: in `winkLeft` and `smileLeft`, if the right-side key outscores the left one in both, the clip is mirrored;
   left and right columns are swapped before learning and the profile says so.
2. Cross-talk: sources are the script's target keys. For every key `j`, fit `c_j ~ sum_i L[j, i] c_i` with `L >= 0`
   over the hold frames of all segments where `j` is not a target (non-negative least squares by a few projected
   gradient steps; small), and only from sources that are targets of those segments. Entries under 0.05 are dropped.
   Corrected before gain: `d = c - L c`, clamped at 0.
3. Gain: for each target key, its 90th percentile on the hold frames of its segments in `d`; gain `1 / peak` clamped to
   1.0 to 4.0. A target whose peak is under 0.1 is "not detected": gain 1, listed. Keys that are never targets keep 1.
4. Apply: `y = clamp(g * (c - L c), 0, 1)` with the mirror swap first. Columns absent from the input are skipped.

### Report and evaluation

Per expression: target peak before and after, mean weight on non-target keys before and after, whether a target key
is the strongest. Per clip: segment times, mirror flag, mean head pitch from the matrices, undetected keys.
`evaluate(profile, capture)` computes the spec's SC-001 to SC-004 on a held-out take.

### Profile file

```json
{"format": "faceforge-actor-profile", "version": 1, "label": "...", "tracker": "mediapipe", "tracker_version": "...",
 "created": "2026-10-05", "mirrored": false, "gains": {"eyeBlinkLeft": 1.6}, "crosstalk": {"eyeSquintLeft": {"mouthSmileLeft": 0.4}},
 "undetected": ["cheekPuff"], "head_pitch_deg": -3.0, "report": [...]}
```

### Integration (after the gate)

`post.process(..., profile=None)` applies the profile between `calibrate` and `smooth`; `video_to_csv.py --profile`
passes it; the live capture's stream does the same per frame; `Import CSV` applies it when `Apply actor profile` is on.
The panel shows the script, a `Calibrate` button (video file and label in, profile and report out, running the helper
with `--capture` first) and the profile path.

## Risks and the gate

- Real footage might not generalize from one take to another (lighting, angle). The gate measures exactly that on two
  takes; if SC-001 to SC-004 fail, integration stops and the numbers go into `research.md`.
- Expressions the actor cannot isolate (a one-sided smile) put real co-activation into the cross-talk; the report shows
  it and the actor can redo the take.
- Over-subtraction on combined expressions (a smile with a real squint): the fit is restricted to hold frames of single
  scripted expressions, and the gate's neutral and leakage numbers watch for it.

## Complexity Tracking

No violations.
