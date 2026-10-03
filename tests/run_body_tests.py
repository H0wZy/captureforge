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
from captureforge.body import apply, calibrate, profile, rigtools, solve  # noqa: E402

TMP = tempfile.mkdtemp()


def clean():
    """Empty scene between tests."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    for coll in (bpy.data.armatures, bpy.data.actions, bpy.data.meshes):
        for item in list(coll):
            coll.remove(item)
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
    assert [b.name for b in obj.data.bones] == ["mixamorig:" + n for n in profile.NAMES]
    for i, name in enumerate(profile.NAMES):
        bone = obj.data.bones["mixamorig:" + name]
        assert np.allclose(np.array(bone.head_local), profile.HEAD[i], atol=1e-5), name
        assert np.allclose(np.array(bone.tail_local), profile.TAIL[i], atol=1e-5), name
        assert np.allclose(np.array(bone.matrix_local.to_3x3()), profile.ROT[i], atol=1e-4), f"{name}: rest frame"
        expected = profile.BONES[i].parent
        assert (bone.parent.name[len("mixamorig:"):] if bone.parent else None) == expected, name
    plain = rigtools.create_reference_armature(name="Plain", prefix="")
    assert [b.name for b in plain.data.bones] == list(profile.NAMES)
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
    assert len(clip.times) == 105 and scene.frame_end == 105 and s.warnings == ""
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
