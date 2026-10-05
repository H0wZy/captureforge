# CaptureForge

[Português](README.pt-BR.md) | [howzysolutions.com](https://howzysolutions.com)

CaptureForge is a free Blender extension for capture-driven animation, built as a suite of modules that share
one sidebar tab (`CaptureForge`):

| Module | What it does | Status |
|---|---|---|
| **FaceForge** | Turns a posed facial rig into **ARKit 52 shape keys** (or your own list) and drives them from a video or a webcam, no iPhone needed. | available |
| **BodyForge** | Markerless **body mocap from one phone video**: clean-up, foot lock, report, and a Unity Humanoid FBX export. | available (0.2) |
| **ScanForge** | Face and body scan from a 360-degree video. | roadmap |

License: GPL-3.0-or-later. Blender 4.4 LTS or newer (developed on 5.2). Pure Python, no extra packages inside
Blender. **Platforms:** Windows, Linux and Apple Silicon macOS (M1 and later) are supported; **Intel macOS is not
supported** (MediaPipe publishes no current wheel for it). The FaceForge sections come first; [BodyForge](#bodyforge-body-mocap-from-one-phone-video) has its own section.

## Why this exists

I am building my first game with AI-assisted development and AI-assisted 3D modeling. Facial blendshapes were
one of the places where the tools I needed were paid, iPhone-only, or both. So I built one, with an AI
pair-programmer, and I am sharing it for free. AI-assisted creation is growing fast; the more free tools
that fit into it, the better for everybody who is learning like me. Issues, ideas and pull requests are
very welcome.

## FaceForge features

- **Pose library on the timeline.** One marker per shape (ARKit 52, ARKit symmetric 34, or your own
  names). Pose, `Key pose`, repeat.
- **Bake.** `evaluated(pose) - evaluated(neutral)` per mesh (head, eyes, teeth, tongue), so shape keys,
  deform modifiers and Armature are baked exactly as you see them. Every mesh gets the same key names.
- **Split Left/Right** with a smooth falloff across the midline (no step on the nose, lips or chin).
- **Mocap import.** CSV from Live Link Face or a generic CSV (`time` in seconds plus one column per shape).
- **Head pose.** `Video to face` also writes the head rotation, and the import keys it on your head bone
  (default `Head`, with an optional neck share, a gain and an on/off switch).
- **Video to face**. Pick a video, FaceForge runs MediaPipe Face Landmarker in a separate Python and keys
  the result onto your shape keys. Works with any phone (Android friendly), no iPhone needed.
- **Live webcam.** A helper process streams the 52 scores over localhost UDP; Blender drives the shape keys
  in real time and can record into an action.
- **Quality inspector.** Per-key report (empty keys, max delta, left/right symmetry error, mesh-inside-mesh
  checks, flipped normals, crushed triangles), a delta heatmap as a color attribute, and a txt/json report.
- **Auto rig fit.** Renders the head, finds the face landmarks with MediaPipe, and places a lean face rig
  (jaw, eyes, lids, brows, mouth, cheeks, tongue) with automatic weights, or fits a Rigify face metarig.
- **Review sheet.** A PNG grid with the neutral face and every shape, labelled.
- **Headless friendly.** Every feature is a plain Python function that takes explicit objects, so scripts
  and AI agents can run it with `blender --background`.

## Install

**From a zip**

1. Build it (needs Blender; the quotes and the `&` matter in PowerShell):
   ```
   & "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --command extension build --source-dir captureforge --output-dir dist
   ```
   This writes `dist/captureforge-<version>.zip`. Or grab the zip from the GitHub releases page when one exists.
2. In Blender: `Edit > Preferences > Get Extensions`, the `v` menu in the corner, `Install from Disk...`,
   choose the zip.
3. Open the sidebar in the 3D viewport (hover, press `N`), tab `CaptureForge`, panel `FaceForge`.

**From Get Extensions**: CaptureForge is not listed on extensions.blender.org yet. Once it is, search for
`CaptureForge` in `Edit > Preferences > Get Extensions` and press Install.

## Quickstart

1. **Rig temporarily.** Rig the face (Rigify face works well, or let `Auto rig from face` build one, see below). Head, eyes, teeth and
   tongue in the same rig. The rest pose must be a real neutral: eyes open, mouth closed and relaxed.
2. **Markers.** Pick the preset and press `Create markers`: a `neutral` marker at frame 0 and one marker per
   shape from frame 1. This replaces the timeline markers you already had.
3. **Pose.** Jump marker to marker, pose the rig, press `Key pose` (armature active). Do the neutral first.
   Pose each shape alone, from neutral, at full amplitude (`eyeBlink` closes 100 %).
4. **Bake.** Select the rigged meshes, `Make target` (creates an unrigged copy `<name>_FF` and the
   Source/Target pair), then `Bake shape keys`. `Skip empty` drops keys that do not move a given mesh.
5. **Split L/R** (symmetric preset): `Split all`. `jawLeft/Right` and `mouthLeft/Right` are never split.
6. **Test** with a mocap CSV (or a video, or the live webcam; see below), then `Render review sheet`
   and the quality inspector.
7. Export the target as FBX or glTF with shape keys (and blendshape normals if your engine wants them).

## Auto rig fit

Rigging the face is the slowest step, so FaceForge can do a first pass for you (panel section 0).

1. Make the **head** the active mesh and select the other face meshes too (eyeballs, teeth, tongue, and any
   nose or brow pieces that are separate objects).
2. Set the **Python** and **Model** in the add-on preferences (the same ones `Video to face` uses).
3. Pick the rig and press `Auto rig from face`. FaceForge renders the selected meshes from the front
   (orthographic, Workbench), asks MediaPipe Face Landmarker for the 478 face points, drops them on the mesh with
   a ray along +Y, and builds the rig from those points.

**FaceForge rig** (26 bones): `head`, `jaw`, `eye`, upper/lower `lid`, three `brow` bones, `mouth.corner`, `cheek`
and three lip bones per side (`lip.T`/`lip.B` plus `.L`/`.R`), the center `lip.T`/`lip.B`, and `tongue` with
`tongue.tip`. Bones follow the Rigify naming (`.L` is the character's left, +X). The head mesh gets automatic
weights computed from distance: a falloff around each bone's anchor (lids, brows, lips, corners, cheeks), the jaw
takes everything below the lip line and in front of the hinge, and `head` keeps the rest, so every vertex sums to
1. Blender's bone-heat weights are not used: they fail on lids and lips and need UI context. Extra meshes are bound
rigidly: eyeballs to the nearest eye bone, a mesh named `tongue` to `tongue`, anything below the lip line to
`jaw`, the rest to `head`. Eye bones sit at the eyeball meshes when they exist.

**Rigify metarig**: choose `Rigify metarig` (needs the Rigify add-on enabled) and FaceForge adds Rigify's face
sample metarig scaled and placed to match the eyes and chin. Adjust it and generate with Rigify as usual.

Limits: the character must face -Y with its left on +X, a clear front view with visible eyes and mouth, and
human-like proportions. If MediaPipe finds no face you get a clear error; stylized heads sometimes need the
eyes and lips modelled before it recognises them. The result is a starting point: check the bones, then pose
each shape.

## Quality inspector

Select the targets and press `Inspect keys` (panel section 5). For every shape key it reports:

- **empty keys** and the **max delta** (largest vertex move, object units);
- **left/right symmetry error**: each `...Left` key mirrored against its `...Right` (and `.L`/`.R`) partner;
- **mesh inside mesh**: pick a closed **Collider** mesh (the eyeball, the teeth) and optionally a vertex **Group**
  of the inspected mesh (eyelids, lips); vertices the key pushes into the collider are counted with the deepest one;
- **flipped normals** and **crushed triangles** (area under 10 % of the neutral one).

Problems are listed in the panel and written to the **Report file** (`.txt` or `.json`). `Delta heatmap` paints the
active shape key's delta into a color attribute (blue = still, red = most moved; Solid shading, Color: Attribute).

## Face mocap without an iPhone

CSV import, **Video to face** and **Live webcam** work today.

FaceForge reads a generic CSV: a `time` column in seconds and one column per ARKit shape, in the same
spelling as the shape keys (`eyeBlinkLeft`, ...). Column names are matched case-insensitively and a
`column=key` rename map is available.

**Head pose.** The video helper also writes six optional columns after the shapes (`--no-head-pose` leaves them out):

| Column | Unit | Meaning |
|---|---|---|
| `headRotX`, `headRotY`, `headRotZ` | radians | pitch, yaw, roll of the head relative to its neutral pose (zero = the head of the neutral seconds) |
| `headPosX`, `headPosY`, `headPosZ` | centimeters | head position relative to the neutral one (MediaPipe's scale: approximate) |

The head frame is X = the person's left, Y up, Z out of the face, and the angles are in the order `Ry * Rx * Rz`
(yaw, then pitch, then roll; Blender Euler `ZXY`). A positive yaw turns to the person's left, a positive pitch looks
down, a positive roll takes the left side up. The angles come from the MediaPipe facial transformation matrix, are
made continuous across frames (no 360 degree jumps), and get the same `Smooth` and neutral calibration as the shapes;
frames without a face hold the last pose. `Gain` does not scale them: use `Head gain` on import.

On import (`4. Mocap CSV`), `Head pose` keys the rotation on the bone called `Head` (any case) of the rig you pick
in `Rig`; empty, it uses the armature of the targets, else the only armature in the scene that has the bone.
`Neck share` (0.3 = 30 %) gives that part of the rotation to the `Neck` bone and the head bone keeps the rest, so
the two add up. `Head gain` multiplies the angles (0.5 for a subtle character). `Translation` also moves the head
bone with `Scale` scene units per centimeter (0.01 = meters); it needs a head bone that is not Connected, and the
movement is that of the face, not of the neck. Keys follow the bone's rotation mode (Quaternion or Euler) and go into
the rig's current action (a new `<rig>_headmocap` one when it has none); other channels of the action are untouched.
The rig is assumed to be in Blender's default orientation (the character faces -Y, +Z up); bone rolls do not matter.
A CSV without these columns (older files, Live Link Face) imports exactly as before. Unchecking `Head pose` skips it.

**From a video** (phone recording, Iriun Webcam recording, anything OpenCV can open):

1. Create a Python environment with MediaPipe and OpenCV (any Python version MediaPipe supports):
   ```
   python -m venv .venv
   .venv/Scripts/python -m pip install -r requirements-mocap.txt      # Linux/macOS: .venv/bin/python
   ```
2. Download the MediaPipe Face Landmarker model (about 3.6 MB) from Google's model storage:
   `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`
3. In `Edit > Preferences > Add-ons > CaptureForge`, set the **Python** (the venv's python) and the **model
   file**. The panel's `Video to face` section has a `Setup instructions` button that repeats these steps.
4. Pick the video in the panel and press `Video to face`.

Recording tips: front, diffuse light; face about half the frame; no glasses; start with 2 s of a still
neutral face (it becomes the zero of every channel), then hold each expression for 2 s. Iriun Webcam turns
an Android (or iPhone) into a webcam, which also works for the live mode.

MediaPipe does not produce `tongueOut`, so 51 of the 52 shapes are driven.

**Live webcam** (panel section 4c): set the same Python and model in the preferences, press `Start`, hold a still
neutral face for 2 seconds (it calibrates), and the shape keys of the targets follow your face. `Record` keyframes
what arrives into an action `<object>_livemocap` (it can be switched on mid-capture and starts at the current frame).
`Stop` ends the helper. `Camera` is the webcam index (Iriun shows up as one); `Smooth`, `Neutral s` and `Gain` are shared
with `Video to face`. Press `Start` with `Start helper` off to only listen: anything that sends the packet below
to `127.0.0.1:<port>` can drive the rig.

The packet is one UDP datagram of JSON, about 30 per second: `{"t": seconds, "state": "calibrating" | "live" |
"noface", "v": [52 floats in ARKit order]}`, or `"s": {"jawOpen": 0.3, ...}` instead of `"v"` to name only some
shapes. Invalid datagrams are ignored; with `noface` the last pose is held. Run the sender yourself with
`python captureforge/face/helpers/webcam_stream.py --model face_landmarker.task --source 0 --port 9876`
(`--source` also takes a video file, with `--loop`).

You can also run the helper script yourself:
`python captureforge/face/helpers/video_to_csv.py video.mp4 -o out.csv --model face_landmarker.task`.

## BodyForge: body mocap from one phone video

BodyForge turns one ordinary phone video (any Android phone or webcam, no iPhone, depth sensor or LiDAR) into an
animation on a **Mixamo/Unity Humanoid** armature, cleans it up and exports an FBX that Unity reads as a Humanoid
clip. It adds a `BodyForge` panel in the same `CaptureForge` tab.

1. **Helper (one time).** Preferences > Add-ons > CaptureForge > **Install helper**. It shows what it will do (a
   Python environment with `mediapipe` and `opencv-python`, and the MediaPipe pose model, about 31 MB, Apache-2.0,
   from Google's storage) and asks before it downloads anything. The same environment serves FaceForge. Without the
   helper the add-on keeps working and shows setup steps.
2. **Rig.** Pick your Mixamo-style armature (names with or without `mixamorig:`), or **Create reference armature**.
3. **Film.** Follow the [recording guide](docs/BODYFORGE-RECORDING.md) (fixed phone, 30 fps or more, head to feet in
   view, 1.5 to 2 s standing still at the start). BodyForge warns about low frame rate, a body out of the picture, low
   confidence and several people.
4. **Video to body.** Esc cancels while it tracks. **Hands and fingers** (needs the hand model) adds finger curl and a
   palm-driven forearm twist; **Video to body and face** also keys the face of the same video with FaceForge.
5. **Clean up.** Zero-phase smoothing (or a causal preview filter), foot-contact detection and **foot lock**, then
   **In place**, **Trim**, **Close loop**, **Mirror**. Everything restarts from the raw clip kept on the action.
6. **Report.** Foot skate (cm/s), bone length drift, joint-limit violations, jitter and weak frame ranges, as text,
   `report.json` and a `filmstrip.png` for review, written next to the video.
7. **Export for Unity.** An FBX with the documented preset (T-pose rest, no leaf bones, Y up, baked, deform bones only);
   it refuses, listing the missing or extra bones, when the armature does not match. In Unity: Animation Type
   Humanoid, Avatar = the character's avatar.

The pure steps (landmark reader, solver, filters, foot lock, report) are plain numpy functions that take explicit
data, so scripts and agents can call them without Blender. Limits: one person, one fixed camera, mostly in place;
depth is the weak axis of single-camera tracking; the foot lock is a heuristic that needs to be off for jumps and
seated poses; fingers are curl and twist only. Model licenses and checksums are in
[`docs/BODYFORGE-MODELS.md`](docs/BODYFORGE-MODELS.md). The MediaPipe models are Apache-2.0, are downloaded only
after you confirm and are never bundled with CaptureForge; the output (landmarks, shape-key and bone animation) is yours. Do not film or animate a real person without their consent
([POLICY.md](POLICY.md)).

## Headless, command line and AI agents

The core modules (`bake`, `markers`, `split`, `mocap`, `sheet`, `video`, `quality`, `autofit`, `live`) take explicit objects and do not depend on the UI context, so they run in background Blender:

```python
# blender --background rig.blend --python bake_it.py
import sys
sys.path.insert(0, "/path/to/captureforge-repo")  # the repository root
from captureforge.face import bake, markers, split, presets
import bpy

scene = bpy.context.scene
markers.create_markers(scene, presets.ARKIT_SYMMETRIC)
# ... key the poses (markers.key_pose(armature, frame) for each marker) ...
head, head_target = bpy.data.objects["Head"], None
head_target = bake.make_target(head)
bake.bake_shapes(scene, [(head, head_target)], markers.frames_from_markers(scene), neutral_frame=0)
split.split_all(head_target)
```

`video.run(python, model, video_path, out_csv)` runs MediaPipe and writes the CSV; `mocap.import_csv(scene, targets, csv_path)` keys it.

`quality.inspect(target, depsgraph, collider=eyeball)` returns the per-key report as a dict, `quality.write_report(report, "report.json")` saves it.

The test suite is the best set of examples: `tests/run_tests.py`.

## Tests

Headless, one Blender process:

```
timeout 300 "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup --python tests/run_tests.py
python tests/test_video_to_csv.py
python tests/test_webcam_stream.py
# Live capture (spec 004): protocol, errors, installer, post-processing, tracker contract; the helper test needs numpy
for t in post contract protocol errors setup helper; do python tests/test_capture_$t.py; done
# BodyForge: pure numpy tests, then the Blender side
for t in landmarks quat solve helper cleanup; do python tests/test_body_$t.py; done
timeout 600 "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup --python tests/run_body_tests.py
```

BodyForge's real-MediaPipe test renders a synthetic mannequin video and runs it end to end; it is skipped unless
`BODYFORGE_PYTHON` (the helper venv's python) and `BODYFORGE_POSE_MODEL` (a pose `.task` file) are set.

The first builds a procedural head (sphere, armature, eyes, teeth) and prints `FaceForge tests: N passed,
M failed`, exiting non-zero on failure. GitHub Actions runs the same on every push. Set `FACEFORGE_PYTHON` (a python with mediapipe and opencv) and
`FACEFORGE_MODEL` (the `.task` file) to also run the tests that exercise the real MediaPipe helpers (video, auto rig on a dummy face, live stream); without them those tests print `skipped` and pass. They are also
used by `Video to face` when the add-on preferences are empty.
Validate the manifest with `blender --command extension validate captureforge`.

## Known limits

- Source and Target need the same vertex count and order (Target is a duplicate of the base mesh).
  Topology-changing modifiers (Subsurf, Mirror, Solidify, Geometry Nodes, ...) are switched off during the
  bake and restored afterwards.
- The split assumes the midline is at X = 0 of the object.
- Head and eye rotations from Live Link Face are ignored for now; head rotation comes from `Video to face` only.
- The live capture timer (the `Start` button) is a modal operator and is tested by hand; its receive path, parsing,
  recording and helper handling are covered by the headless tests.
- The review sheet is a Workbench render: good for checking shape, not for presentation.

## Roadmap

- Presets of starting poses for the generated rig (e.g. `jawOpen` = jaw rotation), so you only tweak style.
- Corrective shapes for combinations (`jawOpen + mouthSmile`), baked from the combined pose.
- Export checker: exact 52 names on every mesh, order, blendshape normals, unzeroed keys.
- Eye rotation from the mocap onto bones; Live Link Face UDP streaming.
- Loadable name lists (Audio2Face and others).
- Listing on extensions.blender.org.

v1.1 ideas:

- Pose from a reference image: solve the rig so MediaPipe sees the same expression as a photo or an AI image.
- Automatic wrinkle and tension maps per shape.
- Expression transfer between characters.
- Live capture panel inside Blender (spec 004): camera list, preview, record and bake onto the character. Done so
  far: the capture helper with its local protocol, the tracker contract (`docs/TRACKER-CONTRACT.md`), the helper
  installer (Blender's own Python, pinned packages, offline afterwards) and the face model in the release zip. Next:
  the Blender session, the preview overlay and the panel.
- Weights fitted to the character's own shape keys (spec 003): on hold. A measurement showed that fitting the
  tracked landmarks makes the weights worse than MediaPipe's own scores on stylized test heads, because the
  landmarks between the visible features do not follow the skin closely enough. Details:
  `specs/003-character-fitted-weights/research.md`.

### The Forge family

Sister modules of CaptureForge, in the same spirit (free, Blender, AI-friendly):

- **BodyForge** (available, see above). Next ideas: more estimators (RTMW), other rigs and retargeting, 1 to 3 cameras.
- **ScanForge**: face and body scan from a 360-degree video (sharp-frame pick, COLMAP or Meshroom as external
  tools, wrap onto a clean animatable topology, then FaceForge).

## Responsible use

Do not scan, recreate or animate a real person, including celebrities, without their explicit consent, and
follow your local likeness and privacy laws. The maintainer is not responsible for misuse. This is a strong
recommendation and a warning, not a license term. Read [POLICY.md](POLICY.md).

## Credits and clean room

CaptureForge is written from scratch from public documentation and the Blender API: Apple's ARKit blendshape
list, Google's MediaPipe Face Landmarker, the Live Link Face CSV format as seen in open importers, and the
Blender manual. No paid add-on was downloaded, decompiled or copied. Research notes (in Portuguese) are in
[`docs/pt-BR`](docs/pt-BR/RESEARCH.md); the design is in [`docs/pt-BR/DESIGN.md`](docs/pt-BR/DESIGN.md).

Maintainer: H0wZy. See [CONTRIBUTING.md](CONTRIBUTING.md).
