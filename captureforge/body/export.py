"""FBX export with the documented Unity Humanoid preset, and a read-back used by the tests (bpy).
Preset: specs/001-bodyforge-v1/contracts/unity-export-preset.md."""

import os
from contextlib import contextmanager

import bpy
import numpy as np
from mathutils import Quaternion, Vector

from . import apply, profile, rigtools

# What "Export for Unity" passes to the FBX exporter (see the contract for the reasons).
FBX_OPTIONS = {
    "use_selection": True, "object_types": {"ARMATURE"},
    "global_scale": 1.0, "apply_unit_scale": True, "apply_scale_options": "FBX_SCALE_NONE",
    "bake_space_transform": True, "axis_forward": "-Z", "axis_up": "Y",
    "primary_bone_axis": "Y", "secondary_bone_axis": "X", "add_leaf_bones": False,
    "use_armature_deform_only": True,
    "bake_anim": True, "bake_anim_use_all_bones": True, "bake_anim_use_nla_strips": False,
    "bake_anim_use_all_actions": False, "bake_anim_force_startend_keying": True,
    "bake_anim_step": 1.0, "bake_anim_simplify_factor": 0.0,
    "path_mode": "AUTO",
}


@contextmanager
def _rest_pose_frame(obj, scene):
    """Blender's FBX exporter writes each bone's static transform from the pose at the current frame, and Unity
    (and the importer) take that as the rest pose. Park the current frame one before the clip on a temporary
    rest-pose key, so the file carries the T-pose and the baked frames (the scene range) are untouched."""
    frame, rest_frame = scene.frame_current, scene.frame_start - 1
    keyed = []
    try:
        for bone in profile.NAMES:
            actual = next((b.name for b in obj.data.bones if profile.normalise(b.name) == bone), None)
            if actual is None:
                continue
            pb = obj.pose.bones[actual]
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = Quaternion((1, 0, 0, 0))
            pb.keyframe_insert("rotation_quaternion", frame=rest_frame)
            keyed.append((pb, "rotation_quaternion"))
            if bone == "Hips":
                pb.location = Vector((0, 0, 0))
                pb.keyframe_insert("location", frame=rest_frame)
                keyed.append((pb, "location"))
        scene.frame_set(rest_frame)
        yield
    finally:
        for pb, path in keyed:
            pb.keyframe_delete(path, frame=rest_frame)
        scene.frame_set(frame)


def export_unity(obj, path, include_meshes=False):
    """Export the armature and its current clip as an FBX Unity reads as a Humanoid animation. Refuses, listing
    the problems, when the armature does not match the profile. Returns a summary dict."""
    res = rigtools.validate(obj)
    if not res["ok"]:
        raise ValueError("Not exported: the armature does not match the Mixamo/Unity profile.\n" + rigtools.describe(res))
    if np.abs(np.array(obj.scale) - 1.0).max() > 1e-6:
        raise ValueError("Not exported: apply the armature's scale first (Object > Apply > Scale), "
                         "Unity needs a clip in meters at scale 1.")
    clip = apply.stored_clip(obj)
    scene = bpy.context.scene
    options = dict(FBX_OPTIONS)
    meshes = [c for c in obj.children_recursive if c.type == "MESH"] if include_meshes else []
    if meshes:
        options["object_types"] = {"ARMATURE", "MESH"}
    for other in list(bpy.context.view_layer.objects):
        if other is not None:
            other.select_set(False)
    for o in [obj] + meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obj
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with _rest_pose_frame(obj, scene):
        bpy.ops.export_scene.fbx(filepath=path, **options)
    return {"path": path, "frames": len(clip.times), "fps": float(clip.fps), "in_place": bool(clip.flags["in_place"]),
            "looped": bool(clip.flags["looped"]), "bones": len(obj.data.bones),
            "action": obj.animation_data.action.name, "frame_range": (scene.frame_start, scene.frame_end)}


def readback(path):
    """Import an FBX into the current scene, describe what came back, and remove it again. Returns a dict: the
    file's frame rate, bone names, parents and rest head positions (armature space), the animation's frame
    range, the hips head height and horizontal position per frame, and the left hand's height per frame."""
    scene = bpy.context.scene
    objects, armatures, actions = set(bpy.data.objects), set(bpy.data.armatures), set(bpy.data.actions)
    rate = (scene.render.fps, scene.render.fps_base)
    bpy.ops.import_scene.fbx(filepath=path, anim_offset=0.0)
    try:
        new = [o for o in bpy.data.objects if o not in objects]
        arm = next(o for o in new if o.type == "ARMATURE")
        bones = [b.name for b in arm.data.bones]
        info = {"fps": round(scene.render.fps / scene.render.fps_base, 3), "bones": bones,
                "parents": {b.name: b.parent.name if b.parent else None for b in arm.data.bones},
                "rest_heads": {b.name: tuple(arm.matrix_world @ b.head_local) for b in arm.data.bones}}
        action = arm.animation_data.action
        first, last = (int(round(v)) for v in action.frame_range)
        info["frame_range"] = (first, last)
        hips = next(n for n in bones if profile.normalise(n) == "Hips")
        hand = next(n for n in bones if profile.normalise(n) == "LeftHand")
        z, xy, hand_z = [], [], []
        for frame in range(first, last + 1):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            head = arm.matrix_world @ arm.pose.bones[hips].head
            z.append(head.z)
            xy.append((head.x, head.y))
            hand_z.append((arm.matrix_world @ arm.pose.bones[hand].head).z)
        info["hips_z"], info["hips_xy"], info["left_hand_z"] = z, xy, hand_z
        if info["fps"] == int(info["fps"]):
            info["fps"] = int(info["fps"])
        return info
    finally:
        for o in [o for o in bpy.data.objects if o not in objects]:
            bpy.data.objects.remove(o)
        for a in [a for a in bpy.data.armatures if a not in armatures]:
            bpy.data.armatures.remove(a)
        for a in [a for a in bpy.data.actions if a not in actions]:
            bpy.data.actions.remove(a)
        scene.render.fps, scene.render.fps_base = rate
