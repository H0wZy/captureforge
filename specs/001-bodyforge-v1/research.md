# Research: BodyForge v1

Phase 0 decisions. Source survey: `docs/pt-BR/BODYFORGE-RESEARCH.md` (refs `[Sn]` point to its section 8). Items the
survey could not verify are marked **(to verify)** and have a task to verify them before release.

## D1. Estimator: MediaPipe Pose (and Hands) in the shared helper venv

- **Decision**: MediaPipe Pose Landmarker (heavy model by default, lite as automatic fallback) plus the optional Hand
  Landmarker, run in a subprocess. Video mode (tracking) is used so the points are temporally coherent.
- **Rationale**: Apache-2.0 [S19], installable with `pip` on Windows, already the FaceForge pattern, gives 33 image
  points and 33 "world" points in meters with the origin at the hips [S15], plus heel and toe (needed for the foot) and
  thumb, index and pinky (needed for the wrist twist).
- **Alternatives**: SMPL-based video models (GVHMR, WHAM, TRAM) are better but need SMPL, whose license forbids
  commercial use [S11][S12]; rejected for the default path (Constitution V). SAM 3D Body + MHR is a promising SMPL-free
  v2 option but is image-based and heavy on a 4 to 6 GB GPU [S32][S35]. RTMW (rtmlib) is a v2 quality pack [S20][S22].
- **Open item (to verify)**: license text on the pose model card; record it in `docs/` and pin the model hash.

## D2. Rotations from positions: swing from segment direction, twist from a second vector

- **Decision**: for each bone, the swing is the rotation that takes the rest direction to the observed segment
  direction; the twist is fixed by a second vector: palm plane (wrist, index, pinky) for the forearm, heel and toe for
  the foot, shoulder line and hip line for the torso and spine distribution. Rotations are computed in world space and
  converted to the target bone's local rest frame, so no constraints are needed.
- **Rationale**: MediaPipe gives positions only [S15]. The direct, constraint-free computation is deterministic and
  headless-testable, which Constitution III needs; constraint-and-bake retargeting ([S58]) is not testable in plain Python.
- **Alternatives**: Copy Rotation constraints plus bake (the common recipe [S58]); rejected because it needs a
  Blender context and hides the math. The community Retarget extension [S54] is not reimplemented; interop is v2.
- **Risk**: depth noise makes swing around the camera axis weak; mitigated by D4 and D5.

## D3. Calibration from a neutral pose

- **Decision**: the first 1 to 2 s (configurable) are averaged to get the bone lengths, the up vector (from the
  hips-to-shoulders and hips-to-feet directions with gravity assumed along the average standing axis), the facing
  direction and the floor level (minimum of the heel and toe heights). If no stable neutral window exists, fall back
  to the rig's own proportions and warn.
- **Rationale**: the survey proposes exactly this for MediaPipe, which has no floor or global translation [S15].
- **Alternatives**: a separate calibration photo (extra step, rejected for v1); learned gravity (needs another model).

## D4. Depth ambiguity and jitter mitigations

- **Decision**: fixed bone lengths from calibration (re-project each segment to its length), joint limits from the
  profile (elbow and knee cannot bend backwards), per-point weight from `visibility`, hold or blend through low
  confidence, and a temporal-continuity guard that rejects single-frame front/back flips.
- **Rationale**: depth is the weak axis of MediaPipe [S16]; these steps are cheap and testable on synthetic data.
- **Alternatives**: 2D lift with MotionBERT [S25] (extra model and training-data license questions); deferred to v2.

## D5. Filtering

- **Decision**: One Euro filter (causal, quaternion-aware, SLERP) for the preview and a zero-phase 4th-order
  Butterworth (a 2nd-order section run forward and backward, numpy only, about 6 Hz on rotations and 3 Hz on hips
  translation) for the final clip. Filter quaternions, never Euler angles, with sign-continuity enforced first.
- **Rationale**: [S59] for One Euro, [S66] for the Butterworth practice, [S35] for quaternion filtering. No scipy is
  needed, which keeps the add-on at bpy plus numpy (Constitution VIII).
- **Alternatives**: scipy `filtfilt` (not bundled); Blender's Gaussian Smooth F-curve modifier [S60] (not headless-testable
  here and not available on 4.4).

## D6. Foot contact and foot lock

- **Decision**: a foot is planted when its vertical speed and its height above the calibrated floor are both under
  thresholds for a minimum number of frames (with hysteresis). During a plant the foot target is frozen in world space
  and a two-bone leg solve adjusts hips height and leg rotations to reach it, within bone lengths and joint limits.
  Each foot and each frame range can switch the lock off.
- **Rationale**: heuristic contact is the classical route [S64][S65] and is the only option without an SMPL-trained
  contact predictor [S4][S7].
- **Known failure modes (documented, not solved)**: jumps, deep crouches, a seated rider; the guide tells users to
  turn the lock off or pose the feet by hand for the motorcycle clip.

## D7. Unity export preset

- **Decision**: `bpy.ops.export_scene.fbx` with Apply Transform on, Add Leaf Bones off, Forward -Z, Up Y, primary bone
  axis Y and secondary X, Only Deform Bones on, baked animation with simplify off, at the clip's frame rate. The
  armature must match the Mixamo/Unity profile (15 required bones, T-pose rest [S61]). A read-back test imports the
  FBX headless and checks names, hierarchy, rest pose and frame rate. The Unity side check is manual.
- **Rationale**: [S81] for the settings, [S61] for the Humanoid requirements, [S62][S63] for root motion; the four client
  clips are in place, so the hips path has no horizontal drift and Unity can bake it into the pose.
- **Alternatives**: glTF (not accepted by Unity's Humanoid pipeline as-is); BVH (loses the rig and skin).

## D8. Helper install and models

- **Decision**: an "Install helper" operator runs `helpers/setup_env.py`, which creates a venv in the user's add-on
  data directory, installs `mediapipe` and `opencv-python`, and downloads the model files only after the user clicks
  and sees the URLs. The venv is shared with FaceForge through `captureforge/prefs.py`. A manual-setup text remains as fallback.
- **Rationale**: Constitution Technical Constraints (helper venv created by the extension, no admin rights, network
  only on explicit action); spec SC-002 (non-terminal user).
- **Alternatives**: Blender wheels in the manifest (`wheels = [...]` [S69]); rejected because MediaPipe's native wheels
  and size make the extension heavy and tie it to Blender's Python version (3.13 on 5.1 and later [S60b]).

## D9. Landmark interface

- **Decision**: a single `landmarks.npz` with a versioned schema ([contracts/landmarks-file.md](contracts/landmarks-file.md)).
  The add-on never imports MediaPipe; the helper never imports `bpy`.
- **Rationale**: Constitution II; the same file feeds the tests (synthetic files) and a future RTMW or Pose2Sim importer.
- **Alternatives**: JSON (large for 60 s at 30 fps with 75 points, slow to parse); a socket (needed only for live, out of scope).

## D10. Body plus face from one video (stretch)

- **Decision**: the pose helper also writes a per-frame head box (from nose, ears, eyes) into the landmark file; the
  FaceForge video helper gains an optional `--crop` argument that reads those boxes, runs on the crop and keys on the same
  timeline. If the face is too small, the face part is skipped with a warning.
- **Rationale**: Holistic would work but gives a small face in a full-body frame [S18]; cropping reuses code that exists.
- **Alternatives**: Holistic Landmarker (one pass, lower face quality); a second video of the face (extra work for the user).

## D11. Testing without real people

- **Decision**: fixtures generate synthetic skeletons (parametric motions) and write them through the same landmark
  schema, plus a tiny synthetic video (moving stick figure) only for a smoke test of the helper's argument handling
  when MediaPipe is not installed (skipped in CI if the package is absent).
- **Rationale**: Constitution VI forbids real captures in the repo and III needs headless tests.
- **Alternatives**: licensed sample videos (license review per file, large); kept as an optional manual acceptance.

## D12. Performance on the reference machine

- **Decision**: measure on the RTX 3050 laptop at the end of the helper task and record the numbers in the quickstart.
  Treat SC-006 as a target, not a guarantee, until measured. Nothing in the survey gives numbers for 4 to 6 GB [S1-S9],
  so no claim is made here. **(to verify by measurement)**.

## Open verification items

1. MediaPipe model card license text (D1).
2. Real speed of the pose helper on the reference laptop (D12).
3. Behavior of the Unity Humanoid import with the preset on the maintainer's character avatar (D7).
4. Whether the Hand Landmarker is good enough for frisk gestures when hands overlap the torso (spec User Story 4).
