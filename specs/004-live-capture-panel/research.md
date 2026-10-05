# Research: live capture inside Blender

Checked on 2026-10-05. Sources: PyPI JSON metadata (`pypi.org/pypi/<name>/json`), the dist-info of an existing local
helper environment, a local Blender 5.2.1 run, and the model license verification already recorded in
`docs/pt-BR/BODYFORGE-T051-LICENCA.md` and `docs/BODYFORGE-MODELS.md` (2026-10-04). Nothing was installed or downloaded
for this note.

## Licenses (FR-001)

| Component | License | Source of the claim | Notes |
|---|---|---|---|
| Blender | GPL-3.0-or-later | upstream | host |
| `mediapipe` 1.0.1 | Apache-2.0 | PyPI metadata (`License: Apache 2.0`, wheel has `LICENSE` and `NOTICE`) | GPL-3.0 compatible (FSF) |
| `opencv-python` 5.0.0.93 | Apache-2.0 (the wheel bundles third-party libraries under their own licenses) | PyPI metadata | already in `THIRD_PARTY_NOTICES.md` |
| `numpy` 2.5.3 | BSD-3-Clause | upstream, standard | add to the notices |
| `cv2-enumerate-cameras` 1.4.0 | MIT | PyPI metadata | optional, names of cameras |
| `face_landmarker.task` (BlazeFace short range, Face Mesh V2, Blendshape V2) | Apache-2.0 on each model card | read on the cards 2026-10-04 | the `.task` carries no NOTICE file |

Redistributing the `.task` inside the add-on zip: allowed. Apache-2.0 section 4 asks for a copy of the license, kept
copyright and attribution notices, and a NOTICE if the work has one (it has none); a `THIRD_PARTY_NOTICES.md` entry plus the license text in the zip is enough. The
current constitution wording says models are downloaded by the user and never committed, so bundling needs either
the CI-adds-it-to-the-zip route or a wording amendment (see the spec).

Model file fact: the local copy from the pinned `float16/1` URL is 3,758,596 bytes with SHA-256
`64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff` (this is the checksum `docs/BODYFORGE-MODELS.md`
still lacks).

## Python 3.13 and wheels

- `mediapipe` has moved to version-independent wheels: the installed 1.0.1 wheel's tag is `py3-none-win_amd64`. On PyPI,
  1.0.0 (2026-07-27) and 1.0.1 (2026-08-14) list wheels for macOS arm64, Linux x86-64 and aarch64, Windows x86-64 and
  ARM64; 0.10.33 and 0.10.35 list macOS arm64, Linux x86-64 and Windows x86-64 (and ARM64 from 0.10.35). **No macOS
  Intel wheel in any of these.** Blender 5.2 bundles Python 3.13 and 4.4 bundles 3.11, so both are covered by the tag.
- `opencv-python` 5.0.0.93: `cp37-abi3` wheels for Windows x86-64 and 32-bit, macOS arm64 and x86-64, Linux x86-64 and aarch64.
- Blender 5.2's bundled interpreter (3.13.13) imports `venv` and `ensurepip` and creates a venv with `pip`, so no system
  Python is needed to create the helper environment.
- Building MediaPipe from source: Bazel, a C++ toolchain and OpenCV development files; long and fragile. Only a last
  resort for a platform with no wheel (macOS Intel), documented, not automated. Not attempted here.

## Preview options

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Viewport overlay, draw handler with a `GPUTexture` | no datablock, fast upload, sits where the character is | needs a GPU; API names to check on 4.4 and 5.2 | chosen |
| Image Editor area fed through `bpy.data.images[...].pixels` | stable API | a Python pixel copy per frame, a datablock to clean up, an extra area to arrange | rejected |
| Helper shows its own window (OpenCV `imshow`) | trivial | a second window outside Blender, focus and macOS GUI-thread problems, not "inside Blender" | rejected |

## Camera list

OpenCV has no enumerate call. `cv2-enumerate-cameras` (MIT) lists name, index and backend on Windows, macOS and
Linux; without it the helper probes indices 0 to 9. Probing opens devices (camera light, possible permission prompt),
so only on an explicit button.

## Transport

| Option | Verdict |
|---|---|
| UDP JSON (existing live mode) | keeps for external senders; 64 KB limit, no preview, no auth |
| TCP loopback, framed, token | chosen: reliable, carries a preview frame, simple to test |
| stdin/stdout pipes of the helper | works, but ties data and logs together and is awkward to read non-blocking on Windows from Blender |
| shared memory | fastest, but platform specific and more code than the problem needs |

## Latency model (to be measured, task T001)

capture to MediaPipe result about 20 to 60 ms on a laptop CPU in LIVE_STREAM mode (the earlier video runs processed a
1080p 60 fps clip of 1273 frames in about 29 s, roughly 22 ms per frame including decode, which is the right order of
magnitude), loopback under 2 ms, Blender timer at most 17 ms at 60 Hz, depsgraph update tens of milliseconds for a face
rig. The target of 150 ms p95 has margin only if the rig update stays cheap; the measurement decides.

## Mobile (future note)

An Android phone could run MediaPipe on device (the same model, the Tasks API) and an iPhone could send its native
ARKit 52 blendshapes and head pose; both would send the same CSV contract (or the capture file) to this panel. Not
part of this spec.
