"""Headless BodyForge tests inside Blender: reference armature, profile validation, applying clips, operators,
export. The pure maths is covered by tests/test_body_*.py; here the Blender side must agree with it.

blender --background --factory-startup --python tests/run_body_tests.py
Prints PASS/FAIL per test and a summary line; exits non-zero on any failure.

Optional real-MediaPipe test: set BODYFORGE_PYTHON (a venv python with mediapipe and opencv-python) and
BODYFORGE_POSE_MODEL (a pose_landmarker .task file); otherwise it is skipped.
"""

import math
import os
import sys
import tempfile
import traceback

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # repo root, so "import captureforge" finds the package
sys.path.insert(0, HERE)

import captureforge  # noqa: E402
import fixtures_body as fx  # noqa: E402
from captureforge.body import apply, calibrate, clipops, export, profile, rigtools, solve  # noqa: E402

TMP = tempfile.mkdtemp()


def clean():
    """Empty scene between tests."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    for coll in (bpy.data.armatures, bpy.data.actions, bpy.data.meshes):
        for item in list(coll):
            coll.remove(item)
    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = 30, 1.0
    scene.frame_start, scene.frame_end = 1, 250
    bpy.context.view_layer.update()


def solved_hands_up():
    clip = fx.hands_up_clip(neutral=30, raise_=20, hold=10)
    lm = clip.landmarks()
    return solve.solve(lm, calibrate.calibrate(lm, 1.0))


def angle_deg(a, b):
    """Angle between two 3x3 rotation matrices (numpy)."""
    return math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(a.T @ b) - 1) / 2))))


# ---------------------------------------------------------------- reference armature and profile validation

def test_01_reference_armature_has_the_profile_bones_in_t_pose():
    clean()
    obj = fx.implemented(rigtools.create_reference_armature())
    assert obj.type == "ARMATURE" and obj.name in bpy.context.scene.objects
    assert sorted(b.name for b in obj.data.bones) == sorted("mixamorig:" + n for n in profile.NAMES)
    for i, name in enumerate(profile.NAMES):
        bone = obj.data.bones["mixamorig:" + name]
        assert np.allclose(np.array(bone.head_local), profile.HEAD[i], atol=1e-5), name
        assert np.allclose(np.array(bone.tail_local), profile.TAIL[i], atol=1e-5), name
        assert np.allclose(np.array(bone.matrix_local.to_3x3()), profile.ROT[i], atol=1e-4), f"{name}: rest frame"
        expected = profile.BONES[i].parent
        assert (bone.parent.name[len("mixamorig:"):] if bone.parent else None) == expected, name
    plain = rigtools.create_reference_armature(name="Plain", prefix="")
    assert sorted(b.name for b in plain.data.bones) == sorted(profile.NAMES)
    assert plain.name != obj.name


def test_02_validation_lists_missing_extra_and_misparented_bones():
    clean()
    obj = rigtools.create_reference_armature()
    res = fx.implemented(rigtools.validate(obj))
    assert res["ok"] and res["missing"] == [] and res["extra"] == [] and res["misparented"] == [], res
    assert res["rest_off"] == [], res
    plain = rigtools.create_reference_armature(name="Plain", prefix="")
    assert rigtools.validate(plain)["ok"], "names without the mixamorig: prefix are accepted"

    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    eb = obj.data.edit_bones
    eb.remove(eb["mixamorig:LeftForeArm"])  # also its children lose their parent
    extra = eb.new("Prop_Handle")
    extra.head, extra.tail = Vector((0, 0, 0)), Vector((0, 0, 0.1))
    eb["mixamorig:RightHand"].parent = eb["mixamorig:RightArm"]  # skips the forearm
    eb.remove(eb["mixamorig:Spine1"])  # optional bones may be absent when their children hang off the next one up
    eb.remove(eb["mixamorig:Spine2"])
    for child in ("Neck", "LeftShoulder", "RightShoulder"):
        eb["mixamorig:" + child].parent = eb["mixamorig:Spine"]
    bpy.ops.object.mode_set(mode="OBJECT")
    res = rigtools.validate(obj)
    assert not res["ok"] and res["missing"] == ["LeftForeArm"], res
    assert res["extra"] == ["Prop_Handle"], res
    assert any(b == "RightHand" for b, *_ in res["misparented"]), res["misparented"]
    assert not any(b in ("Neck", "LeftShoulder") for b, *_ in res["misparented"]), "absent optional bones are fine"
    assert "Spine1" in res["optional_missing"]
    text = rigtools.describe(res)
    assert "LeftForeArm" in text and "Prop_Handle" in text and "RightHand" in text, text


def test_03_validation_flags_a_rest_pose_that_is_not_a_t_pose():
    clean()
    obj = fx.implemented(rigtools.create_reference_armature())
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    for name, sign in (("LeftArm", 1), ("RightArm", -1)):  # an A-pose: arms 35 degrees down
        e = obj.data.edit_bones["mixamorig:" + name]
        length = (e.tail - e.head).length
        e.tail = e.head + Vector((sign * math.cos(math.radians(35)), 0, -math.sin(math.radians(35)))) * length
    bpy.ops.object.mode_set(mode="OBJECT")
    res = rigtools.validate(obj)
    assert not res["ok"] and {b for b, _ in res["rest_off"]} >= {"LeftArm", "RightArm"}, res
    assert all(deg > 30 for b, deg in res["rest_off"] if b in ("LeftArm", "RightArm")), res["rest_off"]
    assert "T-pose" in rigtools.describe(res)


# ---------------------------------------------------------------- applying a clip

def test_04_applying_a_clip_writes_one_key_set_per_frame_and_poses_the_rig():
    clean()
    obj = rigtools.create_reference_armature()
    clip = solved_hands_up()
    m = len(clip.times)
    act = fx.implemented(apply.write_clip(obj, clip, name="HandsUp"))
    scene = bpy.context.scene
    assert obj.animation_data.action == act and act.name == "HandsUp"
    assert scene.render.fps == 30 and tuple(act.frame_range) == (1.0, float(m)), (scene.render.fps, act.frame_range)
    path = 'pose.bones["mixamorig:LeftArm"].rotation_quaternion'
    curves = [fc for fc in apply.fcurves(act) if fc.data_path == path]
    assert len(curves) == 4 and all(len(fc.keyframe_points) == m for fc in curves), "a key per frame, four channels"
    hips = [fc for fc in apply.fcurves(act) if fc.data_path == 'pose.bones["mixamorig:Hips"].location']
    assert len(hips) == 3 and all(len(fc.keyframe_points) == m for fc in hips)
    G, head = solve.fk(clip.rot, clip.hips_pos)
    for frame in (0, m // 2, m - 1):  # Blender's own pose evaluation must agree with the solver's forward kinematics
        scene.frame_set(1 + frame)
        bpy.context.view_layer.update()
        for i, name in enumerate(profile.NAMES):
            pb = obj.pose.bones["mixamorig:" + name]
            want = G[frame, i] @ profile.ROT[i]
            assert angle_deg(np.array(pb.matrix.to_3x3()), want) < 0.2, (frame, name)
            assert np.linalg.norm(np.array(pb.head) - head[frame, i]) < 1e-3, (frame, name, tuple(pb.head), head[frame, i])
    assert all(obj.pose.bones["mixamorig:" + n].rotation_mode == "QUATERNION" for n in profile.NAMES)


def test_05_raw_and_current_clips_are_stored_on_the_action_and_read_back():
    clean()
    obj = rigtools.create_reference_armature()
    clip = solved_hands_up()
    act = apply.write_clip(obj, clip, name="Stored", raw=True)
    back = fx.implemented(apply.read_clip(act, "raw"))
    assert back.fps == clip.fps and back.rot.shape == clip.rot.shape
    assert np.allclose(back.rot, clip.rot, atol=1e-6) and np.allclose(back.hips_pos, clip.hips_pos, atol=1e-6)
    assert np.allclose(back.conf, clip.conf, atol=1e-6) and back.flags == clip.flags
    assert apply.read_clip(act, "clip").rot.shape == clip.rot.shape
    assert apply.read_clip(bpy.data.actions.new("foreign"), "raw") is None


def test_06_retargeting_follows_the_armatures_own_rest_frames():
    """A rig whose bones carry a roll still gets the same pose: the global orientation must not change."""
    clean()
    plain = fx.implemented(rigtools.create_reference_armature(prefix=""))
    rolled = rigtools.create_reference_armature(name="Rolled", prefix="")
    bpy.context.view_layer.objects.active = rolled
    bpy.ops.object.mode_set(mode="EDIT")
    for eb in rolled.data.edit_bones:
        eb.roll += math.radians(40)
    bpy.ops.object.mode_set(mode="OBJECT")
    clip = solved_hands_up()
    apply.write_clip(plain, clip, name="A")
    apply.write_clip(rolled, clip, name="B")
    scene = bpy.context.scene
    for frame in (1, 40):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        for name in profile.NAMES:
            a = np.array(plain.pose.bones[name].matrix.to_3x3())
            b = np.array(rolled.pose.bones[name].matrix.to_3x3())
            # same bone direction, whatever the roll
            assert np.allclose(a[:, 1], b[:, 1], atol=1e-3), (frame, name)


# ---------------------------------------------------------------- operators

def test_07_operators_create_the_reference_rig_and_solve_a_landmark_file():
    clean()
    scene = bpy.context.scene
    assert bpy.ops.bodyforge.create_reference() == {"FINISHED"}
    s = scene.bodyforge
    arm = fx.implemented(s.armature)
    assert arm.name in scene.objects and rigtools.validate(arm)["ok"]
    s.landmarks_path = fx.hands_up_clip(neutral=45, raise_=30, hold=30).save(os.path.join(TMP, "hu.npz"))
    assert bpy.ops.bodyforge.landmarks_to_body() == {"FINISHED"}
    act = arm.animation_data.action
    clip = apply.read_clip(act, "raw")
    assert len(clip.times) == 105 and scene.frame_end == 105
    assert "neutral" not in s.warnings and "No person" not in s.warnings, s.warnings  # raised hands leave the picture
    _, head = solve.fk(clip.rot, clip.hips_pos)
    ix = profile.INDEX
    assert head[-1, ix["LeftHand"], 2] > head[-1, ix["Head"], 2] + 0.2, "wrists above the head"
    scene.frame_set(105)
    bpy.context.view_layer.update()
    assert arm.pose.bones["mixamorig:LeftHand"].head.z > arm.pose.bones["mixamorig:Head"].head.z + 0.2


def test_08_missing_helper_gives_the_setup_text_and_nothing_breaks():
    clean()
    saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith(("BODYFORGE_", "FACEFORGE_"))}
    try:
        s = bpy.context.scene.bodyforge
        s.video_path = os.path.join(TMP, "clip.mp4")
        open(s.video_path, "wb").write(b"x")
        s.armature = rigtools.create_reference_armature()
        for op in (bpy.ops.bodyforge.video_to_body, bpy.ops.bodyforge.check_helper):
            try:
                op()
            except RuntimeError as e:
                assert "Install helper" in str(e) and "Python for the pose helper not found" in str(e), str(e)
            else:
                raise AssertionError("expected the setup message")
        assert bpy.ops.bodyforge.create_reference() == {"FINISHED"}, "the rest of the add-on keeps working"
    finally:
        os.environ.update(saved)


def test_09_an_armature_that_does_not_match_is_refused_with_a_bone_list():
    clean()
    s = bpy.context.scene.bodyforge
    arm = rigtools.create_reference_armature()
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    arm.data.edit_bones.remove(arm.data.edit_bones["mixamorig:RightLeg"])
    bpy.ops.object.mode_set(mode="OBJECT")
    s.armature = arm
    s.landmarks_path = fx.hands_up_clip(neutral=45, raise_=10, hold=5).save(os.path.join(TMP, "hu2.npz"))
    try:
        bpy.ops.bodyforge.landmarks_to_body()
    except RuntimeError as e:
        assert "RightLeg" in str(e), str(e)
    else:
        raise AssertionError("expected a refusal")
    assert arm.animation_data is None or arm.animation_data.action is None


def test_10_install_helper_shows_the_plan_first():
    from captureforge.body import ops
    text = fx.implemented(ops.install_plan(bpy.context))
    assert "storage.googleapis.com" in text and "mediapipe" in text and "Run it again with --yes" in text


def noisy_setup(name, noise=0.01):
    """Reference rig with a solved noisy hands-up clip on it (through the operator)."""
    clean()
    scene = bpy.context.scene
    bpy.ops.bodyforge.create_reference()
    s = scene.bodyforge
    s.landmarks_path = fx.hands_up_clip(neutral=45, raise_=30, hold=30, noise=noise).save(os.path.join(TMP, name + ".npz"))
    assert bpy.ops.bodyforge.landmarks_to_body() == {"FINISHED"}
    return s, s.armature


def jitter(a):
    return float(np.mean(np.abs(a[2:] - 2 * a[1:-1] + a[:-2])))


def test_12_cleanup_smooths_from_the_raw_clip_and_can_be_repeated():
    s, arm = noisy_setup("noisy")
    raw = apply.read_clip(arm.animation_data.action, "raw")
    assert bpy.ops.bodyforge.cleanup() == {"FINISHED"}
    act = arm.animation_data.action
    out = apply.read_clip(act, "clip")
    assert out.rot.shape == raw.rot.shape and not np.allclose(out.rot, raw.rot)
    assert jitter(out.rot) < 0.5 * jitter(raw.rot), (jitter(out.rot), jitter(raw.rot))
    assert out.contact.any(), "planted feet found"
    assert np.allclose(apply.read_clip(act, "raw").rot, raw.rot, atol=1e-6), "the raw clip is kept"
    s.smooth_mode = "PREVIEW"
    assert bpy.ops.bodyforge.cleanup() == {"FINISHED"}
    assert apply.read_clip(arm.animation_data.action, "raw") is not None
    scene = bpy.context.scene
    scene.frame_set(105)
    bpy.context.view_layer.update()
    assert arm.pose.bones["mixamorig:LeftHand"].head.z > arm.pose.bones["mixamorig:Head"].head.z


def test_13_report_writes_json_and_a_filmstrip_png_blender_can_load():
    s, arm = noisy_setup("rep")
    bpy.ops.bodyforge.cleanup()
    assert bpy.ops.bodyforge.report() == {"FINISHED"}
    base = os.path.join(TMP, "rep")
    from captureforge.body import report
    rep = report.read(base + ".report.json")
    assert rep["frames"] == 105 and set(rep["skate_cm_s"]) == {"left", "right"} and "LeftForeArm" in rep["bone_drift"]
    assert "Foot skate" in s.report_text and "Jitter" in s.report_text
    img = bpy.data.images.load(base + ".filmstrip.png")
    assert tuple(img.size) == (960, 440), tuple(img.size)


def test_14_edit_operators_trim_loop_in_place_and_mirror():
    s, arm = noisy_setup("edit", noise=0.0)
    scene = bpy.context.scene
    s.trim_start, s.trim_end = 10, 59
    assert bpy.ops.bodyforge.trim() == {"FINISHED"}
    clip = apply.read_clip(arm.animation_data.action, "clip")
    assert len(clip.times) == 50 and scene.frame_end == scene.frame_start + 49
    s.loop_blend_frames = 6
    assert bpy.ops.bodyforge.loop() == {"FINISHED"}
    clip = apply.read_clip(arm.animation_data.action, "clip")
    assert np.abs(np.sum(clip.rot[-1] * clip.rot[0], axis=-1)).min() > 1 - 1e-6 and clip.flags["looped"]
    assert bpy.ops.bodyforge.mirror() == {"FINISHED"} and bpy.ops.bodyforge.in_place() == {"FINISHED"}
    mirrored = apply.read_clip(arm.animation_data.action, "clip")
    assert mirrored.flags["mirrored"] and mirrored.flags["in_place"]
    ix = profile.INDEX
    _, head = solve.fk(mirrored.rot, mirrored.hips_pos)
    assert head[0, ix["RightHand"], 2] < head[0, ix["Head"], 2]
    s.trim_start, s.trim_end = 20, 10
    try:
        bpy.ops.bodyforge.trim()
    except RuntimeError as e:
        assert "End must be after Start" in str(e)
    else:
        raise AssertionError("expected a refusal")
    clean()
    bpy.ops.bodyforge.create_reference()
    try:
        bpy.ops.bodyforge.cleanup()
    except RuntimeError as e:
        assert "no BodyForge clip" in str(e), str(e)
    else:
        raise AssertionError("expected a refusal")


# ---------------------------------------------------------------- export for Unity

def exported(name, noise=0.0, in_place=True, helper_bone=False):
    """Solved (and cleaned) hands-up clip on the reference rig, exported; returns (armature, clip, path)."""
    s, arm = noisy_setup(name, noise)
    if in_place:
        assert bpy.ops.bodyforge.cleanup() == {"FINISHED"}
    if helper_bone:
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        eb = arm.data.edit_bones.new("IK_Helper")
        eb.head, eb.tail, eb.use_deform = Vector((0.5, 0, 0.2)), Vector((0.5, 0, 0.3)), False
        bpy.ops.object.mode_set(mode="OBJECT")
    path = os.path.join(TMP, name + ".fbx")
    info = fx.implemented(export.export_unity(arm, path))
    return arm, apply.read_clip(arm.animation_data.action, "clip"), path, info


def test_15_export_options_follow_the_documented_unity_preset():
    o = fx.implemented(export.FBX_OPTIONS)
    expected = {"add_leaf_bones": False, "use_armature_deform_only": True, "bake_anim": True,
                "bake_anim_use_nla_strips": False, "bake_anim_use_all_actions": False, "bake_anim_simplify_factor": 0.0,
                "bake_space_transform": True, "axis_forward": "-Z", "axis_up": "Y", "primary_bone_axis": "Y",
                "secondary_bone_axis": "X", "global_scale": 1.0, "use_selection": True}
    for key, value in expected.items():
        assert o[key] == value, (key, o.get(key), value)
    assert o["object_types"] == {"ARMATURE"}


def test_16_exported_fbx_reads_back_with_the_humanoid_bones_rest_pose_rate_and_hips_track():
    arm, clip, path, info = exported("unity", noise=0.004, helper_bone=True)
    assert os.path.getsize(path) > 1000 and info["frames"] == 105 and info["fps"] == 30.0 and info["in_place"]
    scene = bpy.context.scene
    scene.render.fps = 24  # the read-back must bring the file's own rate
    objects_before = {o.name for o in bpy.data.objects}
    back = fx.implemented(export.readback(path))
    assert back["fps"] == 30, back["fps"]
    names = [profile.normalise(n) for n in back["bones"]]
    assert sorted(names) == sorted(profile.NAMES), "22 profile bones, no leaf bones, no non-deform helper"
    assert profile.REQUIRED <= set(names)
    for bone, parent in back["parents"].items():
        assert (profile.normalise(parent) if parent else None) == profile.BONES[profile.INDEX[profile.normalise(bone)]].parent
    for name, head in back["rest_heads"].items():
        assert np.linalg.norm(np.array(head) - profile.HEAD[profile.INDEX[profile.normalise(name)]]) < 2e-3, name
    assert back["frame_range"] == (1, 105), back["frame_range"]
    _, head = solve.fk(clip.rot, clip.hips_pos)
    assert np.abs(np.array(back["hips_z"]) - clip.hips_pos[:, 2]).max() < 2e-3, "hips height track"
    assert np.abs(np.array(back["left_hand_z"]) - head[:, profile.INDEX["LeftHand"], 2]).max() < 2e-3, "the pose survives"
    hips_xy = np.array(back["hips_xy"])
    assert np.ptp(hips_xy, axis=0).max() < 1e-4, "an in-place clip has no horizontal drift"
    assert {o.name for o in bpy.data.objects} == objects_before and scene.render.fps == 24, "the read-back cleans up"


def test_17_a_wrong_armature_is_refused_with_the_bone_list_and_nothing_is_written():
    s, arm = noisy_setup("refuse")
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    arm.data.edit_bones.remove(arm.data.edit_bones["mixamorig:LeftHand"])
    extra = arm.data.edit_bones.new("Tail_Helper")
    extra.head, extra.tail = Vector((0, 0, 0)), Vector((0, 0, 0.1))
    bpy.ops.object.mode_set(mode="OBJECT")
    path = os.path.join(TMP, "refused.fbx")
    try:
        export.export_unity(arm, path)
    except ValueError as e:
        assert "LeftHand" in str(e) and "Tail_Helper" in str(e), str(e)
    else:
        raise AssertionError("expected a refusal")
    s.export_path = path
    try:
        bpy.ops.bodyforge.export_unity()
    except RuntimeError as e:
        assert "LeftHand" in str(e)
    else:
        raise AssertionError("expected a refusal from the operator too")
    assert not os.path.exists(path)


def test_18_export_operator_writes_the_file_and_warns_about_scale():
    s, arm = noisy_setup("opexp", noise=0.0)
    s.export_path = os.path.join(TMP, "op.fbx")
    assert bpy.ops.bodyforge.export_unity() == {"FINISHED"} and os.path.isfile(s.export_path)
    arm.scale = (2, 2, 2)
    try:
        bpy.ops.bodyforge.export_unity()
    except RuntimeError as e:
        assert "scale" in str(e).lower()
    else:
        raise AssertionError("expected the scale refusal")


def test_19_hands_flow_through_the_operator_to_the_finger_bones():
    clean()
    scene = bpy.context.scene
    bpy.ops.bodyforge.create_reference()
    s = scene.bodyforge
    arm = s.armature
    assert len(arm.data.bones) == len(profile.NAMES) == 52, "the reference rig has fingers"
    closed = dict(fx.NEUTRAL, **{f"LeftHand{f}{k}": (-a, 0, 0) for f in ("Index", "Middle", "Ring", "Pinky")
                                 for k, a in enumerate((80, 90, 60), 1)})
    frames = [dict(fx.NEUTRAL)] * 45 + [closed] * 20
    s.landmarks_path = fx.motion(frames, hands=True).save(os.path.join(TMP, "hands.npz"))
    s.use_hands = True
    assert bpy.ops.bodyforge.landmarks_to_body() == {"FINISHED"} and s.warnings == ""
    clip = apply.read_clip(arm.animation_data.action, "raw")
    assert clip.flags["fingers"] is True
    _, head = solve.fk(clip.rot, clip.hips_pos)
    scene.frame_set(60)
    bpy.context.view_layer.update()
    for name in ("LeftHandIndex2", "LeftHandIndex3", "LeftHandPinky3"):
        i = profile.INDEX[name]
        got = np.array(arm.pose.bones["mixamorig:" + name].head)
        assert np.linalg.norm(got - head[59, i]) < 1e-3, (name, got, head[59, i])
    open_tip = np.array(arm.pose.bones["mixamorig:RightHandIndex3"].tail)
    scene.frame_set(1)
    bpy.context.view_layer.update()
    assert np.linalg.norm(np.array(arm.pose.bones["mixamorig:LeftHandIndex3"].tail) - open_tip * [-1, 1, 1]) < 1e-3
    s.landmarks_path = fx.motion(frames).save(os.path.join(TMP, "nohands.npz"))  # hands on, but the file has none
    assert bpy.ops.bodyforge.landmarks_to_body() == {"FINISHED"} and "no hand data" in s.warnings
    s.use_hands = False
    s.video_path = os.path.join(TMP, "clip2.mp4")
    open(s.video_path, "wb").write(b"x")
    s.use_hands = True
    os.environ.pop("BODYFORGE_HAND_MODEL", None)
    try:
        bpy.ops.bodyforge.video_to_body()
    except RuntimeError as e:
        assert "hand model" in str(e) or "Python for the pose helper" in str(e)
    else:
        raise AssertionError("expected the setup message")


def test_20_body_and_face_share_one_timeline_and_a_tiny_face_is_skipped():
    import importlib
    from captureforge.body import ops as body_ops
    face_video = importlib.import_module("captureforge.face.video")
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "captureforge", "body", "helpers"))
    import pose_to_landmarks as ptl
    clean()
    scene = bpy.context.scene
    bpy.ops.bodyforge.create_reference()
    s = scene.bodyforge
    clip = fx.hands_up_clip(neutral=45, raise_=30, hold=30)
    size = clip.size

    def boxes(scale):
        out = []
        for row in clip.pose_image:
            box = ptl.head_box(row, size)
            c = np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])
            half = np.array([(box[2] - box[0]) / 2, (box[3] - box[1]) / 2]) * scale
            out.append([c[0] - half[0], c[1] - half[1], c[0] + half[0], c[1] + half[1]])
        return np.array(out, np.float32)

    s.landmarks_path = clip.save(os.path.join(TMP, "face_ok.npz"), head_box=boxes(1.0))
    assert bpy.ops.bodyforge.landmarks_to_body() == {"FINISHED"}
    body_action = s.armature.animation_data.action
    head = bpy.data.objects.new("FaceMesh", bpy.data.meshes.new("FaceMesh"))
    head.data.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    bpy.context.scene.collection.objects.link(head)
    head.shape_key_add(name="Basis")
    head.shape_key_add(name="jawOpen")
    bpy.context.view_layer.objects.active = head
    calls = []

    def fake_run(python, model, video, out_csv, smooth=0.3, neutral_seconds=2.0, gain=1.0, script=None, timeout=None,
                 crop=None):
        calls.append(crop)
        with open(out_csv, "w", newline="") as f:
            f.write("time,jawOpen\n" + "".join(f"{i / 30.0:.6f},{(i % 10) / 10.0}\n" for i in range(105)))
        return "fake"

    video = os.path.join(TMP, "face.mp4")
    open(video, "wb").write(b"x")
    real_run, face_video.run = face_video.run, fake_run
    try:
        msg = body_ops.apply_face(bpy.context, video, s.landmarks_path)
        assert calls == [s.landmarks_path], "the face tracker runs on the head box of the body landmarks"
        keys = head.data.shape_keys.animation_data.action
        body_range = tuple(int(v) for v in body_action.frame_range)
        face_range = tuple(int(v) for v in keys.frame_range)
        assert face_range == body_range == (1, 105), (face_range, body_range)
        assert scene.render.fps == 30 and "jawOpen" in msg or "keys animated" in msg

        calls.clear()
        s.landmarks_path = clip.save(os.path.join(TMP, "face_tiny.npz"), head_box=boxes(0.3))
        msg = body_ops.apply_face(bpy.context, video, s.landmarks_path)
        assert calls == [] and "too small" in msg and "skipped" in msg, msg
        assert s.armature.animation_data.action == body_action, "the body result is unaffected"
    finally:
        face_video.run = real_run


def test_11_real_mediapipe_end_to_end():
    python, model = os.environ.get("BODYFORGE_PYTHON"), os.environ.get("BODYFORGE_POSE_MODEL")
    if not (python and model and os.path.isfile(python) and os.path.isfile(model)):
        print("  (skipped: set BODYFORGE_PYTHON and BODYFORGE_POSE_MODEL)")
        return
    import subprocess
    import time
    clean()
    video = os.path.join(TMP, "mannequin.mp4")
    subprocess.run([python, os.path.join(HERE, "make_mannequin_video.py"), video], check=True)
    s = bpy.context.scene.bodyforge
    s.armature = rigtools.create_reference_armature()
    s.video_path = video
    t0 = time.time()
    assert bpy.ops.bodyforge.video_to_body() == {"FINISHED"}
    took = time.time() - t0
    clip = apply.read_clip(s.armature.animation_data.action, "raw")
    _, head = solve.fk(clip.rot, clip.hips_pos)
    ix = profile.INDEX
    assert len(clip.times) == 105 and os.path.isfile(os.path.splitext(video)[0] + ".landmarks.npz")
    assert head[0, ix["LeftHand"], 2] < head[0, ix["Head"], 2], "hands start down"
    assert head[-1, ix["LeftHand"], 2] > head[-1, ix["Head"], 2] + 0.2, "left wrist above the head at the end"
    assert head[-1, ix["RightHand"], 2] > head[-1, ix["Head"], 2] + 0.2, "right wrist above the head at the end"
    print(f"  real MediaPipe path: 105 frames in {took:.1f} s")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main():
    captureforge.register()
    failed = 0
    for fn in TESTS:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"BodyForge tests: {len(TESTS) - failed} passed, {failed} failed")
    sys.stdout.flush()
    sys.exit(1 if failed else 0)


main()
