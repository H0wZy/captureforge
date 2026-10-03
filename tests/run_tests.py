"""Headless FaceForge tests on a procedural head.

timeout 300 "<blender.exe>" --background --factory-startup --python tests/run_tests.py
Prints PASS/FAIL per test and a summary line; exits non-zero on any failure.
"""

import math
import os
import sys
import tempfile
import traceback

import bmesh
import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # repo root, so "import faceforge" finds the package

import faceforge  # noqa: E402
from faceforge import bake, markers, mocap, presets, quality, sheet, split, video  # noqa: E402

SAMPLE_CSV = os.path.join(HERE, "sample_livelink.csv")
POSES = ["jawOpen", "eyeBlink", "browInnerUp"]
S = {}  # shared scene state between tests


# ---------------------------------------------------------------- scene

def smooth(v):
    v = min(max(v, 0.0), 1.0)
    return v * v * (3 - 2 * v)


def sphere(name, radius, center, u=32, v=16):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=radius)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = center
    bpy.context.scene.collection.objects.link(obj)
    return obj


def weight(obj, group, fn):
    vg = obj.vertex_groups.new(name=group)
    for v in obj.data.vertices:
        w = fn(obj.matrix_world @ v.co)
        if w > 0:
            vg.add([v.index], w, "REPLACE")


def rig(obj, arm):
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm


def build_scene():
    scene = bpy.context.scene
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)

    arm = bpy.data.objects.new("FaceRig", bpy.data.armatures.new("FaceRig"))
    scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    bones = {
        "jaw": ((0, 0.1, 0), (0, -0.6, -0.4)),
        "brow.L": ((0.3, -0.8, 0.5), (0.3, -0.8, 0.7)),
        "brow.R": ((-0.3, -0.8, 0.5), (-0.3, -0.8, 0.7)),
        "lid.L": ((0.35, -0.75, 0.3), (0.35, -0.95, 0.3)),
        "lid.R": ((-0.35, -0.75, 0.3), (-0.35, -0.95, 0.3)),
        "eye.L": ((0.35, -0.85, 0.2), (0.35, -1.05, 0.2)),
        "eye.R": ((-0.35, -0.85, 0.2), (-0.35, -1.05, 0.2)),
    }
    for name, (head, tail) in bones.items():
        eb = arm.data.edit_bones.new(name)
        eb.head, eb.tail = head, tail
    bpy.ops.object.mode_set(mode="OBJECT")

    head = sphere("Head", 1.0, (0, 0, 0))
    weight(head, "jaw", lambda p: smooth(-p.z / 0.3) * smooth(-p.y / 0.3))
    for side, sx in (("L", 1), ("R", -1)):
        weight(head, f"brow.{side}",
               lambda p, sx=sx: smooth(1 - math.dist((p.x, p.z), (0.3 * sx, 0.55)) / 0.3) * smooth(-p.y / 0.3))
        weight(head, f"lid.{side}",
               lambda p, sx=sx: smooth(1 - math.dist((p.x, p.z), (0.35 * sx, 0.28)) / 0.25) * smooth(-p.y / 0.3))
    rig(head, arm)
    head.modifiers.new("Subsurf", "SUBSURF").levels = 1
    # An extra shape key already on the source: "what you see is what bakes".
    head.shape_key_add(name="Basis", from_mix=False)
    fat = head.shape_key_add(name="Fat", from_mix=False)
    co = bake.key_coords(fat)
    bake.set_key_coords(fat, co * 1.03)
    fat.value = 0.5

    eyes = []
    for side, sx in (("L", 1), ("R", -1)):
        eye = sphere(f"Eye.{side}", 0.12, (0.35 * sx, -0.85, 0.2), u=12, v=8)
        weight(eye, f"eye.{side}", lambda p: 1.0)
        rig(eye, arm)
        eyes.append(eye)

    teeth = sphere("Teeth", 0.15, (0, -0.7, -0.35), u=12, v=6)
    weight(teeth, "jaw", lambda p: 1.0)
    rig(teeth, arm)

    S.update(scene=scene, arm=arm, head=head, eyes=eyes, teeth=teeth)


def set_pose(**bones):
    """Rest pose plus the given {bone: (attr, value)} overrides."""
    for pb in S["arm"].pose.bones:
        pb.rotation_mode = "XYZ"  # keyed channel stays the same on every frame
        pb.location = (0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.scale = (1, 1, 1)
    for name, (attr, value) in bones.items():
        setattr(S["arm"].pose.bones[name.replace("_", ".")], attr, value)


def key_poses(scene):
    """neutral at 0; jawOpen, eyeBlink, browInnerUp at 1..3; eyeLookUp at 4."""
    arm = S["arm"]
    set_pose()
    markers.key_pose(arm, 0)
    set_pose(jaw=("rotation_euler", (0.45, 0, 0)))
    markers.key_pose(arm, 1)
    set_pose(lid_L=("location", (0, 0, -0.12)), lid_R=("location", (0, 0, -0.12)))
    markers.key_pose(arm, 2)
    set_pose(brow_L=("location", (0, 0.1, 0)), brow_R=("location", (0, 0.1, 0)))
    markers.key_pose(arm, 3)
    set_pose(eye_L=("rotation_euler", (0.3, 0, 0)), eye_R=("rotation_euler", (0.3, 0, 0)))
    markers.key_pose(arm, 4)
    set_pose()


def delta(obj, name):
    keys = obj.data.shape_keys
    return bake.key_coords(keys.key_blocks[name]) - bake.key_coords(keys.reference_key)


def key_names(obj):
    return [kb.name for kb in obj.data.shape_keys.key_blocks]


# ---------------------------------------------------------------- tests

def test_01_markers():
    scene = S["scene"]
    n = markers.create_markers(scene, presets.ARKIT_52)
    m = {mk.name: mk.frame for mk in scene.timeline_markers}
    assert n == 53 and len(scene.timeline_markers) == 53, n
    assert m["neutral"] == 0 and m["tongueOut"] == 52 and m["eyeBlinkLeft"] == 1, m
    assert len(presets.ARKIT_52) == len(set(presets.ARKIT_52)) == 52
    assert len(presets.ARKIT_SYMMETRIC) == 34, len(presets.ARKIT_SYMMETRIC)
    assert "eyeBlink" in presets.ARKIT_SYMMETRIC and "jawLeft" in presets.ARKIT_SYMMETRIC
    assert markers.neutral_frame(scene) == 0
    assert markers.frames_from_markers(scene)[-1] == ("tongueOut", 52)


def test_02_bake():
    scene = S["scene"]
    head, eyes = S["head"], S["eyes"]
    markers.create_markers(scene, POSES)
    key_poses(scene)
    scene.frame_set(7)
    targets = [bake.make_target(o) for o in [head] + eyes]
    S["head_t"], S["eyes_t"] = targets[0], targets[1:]
    pairs = list(zip([head] + eyes, targets))
    names = bake.bake_shapes(scene, pairs, markers.frames_from_markers(scene), 0)
    assert names == POSES, names
    for t in targets:
        assert key_names(t) == ["Basis"] + POSES, (t.name, key_names(t))
        assert not t.modifiers and t.parent is None
    basis = bake.key_coords(S["head_t"].data.shape_keys.reference_key)
    d = delta(S["head_t"], "jawOpen")
    chin = (basis[:, 2] < -0.5) & (basis[:, 1] < -0.5)
    top = basis[:, 2] > 0.6
    assert chin.any() and top.any()
    assert (-d[chin, 2]).max() > 0.05, (-d[chin, 2]).max()
    assert np.abs(d[top]).max() < 1e-5, np.abs(d[top]).max()
    assert np.abs(delta(S["head_t"], "eyeBlink")).max() > 0.01
    assert head.modifiers["Subsurf"].show_viewport is True
    assert scene.frame_current == 7, scene.frame_current
    S["jaw_ref"] = bake.key_coords(S["head_t"].data.shape_keys.key_blocks["jawOpen"]).copy()


def test_03_vertex_count_mismatch():
    scene, head = S["scene"], S["head"]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    dense = bpy.data.objects.new("HeadApplied", bpy.data.meshes.new_from_object(
        head.evaluated_get(depsgraph)))  # Subsurf (and the rest) applied
    scene.collection.objects.link(dense)
    try:
        bake.bake_shapes(scene, [(dense, S["head_t"])], markers.frames_from_markers(scene), 0)
    except ValueError as e:
        msg = str(e)
        assert "HeadApplied" in msg and S["head_t"].name in msg, msg
    else:
        raise AssertionError("expected ValueError")
    finally:
        bpy.data.objects.remove(dense)


def test_04_overwrite():
    scene, t = S["scene"], S["head_t"]
    pairs, frames = [(S["head"], t)], markers.frames_from_markers(scene)
    before = key_names(t)
    try:
        bake.bake_shapes(scene, pairs, frames, 0, overwrite=False)
    except ValueError as e:
        assert "jawOpen" in str(e), e
    else:
        raise AssertionError("expected ValueError")
    assert key_names(t) == before
    bake.bake_shapes(scene, pairs, frames, 0, overwrite=True)
    assert key_names(t) == before, key_names(t)
    jaw = bake.key_coords(t.data.shape_keys.key_blocks["jawOpen"])
    assert np.allclose(jaw, S["jaw_ref"], atol=1e-6)


def test_05_split():
    t = S["head_t"]
    orig = delta(t, "eyeBlink")
    basis = bake.key_coords(t.data.shape_keys.reference_key)
    x = basis[:, 0]
    left, right = split.split_lr(t, "eyeBlink", width=0.1)
    assert (left, right) == ("eyeBlinkLeft", "eyeBlinkRight")
    names = key_names(t)
    assert "eyeBlink" not in names and left in names and right in names, names
    dl, dr = delta(t, left), delta(t, right)
    assert np.abs(dl[x < -0.1]).max() == 0.0
    assert np.allclose(dl[x > 0.1], orig[x > 0.1], atol=1e-6)
    assert np.allclose(dl + dr, orig, atol=1e-6)  # Left + Right - Basis == original
    assert abs(float(split.left_weight(0.0, 0.1)) - 0.5) < 1e-9
    mid = np.abs(x) < 1e-6
    assert mid.any() and np.allclose(dl[mid], 0.5 * orig[mid], atol=1e-6)
    assert split.symmetric_keys(t) == []  # eyeBlink is gone


def test_06_read_csv():
    names, times, rows = mocap.read_livelink_csv(SAMPLE_CSV, csv_fps=60)
    assert len(names) == 52, len(names)
    assert [n.lower() for n in names] == [n.lower() for n in presets.ARKIT_52]
    assert not set(names) & set(presets.LIVELINK_ROTATION_COLUMNS)
    assert rows.shape == (12, 52), rows.shape
    assert times[0] == 0.0 and abs(times[-1] - 11 / 60) < 1e-9, times
    assert abs(times[5] - 5 / 60) < 1e-9, times  # crosses a second boundary


def test_07_apply_mocap():
    from bpy_extras import anim_utils
    scene, t = S["scene"], S["head_t"]
    keys = t.data.shape_keys
    names, times, rows = mocap.read_csv(SAMPLE_CSV, 60)
    old_fps = scene.render.fps, scene.render.fps_base
    scene.render.fps, scene.render.fps_base = 30, 1.0
    try:
        matched, unmatched = mocap.apply_mocap(t, names, times, rows, 30, start_frame=1)
        assert set(matched) == {"jawOpen", "eyeBlinkLeft", "eyeBlinkRight", "browInnerUp"}, matched
        assert "TongueOut" in unmatched and "JawOpen" not in unmatched
        assert len(unmatched) == 52 - len(matched)
        action = keys.animation_data.action
        bag = anim_utils.action_get_channelbag_for_slot(action, keys.animation_data.action_slot)
        fc = bag.fcurves.find('key_blocks["jawOpen"].value')
        assert fc is not None
        expected = {}
        for i, tm in enumerate(times):
            k = round(tm * 60)  # exact 60 fps row index
            expected[1 + (k + 1) // 2] = i  # 30 fps, halves round up, last row wins
        assert len(fc.keyframe_points) == len(expected) == 7, len(fc.keyframe_points)
        assert all(kp.interpolation == "LINEAR" for kp in fc.keyframe_points)
        col = [n.lower() for n in names].index("jawopen")
        for frame, i in expected.items():
            assert abs(fc.evaluate(frame) - rows[i, col]) < 1e-5, (frame, fc.evaluate(frame))
        scene.frame_set(4)
        assert abs(keys.key_blocks["jawOpen"].value - rows[expected[4], col]) < 1e-5
    finally:
        keys.animation_data_clear()
        scene.render.fps, scene.render.fps_base = old_fps
        bake.reset_keys(t)


def test_08_render_sheet():
    scene, t = S["scene"], S["head_t"]
    kb = t.data.shape_keys.key_blocks
    kb["browInnerUp"].value = 0.25
    S["eyes"][0].hide_render = True
    objects_before = set(bpy.data.objects.keys())
    hidden_before = {o.name: o.hide_render for o in scene.objects}
    out = os.path.join(tempfile.gettempdir(), "faceforge_test_sheet.png")
    if os.path.exists(out):
        os.remove(out)
    names = ["jawOpen", "eyeBlinkLeft", "eyeBlinkRight", "browInnerUp"]
    path = sheet.render_sheet(scene, [t], out, names=names, tile=64, columns=3)
    assert os.path.isfile(path), path
    img = bpy.data.images.load(path)
    try:
        assert tuple(img.size) == (192, 128), tuple(img.size)
        px = np.empty(192 * 128 * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        assert px.reshape(128, 192, 4)[..., :3].std() > 0.01  # not a blank sheet
    finally:
        bpy.data.images.remove(img)
    assert set(bpy.data.objects.keys()) == objects_before
    assert not any(n.startswith("FF_Sheet") for n in bpy.data.cameras.keys() + bpy.data.curves.keys())
    assert {o.name: o.hide_render for o in scene.objects} == hidden_before
    assert abs(kb["browInnerUp"].value - 0.25) < 1e-6 and kb["jawOpen"].value == 0.0
    assert scene.camera is None
    S["eyes"][0].hide_render = False
    kb["browInnerUp"].value = 0.0


def test_09_operators():
    scene = S["scene"]
    faceforge.register()
    try:
        s = scene.faceforge
        s.preset, s.custom_names = "CUSTOM", ", ".join(POSES)
        s.start_frame, s.neutral_frame = 1, 0
        assert bpy.ops.faceforge.create_markers() == {"FINISHED"}
        assert [m[0] for m in markers.frames_from_markers(scene)] == POSES
        target = bake.make_target(S["head"])
        pair = s.pairs.add()
        pair.source, pair.target = S["head"], target
        assert bpy.ops.faceforge.bake() == {"FINISHED"}
        assert key_names(target) == ["Basis"] + POSES
        jaw = bake.key_coords(target.data.shape_keys.key_blocks["jawOpen"])
        assert np.allclose(jaw, S["jaw_ref"], atol=1e-6)
        s.split_width = 0.1
        assert bpy.ops.faceforge.split_all() == {"FINISHED"}
        assert "eyeBlinkLeft" in key_names(target) and "eyeBlink" not in key_names(target)
        s.csv_path = SAMPLE_CSV
        assert bpy.ops.faceforge.import_csv() == {"FINISHED"}
        assert target.data.shape_keys.animation_data.action is not None
        assert bpy.ops.faceforge.reset_keys() == {"FINISHED"}
        target.data.shape_keys.animation_data_clear()
        s.pairs.clear()
        bpy.data.objects.remove(target)
    finally:
        faceforge.unregister()
    assert not hasattr(scene, "faceforge")


def test_10_multi_target():
    """Head, both eyes and teeth get the same key list; each moves only where its bones do."""
    scene = S["scene"]
    markers.create_markers(scene, ["jawOpen", "eyeBlink", "browInnerUp", "eyeLookUp"])
    sources = [S["head"]] + S["eyes"] + [S["teeth"]]
    targets = [bake.make_target(o) for o in sources]
    frames = markers.frames_from_markers(scene)
    bake.bake_shapes(scene, list(zip(sources, targets)), frames, 0)
    expected = ["Basis", "jawOpen", "eyeBlink", "browInnerUp", "eyeLookUp"]
    for t in targets:
        assert key_names(t) == expected, (t.name, key_names(t))
    head_t, eye_l, eye_r, teeth_t = targets
    assert np.abs(delta(teeth_t, "jawOpen")).max() > 0.05
    assert np.abs(delta(teeth_t, "eyeLookUp")).max() < 1e-6
    for eye in (eye_l, eye_r):
        assert np.abs(delta(eye, "eyeLookUp")).max() > 0.01
        assert np.abs(delta(eye, "jawOpen")).max() < 1e-6
    assert np.abs(delta(head_t, "eyeLookUp")).max() < 1e-6
    # skip_empty: each mesh only keeps the shapes that move it.
    targets2 = [bake.make_target(o) for o in sources]
    bake.bake_shapes(scene, list(zip(sources, targets2)), frames, 0, skip_empty=True)
    assert key_names(targets2[3]) == ["Basis", "jawOpen"], key_names(targets2[3])
    assert key_names(targets2[1]) == ["Basis", "eyeLookUp"], key_names(targets2[1])
    for t in targets + targets2:
        bpy.data.objects.remove(t)


def test_11_split_midline_continuity():
    """No step across X = 0: weights are C1-smooth and the split of a midline shape is seamless."""
    width = 0.1
    xs = np.linspace(-0.3, 0.3, 6001)
    w = split.left_weight(xs, width)
    dx = xs[1] - xs[0]
    assert np.abs(np.diff(w)).max() <= 1.5 / (2 * width) * dx + 1e-9  # Lipschitz, no jump
    assert np.all(np.diff(w) >= 0)  # monotonic
    edge = split.left_weight(np.array([-width, -width + 1e-4, width - 1e-4, width]), width)
    assert abs(edge[1] - edge[0]) < 1e-6 and abs(edge[3] - edge[2]) < 1e-6  # flat ends (C1)

    t = S["head_t"]
    jaw = t.data.shape_keys.key_blocks["jawOpen"]
    chin = t.shape_key_add(name="chinTest", from_mix=False)
    bake.set_key_coords(chin, bake.key_coords(jaw))
    orig = delta(t, "chinTest")
    left, right = split.split_lr(t, "chinTest", width=width, suffix="BLENDER")
    assert (left, right) == ("chinTest.L", "chinTest.R")
    dl, dr = delta(t, left), delta(t, right)
    x = bake.key_coords(t.data.shape_keys.reference_key)[:, 0]
    band = (np.abs(x) < width) & (np.linalg.norm(orig, axis=1) > 1e-4)
    assert band.any()
    ratio = np.linalg.norm(dl[band], axis=1) / np.linalg.norm(orig[band], axis=1)
    assert np.all((ratio > 0) & (ratio < 1)), ratio  # partial weights inside the band
    mid = np.abs(x) < 1e-6
    assert np.allclose(dl[mid], dr[mid], atol=1e-6)  # both halves meet at the midline
    # Mirror check: Left at +x equals Right at the mirrored -x vertex (symmetric jaw shape).
    pos = np.where(x > 1e-6)[0]
    basis = bake.key_coords(t.data.shape_keys.reference_key)
    mirrored = basis[pos] * [-1, 1, 1]
    nearest = np.argmin(((basis[None, :, :] - mirrored[:, None, :]) ** 2).sum(-1), axis=1)
    flip = np.array([-1, 1, 1])
    assert np.allclose(dl[pos], dr[nearest] * flip, atol=1e-5)


def blender_python():
    """A real python executable for subprocess tests: the one bundled with Blender, else PATH."""
    import shutil
    for name in ("python.exe", "python3.13", "python3.12", "python3.11", "python"):
        p = os.path.join(sys.prefix, "bin", name)
        if os.path.isfile(p):
            return p
    return shutil.which("python3") or shutil.which("python")


STUB_OK = r"""import sys
a = sys.argv
out = a[a.index("-o") + 1]
assert "--model" in a and "--smooth" in a and "--neutral-seconds" in a and "--gain" in a, a
open(out, "w").write("time,jawOpen,eyeBlinkLeft,eyeBlinkRight\n0,0,0,0\n0.1,0.5,1,0\n0.2,1,0,1\n")
print("wrote " + out + ": 3 frames")
"""
STUB_FAIL = 'import sys; sys.exit("error: missing package (mediapipe). Install with: pip install -r requirements.txt")'


def test_12_video_helper_plumbing():
    """video.run: errors say what to do; a stub helper proves the command line and CSV hand-off."""
    py = blender_python()
    tmp = tempfile.mkdtemp()
    model, vid, out = (os.path.join(tmp, n) for n in ("m.task", "v.mp4", "o.csv"))
    for p in (model, vid):
        open(p, "w").close()
    for bad in [("", model), (os.path.join(tmp, "nope.exe"), model), (py, os.path.join(tmp, "no.task"))]:
        try:
            video.run(bad[0], bad[1], vid, out)
        except ValueError as e:
            assert "Setup:" in str(e) and "pip install mediapipe" in str(e), e
        else:
            raise AssertionError("expected ValueError")
    try:
        video.run(py, model, os.path.join(tmp, "missing.mp4"), out)
    except ValueError as e:
        assert "Video not found" in str(e), e
    else:
        raise AssertionError("expected ValueError")
    stub = os.path.join(tmp, "stub.py")
    open(stub, "w").write(STUB_FAIL)
    try:
        video.run(py, model, vid, out, script=stub)
    except ValueError as e:
        assert "missing package" in str(e) and "Setup:" in str(e), e
    else:
        raise AssertionError("expected ValueError")
    open(stub, "w").write(STUB_OK)
    assert "3 frames" in video.run(py, model, vid, out, script=stub)
    names, times, rows = mocap.read_csv(out)
    assert names == ["jawOpen", "eyeBlinkLeft", "eyeBlinkRight"] and rows.shape == (3, 3)
    S["stub"], S["tmp"], S["model"], S["video"] = stub, tmp, model, vid


def test_13_video_operator():
    """faceforge.video_to_face end to end with the stub helper: CSV written and keyed on the targets."""
    scene, head = S["scene"], S["head"]
    t = bake.make_target(head)
    bake.ensure_basis(t)
    for n in ("jawOpen", "eyeBlinkLeft"):
        t.shape_key_add(name=n, from_mix=False)
    saved = {k: os.environ.get(k) for k in ("FACEFORGE_PYTHON", "FACEFORGE_MODEL")}
    os.environ["FACEFORGE_PYTHON"], os.environ["FACEFORGE_MODEL"] = blender_python(), S["model"]
    old_script = video.SCRIPT
    video.SCRIPT = S["stub"]
    faceforge.register()
    try:
        s = scene.faceforge
        pair = s.pairs.add()
        pair.source, pair.target = head, t
        s.video_path = S["video"]
        assert bpy.ops.faceforge.video_to_face() == {"FINISHED"}
        assert s.csv_path.endswith("v_faceforge.csv") and os.path.isfile(s.csv_path)
        assert t.data.shape_keys.animation_data.action is not None
        jaw = t.data.shape_keys.key_blocks["jawOpen"]
        for frame, want in ((1, 0.0), (3, 0.5), (6, 1.0)):  # 24 fps: t = 0, 0.1, 0.2 s
            scene.frame_set(frame)
            assert abs(jaw.value - want) < 1e-5, (frame, jaw.value)
        os.environ["FACEFORGE_PYTHON"] = ""
        try:
            bpy.ops.faceforge.video_to_face()  # no python configured: clear error, nothing runs
        except RuntimeError as e:
            assert "Python for MediaPipe not found" in str(e), e
        else:
            raise AssertionError("expected an error report")
    finally:
        s.pairs.clear()
        faceforge.unregister()
        video.SCRIPT = old_script
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        t.data.shape_keys.animation_data_clear()
        scene.frame_set(7)
        bpy.data.objects.remove(t)


def test_14_video_real_mediapipe():
    """Optional (needs FACEFORGE_PYTHON with mediapipe+opencv and FACEFORGE_MODEL): the real helper
    must load the model, read a faceless video and report 'no face' cleanly."""
    py, model = os.environ.get("FACEFORGE_PYTHON"), os.environ.get("FACEFORGE_MODEL")
    if not (py and model and os.path.isfile(model)):
        print("  (skipped: set FACEFORGE_PYTHON and FACEFORGE_MODEL)")
        return
    import subprocess
    vid = os.path.join(S["tmp"], "blank.mp4")
    subprocess.run([py, "-c", "import cv2,numpy as np;w=cv2.VideoWriter(r'%s',cv2.VideoWriter_fourcc(*'mp4v'),"
                    "10,(320,240));[w.write(np.zeros((240,320,3),np.uint8)) for _ in range(5)];w.release()" % vid],
                   check=True)
    try:
        video.run(py, model, vid, os.path.join(S["tmp"], "blank.csv"))
    except ValueError as e:
        assert "no face detected" in str(e), e
    else:
        raise AssertionError("expected 'no face detected'")


def quality_mesh():
    """Unit sphere with hand-made keys: a good Left/Right pair, a bad pair, empty, crushed, flipped,
    one that pokes into the collider and one that moves away from it."""
    obj = sphere("QHead", 1.0, (0, 0, 0))
    obj.shape_key_add(name="Basis", from_mix=False)
    basis = bake.key_coords(obj.data.shape_keys.reference_key)
    x, z = basis[:, 0], basis[:, 2]
    up = np.array([0, 0, 0.1])

    def key(name, d):
        kb = obj.shape_key_add(name=name, from_mix=False)
        bake.set_key_coords(kb, basis + d)

    zero = np.zeros_like(basis)
    key("smileLeft", np.where((x > 0.3)[:, None], up, 0))
    key("smileRight", np.where((x < -0.3)[:, None], up, 0))
    key("blinkLeft", np.where((x > 0.3)[:, None], up, 0))
    key("blinkRight", np.where((x < -0.3)[:, None], up * 1.5, 0))  # 0.05 too strong
    key("nothing", zero)
    cap = z > 0.9
    key("crush", np.where(cap[:, None], (np.array([0, 0, 0.95]) - basis) * 0.95, 0))  # cap shrinks to a dot
    key("flip", np.where(cap[:, None], np.stack([-2 * x, zero[:, 1], zero[:, 2]], axis=1), 0))  # cap mirrored
    key("poke", np.where((z > 0.8)[:, None], -basis * 0.2, 0))
    key("away", np.where((z > 0.8)[:, None], basis * 0.2, 0))
    return obj


def test_15_quality_inspector():
    scene = S["scene"]
    q = quality_mesh()
    collider = sphere("QCollider", 0.9, (0, 0, 0))
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    rep = quality.inspect(q, dg, collider=collider)
    by = {r["name"]: r for r in rep["keys"]}
    assert rep["neutral_inside"] == 0 and rep["unmatched_vertices"] == 0, rep
    assert by["nothing"]["empty"] and "empty" in by["nothing"]["problems"]
    assert not by["smileLeft"]["empty"] and abs(by["smileLeft"]["max_delta"] - 0.1) < 1e-6
    assert by["smileLeft"]["sym_error"] < 1e-5 and by["smileRight"]["sym_error"] < 1e-5
    assert by["smileLeft"]["problems"] == [], by["smileLeft"]
    assert abs(by["blinkLeft"]["sym_error"] - 0.05) < 1e-5 and "asymmetric" in by["blinkLeft"]["problems"]
    assert by["nothing"]["sym_error"] is None
    assert by["crush"]["crushed"] > 0 and "crushed triangles" in by["crush"]["problems"]
    assert by["flip"]["flipped"] > 0 and "flipped normals" in by["flip"]["problems"]
    assert by["smileLeft"]["flipped"] == 0 and by["smileLeft"]["crushed"] == 0
    assert by["poke"]["inside"] > 0 and abs(by["poke"]["depth"] - 0.1) < 0.02, by["poke"]
    assert "inside collider" in by["poke"]["problems"]
    assert by["away"]["inside"] == 0 and by["smileLeft"]["inside"] == 0
    # vertex group restricts the collider test to those vertices
    vg = q.vertex_groups.new(name="low")
    vg.add([v.index for v in q.data.vertices if v.co.z < -0.5], 1.0, "REPLACE")
    rep2 = quality.inspect(q, dg, collider=collider, vertex_group="low")
    assert {r["name"]: r["inside"] for r in rep2["keys"]}["poke"] == 0
    try:
        quality.inspect(q, dg, collider=collider, vertex_group="nope")
    except ValueError as e:
        assert "nope" in str(e)
    else:
        raise AssertionError("expected ValueError")
    big = sphere("QBig", 1.05, (0, 0, 0))  # swallows the whole head already at neutral
    bpy.context.view_layer.update()
    rep3 = quality.inspect(q, bpy.context.evaluated_depsgraph_get(), collider=big)
    assert rep3["neutral_inside"] == len(q.data.vertices) and all(r["inside"] == 0 for r in rep3["keys"])
    bpy.data.objects.remove(big)
    # no collider: inside is never reported
    assert all(r["inside"] == 0 for r in quality.inspect(q, dg)["keys"])
    # report files
    tmp = tempfile.mkdtemp()
    import json
    txt, js = os.path.join(tmp, "r.txt"), os.path.join(tmp, "r.json")
    quality.write_report(rep, txt)
    quality.write_report([rep], js)
    text = open(txt, encoding="utf-8").read()
    assert "blinkLeft" in text and "!! blinkLeft" in text and "ok smileLeft" in text, text
    assert json.load(open(js, encoding="utf-8"))[0]["keys"][0]["name"] == "smileLeft"
    # heatmap
    attr = quality.delta_heatmap(q, "smileLeft")
    col = np.empty(len(q.data.vertices) * 4, dtype=np.float32)
    attr.data.foreach_get("color", col)
    col = col.reshape(-1, 4)
    moved = np.linalg.norm(bake.key_coords(q.data.shape_keys.key_blocks["smileLeft"]) -
                           bake.key_coords(q.data.shape_keys.reference_key), axis=1) > 1e-6
    assert np.allclose(col[moved][:, :3], [1, 0, 0], atol=1e-4) and np.allclose(col[~moved][:, :3], [0, 0, 1], atol=1e-4)
    assert q.data.color_attributes.active_color.name == "FF_delta_smileLeft"
    # operators
    faceforge.register()
    try:
        s = scene.faceforge
        s.pairs.clear()
        pair = s.pairs.add()
        pair.source = pair.target = q
        s.quality_collider, s.quality_group = collider, ""
        s.report_path = os.path.join(tmp, "op.json")
        assert bpy.ops.faceforge.inspect() == {"FINISHED"}
        assert len(s.report) == 9 and sum(i.bad for i in s.report) == 6, [(i.name, i.text) for i in s.report]
        assert json.load(open(s.report_path))[0]["object"] == "QHead"
        bpy.context.view_layer.objects.active = q
        q.active_shape_key_index = 2
        assert bpy.ops.faceforge.heatmap() == {"FINISHED"}
        assert "FF_delta_smileRight" in q.data.color_attributes
        s.pairs.clear()
        s.quality_collider = None
    finally:
        faceforge.unregister()
    quality.clear_heatmaps(q)
    assert len(q.data.color_attributes) == 0
    bpy.data.objects.remove(q)
    bpy.data.objects.remove(collider)


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main():
    build_scene()
    failed = 0
    for fn in TESTS:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"FaceForge tests: {len(TESTS) - failed} passed, {failed} failed")
    sys.stdout.flush()
    sys.exit(1 if failed else 0)


main()
