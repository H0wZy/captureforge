# Contract: helper command lines

Both scripts live in `captureforge/body/helpers/` and are run by the add-on with the shared venv's Python
(`subprocess`, no window on Windows). They print one JSON object per line on stdout for progress and a final summary,
and write errors to stderr with a non-zero exit code. They never import `bpy`.

## `pose_to_landmarks.py`

```text
python pose_to_landmarks.py VIDEO -o OUT.npz --pose-model POSE.task
        [--hands-model HANDS.task] [--variant heavy|lite] [--head-box] [--max-seconds N]
```

- Reads frames in order with the container's real timestamps, honors rotation metadata, runs MediaPipe Pose in video
  mode (and Hands if `--hands-model` is given), converts axes, writes `OUT.npz` per
  [landmarks-file.md](landmarks-file.md).
- Progress lines: `{"progress": 0.42, "frame": 126, "frames": 300}`; final line: `{"done": true, "frames": 300,
  "frames_without_person": 4, "path": "OUT.npz"}`.
- Cancel: the add-on terminates the process; the script writes the file only at the end, so a cancel leaves no
  partial file.
- Exit codes: 0 ok; 2 bad arguments or missing file; 3 missing package (message says `missing package`, the add-on then
  shows the setup text); 4 model file unreadable; 5 no person in any frame.
- When MediaPipe or OpenCV is not installed the script fails at import time with exit code 3, and `--help` still works
  so tests can check the argument parser without them.

## `setup_env.py`

```text
python setup_env.py --venv DIR [--yes] [--dry-run]
```

- Without `--yes` it prints the plan (the venv path, the packages `mediapipe` and `opencv-python`, and the model
  URLs with their sizes) and exits 0 without doing anything; the add-on shows that text and asks the user to confirm,
  then runs it again with `--yes`.
- With `--yes` it creates the venv, installs the packages with `pip`, downloads the model files into `DIR/models`, and
  prints the paths as a last JSON line the add-on stores in the preferences. It needs no admin rights and writes only
  inside `DIR`.
- `--dry-run` prints what would run (used by the test).

## Add-on side (`body/video.py`)

`run(python, pose_model, video, out_npz, hands_model=None, variant="heavy", head_box=False, on_progress=None,
timeout=None)` returns the summary dict; raises `ValueError` with the helper's last error lines plus the setup text.
It checks that the Python and model files exist first (the same `check_setup` pattern as `face/video.py`).
