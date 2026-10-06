# Quickstart: validating BodyForge v1

How to prove the feature works end to end. Contracts: [landmarks-file](contracts/landmarks-file.md),
[helper-cli](contracts/helper-cli.md), [unity-export-preset](contracts/unity-export-preset.md). Entities:
[data-model.md](data-model.md).

## 1. Automated (no camera, no Unity)

```sh
# pure tests (needs only numpy)
python tests/test_body_landmarks.py
python tests/test_body_quat.py
python tests/test_body_solve.py
python tests/test_body_cleanup.py
python tests/test_body_helper.py

# Blender tests on a synthetic armature and motions (4.4 and 5.2)
blender --background --factory-startup --python tests/run_body_tests.py
```

Expected: every test prints PASS and the runner exits 0. Each test was first seen failing (Constitution III). CI runs
the same commands on both Blender lines.

## 2. One-time helper setup (Windows, no terminal)

1. In Blender, open Preferences, Add-ons, CaptureForge, and press **Install helper**.
2. Read the text it shows (venv location, packages, model URLs and sizes) and confirm.
3. When it finishes, the Python and model paths are filled in. Press **Check helper**; expected: "helper ready".

If something fails, the panel shows the manual steps (the same `SETUP_LINES` pattern as FaceForge).

*Verified 2026-10-03 on Blender 5.2.1 with a clean factory profile:* `setup_env.py --yes --hands` created a new venv, installed
`mediapipe` and `opencv-python`, downloaded the three models and passed their checksums; **Check helper** answered
"helper ready"; the full BodyForge Blender suite, including the real MediaPipe test on the synthetic mannequin video,
passed with that venv.

## 3. Hands-up clip (the easy one, user story 1)

1. Film yourself (or a consenting person), phone on a stable surface, full body in frame, 30 fps or more, 1 to 2 s
   standing still, then both hands up. Keep the file outside the repository.
2. In the CaptureForge tab, BodyForge panel: press **Create reference armature** (or pick your Mixamo-style armature),
   choose the video, press **Video to body**.
3. Expected: an action with keys at the scene rate, wrists above the head at the end, the rest of the body near neutral.

## 4. Clean-up and report (user story 2)

1. Press **Clean up** with Final mode; leave foot lock on. Press **Report**.
2. Expected: foot skate under 2 cm/s on planted frames, jitter lower than the raw clip, a `report.json` and a
   `filmstrip.png` next to the video. Use **In place**, **Trim**, **Loop**, **Mirror** as needed.

## 5. Export and Unity check (user story 3)

1. Press **Export for Unity**; expected: an FBX, and a refusal with a bone list if the armature is not the profile
   (and a refusal if the armature's object scale is not 1: apply it with Object > Apply > Scale first).
2. In Unity: Animation Type Humanoid, Avatar = the character's avatar; expected: no import warnings, the clip plays.

### Manual Unity Humanoid import check (maintainer, outside CI)

The headless tests prove the FBX has the right bones, T-pose rest, frame rate and animation. They cannot prove Unity
accepts it, so each release does this once with the game's own character:

1. Copy the exported `.fbx` into the Unity project's `Assets` folder.
2. Select it, open the **Rig** tab: **Animation Type = Humanoid**, **Avatar Definition = Copy From Other Avatar**,
   **Source** = the character's avatar, press **Apply**. Expected: no red or yellow warning on the Rig tab.
3. Open the **Animation** tab. Expected: one clip named after the Blender action, frame range and fps as exported, no
   import warnings in the console. For an in-place clip tick **Bake Into Pose** for Root Transform Rotation, Y and XZ.
4. Press play in the preview with the character. Expected: the pose follows the video, feet on the floor, no
   twisted limbs. For a looping clip tick **Loop Time** and check there is no pop at the seam.
5. Record the result (Unity version, avatar setup, pass or the problem seen) in the PR description.

## 6. The four client clips

Follow `docs/BODYFORGE-RECORDING.md` for each: hands up (required), frisk with hands on (required), motorcycle
(best effort, seated, one leg visible), dance (best effort, 60 fps, strong light). Record the result and the limits in
the PR description.

## 7. Performance and privacy checks

- Time the 10 s clip from video to animated rig on the reference laptop; expected under 3 minutes (SC-006).
  **Measured (2026-10-03, Windows 11, an RTX 3050 with 8 GB; MediaPipe ran on the CPU, the GPU was not used):** a 9 s
  synthetic mannequin video, 270 frames, 540x960, heavy pose model, Blender 5.2.1: **Video to body 19.1 s** (tracking,
  solve, and keys on the rig), Clean up 0.9 s, Report 0.1 s, Export for Unity 0.4 s, 20.5 s in all, about nine times
  under the 3-minute target. Real 1080p phone footage adds decode time; the pose model input is 256x256 either way, so
  the tracking cost is about the same. No GPU memory is needed.
- Before every push, grep the diff for absolute local paths, personal names, e-mails and private project names (Constitution VI); expected: no hits.
