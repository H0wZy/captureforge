---

description: "Task list for BodyForge v1"
---

# Tasks: BodyForge v1, markerless body mocap from phone video

**Input**: Design documents from `/specs/001-bodyforge-v1/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: REQUIRED here (Constitution III): every implementation task is preceded by a test task, and the test MUST be
seen failing before the implementation exists. Pure tests run with `python tests/test_body_*.py`; Blender tests run with
`blender --background --factory-startup --python tests/run_body_tests.py`.

**Organization**: grouped by user story (US1 to US6, see spec.md) so each story can be implemented and tested alone.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 to US6, mapped to the spec's user stories
- File paths are relative to the repository root

## Phase 1: Setup (shared infrastructure)

**Purpose**: package skeleton, shared preferences and CI wiring.

- [x] T001 Create the `captureforge/body/` package skeleton (`__init__.py` with `register()`/`unregister()`, empty `helpers/`) and call it from `captureforge/__init__.py`, keeping the add-on loadable with an empty module
- [x] T002 [P] Move the single `AddonPreferences` class to `captureforge/prefs.py` (face property names unchanged, add `pose_model` and `hand_model`), point `captureforge/face/ui.py` at it, and keep the existing face tests green in `tests/run_tests.py`
- [x] T003 [P] Wire CI in `.github/workflows/ci.yml`: install numpy in the unit stage (dev-only), run `tests/test_body_*.py` there, and add a `tests/run_body_tests.py` step to the Blender 4.4 and 5.2 matrix
- [x] T004 [P] Write `tests/fixtures_body.py`: synthetic skeleton generators that write the landmark schema (hands up, planted foot, injected jitter, loopable dance cycle, open and closed hand), no real captures

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the landmark interface and the body profile, used by every story.

**CRITICAL**: no user story starts before this phase is done.

- [x] T005 [P] Write failing tests for the landmark reader in `tests/test_body_landmarks.py` (required keys, bad version, shape mismatch, NaN gap hold, variable frame rate resample, keep source rate)
- [x] T006 Implement `captureforge/body/landmarks.py` (read and validate `landmarks.npz`, hold gaps and report them, resample to the scene or source rate) per `contracts/landmarks-file.md`
- [x] T007 [P] Write failing tests for the body profile in `tests/test_body_solve.py` (name normalising with and without `mixamorig:`, the 15 required bones, validate returns missing and extra, landmark map covers every required bone)
- [x] T008 Implement `captureforge/body/profile.py` (bone list with parents, landmark map, twist references, joint limits, `normalise`, `validate`) per `data-model.md`

**Checkpoint**: a synthetic landmark file loads, resamples and validates; the profile is queryable.

---

## Phase 3: User Story 1 - Video to a humanoid clip in one click (Priority: P1) MVP

**Goal**: pick a video, get an action on a Mixamo-style armature; clear message when the helper is missing.

**Independent Test**: synthetic hands-up landmark file solved onto the reference armature gives keys per frame, wrists above the head, the rest near neutral; with no helper the panel shows setup text.

### Tests for User Story 1 (write first, see them fail)

- [x] T009 [P] [US1] Write failing tests for calibration in `tests/test_body_solve.py` (bone lengths, up vector, facing, floor from a neutral window, rig-default fallback with a warning)
- [x] T010 [P] [US1] Write failing tests for the solver in `tests/test_body_solve.py` (swing from segment direction, twist from the second vector, hips height and sway, world-to-Blender axes, sign-continuous quaternions, hands-up fixture)
- [x] T011 [P] [US1] Write failing tests for the helper CLI in `tests/test_body_helper.py` (argument parser works without mediapipe, exit code 3 and the `missing package` message, `setup_env.py --dry-run` plan text, landmark writer round-trips through the reader)
- [x] T012 [P] [US1] Write failing Blender tests in `tests/run_body_tests.py` (reference armature has the profile bones in T-pose, profile validation lists missing and extra bones, applying a clip writes one key set per frame)

### Implementation for User Story 1

- [x] T013 [P] [US1] Implement `captureforge/body/calibrate.py` (neutral-window calibration and fallback) so T009 passes
- [x] T014 [US1] Implement `captureforge/body/solve.py` (positions to local rotations in the target rest frame, hips height and sway, bone-length re-projection, joint-limit clamp, low-confidence hold, horizontal hips travel dropped unless the keep-travel option is set) so T010 passes
- [x] T015 [P] [US1] Implement `captureforge/body/helpers/pose_to_landmarks.py` (MediaPipe Pose in video mode, real timestamps, rotation metadata, axis conversion, progress lines, `people_seen` recorded in `meta`, write at the end) per `contracts/helper-cli.md`
- [x] T016 [P] [US1] Implement `captureforge/body/helpers/setup_env.py` (plan text, `--yes` creates the shared venv, installs packages, downloads the models into the venv folder after consent, prints the paths)
- [x] T017 [US1] Implement `captureforge/body/video.py` (subprocess runner, `check_setup`, progress callback, cancel, setup text, `ValueError` with the helper's last lines) mirroring `captureforge/face/video.py`
- [x] T018 [P] [US1] Implement `captureforge/body/rigtools.py` (create the reference armature, validate a user armature against the profile) so the T012 rig tests pass
- [x] T019 [US1] Implement `captureforge/body/apply.py` (write the solved clip as an action at the scene rate, store the raw clip on the action, read it back) so the T012 apply test passes
- [x] T020 [US1] Implement thin operators in `captureforge/body/ops.py` (`bodyforge.install_helper`, `check_helper`, `create_reference`, `video_to_body`) calling only core functions; the helper runs are modal with a progress readout and Esc to cancel (FR-019)
- [x] T021 [US1] Implement `captureforge/body/ui.py` (the `Scene.bodyforge` PropertyGroup and the BodyForge panel in the shared CaptureForge tab, setup message when the helper is missing) and register it in `captureforge/body/__init__.py`

**Checkpoint**: video (or a synthetic landmark file) to an animated armature; MVP of the module.

---

## Phase 4: User Story 2 - Clean-up that makes it game ready (Priority: P1)

**Goal**: smoothing, foot lock, in place, trim, loop closer, mirror, quality report and filmstrip.

**Independent Test**: noisy fixture gets under the jitter target while keeping peaks; the planted-foot fixture slides under 2 cm/s; the loop seam matches; the report numbers equal values computed independently in the test.

### Tests for User Story 2 (write first, see them fail)

- [x] T022 [P] [US2] Write failing tests for filters in `tests/test_body_cleanup.py` (One Euro causal behavior, zero-phase Butterworth has no lag and removes injected jitter, quaternion sign continuity, peak amplitude kept)
- [x] T023 [P] [US2] Write failing tests for foot contact and lock in `tests/test_body_cleanup.py` (planted frames detected with hysteresis, skate under the limit, bone lengths kept, per-foot and per-range switch off)
- [x] T024 [P] [US2] Write failing tests for clip operations in `tests/test_body_cleanup.py` (in place keeps height and removes drift, trim range, loop closer matches first and last frame, mirror swaps left and right correctly)
- [x] T025 [P] [US2] Write failing tests for the report in `tests/test_body_cleanup.py` (skate in cm/s, bone drift, limit violations, jitter, low-confidence ranges, json round-trip) and for the filmstrip in `tests/run_body_tests.py`

### Implementation for User Story 2

- [x] T026 [P] [US2] Implement `captureforge/body/filters.py` (One Euro, 2nd-order Butterworth run forward and backward with numpy only, quaternion smoothing) so T022 passes
- [x] T027 [P] [US2] Implement `captureforge/body/contact.py` (contact detection with thresholds and minimum duration, foot lock with a two-bone leg solve inside limits) so T023 passes
- [x] T028 [P] [US2] Implement `captureforge/body/clipops.py` (in place, trim, loop closer, mirror on a `MotionClip`) so T024 passes
- [x] T029 [P] [US2] Implement `captureforge/body/report.py` (metrics, `report.json`, text summary) so the T025 pure tests pass
- [x] T030 [US2] Extend `captureforge/body/apply.py` with re-writing the action from an edited clip and the filmstrip render (a grid of evenly spaced frames to PNG) so the T025 Blender test passes
- [x] T031 [US2] Add operators `bodyforge.cleanup`, `report`, `in_place`, `trim`, `loop`, `mirror` to `captureforge/body/ops.py` and the matching controls and report readout to `captureforge/body/ui.py`

**Checkpoint**: a raw clip can be turned into a clean, loopable, reviewed clip.

---

## Phase 5: User Story 3 - Export that Unity accepts as a Humanoid clip (Priority: P1)

**Goal**: FBX export with the documented preset and a refusal with a bone list for a wrong armature.

**Independent Test**: export the reference armature with a synthetic action, import the FBX back headless, and check names, hierarchy, rest pose, frame rate and hips track.

### Tests for User Story 3 (write first, see them fail)

- [x] T032 [P] [US3] Write failing Blender tests in `tests/run_body_tests.py` for the export (preset options applied, FBX read-back matches bones, rest pose, frame range and rate, hips height track within tolerance, refusal message lists missing and extra bones, in-place clip has no horizontal drift)

### Implementation for User Story 3

- [x] T033 [US3] Implement `captureforge/body/export.py` (profile check, FBX preset per `contracts/unity-export-preset.md`, read-back helper used by the test) so T032 passes
- [x] T034 [US3] Add `bodyforge.export_unity` to `captureforge/body/ops.py` and the export path and button to `captureforge/body/ui.py`
- [x] T035 [US3] Document the manual Unity Humanoid import check (steps and expected result) in `specs/001-bodyforge-v1/quickstart.md` and record the maintainer's result and the character's avatar setup in the PR description

**Checkpoint**: a cleaned clip imports in Unity as a Humanoid clip.

---

## Phase 6: User Story 4 - Hands and fingers for gestures that need them (Priority: P2)

**Goal**: optional hand tracking gives finger curl and a forearm twist that follows the palm.

**Independent Test**: open-hand and fist fixtures give different finger rotations inside limits; hands lost for a few frames relax smoothly; hands off leaves fingers at rest.

### Tests for User Story 4 (write first, see them fail)

- [x] T036 [P] [US4] Write failing tests in `tests/test_body_solve.py` for fingers (open versus fist curl, forearm twist from the palm plane, hold and relax through lost frames, hands-off leaves rest)
- [x] T037 [P] [US4] Write failing test in `tests/test_body_helper.py` for the optional `--hands-model` argument and the `hands_world` and `hands_vis` fields in the landmark writer

### Implementation for User Story 4

- [x] T038 [US4] Add finger curl and palm-driven forearm twist to `captureforge/body/solve.py` and the finger bones to `captureforge/body/profile.py` so T036 passes
- [x] T039 [P] [US4] Add MediaPipe Hands to `captureforge/body/helpers/pose_to_landmarks.py` (left and right order, NaN when absent) so T037 passes
- [x] T040 [US4] Add the `use_hands` option to `captureforge/body/ui.py` and `captureforge/body/ops.py`, and the hand model download to `captureforge/body/helpers/setup_env.py`

**Checkpoint**: the frisk clip can keep its hands.

---

## Phase 7: User Story 5 - Recording guidance and the client's four clips (Priority: P2)

**Goal**: a guide for filming the four clips and warnings before a doomed solve.

**Independent Test**: capture check flags low frame rate, body out of frame, low confidence and several people on fixtures.

### Tests for User Story 5 (write first, see them fail)

- [x] T041 [P] [US5] Write failing tests for the capture check in `tests/test_body_landmarks.py` (fps under 30, body out of frame, low mean visibility, several people from `meta`)

### Implementation for User Story 5

- [x] T042 [US5] Implement the capture check in `captureforge/body/landmarks.py` and show its warnings in the panel and before the solve in `captureforge/body/ops.py` so T041 passes
- [x] T043 [P] [US5] Write the recording guide `docs/BODYFORGE-RECORDING.md` (angle, fps, light, framing, clothing, per-clip notes for hands up, frisk, motorcycle seated with one leg visible, dance at 60 fps, known limits, responsible-use note linking POLICY.md)
- [x] T044 [P] [US5] Write the pt-BR translation `docs/pt-BR/BODYFORGE-RECORDING.md`

**Checkpoint**: a user can film the four clips and is warned about bad takes.

---

## Phase 8: User Story 6 - Body and face from the same video (Priority: P3, stretch)

**Goal**: key the face from the same video on the same timeline as the body.

**Independent Test**: with a head-box fixture, the face and body actions share frame range and rate; a too-small face is skipped with a warning.

### Tests for User Story 6 (write first, see them fail)

- [x] T045 [P] [US6] Write failing tests in `tests/test_body_helper.py` (head box in the landmark writer, the face helper's `--crop` argument reads the boxes) and in `tests/run_body_tests.py` (shared timeline, skip-with-warning for a tiny face)

### Implementation for User Story 6

- [x] T046 [US6] Write the head box from the pose landmarks in `captureforge/body/helpers/pose_to_landmarks.py`
- [x] T047 [US6] Add the optional `--crop` argument to `captureforge/face/helpers/video_to_csv.py` and `captureforge/face/video.py` without changing the default FaceForge behavior (existing face tests stay green)
- [x] T048 [US6] Add `bodyforge.video_to_body_and_face` to `captureforge/body/ops.py` and the option to `captureforge/body/ui.py` so T045 passes

**Checkpoint**: body and face from one video.

---

## Phase 9: Polish and cross-cutting concerns

**Purpose**: docs, release and verification of the open research items.

- [x] T049 [P] Add the BodyForge section to `README.md` and `README.pt-BR.md` in the same change, flipping BodyForge from roadmap to available once released, and link POLICY.md and the recording guide
- [x] T050 [P] Update `captureforge/blender_manifest.toml` (tagline, permissions text for files and network, version 0.2.0 at release) and check `blender --command extension validate` on 4.4 and 5.2
- [x] T051 Verify the MediaPipe pose and hand model licenses on their model cards and record the license, URL and sha256 in `docs/` (research open item 1); the model URLs in `setup_env.py` use those hashes. Done 2026-10-04: all weights are Apache-2.0, see `docs/pt-BR/BODYFORGE-T051-LICENCA.md`.
- [x] T052 Measure the 10 s clip from video to animated rig on the reference RTX 3050 laptop and record the time in `specs/001-bodyforge-v1/quickstart.md` (SC-006, research open item 2)
- [ ] T053 (needs the maintainer's real footage) Run the four client clips through the pipeline, record per-clip results and limits in the PR description (SC-003), and confirm in Unity that the clips play on the game's avatar
- [x] T054 Run the private-data grep (local paths, personal names, e-mails, private project names) over the whole diff and fix any hit (Constitution VI, SC-008)
- [x] T055 Run `quickstart.md` end to end on a clean Blender 5.2 profile and fix any step that fails

---

## Dependencies and execution order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies; T002 to T004 can run in parallel after T001.
- **Foundational (Phase 2)**: depends on Setup; blocks every story. Within it, each test task precedes its implementation.
- **US1 (Phase 3)**: depends on Foundational. MVP. US2 and US3 depend on the US1 solver and `apply.py`.
- **US2 (Phase 4)**: depends on US1 (a solved clip to clean). **US3 (Phase 5)**: depends on US1 (an action to export) and benefits from US2 (in place, loop).
- **US4 (Phase 6)**: depends on US1; independent of US2 and US3.
- **US5 (Phase 7)**: capture check depends on Foundational (`landmarks.py`); docs are independent.
- **US6 (Phase 8)**: depends on US1 and on the existing FaceForge video helper.
- **Polish (Phase 9)**: T049 to T050 after the stories they describe; T051 before the first model URL ships; T052 to T055 last.

### Within each story

Tests first and seen failing; pure modules before Blender glue; core before operators; operators before panel.

### Parallel opportunities

- Setup: T002, T003, T004.
- US1 tests: T009 to T012 together; then T013, T015, T016, T018 together (different files).
- US2: T022 to T025 together; then T026 to T029 together.
- US4 tests T036 and T037; US5 docs T043 and T044; Polish T049 and T050.
- Tasks that edit `tests/test_body_solve.py`, `tests/test_body_cleanup.py` or `tests/run_body_tests.py` are not marked [P] against each other unless they are in different phases or files.

## Parallel example: User Story 1

```text
Task: "Write failing tests for calibration in tests/test_body_solve.py"        # T009
Task: "Write failing tests for the helper CLI in tests/test_body_helper.py"    # T011
Task: "Write failing Blender tests in tests/run_body_tests.py"                 # T012
Task: "Implement captureforge/body/helpers/pose_to_landmarks.py"               # T015
Task: "Implement captureforge/body/helpers/setup_env.py"                       # T016
```

## Implementation strategy

### MVP first (US1 only)

1. Phase 1 and 2 (T001 to T008). 2. US1 (T009 to T021). 3. Stop and validate with the hands-up fixture and, when a
video exists, the hands-up clip. 4. Then US2 and US3 (both P1) to reach a usable Unity clip; this is the v1 floor.

### Incremental delivery

US1 then US2 then US3 (usable clips), then US4 (hands, the frisk clip), then US5 (guide and warnings), then US6 (stretch).
The hands-up and frisk clips are required for v1 (SC-003); the motorcycle and dance clips are best effort.

## Notes

- [P] tasks touch different files and have no dependency on unfinished work.
- Every task issue gets the `task` and `module:body` labels, Module Body on the board, and is a sub-issue of epic #1.
- Commit after each task or logical group with the Co-Authored-By trailer; PR closes #1.
- Avoid: vague tasks, same-file conflicts, a story that needs another story's unfinished code.
