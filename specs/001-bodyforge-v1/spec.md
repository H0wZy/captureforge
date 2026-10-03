# Feature Specification: BodyForge v1, markerless body mocap from phone video

**Feature Branch**: `001-bodyforge-v1`

**Created**: 2026-10-03

**Status**: Draft

**Input**: User description: "BodyForge v1: markerless body mocap from phone video. One phone camera, Windows with an RTX 3050, MediaPipe Pose as the default estimator, no SMPL in the default path, retarget to a Mixamo/Unity humanoid with foot lock and smoothing, body plus face from the same video as a stretch goal. First client: a Unity game that needs clips Mixamo lacks (hands-up surrender, a frisk gesture, riding a motorcycle, a dance)." Research: `docs/pt-BR/BODYFORGE-RESEARCH.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Video to a humanoid clip in one click (Priority: P1)

A game developer films a short gesture with an ordinary phone (Android or any other), picks the video file
inside Blender, and gets an animation action on a Mixamo-style humanoid armature, with no terminal work after a
one-time setup. The first seconds of the video show the person standing in a neutral pose, so the tool can
measure the body proportions, the "up" direction and the floor level.

**Why this priority**: this is the whole product. Without a video-to-motion path nothing else has input.
The "hands up, surrender" clip is the easiest of the client's four clips and proves the chain end to end.

**Independent Test**: run the video-to-landmarks step on a synthetic or licensed sample video (or load a
landmark file made by the test fixtures), solve it onto a test humanoid armature, and check that the resulting
action has one key set per frame, that both arms end above the head in the hands-up fixture, and that the rest
of the body stays within a small tolerance of the neutral pose.

**Acceptance Scenarios**:

1. **Given** a phone video of a person standing neutral for 1 to 2 seconds and then raising both hands,
   **When** the user picks the video and presses the "Video to body" button, **Then** a new action keys the
   humanoid armature at the video's real frame rate, and both wrists rise above the head in the result.
2. **Given** the helper (the external Python with the pose estimator) is not installed,
   **When** the user presses the button, **Then** the add-on stays usable and shows a clear message with the
   setup steps; nothing else in the add-on breaks.
3. **Given** a video where no person is found for some frames, **When** the solve runs, **Then** those frames
   hold the last good pose (or blend through the gap) and the report lists the gap.
4. **Given** a video with no neutral pose at the start, **When** the solve runs, **Then** the tool falls back
   to the standard proportions of the target rig, warns the user, and still produces a clip.

---

### User Story 2 - Clean-up that makes it game ready (Priority: P1)

The raw result jitters, drifts and slides on the floor. The user runs a clean-up pass: smoothing, foot lock,
in-place (no root drift), trim, loop closer for looping clips, and mirror. A quality report and a review
filmstrip tell the user whether the clip is good enough before it goes into a game.

**Why this priority**: the research says the pose estimator's depth is noisy; the value of this module is
the clean-up and the report, not a new model. A raw clip is not usable in a game, a cleaned one is.

**Independent Test**: feed a landmark fixture with injected noise and a known foot plant; after clean-up the
jitter metric drops below the target, planted feet move less than the skate limit, and the report numbers match
values computed independently in the test.

**Acceptance Scenarios**:

1. **Given** a clip with injected jitter, **When** the user runs smoothing, **Then** the jitter metric falls by
   at least the target factor and the motion peaks of a fast gesture keep at least the target fraction of
   their amplitude.
2. **Given** a clip where a foot is planted for 20 frames, **When** foot lock runs, **Then** that foot's world
   position changes by less than the skate limit during the plant, and the pelvis and leg keep valid bone lengths.
3. **Given** a looping clip (a dance cycle), **When** the user runs the loop closer, **Then** the last frame
   matches the first within a tolerance and no pop is visible at the seam.
4. **Given** any clip, **When** the user opens the report, **Then** it shows foot skate (cm/s), bone length
   drift, joint limit violations and jitter, and can write a filmstrip PNG of evenly spaced frames for review.
5. **Given** a clip, **When** the user presses "In place", **Then** the hips keep their height and lose
   horizontal drift, without changing the pose of the limbs.

---

### User Story 3 - Export that Unity accepts as a Humanoid clip (Priority: P1)

The user exports the cleaned action as an FBX with a preset that Unity reads as a Humanoid animation, using the
same avatar as the game character. The preset is validated against a Unity test project and the settings are
documented.

**Why this priority**: the client is a Unity game; a clip that does not import as a Humanoid has zero value.

**Independent Test**: export a test armature with the preset and read the FBX back headless: bone names,
hierarchy, rest pose (T-pose), scale, axes and frame rate match the documented preset. The Unity import check
is a manual step documented in the quickstart, run by the maintainer.

**Acceptance Scenarios**:

1. **Given** a cleaned action on the Mixamo-style armature, **When** the user presses "Export for Unity",
   **Then** the FBX is written with the preset (transforms applied, no leaf bones, Unity axes, deform bones only)
   and a read-back test confirms the 15 required humanoid bones and the frame rate.
2. **Given** a clip marked "in place", **When** exported, **Then** the hips path has no horizontal drift so
   the Unity import can bake the root motion into the pose.
3. **Given** the armature does not match the Mixamo-style profile, **When** the user tries to export,
   **Then** the tool names the missing or extra bones instead of exporting something that Unity will reject.

---

### User Story 4 - Hands and fingers for gestures that need them (Priority: P2)

For gestures where hands matter (the police frisk, open palms in the surrender), the user can switch on hand
tracking. Each finger gets a curl and the wrist twist is driven from the hand, so the forearm rotates correctly.

**Why this priority**: the frisk clip is meaningless with dead hands, but the body can ship without fingers,
so this story comes after the P1 chain.

**Independent Test**: fixture with an open hand and a closed fist; the solved finger rotations differ in the
expected direction and stay inside the joint limits.

**Acceptance Scenarios**:

1. **Given** a video with visible hands and hands tracking on, **When** the solve runs, **Then** each finger
   keys a curl and the forearm twist follows the palm orientation.
2. **Given** hands are lost for some frames, **When** the solve runs, **Then** fingers hold or relax smoothly to
   a rest pose instead of snapping.
3. **Given** hand tracking is off, **When** the solve runs, **Then** the fingers stay at rest and the clip is
   otherwise identical.

---

### User Story 5 - Recording guidance and the client's four clips (Priority: P2)

A short in-repo guide tells the user how to film each of the four target clips (hands up, frisk, riding a
motorcycle, dance): camera angle, frame rate, light, framing, what to wear, and where the estimator is known
to struggle. The tool shows capture warnings when the video is likely to fail (low frame rate, body cut off,
heavy motion blur).

**Why this priority**: the quality of the result is decided at the camera. This costs little and prevents
most failed takes.

**Independent Test**: the capture check runs on file metadata and landmark confidence and flags the known
bad cases in fixtures (low fps, body out of frame, low confidence).

**Acceptance Scenarios**:

1. **Given** a video at less than 30 fps or with the body partly out of frame, **When** the user picks it,
   **Then** the tool warns before spending time on the solve.
2. **Given** the motorcycle clip with the legs hidden, **When** the user reads the guide, **Then** it explains
   how to film it (seated, one leg visible) and the cleanup that helps (pose the feet by hand).

---

### User Story 6 - Body and face from the same video (Priority: P3, stretch)

The user runs the FaceForge video-to-face step on the same video and keys the face onto the same timeline as
the body, so a talking or emoting performance lands in one action set.

**Why this priority**: valuable but not needed for the four silent clips; depends on FaceForge and on face
size in a full-body frame.

**Independent Test**: with a fixture video that has a head crop, the face and body actions have the same
frame range and frame rate.

**Acceptance Scenarios**:

1. **Given** a full-body video, **When** the user asks for body and face, **Then** the head region is cropped
   from the body landmarks, the face tracker runs on the crop, and both results share one timeline.
2. **Given** the face is too small or hidden, **When** the step runs, **Then** the face part is skipped with a
   warning and the body result is unaffected.

---

### Edge Cases

- Video with several people: the tool picks the most prominent person and warns, or lets the user pick.
- Variable frame rate video (common on phones): the real timestamps are used, and the clip is resampled to a fixed rate.
- Portrait (rotated) video from a phone: orientation metadata is honored.
- Body partly outside the frame, or legs hidden by an object: low-confidence joints are held, relaxed or solved by
  limits, and the report flags them.
- Fast movement and motion blur (the dance): the estimator may lose joints; the report shows which ranges are weak.
- Front/back flip of an arm when depth is ambiguous: temporal continuity must prevent single-frame flips.
- Crouch, jump, sitting on a bike: heuristic foot contact can fail; the user can switch foot lock off per foot or per range.
- Very long videos: the helper reports progress and the user can cancel; the add-on never blocks forever.
- The user's armature uses different bone names or a different roll: the tool validates the profile first and
  refuses with a precise list.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST turn a video file recorded by any phone or webcam into an animation action on a
  Mixamo/Unity-style humanoid armature, without requiring an iPhone, depth sensor or LiDAR.
- **FR-002**: The system MUST work from one camera.
- **FR-003**: The default estimator MUST be MediaPipe Pose (and Hands when enabled), run in an external helper
  process; no SMPL, SMPL-X, AMASS or other non-commercial weights may be required by the default path.
- **FR-004**: The add-on MUST keep working, with a clear setup message, when the helper is not installed.
- **FR-005**: The helper MUST write a documented landmark file (pose, optional hands, confidence per point, real
  frame timestamps) that the add-on reads; the add-on never imports the estimator.
- **FR-006**: The system MUST measure bone lengths, the up direction and the floor level from a neutral pose at
  the start of the clip, and MUST fall back to the rig's standard proportions with a warning when there is none.
- **FR-007**: The solver MUST compute local bone rotations for the fixed Mixamo/Unity humanoid profile (the 15
  required humanoid bones plus the optional spine, neck, toe and finger bones) and the hips translation.
- **FR-008**: The system MUST offer smoothing with a causal mode for preview and a zero-phase mode for the final
  result, applied to rotations in a way that avoids Euler artifacts.
- **FR-009**: The system MUST offer heuristic foot contact detection and a foot lock that removes sliding on
  planted feet, per foot, with the option to turn it off.
- **FR-010**: The system MUST offer in-place, trim, loop closer and mirror operations on the resulting action.
- **FR-011**: The system MUST produce a quality report (foot skate in cm/s, bone length drift, joint limit
  violations, jitter, low-confidence ranges) as text and JSON, and a filmstrip PNG for visual review.
- **FR-012**: The system MUST export an FBX using a documented Unity Humanoid preset and MUST refuse, listing the
  problems, when the armature does not match the profile.
- **FR-013**: Hands tracking MUST be optional; when on, each finger gets a curl and the forearm twist follows the
  palm; when off, fingers stay at rest.
- **FR-014**: The system SHOULD warn before solving when the capture is likely to fail (low frame rate, body out of
  frame, low confidence, several people).
- **FR-015**: The system MUST expose its core steps as pure functions that take explicit data, so every step is
  testable headless and usable by scripts and agents, with operators as thin wrappers.
- **FR-016**: The system SHOULD allow the face of the same video to be keyed on the same timeline using FaceForge
  (stretch goal, user story 6).
- **FR-017**: The repository MUST NOT contain captures of real people; all fixtures are synthetic or explicitly
  licensed, and the docs MUST repeat the responsible-use policy (no capture of a real person without consent).
- **FR-018**: User-facing docs (README sections and the recording guide) MUST exist in English and pt-BR.
- **FR-019**: Long operations MUST report progress and allow cancel, or MUST be bounded by a timeout with a clear error.

### Key Entities

- **Landmark file**: per frame, the body points (image and metric-like coordinates), optional hand points, a
  confidence per point, the timestamp, plus the video's real frame rate and orientation. The only interface
  between the helper and the add-on.
- **Body profile**: the fixed map from the estimator's points to the humanoid bones, with rest orientations and
  joint limits (the Mixamo/Unity Humanoid profile in v1).
- **Calibration**: the measurements taken from the neutral pose: bone lengths, up vector, floor level, facing direction.
- **Motion clip**: the action produced by the solver (rotations per bone plus hips translation) with its frame
  range and frame rate.
- **Quality report**: the metrics and the review filmstrip attached to a clip.
- **Export preset**: the documented set of FBX options that Unity reads as a Humanoid animation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with the helper installed goes from a video file to an animated humanoid in Blender in
  under 5 minutes of hands-on time for a 10-second clip (excluding the one-time setup).
- **SC-002**: The one-time setup (helper environment and model download) can be completed by a user who has never
  used a terminal, by following the in-add-on instructions, in under 15 minutes.
- **SC-003**: The client's four clips (hands up, frisk, motorcycle, dance) are each filmed and delivered into the
  game as Unity Humanoid animations that the maintainer rates acceptable for the game, with the hands-up clip
  and the frisk clip required for v1 and the motorcycle and dance clips best effort with documented limits.
- **SC-004**: After clean-up, planted feet slide less than 2 cm/s on the synthetic foot-plant fixtures, and
  injected jitter is reduced by at least 70 percent while fast-gesture peaks keep at least 85 percent of
  their amplitude.
- **SC-005**: Exported FBX files import in a Unity project as Humanoid clips with the character's own avatar,
  with zero import warnings in the maintainer's check.
- **SC-006**: A 10-second 30 fps clip is processed end to end in under 3 minutes on a Windows laptop with an
  RTX 3050 (4 to 6 GB), and never needs more than that GPU's memory.
- **SC-007**: Every core function has a headless test that was seen failing first, and CI is green on Blender
  4.4 and 5.2.
- **SC-008**: No file in the repository contains personal data or captures of real people, and no default-path
  dependency or weight has a non-commercial license.

## Assumptions

- Target hardware for the reference measurements: Windows 11, an RTX 3050 laptop GPU, one Android phone. The
  estimator may run on CPU or GPU; GPU is not required.
- The phone is used as a plain video source: either a recorded file or Iriun Webcam (one device) for a later
  live mode. Live preview is out of scope for v1.
- Mixamo/Unity Humanoid is the only target profile in v1 (T-pose rest, the 15 required bones). Other rigs (Rigify,
  UE5) and generic retargeting are out of scope; interoperating with the community Retarget extension is a v2 idea.
- The four client clips are mostly in place (surrender, frisk, parked motorcycle, dance), so large world motion and
  camera movement are out of scope; the camera is fixed (tripod or a stable surface).
- The model files are downloaded by the user on explicit action, never committed or bundled; the destination is shown.
- One person per clip is the supported case; several people only trigger a warning.
- Out of scope for v1: SMPL-based estimators (GVHMR, WHAM and similar) as the default, any multi-camera pipeline,
  cloud processing, live capture, retargeting to arbitrary rigs, finger-accurate hand pose beyond curl and twist.
- FaceForge exists and exposes video-to-face; the face stretch goal reuses it and its helper pattern.
- A Unity test project for the import check is the maintainer's local setup and is not part of the repository.
