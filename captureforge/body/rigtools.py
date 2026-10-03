"""Armature helpers (bpy): build the reference Mixamo armature, validate a user armature against the profile,
and read the armature's own rest frames for retargeting."""

import math

import bpy
import numpy as np
from mathutils import Vector

from . import profile

ARM_BONES = ("Arm", "ForeArm", "Hand")
TOLERANCE = 10.0  # degrees of rest-pose direction error accepted on the arms; twice that elsewhere


def create_reference_armature(name="BodyForge Reference", prefix="mixamorig:"):
    """A T-pose armature with the Mixamo bone names (`prefix` + name), 1 m hips, feet on the floor.
    Linked to the active scene; uses the active view layer to enter edit mode."""
    arm = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, arm)
    bpy.context.scene.collection.objects.link(obj)
    for other in list(bpy.context.view_layer.objects):
        if other is not None:
            other.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        made = {}
        for i, bone in enumerate(profile.BONES):
            eb = arm.edit_bones.new(prefix + bone.name)
            eb.head, eb.tail, eb.roll = Vector(profile.HEAD[i]), Vector(profile.TAIL[i]), 0.0
            if bone.parent:
                eb.parent = made[bone.parent]
                eb.use_connect = bool(np.allclose(profile.HEAD[i], profile.TAIL[profile.INDEX[bone.parent]]))
            made[bone.name] = eb
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    return obj


def _present(obj):
    """{profile name: Bone} for the armature's bones that the profile knows."""
    found = {}
    for b in obj.data.bones:
        n = profile.normalise(b.name)
        if n in profile.INDEX and n not in found:
            found[n] = b
    return found


def _expected_parent(name, present):
    """The profile parent of `name`, skipping optional bones the armature does not have."""
    p = profile.BONES[profile.INDEX[name]].parent
    while p is not None and p not in present and not profile.BONES[profile.INDEX[p]].required:
        p = profile.BONES[profile.INDEX[p]].parent
    return p


def validate(obj, tolerance=TOLERANCE):
    """Compare an armature with the profile. Returns a dict: `ok`, `missing` (required bones that are absent),
    `extra` (names the profile does not know), `misparented` [(bone, expected parent, found parent)],
    `rest_off` [(bone, degrees)] for rest directions that differ from the T-pose, `optional_missing`."""
    present = _present(obj)
    missing, extra = profile.validate([b.name for b in obj.data.bones])
    misparented, rest_off = [], []
    for name, bone in present.items():
        expected = _expected_parent(name, present)
        actual = profile.normalise(bone.parent.name) if bone.parent else None
        if actual is not None and actual not in profile.INDEX:
            continue  # parented to a helper bone: reported as extra
        if actual != expected:
            misparented.append((name, expected, actual))
        d = np.array(bone.tail_local - bone.head_local)
        d /= max(np.linalg.norm(d), 1e-9)
        deg = math.degrees(math.acos(max(-1.0, min(1.0, float(d @ profile.DIR[profile.INDEX[name]])))))
        limit = tolerance if name.endswith(ARM_BONES) else 2 * tolerance
        if deg > limit:
            rest_off.append((name, round(deg, 1)))
    optional = [n for n in profile.NAMES if n not in present and n not in profile.REQUIRED]
    return {"ok": not (missing or misparented or rest_off), "missing": missing, "extra": extra,
            "misparented": misparented, "rest_off": rest_off, "optional_missing": optional}


def describe(res):
    """Plain-text list of what is wrong, for the panel and the export refusal."""
    lines = []
    if res["missing"]:
        lines.append("Missing required bones: " + ", ".join(res["missing"]))
    if res["extra"]:
        lines.append("Bones the profile does not know: " + ", ".join(res["extra"]))
    for bone, expected, actual in res["misparented"]:
        lines.append(f"Wrong parent: {bone} should be under {expected}, found {actual}")
    for bone, deg in res["rest_off"]:
        lines.append(f"Rest pose is not a T-pose: {bone} is {deg:g} degrees off")
    return "\n".join(lines) or "The armature matches the Mixamo/Unity profile."


def rig_info(obj):
    """What retargeting needs from an armature: per profile bone the actual name, whether it is present,
    its rest frame in armature space, its parent as a profile index, plus the Hips rest head."""
    present = _present(obj)
    B = len(profile.BONES)
    names, have = [None] * B, np.zeros(B, bool)
    rest = profile.ROT.copy()
    parent = np.full(B, -1)
    for name, bone in present.items():
        i = profile.INDEX[name]
        names[i], have[i] = bone.name, True
        rest[i] = np.array(bone.matrix_local.to_3x3())
        if bone.parent:
            parent[i] = profile.INDEX.get(profile.normalise(bone.parent.name), -1)
    hips_head = np.array(present["Hips"].head_local) if "Hips" in present else profile.HEAD[0]
    return {"names": names, "present": have, "rest": rest, "parent": parent, "hips_head": hips_head}
