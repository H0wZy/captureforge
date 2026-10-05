# Tasks: FaceForge per-actor calibration of the face scores

**Input**: `specs/005-actor-calibration/` (spec.md, plan.md)

**Tests**: REQUIRED (Constitution III): each test task comes first and MUST be seen failing before its implementation task.

**Format**: `[ID] [P?] [Story] Description`. Paths are relative to the repository root.

## Phase 1: Pure core (US1, US2) — no recording needed

- [x] T001 [P] [US1] Tests in `tests/test_capture_calib.py`: `SCRIPT` (18 expressions, known target keys), `segment` on synthetic activity (18 segments found, short blips dropped, close runs merged, count mismatch reported with times), the score fallback without landmarks
- [x] T002 [US1] Implement `SCRIPT`, `activity`, `segment` in `captureforge/face/capture/calib.py`
- [x] T003 [P] [US1] Tests: `learn` on synthetic takes made from known gains and cross-talk recovers them (gains within 5 %, cross-talk within 0.05), bounds 1.0 to 4.0, undetected keys, mirror detection and swap; `apply` with no profile is the identity, clamps to 0..1, skips absent columns
- [x] T004 [US1] Implement `learn`, `apply`, profile save and load (format and version checked) in `calib.py`
- [x] T005 [P] [US3] Tests then code: `report` (per expression before and after) and `evaluate` (SC-001 to SC-004 numbers on a held-out take)

## Phase 2: Capture file (US1)

- [ ] T006 [US1] Test in `tests/test_video_to_csv.py`, then `--capture PATH` in `captureforge/face/helpers/video_to_csv.py` (interface 2: times, valid, landmarks, raw scores, names, size, head matrices; faceless frames NaN); `load_capture` in `calib.py`; `.gitignore` gets `*.capture.npz` and `*.faceprofile.json`

## Phase 3: Gate (needs the maintainer's recordings)

- [ ] T007 Go/no-go: two scripted takes of the maintainer (not committed); learn on take 1, evaluate on take 2 and the other way round; SC-001 to SC-004. Numbers in `specs/005-actor-calibration/research.md`. No-go stops the feature here.

## Phase 4: Integration (after a go)

- [ ] T008 [US2] Tests then code: `post.process(..., profile=None)` and `video_to_csv.py --profile` (no profile: byte-identical CSV, the existing golden test stays green)
- [ ] T009 [US2] Tests then code: the live capture stream applies the profile per frame (spec 004 helper `--profile`)
- [ ] T010 [US1][US2][US3] Blender tests then code: settings (`actor_profile`, `csv_apply_profile`), `faceforge.calibrate` (video and label in, profile and report out, replace only after confirmation), `faceforge.profile_report`, the script text and the profile box in the panel; `Video to face` and `Import CSV` use the profile when set

## Phase 5: Docs and checks

- [ ] T011 [P] README.md, README.pt-BR.md and `docs/pt-BR/CALIBRACAO.md`: the script, how to record (eye level, whole face, steady light), panel steps, report, limits, privacy
- [ ] T012 Run every suite (pure, Blender 5.2; CI on 4.4) and the extension validation

## Dependencies

T001 to T006 need no recording and can start now. T007 needs T001 to T006 and the recordings. T008 to T012 only after
a go in T007.
