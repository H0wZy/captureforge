# Feature Specification: FaceForge per-actor calibration of the face scores

**Feature Branch**: `005-actor-calibration` (stacked on `004-live-capture-panel`; rebase when the stack merges)

**Created**: 2026-10-05

**Status**: Draft

**Input**: User description: "FaceForge per-actor calibration of the generic MediaPipe blendshape scores. The actor records a short scripted calibration clip (neutral, then each expression once). From it FaceForge learns, per key, a gain (so the actor's full expression reaches 1.0) and a cross-talk correction (subtract the co-activation that leaks into other keys, e.g. eyeSquint during a smile, eyeLookDown during a blink). The calibration is saved as a small profile file per actor and applied to every later video, CSV import and live capture of that actor, on any character. Stays on MediaPipe's own scores (spec 003's geometric fit was a no-go). Free/open-source only, numpy only in Blender, pure-testable, off by default, generic path unchanged."

## Background

FaceForge turns a face video into 52 ARKit scores per frame (MediaPipe's blendshapes) and keys them onto the character's
shape keys of the same names. Spec 003 tried to replace those scores with a geometric fit of the tracked landmarks and
failed its go/no-go on synthetic and real footage (`specs/003-character-fitted-weights/research.md`): MediaPipe's own
scores separate the expressions better. The real clips of that test also showed what is wrong with the scores for one
actor, and it is consistent rather than random:

| Observation on the maintainer's clips | Effect on the character |
|---|---|
| A full blink peaks at about 0.6 (0.52 to 0.86 depending on the take) | the eyes never close |
| A blink leaks about 0.3 into `eyeSquint` and `eyeLookDown` | the eyes squint and look down while blinking |
| A smile raises both `eyeSquint` above 0.3 in about 80 % of its frames, and `mouthUpperUp` to 0.9 | every smile squints and bares the upper teeth |
| A frown peaks at 0.26 to 0.40; a sad brow reads `browInnerUp` 0.16 | sad faces barely read |
| `cheekPuff` and `noseSneer` never rise above 0.0 | puffed cheeks and sneers are lost |

A short calibration of the actor turns these into two simple corrections per key: how far the actor's full expression
actually goes (a gain) and what leaks along with it (cross-talk to subtract).

## Clarifications

### Session 2026-10-05

Answered with the recommended default; no user was blocked. The maintainer should confirm or override.

- Q: What does the actor record? -> A: one calibration clip that follows a fixed script, shown in the panel and in the
  docs: 3 s neutral, then 18 expressions in this order, each held about 1 s with about 1 s of neutral between them:
  jaw open, smile, smile left only, pucker, funnel ("O"), blink both, wink left, wink right, brows up, brows down
  (frown the forehead), mouth corners down (frown), stretch, mouth left, mouth right, cheek puff, sneer, eyes wide,
  closed-mouth smile with pressed lips (mouthPress). About 40 s in total. Left and right are the actor's own.
- Q: How does FaceForge know which part of the clip is which expression? -> A: automatically: the neutral stretches
  between expressions split the clip into segments, which are matched to the script in order. If the count does not
  match, the calibration stops and lists the segments it found with their times, so the actor can redo the clip; no
  manual segment editing in v1.
- Q: What exactly is learned? -> A: on the neutral-subtracted scores (the existing neutral calibration), per scripted
  expression: (1) the peak of its target key(s) gives a gain so that the peak maps to 1.0, bounded to 1.0 to 4.0 so
  noise is not blown up; (2) the mean of every other key during that expression, relative to the target's value, is the
  cross-talk that is subtracted whenever the target is active. A key the script never targets keeps gain 1 and only
  loses the cross-talk it receives. The result is clamped to 0..1 like today.
- Q: Keys that never fire for this actor (`cheekPuff`, `noseSneer` in the evidence)? -> A: no gain can raise a score
  that stays at 0. The profile marks them "not detected for this actor" and the report says so. Deriving them from
  other signals is out of scope.
- Q: Front camera mirror? -> A: the wink-left segment tells which side the tracker calls left. If it is swapped (a
  mirrored front-camera recording), the profile records it and left and right columns are swapped when the profile is
  applied, and the report says so.
- Q: Where is the profile applied? -> A: `Video to face`, the live capture of spec 004 and the bake from it, when an
  actor profile is chosen in the panel (empty by default). `Import CSV` gets an `Apply actor profile` option, off by
  default, because a CSV may come from another tracker (Live Link Face) or may already be corrected.
- Q: What is stored? -> A: a small text file per actor (`<label>.faceprofile.json`): the label the user typed, the
  tracker and its version, the date, gains, the cross-talk table, the mirror flag, the undetected keys and the
  calibration report numbers. No image, landmark or raw score. The calibration clip is not kept unless the user keeps
  it. Profiles are user data, never committed; the label must not have to be a real name.
- Q: How is success measured without being circular (the lesson of spec 003)? -> A: on a second, held-out take of the
  same script, never on the take the profile was learned from. Per scripted expression: does a target key become the
  strongest key, how high does it get, and how much weight goes to the other keys; plus the weight on neutral
  stretches. The numbers are compared with the uncorrected scores on the same take.
- Q: Is this implemented now? -> A: no. This branch carries the spec; plan and tasks follow. The first task will be a
  go/no-go measurement on two scripted takes of the maintainer (the same gate idea as spec 003).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Calibrate my face once (Priority: P1)

An animator opens the FaceForge panel, reads the calibration script, records a 40-second clip of themselves following
it, points FaceForge at the clip, types a label for the profile and presses `Calibrate`. FaceForge processes the clip,
finds the 18 expressions, and shows a short report: for each expression how high the score went before and after, what
leaked and how much less leaks now, which keys it cannot detect for this face, and whether the camera was mirrored.
The profile is saved.

**Why this priority**: without a profile nothing else in this spec does anything, and the report alone already tells
the user what their recordings will and will not capture.

**Independent Test**: feed a synthetic calibration clip's scores (made from known gains and cross-talk) to the
calibration and check the recovered numbers; feed a clip with a missing expression and check the error lists the
segments found.

**Acceptance Scenarios**:

1. **Given** a clip that follows the script, **When** the user presses `Calibrate`, **Then** a profile file is written and the report lists all 18 expressions with before and after values.
2. **Given** a clip where the actor skipped one expression, **When** calibrating, **Then** nothing is saved and the message lists the segments found with their start and end times and how many the script expects.
3. **Given** a clip recorded mirrored, **When** calibrating, **Then** the report says left and right are swapped and the profile corrects it.
4. **Given** an expression whose key never rises (cheek puff), **When** calibrating, **Then** the report names the key as not detected for this actor and its gain stays 1.

---

### User Story 2 - Every later take of me is corrected (Priority: P1)

With the profile chosen in the panel, `Video to face` and the live capture key the character with corrected scores:
blinks close the eyes, smiles do not squint unless the actor squints, frowns read. Without a profile chosen, nothing
changes from today.

**Why this priority**: it is the value: better animation from the same footage and the same free tools.

**Independent Test**: a held-out scripted take processed with and without the profile, scored per expression
(target key strongest, peak height, leakage, neutral weight).

**Acceptance Scenarios**:

1. **Given** a profile and a new video of the same actor, **When** `Video to face` runs, **Then** the keyed curves are the corrected scores, with the existing neutral, gain and smoothing options still applied.
2. **Given** no profile chosen, **When** any import runs, **Then** the output is identical to today's.
3. **Given** a profile and a live capture (spec 004), **When** the actor blinks, **Then** the character's eyes close fully in the live drive and in the bake.
4. **Given** a FaceForge CSV made without a profile, **When** the user imports it with `Apply actor profile` on, **Then** the corrected values are keyed; with the option off (default) the CSV imports as today.

---

### User Story 3 - Check and redo (Priority: P2)

The user can reopen a profile's report, compare a held-out take with and without it, and recalibrate (new lighting, a
new camera position, a beard shaved) by recording the script again under the same or a new label.

**Why this priority**: trust: the user sees what the profile does and can replace it.

**Independent Test**: load a saved profile, regenerate its report, recalibrate under the same label and check the file
is replaced only after confirmation.

**Acceptance Scenarios**:

1. **Given** a saved profile, **When** the user opens it, **Then** the report is shown again from the file.
2. **Given** an existing label, **When** calibrating again, **Then** the user is asked before the old profile is replaced.

### Edge Cases

- The actor holds an expression too briefly or blends two expressions: the segment's target is still taken by order; the report flags segments where another key outscored the target and suggests redoing that part.
- Very little neutral between expressions: segments merge; the count check catches it and the message says to pause longer.
- The face leaves the frame during the clip: frames without a face are skipped; a missing expression is caught by the count check.
- Head turned or camera at a steep angle (the from-below tripod clip read 11 degrees of pitch): the calibration still works, but a profile learned at one angle and used at a very different one corrects less well; the report shows the mean head angle of the calibration so the user can match it.
- A profile from one actor used on another actor: allowed (the user chooses), with a note in the report that profiles are per actor.
- A profile made with another tracker version: it is applied, with a warning that recalibrating is recommended.
- A gain at its upper bound (the actor's expression barely reads): the report says the key is weak for this face and may be noisy.
- Correction pushes a value below 0 or above 1: clamped, as today.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: FaceForge MUST show the calibration script (the expressions, their order, the hold and pause times) in the panel and in the docs, in English and Brazilian Portuguese.
- **FR-002**: FaceForge MUST turn a calibration video into a profile without any manual step besides choosing the file and a label, using the same tracker and neutral handling as `Video to face`.
- **FR-003**: The calibration MUST split the clip into expression segments using the neutral pauses and match them to the script by order; when the number of segments differs from the script, it MUST stop without saving and list the segments it found with their times.
- **FR-004**: For each scripted expression the profile MUST hold a gain for its target key(s), bounded to 1.0 to 4.0, so that the actor's peak maps to 1.0.
- **FR-005**: The profile MUST hold, for each scripted expression, the cross-talk into every other key relative to the target, and applying the profile MUST subtract it in proportion to how active the target is.
- **FR-006**: Keys whose scores never rise during their own expression MUST be marked as not detected for this actor, keep gain 1, and be named in the report.
- **FR-007**: The calibration MUST detect a left-right swap from the one-sided expressions and the profile MUST correct it when applied.
- **FR-008**: Applying a profile MUST be off by default; with no profile chosen, every existing output (CSV files, keyed curves, live drive) MUST be identical to today's.
- **FR-009**: With a profile chosen, `Video to face`, the live capture and its bake MUST use corrected scores; `Import CSV` MUST offer `Apply actor profile`, off by default.
- **FR-010**: The profile MUST be a small human-readable file that holds only numbers and a user-chosen label (no image, landmark or raw score), and MUST be documented as personal data that stays out of the repository.
- **FR-011**: The report MUST show, per expression, the target score before and after, the leakage before and after, undetected keys, the mirror flag and the mean head angle of the calibration clip.
- **FR-012**: The calibration and the correction MUST be testable without Blender, without a camera and without the tracker, from score tables alone.
- **FR-013**: README and README.pt-BR MUST document the script, how to record it (camera at eye level, the whole face in view, steady light), the panel steps, the report, the limits and the privacy note.

### Key Entities

- **Calibration script**: the ordered list of expressions with their target keys and the hold and pause times.
- **Actor profile**: label, tracker and version, date, per-key gains, cross-talk table, mirror flag, undetected keys, report numbers.
- **Calibration report**: per expression the target before and after and the leakage before and after; per clip the segment times, the mirror flag, the head angle and the undetected keys.

## Success Criteria *(mandatory)*

All measured on a held-out take of the script by the same actor (never the take the profile was learned from),
compared with the uncorrected scores of the same take.

### Measurable Outcomes

- **SC-001**: In at least 15 of the 18 scripted expressions a target key is the strongest key with the profile (the uncorrected scores managed 7 of 15 comparable windows on the maintainer's unscripted clip).
- **SC-002**: The median peak of the target keys over the detectable expressions is at least 0.85 with the profile (blinks peaked at about 0.6 without it).
- **SC-003**: The visible weight (above 0.05, which no character shows) on keys that are not part of the expression drops by at least 50 % on average.
- **SC-004**: The total visible weight on neutral stretches does not grow by more than 0.05 (the correction must not create motion on a still face).
- **SC-005**: A user who has never calibrated finishes the recording and the calibration in under 5 minutes, following only the panel text.
- **SC-006** (go/no-go, measured first on two scripted takes of the maintainer): SC-001 to SC-004 are met; if not, the feature does not ship and the finding goes into the research note, as in spec 003.

## Assumptions

- The actor records with any phone or webcam (Android is the reference, Constitution IX), camera at about eye level, face fully in view; the tripod clip that cut off the chin and looked up from below is the example to avoid.
- One profile per actor and recording setup; a new camera angle or lighting may call for a new profile.
- Corrections are linear (a gain and subtracted cross-talk per key on top of the existing neutral calibration); anything heavier is out of scope.
- The tracker is MediaPipe through the tracker contract of spec 004; a profile records which tracker made it.
- Out of scope: per-character artistic tuning (the artist's job in the character's keys), manual editing of a profile in the UI, deriving undetected keys (`cheekPuff`, `noseSneer`) from other signals, Live Link Face and other trackers' CSVs.
