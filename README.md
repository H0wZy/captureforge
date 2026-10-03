# FaceForge

[Português](README.pt-BR.md)

FaceForge is a free Blender extension that turns a posed facial rig into **ARKit 52 shape keys** (or any
list of names you choose), ready to export to Unity, Unreal, Godot or glTF. It also drives those shape keys
from a video or a webcam, so you can test a face without an iPhone.

License: GPL-3.0-or-later. Blender 4.4 LTS or newer (developed on 5.2). Pure Python, no extra packages inside
Blender.

## Why this exists

I am building my first game with AI-assisted development and AI-assisted 3D modeling. Facial blendshapes were
one of the places where the tools I needed were paid, iPhone-only, or both. So I built one, with an AI
pair-programmer, and I am sharing it for free. AI-assisted creation is growing fast; the more free tools
that fit into it, the better for everybody who is learning like me. Issues, ideas and pull requests are
very welcome.

## Features

- **Pose library on the timeline.** One marker per shape (ARKit 52, ARKit symmetric 34, or your own
  names). Pose, `Key pose`, repeat.
- **Bake.** `evaluated(pose) - evaluated(neutral)` per mesh (head, eyes, teeth, tongue), so shape keys,
  deform modifiers and Armature are baked exactly as you see them. Every mesh gets the same key names.
- **Split Left/Right** with a smooth falloff across the midline (no step on the nose, lips or chin).
- **Mocap import.** CSV from Live Link Face or a generic CSV (`time` in seconds plus one column per shape).
- **Video to face**. Pick a video, FaceForge runs MediaPipe Face Landmarker in a separate Python and keys
  the result onto your shape keys. Works with any phone (Android friendly), no iPhone needed.
- **Live webcam** *(coming in v1)*. A helper process streams the 52 scores over localhost UDP; Blender drives the shape keys
  in real time and can record into an action.
- **Quality inspector.** Per-key report (empty keys, max delta, left/right symmetry error, mesh-inside-mesh
  checks, flipped normals, crushed triangles), a delta heatmap as a color attribute, and a txt/json report.
- **Auto rig fit** *(coming in v1)*. Renders the head, finds the face landmarks with MediaPipe, and places a lean face rig
  (jaw, eyes, lids, brows, mouth, cheeks, tongue) with automatic weights, or fits a Rigify face metarig.
- **Review sheet.** A PNG grid with the neutral face and every shape, labelled.
- **Headless friendly.** Every feature is a plain Python function that takes explicit objects, so scripts
  and AI agents can run it with `blender --background`.

## Install

**From a zip**

1. Build it (needs Blender; the quotes and the `&` matter in PowerShell):
   ```
   & "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --command extension build --source-dir faceforge --output-dir dist
   ```
   This writes `dist/faceforge-<version>.zip`. Or grab the zip from the GitHub releases page when one exists.
2. In Blender: `Edit > Preferences > Get Extensions`, the `v` menu in the corner, `Install from Disk...`,
   choose the zip.
3. Open the sidebar in the 3D viewport (hover, press `N`), tab `FaceForge`.

**From Get Extensions**: FaceForge is not listed on extensions.blender.org yet. Once it is, search for
`FaceForge` in `Edit > Preferences > Get Extensions` and press Install.

## Quickstart

1. **Rig temporarily.** Rig the face (Rigify face works well, or use the auto rig fit). Head, eyes, teeth and
   tongue in the same rig. The rest pose must be a real neutral: eyes open, mouth closed and relaxed.
2. **Markers.** Pick the preset and press `Create markers`: a `neutral` marker at frame 0 and one marker per
   shape from frame 1. This replaces the timeline markers you already had.
3. **Pose.** Jump marker to marker, pose the rig, press `Key pose` (armature active). Do the neutral first.
   Pose each shape alone, from neutral, at full amplitude (`eyeBlink` closes 100 %).
4. **Bake.** Select the rigged meshes, `Make target` (creates an unrigged copy `<name>_FF` and the
   Source/Target pair), then `Bake shape keys`. `Skip empty` drops keys that do not move a given mesh.
5. **Split L/R** (symmetric preset): `Split all`. `jawLeft/Right` and `mouthLeft/Right` are never split.
6. **Test** with a mocap CSV (or a video; the webcam is coming in v1; see below), then `Render review sheet`
   and the quality inspector.
7. Export the target as FBX or glTF with shape keys (and blendshape normals if your engine wants them).

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

CSV import and **Video to face** work today; **Live webcam** is *coming in v1*.

FaceForge reads a generic CSV: a `time` column in seconds and one column per ARKit shape, in the same
spelling as the shape keys (`eyeBlinkLeft`, ...). Column names are matched case-insensitively and a
`column=key` rename map is available.

**From a video** (phone recording, Iriun Webcam recording, anything OpenCV can open):

1. Create a Python environment with MediaPipe and OpenCV (any Python version MediaPipe supports):
   ```
   python -m venv .venv
   .venv/Scripts/python -m pip install -r requirements-mocap.txt      # Linux/macOS: .venv/bin/python
   ```
2. Download the MediaPipe Face Landmarker model (about 3.6 MB) from Google's model storage:
   `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`
3. In `Edit > Preferences > Add-ons > FaceForge`, set the **Python** (the venv's python) and the **model
   file**. The panel's `Video to face` section has a `Setup instructions` button that repeats these steps.
4. Pick the video in the panel and press `Video to face`.

Recording tips: front, diffuse light; face about half the frame; no glasses; start with 2 s of a still
neutral face (it becomes the zero of every channel), then hold each expression for 2 s. Iriun Webcam turns
an Android (or iPhone) into a webcam, which also works for the live mode.

MediaPipe does not produce `tongueOut`, so 51 of the 52 shapes are driven.

**Live webcam** *(coming in v1)*: set the same Python and model in the preferences, press `Start`, and the shape keys follow
your face. `Record` keys what it receives into an action. `Stop` ends the helper.

You can also run the helper script yourself:
`python faceforge/helpers/video_to_csv.py video.mp4 -o out.csv --model face_landmarker.task`.

## Headless, command line and AI agents

The core modules (`bake`, `markers`, `split`, `mocap`, `sheet`, `video`, `quality`; `autofit` and `live` are coming in v1) take explicit objects and do not depend on the UI context, so they run in background Blender:

```python
# blender --background rig.blend --python bake_it.py
import sys
sys.path.insert(0, "/path/to/faceforge")          # the repository root
from faceforge import bake, markers, split, presets
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
```

The first builds a procedural head (sphere, armature, eyes, teeth) and prints `FaceForge tests: N passed,
M failed`, exiting non-zero on failure. GitHub Actions runs the same on every push. Set `FACEFORGE_PYTHON` (a python with mediapipe and opencv) and
`FACEFORGE_MODEL` (the `.task` file) to also run the test that exercises the real MediaPipe helper; they are also
used by `Video to face` when the add-on preferences are empty.
Validate the manifest with `blender --command extension validate faceforge`.

## Known limits

- Source and Target need the same vertex count and order (Target is a duplicate of the base mesh).
  Topology-changing modifiers (Subsurf, Mirror, Solidify, Geometry Nodes, ...) are switched off during the
  bake and restored afterwards.
- The split assumes the midline is at X = 0 of the object.
- Head and eye rotations from Live Link Face are ignored for now.
- The review sheet is a Workbench render: good for checking shape, not for presentation.

## Roadmap

- Presets of starting poses for the generated rig (e.g. `jawOpen` = jaw rotation), so you only tweak style.
- Corrective shapes for combinations (`jawOpen + mouthSmile`), baked from the combined pose.
- Export checker: exact 52 names on every mesh, order, blendshape normals, unzeroed keys.
- Head and eye rotation from the mocap onto bones; Live Link Face UDP streaming.
- Loadable name lists (Audio2Face and others).
- Listing on extensions.blender.org.

v1.1 ideas:

- Pose from a reference image: solve the rig so MediaPipe sees the same expression as a photo or an AI image.
- Automatic wrinkle and tension maps per shape.
- Expression transfer between characters.

### The Forge family

Two future sister projects, in the same spirit (free, Blender, AI-friendly):

- **BodyForge**: markerless body mocap from 1 to 3 phone videos (MediaPipe Pose, multi-camera
  triangulation, foot lock, retarget to a humanoid).
- **ScanForge**: face and body scan from a 360-degree video (sharp-frame pick, COLMAP or Meshroom as external
  tools, wrap onto a clean animatable topology, then FaceForge).

## Credits and clean room

FaceForge is written from scratch from public documentation and the Blender API: Apple's ARKit blendshape
list, Google's MediaPipe Face Landmarker, the Live Link Face CSV format as seen in open importers, and the
Blender manual. No paid add-on was downloaded, decompiled or copied. Research notes (in Portuguese) are in
[`docs/pt-BR`](docs/pt-BR/RESEARCH.md); the design is in [`docs/pt-BR/DESIGN.md`](docs/pt-BR/DESIGN.md).

Maintainer: H0wZy. See [CONTRIBUTING.md](CONTRIBUTING.md).
