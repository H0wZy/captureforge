# Tasks: FaceForge weights fitted to the character

**Input**: `specs/003-character-fitted-weights/` (spec.md, plan.md)

**Tests**: REQUIRED (Constitution III): each test task comes first and MUST be seen failing before its implementation task.

**Format**: `[ID] [P?] [Story] Description`; `[P]` = different files, no dependency on an unfinished task. Paths are relative to the repository root.

## Phase 0: Gate (before any UI)

- [x] T001 Spike (throwaway script, not committed, real clip not committed): with the helper venv, dump landmarks of a real clip, build the basis for two or three stylized heads of different styles, solve, and write down the landmark residual of generic versus fitted weights and a side-by-side look at the keyed result. Go/no-go for SC-004; tune the starting `l1`, `l2` and the alignment subset indices here. Record the numbers in `specs/003-character-fitted-weights/research.md`.
  **Result (2026-10-05): no-go on the synthetic proxy** (no real footage in the measuring environment). The residual
  dropped 20 to 50 % (circular: the solver minimizes it), but the fitted weights were further from the truth than the
  generic scores on all three characters (weight RMS 0.12 to 0.29 against 0.12 to 0.13). Everything below is on hold.
  Real footage (same day): also no-go, generic wins 7 of 15 labelled windows against at most 2 to 8 for the fit, and
  blinks get weaker with more leakage; numbers in `research.md`.

## On hold after T001 (do not start without a new go decision)

## Phase 1: Landmark file (US3, helper)

- [ ] T002 [P] [US3] Test in `tests/test_video_to_csv.py`: the landmark writer's arrays, shapes, NaN and `valid` for faceless frames, `interface` version, round trip through `numpy.load`
- [ ] T003 [US3] Implement `--landmarks PATH` in `captureforge/face/helpers/video_to_csv.py` (landmarks for all frames, raw scores, `savez_compressed`); `video.run(..., landmarks=None)` passes it; `.gitignore` gets `*.landmarks.npz`

## Phase 2: Pure math (US1, US2)

- [ ] T004 [P] [US1] Tests in `tests/test_fit_solve.py`: `load_landmarks` (valid file, wrong interface version, wrong shapes), `to_frame` coordinates and normalization by the eye distance
- [ ] T005 [P] [US1] Tests: `align` (Umeyama) is invariant to a random rotation, translation and scale of the frame, and a synthetic jaw opening leaves the subset's alignment unchanged
- [ ] T006 [P] [US1] Tests: `solve` recovers known weights from `A W = B` (noise-free exact, noisy within 0.05 RMS), respects 0..1, a larger `l1` gives sparser weights, `l2` pulls toward the generic weights, unobservable keys keep the generic score, 3000 x 52 runs under the SC-002 budget with no per-frame Python loop
- [ ] T007 [US1] Implement `captureforge/face/fitsolve.py`: `load_landmarks`, `to_frame`, `neutral_face`, `align`, `residuals`, `observable`, `solve` (FISTA), `fit_report_numbers`
- [ ] T008 [US2] Tests then code: `Fit strength` mixing (0 equals generic, 1 equals fit) and `Expression gain` scaling the residual, in `fitsolve.py`

## Phase 3: Blender side (US1)

- [ ] T009 [US1] Tests in `tests/run_tests.py`: `fitweights.character_basis` on the procedural head with fabricated neutral landmarks: a key that moves the surface under landmark `i` by a known vector gives exactly that column (barycentric interpolation), symmetric-only keys fall back to one column, a ray that misses uses the nearest point
- [ ] T010 [US1] Implement `captureforge/face/fitweights.py`: `character_basis` (reusing `autofit.front_camera`, `render_front`, `video.landmarks`, BVH ray cast with face index), `fit_to_character` (basis plus frames plus solve plus `mocap.apply_mocap`), `format_report`
- [ ] T011 [US1] End-to-end test in `tests/run_tests.py`: fabricate frames from known weights of the target's keys, run `fit_to_character` from a `.npz`, check the keyed curves against the known weights and the residual against a cross-talking generic estimate (SC-001); second run with other options starts no subprocess (US3)
- [ ] T012 [US1] Optional real-MediaPipe test (skipped without `FACEFORGE_PYTHON` / `FACEFORGE_MODEL`): render the procedural head, find its landmarks, fit a synthetic clip

## Phase 4: Panel, operators, docs

- [ ] T013 [US2] Tests then code: `scene.faceforge` settings (`fit_landmarks`, `keep_landmarks`, `fit_strength`, `fit_gain`, `fit_sparsity`, `fit_prior`), `faceforge.fit_weights`, `faceforge.delete_landmarks`, box `4d. Fit to character` in `captureforge/face/ui.py` and `ops.py`; the fit off changes nothing (SC-003: the existing suite passes unchanged)
- [ ] T014 [P] README.md and README.pt-BR.md: workflow, options, limits (absolute matching, no manual landmarks, face data note), SC-004 result from T001
- [ ] T015 [P] CI: `tests/test_fit_*.py` joins the unit stage numpy loop in `.github/workflows/ci.yml`

## Phase 5: Checks

- [ ] T016 Run the pure tests, the Blender suite on 5.2 (CI on 4.4), the extension validation, and one real clip with the fit on and off; record the final residual numbers in `research.md`

## Dependencies

T001 gates everything. T002 to T003 and T004 to T008 are independent of each other (different files). T009 needs T007; T010 needs T009; T011 needs T010 and T003; T013 needs T010; T014 and T015 can run any time after T010. Suggested order: T001, then T004 to T008 and T002 to T003 in parallel, then T009 to T013, then docs and checks.

## Estimate

About 700 lines of code, 600 of tests, and the docs: a full working day. Not started in this branch on purpose; the gate T001 decides whether to start at all.
