# Feature Specification: FaceForge head pose from the video

**Feature Branch**: `002-face-head-pose`

**Created**: 2026-10-05

**Status**: Draft

**Input**: User description: "MediaPipe Face Landmarker can output the facial transformation matrix. Write the per-frame head rotation (and optionally translation) into the mocap CSV in a backward-compatible way, with a continuous-Euler unbreak step and the same smoothing and neutral calibration as the blendshapes, and key it onto a chosen head bone in Blender (default `Head`, optional neck share, gain, on/off)." Research: `docs/research/keentools-facetracker.md`, idea 1.

## Clarifications

### Session 2026-10-05

Answered with the recommended default; no user was blocked. The maintainer should confirm or override.

- Q: Which columns, which units? -> A: `headRotX`, `headRotY`, `headRotZ` (radians) and, optional, `headPosX`, `headPosY`, `headPosZ` (centimeters, MediaPipe canonical scale). The names are ours on purpose: Live Link Face's `HeadYaw/Pitch/Roll` stay ignored, because their sign and unit were not verified.
- Q: Which Euler convention? -> A: intrinsic yaw (about Y, up), then pitch (about X), then roll (about Z, forward), in the head frame (X = the person's left, Y up, Z out of the face). That is `R = Ry(headRotY) * Rx(headRotX) * Rz(headRotZ)`; in Blender it is Euler order `ZXY`. A frontal neutral face is all zeros.
- Q: How is "neutral = zero" done for rotations? -> A: the mean rotation of the valid frames in the neutral window (the same window as the blendshapes) is removed as `R_neutral^T * R_frame`, so a head that rests tilted still starts at zero. With `--neutral-seconds 0` or no detection in the window the neutral is the identity.
- Q: Does the helper write the columns by default? -> A: yes, `--no-head-pose` switches them off. Old CSVs (no head columns) and Live Link Face CSVs import exactly as before.
- Q: Where does the pose go in Blender? -> A: onto one pose bone of a chosen armature (default bone `Head`, matched case-insensitively), as Quaternion or Euler keys following the bone's rotation mode, into the armature's current action (a new `<armature>_headmocap` action when it has none). Other channels of that action are untouched. Optional `Neck share` (0 to 1, default 0) gives that fraction of the rotation to a `Neck` bone and the rest to the head. A `Gain` multiplies the angle. Translation is off by default and has its own scale (default 0.01, centimeters to meters).
- Q: Which rig orientation is assumed? -> A: the armature is in the Blender default pose: the character faces -Y with +Z up, whatever the bone rolls are (they are compensated). Anything else is the user's job (rotate the armature object, not the bones).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The head follows the video (Priority: P1)

An animator runs `Video to face` on a phone video of themselves and, besides the shape keys, the character's head
bone nods, turns and tilts like the video.

**Why this priority**: it closes the documented limit that head rotation is ignored, and it is what makes a
mocap'd face look alive instead of a mask on a still head.

**Independent Test**: a pure-Python test turns known rotation matrices into the CSV columns and back; a headless
Blender test imports a CSV with a known yaw and checks where the head bone's forward axis points.

**Acceptance Scenarios**:

1. **Given** a video, **When** the helper runs, **Then** the CSV has `headRotX/Y/Z` columns next to the shapes, zero over the neutral window.
2. **Given** that CSV and an armature with a `Head` bone, **When** the user imports it, **Then** the bone is keyed and a turn to the person's left turns the character's head to its left.
3. **Given** an old CSV with no head columns, **When** it is imported, **Then** the shape keys are keyed as before and the import reports that it holds no head pose.

### User Story 2 - Control (Priority: P2)

The user can switch the head pose off, scale it (a subtle character wants 0.5), give part of it to the neck, and
pick another bone or armature.

**Independent Test**: headless Blender test with gain 0.5, neck share 0.3 and the switch off.

**Acceptance Scenarios**:

1. **Given** gain 0.5, **When** imported, **Then** the head angle is half.
2. **Given** neck share 0.3, **When** imported, **Then** the neck turns 30 % and neck plus head add up to the full rotation.
3. **Given** the switch off, **When** imported, **Then** no armature channel is created.

### Edge Cases

- Frames with no face: the last valid matrix is held, like the blendshapes.
- Euler wrap-around (a roll past 180 degrees): the angles stay continuous across frames.
- The matrix carries a scale: it is removed before the angles are read.
- The bone is missing, or the armature is missing: the import still keys the shapes and says why the head was skipped.
- A bone in Axis-Angle mode: reported, nothing keyed (Quaternion and every Euler mode are supported).
- `--crop` (a head box from BodyForge): rotation is valid, translation is relative to the crop window and not reliable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The video helper MUST request the facial transformation matrix and write `headRotX/Y/Z` (radians) after the shape columns, and `headPosX/Y/Z` (centimeters) too.
- **FR-002**: The rotation MUST be orthonormalized, expressed relative to the neutral head, converted to the documented Euler order, unbroken to be continuous across frames, and smoothed with the blendshape `--smooth`.
- **FR-003**: Missing-face frames MUST hold the last valid pose; the calibration window MUST ignore held frames.
- **FR-004**: The CSV reader MUST keep ignoring the head columns as shapes, and a reader function MUST return them (or nothing when absent), so old and new files both import.
- **FR-005**: The importer MUST key one head bone (and optionally one neck bone) from those columns with gain, neck share, on/off and optional translation, without removing other animation of the armature.
- **FR-006**: The axis mapping MUST be covered by a headless test that checks a world-space direction, not only numbers.
- **FR-007**: README and README.pt-BR MUST document the CSV columns, the import options and the removed known limit.

### Key Entities

- **Head pose columns**: six optional CSV columns, defined above.
- **Head pose settings**: on/off, armature, head bone, neck bone, neck share, gain, translation on/off, translation scale (in `scene.faceforge`).

## Success Criteria *(mandatory)*

- **SC-001**: matrix to Euler to matrix round trip within 1e-6 over a grid of angles, and a continuous sequence across a full turn.
- **SC-002**: an imported 30 degree yaw puts the head bone's forward axis 30 degrees (within 0.1) from rest, toward the character's left.
- **SC-003**: every existing test still passes, on Blender 4.4 and 5.2.
