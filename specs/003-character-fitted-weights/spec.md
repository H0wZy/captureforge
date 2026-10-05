# Feature Specification: FaceForge weights fitted to the character

**Feature Branch**: `003-character-fitted-weights`

**Created**: 2026-10-05

**Status**: On hold. The go/no-go measurement (T001) failed on a synthetic proxy; see [research.md](research.md)

**Input**: User description: "Instead of keying the generic MediaPipe blendshape scores onto the character, solve, per video frame, the weights of the character's own ARKit shape keys that best reproduce the tracked face landmarks, so the expression 'sticks' to a stylized face and not to the average human one." Research: `docs/research/keentools-facetracker.md`, idea 5 (character-fitted weights); the spec 002 head pose is not a prerequisite.

## Clarifications

### Session 2026-10-05

Answered with the recommended default; no user was blocked. The maintainer should confirm or override.

- Q: What does weight 1.0 mean on the character: the actor's absolute motion, or the actor's own range? -> A: absolute. The actor's landmark displacement divided by the actor's outer eye-corner distance is matched to the character's key displacements divided by the character's outer eye-corner distance, so a key at 1.0 is whatever the artist baked as its full expression. A single `Expression gain` (default 1.0) scales the actor's displacement for cartoony characters. No per-actor range calibration in v1 (it would need a calibration-video protocol); noted as a limit, and the per-key gains of the importer stay available.
- Q: Which landmarks enter the solve? -> A: the 468 face-mesh points, not the 10 iris points (the head mesh's keys do not move the eyeballs, so eye-look keys stay generic). Equal weights, except depth (the noisiest MediaPipe axis) counts half. Both are constants in the code, not settings.
- Q: How is head motion removed? -> A: each frame is aligned to the neutral face (the mean of the neutral window, as in the generic path) with a similarity transform (rotation, translation, uniform scale) computed on a fixed subset of points that do not move with expressions (forehead, temples, nose bridge). The index list is fixed in the plan from the public canonical face mesh and checked by a test that a synthetic jaw opening leaves the subset's alignment unchanged.
- Q: Objective and solver? -> A: `|A w - b|^2 + l1 * sum(w) + l2 * |w - w_generic|^2`, 0 <= w <= 1, solved with FISTA (projected, fixed step from the Lipschitz constant, a fixed iteration count) for all frames at once with numpy. Starting values: the generic weights. `l1` and `l2` are exposed as `Sparsity` and `Generic prior` in an advanced fold, defaults tuned on synthetic data and one real clip in the plan (starting guess 0.02 and 0.1 in normalized units).
- Q: Which keys count as observable? -> A: a key whose basis column has an L2 norm below 5 % of the median key norm moves no tracked point (eye look, tongue, an empty key) and keeps its generic score. The report names these keys.
- Q: Keys that exist only as a symmetric pair (`eyeBlink` instead of `eyeBlinkLeft/Right`)? -> A: fitted as one column that moves both sides; its generic prior is the mean of the Left and Right generic scores; the report says so.
- Q: Where do the character's neutral landmarks come from? -> A: the same front render and MediaPipe call as the auto rig fit, on the target with every key at 0, with the 478 points raycast onto the surface and kept as triangle plus barycentric coordinates, so a key's displacement at a point is the barycentric interpolation of the triangle's corner deltas. If MediaPipe finds no face in the render the fit stops with advice. No manual landmark editing in v1.
- Q: What is stored and when? -> A: `<csv stem>.landmarks.npz` with `interface` (1), `times`, `valid`, `landmarks` (n, 478, 3) float32, `scores` (n, 52) float32 in ARKit order, `names`, `size`. The helper writes it only when asked (`--landmarks PATH`), and `Video to face` asks only when `Keep landmarks` is ticked (default off, because it is face data). About 6 KB per frame.
- Q: What does the fit produce? -> A: the same kind of rows as the generic path: keyed through `mocap.apply_mocap` into `<target>_facemocap`, and written as `<csv stem>_fitted.csv` in the generic format (head pose columns copied unchanged when present). The frame mapping and smoothing are the existing ones.
- Q: UI? -> A: a box `4d. Fit to character` in the FaceForge panel: landmark file, `Fit strength`, `Expression gain`, an advanced fold, `Fit to character`, `Delete landmark file`. The operators are `faceforge.fit_weights` and `faceforge.delete_landmarks`.
- Q: Is this in scope for this change to implement? -> A: this branch stops at spec, plan and tasks. The estimate is about 700 lines of code plus tests and docs, and SC-004 needs a go/no-go measurement on a real clip first (task T001), so implementation is a separate session.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A stylized character that follows the actor's face shape, not only the actor's scores (Priority: P1)

An animator has baked ARKit shape keys on a stylized head (big eyes, a wide mouth, a smile that pulls the cheeks
differently from a human one) and a phone video of an actor. Today `Video to face` keys the 52 generic MediaPipe
scores, so a smile is whatever the model says a human smile is, and channels that the model confuses (smile versus
stretch, pucker versus funnel) drive the wrong keys. With the fit on, FaceForge keys the weights that make the
character's own keys move the character's face points the way the actor's face points moved.

**Why this priority**: it is the one thing a paid tracker sells (the conversion onto the character's own shapes) that
FaceForge cannot do yet, and it fixes the most visible mocap complaint: an expression that reads wrong on the
character.

**Independent Test**: build a head with shape keys that move known surface points, synthesize landmark frames from
known weights (with noise), fit, and check the recovered weights and the landmark residual against the generic
weights. No MediaPipe needed.

**Acceptance Scenarios**:

1. **Given** landmark frames made from known weights of the character's keys, **When** the fit runs, **Then** the recovered weights are within 0.05 RMS of the known ones and the landmark residual is lower than with the weights of a different (mis-scaled, cross-talking) generic estimate.
2. **Given** a clip and a character, **When** the user presses `Fit to character`, **Then** the character's shape keys are keyed with the fitted weights and a report says how much the landmark error dropped and which keys were not observable and kept the generic score.
3. **Given** the fit is off, **When** the user imports a CSV or runs `Video to face`, **Then** nothing changes from today.

---

### User Story 2 - Control and honesty (Priority: P2)

The user can blend fitted and generic weights, raise the expression gain for a cartoony character, and see which keys
were really fitted.

**Independent Test**: unit tests on the solver options and the report.

**Acceptance Scenarios**:

1. **Given** `Fit strength` 0, **When** fitted, **Then** the result equals the generic weights; at 1, the pure fit.
2. **Given** `Expression gain` 1.5, **When** fitted on the same clip, **Then** the face displacement asked of the character is 1.5 times larger and the weights grow accordingly (clamped to 0..1).
3. **Given** a key that moves no tracked point (eye look, tongue, a nearly empty key), **When** fitted, **Then** it keeps its generic score and the report names it.

---

### User Story 3 - Reuse without rerunning MediaPipe (Priority: P3)

The landmarks of a clip are kept in a file next to the CSV, so a second character or a retry of the fit, strength or
gain does not rerun the tracker.

**Independent Test**: fit twice from the file with different options and check that the helper is not called.

**Acceptance Scenarios**:

1. **Given** the landmark file exists, **When** the fit runs again, **Then** no subprocess starts.
2. **Given** the user presses `Delete landmark file`, **When** done, **Then** the file is gone and the CSV still imports.

### Edge Cases

- MediaPipe finds no face in the character render: the fit stops with a message that says what to change (front view, visible eyes and mouth), the generic path still works.
- Frames without a face in the video: generic hold, like today; they do not enter the solve.
- A character with only symmetric keys (`eyeBlink` instead of `eyeBlinkLeft/Right`): those keys are fitted as one key against both sides; the report says so.
- Keys that are strongly correlated (two keys that move the same points): the generic prior and the sparsity term decide; the report lists keys that stay near 0 or near 1 for the whole clip.
- Head turned or tilted: the face points are aligned to the neutral face first (rotation, translation, scale), so head motion is not read as expression.
- A mesh with other modifiers than the shape keys (Armature, Subsurf): the fit reads the evaluated target the way the quality inspector does.
- Very long clips: the solve is vectorized over frames and stays within the time budget in SC-002.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The video helper MUST be able to write, next to the CSV, a landmark file with per frame: the 478 normalized landmarks, a valid flag, the raw generic scores in ARKit order, the times, the image size and an interface version. It stays optional; the CSV is unchanged.
- **FR-002**: FaceForge MUST build the character basis: the neutral landmarks mapped onto the target surface (reusing the auto rig fit camera and landmark mapping), and for each shape key the displacement of those surface points at weight 1, in face-size-normalized units.
- **FR-003**: FaceForge MUST align each video frame's landmarks to the neutral face (similarity transform on points that do not move with expressions) and express the residual in the same normalized units and axes as the basis.
- **FR-004**: The solver MUST find, for every frame, weights in 0..1 that minimize the landmark residual plus a sparsity term plus a penalty for leaving the generic weights, and MUST be pure numpy and vectorized over frames.
- **FR-005**: Keys whose basis moves no tracked point (sensitivity below a threshold) MUST keep the generic score, and the report MUST list them.
- **FR-006**: The user MUST be able to set `Fit strength` (0..1), `Expression gain`, and the sparsity and prior weights, and the fitted weights MUST be smoothed with the same `Smooth` as the generic path.
- **FR-007**: The result MUST be keyed through the existing mocap import (`<target>_facemocap` action, same frame mapping) and saved as a CSV in the generic format.
- **FR-008**: The landmark file is face data: it MUST be documented as personal data, MUST be ignored by git, and the panel MUST have a button that deletes it.
- **FR-009**: The fit MUST be off by default and the generic path MUST stay bit-for-bit as it is.
- **FR-010**: README and README.pt-BR MUST document the workflow, the options, the limits and the privacy note.

### Key Entities

- **Landmark file**: `<csv name>.landmarks.npz` with the arrays of FR-001.
- **Character basis**: matrix of shape (3 x points, keys) plus per-key sensitivity, built from a target mesh and a front render.
- **Fit report**: per key: fitted or kept generic, mean and max weight; per clip: residual before and after.

## Success Criteria *(mandatory)*

- **SC-001**: on synthetic clips with known weights and noise, RMS weight error 0.05 or less, and residual lower than the generic weights by at least 30 %.
- **SC-002**: 3000 frames by 52 keys solve in under 10 s on a laptop CPU, without a Python loop over frames.
- **SC-003**: with the fit off, every existing test passes unchanged and the CSV import output is identical.
- **SC-004** (go/no-go, measured on a real clip before this ships): the landmark residual of the fitted weights is at least 20 % lower than that of the generic weights on the character, and a side-by-side review of the keyed result does not look worse. If not met, the feature stays out of the default UI and the finding goes in the README.
