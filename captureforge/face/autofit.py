"""Auto rig fit: render the head from the front, find the face landmarks with MediaPipe (separate Python,
see video.py), raycast them onto the mesh and build a rig on the real face.

Two outputs: our lean FaceForge rig (bones + automatic distance-falloff weights), or a Rigify face metarig
scaled to the face. Conventions: the character looks toward -Y, its left is +X (landmark "L" = +X).
"""

import math
import os
import shutil
import tempfile

import bpy
import numpy as np
from mathutils import Vector

from . import video
from .quality import collider_bvh
from .sheet import _world_bbox

# MediaPipe Face Landmarker indices (the public canonical face mesh). Image left is the person's right.
LANDMARKS = {
    "iris.L": 473, "iris.R": 468,
    "eye_out.L": 263, "eye_in.L": 362, "eye_up.L": 386, "eye_low.L": 374,
    "eye_out.R": 33, "eye_in.R": 133, "eye_up.R": 159, "eye_low.R": 145,
    "brow_in.L": 336, "brow_mid.L": 334, "brow_out.L": 300,
    "brow_in.R": 107, "brow_mid.R": 105, "brow_out.R": 70,
    "mouth.L": 291, "mouth.R": 61, "lip_up": 0, "lip_low": 17, "lip_in_up": 13, "lip_in_low": 14,
    "lip_up.L": 269, "lip_up.R": 39, "lip_low.L": 405, "lip_low.R": 181,
    "cheek.L": 425, "cheek.R": 205, "chin": 152, "top": 10,
}
SIDES = ("L", "R")
UP, FRONT = Vector((0, 0, 1)), Vector((0, -1, 0))


# ------------------------------------------------------------------ camera, render, landmarks -> surface

def front_camera(objs, margin=1.25):
    """Front orthographic framing of objs (world space), as plain numbers: image (u, v) <-> world (x, z)."""
    lo, hi = _world_bbox(objs)
    size = max(hi.x - lo.x, hi.z - lo.z) * margin
    return {"cx": (lo.x + hi.x) / 2, "cz": (lo.z + hi.z) / 2, "scale": size, "y": lo.y - size,
            "depth": hi.y - lo.y}


def uv_to_world(cam, u, v):
    """Normalized image point (u right, v down) -> world (x, z) on the camera plane."""
    return cam["cx"] + (u - 0.5) * cam["scale"], cam["cz"] + (0.5 - v) * cam["scale"]


def render_front(scene, objs, path, cam, size=768, color_type="TEXTURE"):
    """Workbench render of objs only, from -Y, to path (PNG). Scene settings are restored."""
    r, im, sh = scene.render, scene.render.image_settings, scene.display.shading
    saved = (r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath, scene.camera,
             im.file_format, im.color_mode, sh.color_type, sh.light)
    hidden = {o.name: o.hide_render for o in scene.objects}
    cam_obj = None
    try:
        data = bpy.data.cameras.new("FF_FitCam")
        data.type, data.ortho_scale = "ORTHO", cam["scale"]
        data.clip_start, data.clip_end = 0.01, cam["depth"] + cam["scale"] * 4
        cam_obj = bpy.data.objects.new("FF_FitCam", data)
        cam_obj.location = (cam["cx"], cam["y"], cam["cz"])
        cam_obj.rotation_euler = (math.pi / 2, 0.0, 0.0)  # looks +Y, up +Z
        scene.collection.objects.link(cam_obj)
        for o in scene.objects:
            o.hide_render = not (o in objs or o == cam_obj)
        scene.camera = cam_obj
        r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage = "BLENDER_WORKBENCH", size, size, 100
        im.file_format, im.color_mode = "PNG", "RGB"
        sh.color_type, sh.light = color_type, "STUDIO"
        r.filepath = path
        bpy.ops.render.render(write_still=True, scene=scene.name)
    finally:
        if cam_obj is not None:
            data = cam_obj.data
            bpy.data.objects.remove(cam_obj)
            bpy.data.cameras.remove(data)
        (r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath, scene.camera,
         im.file_format, im.color_mode, sh.color_type, sh.light) = saved
        for o in scene.objects:
            if o.name in hidden:
                o.hide_render = hidden[o.name]
    return path


def map_landmarks(landmarks, cam, head, depsgraph):
    """{name: world Vector on the head surface} for every entry of LANDMARKS. Each landmark is a ray along
    +Y through its image point; a ray that misses (outside the silhouette) takes the closest surface point."""
    bvh = collider_bvh(head, depsgraph)
    out = {}
    for name, i in LANDMARKS.items():
        x, z = uv_to_world(cam, landmarks[i][0], landmarks[i][1])
        origin = Vector((x, cam["y"], z))
        hit = bvh.ray_cast(origin, Vector((0, 1, 0)))[0]
        out[name] = hit if hit is not None else bvh.find_nearest(origin)[0]
    return out


# ------------------------------------------------------------------ geometry shared by both rigs

def _center(obj):
    lo, hi = _world_bbox([obj])
    return (lo + hi) / 2


def face_geometry(P, head, extras=()):
    """Sizes and anchor points derived from the mapped landmarks (all world space)."""
    g = {"ew": sum((P[f"eye_out.{s}"] - P[f"eye_in.{s}"]).length for s in SIDES) / 2,
         "mw": (P["mouth.L"] - P["mouth.R"]).length,
         "line": (P["lip_in_up"] + P["lip_in_low"]) / 2}
    lo, hi = _world_bbox([head])
    g["y_mid"], g["cx"] = (lo.y + hi.y) / 2, (lo.x + hi.x) / 2
    g["eye"] = {}
    for s, sign in (("L", 1), ("R", -1)):
        iris = P[f"iris.{s}"]
        balls = [e for e in extras if sign * _center(e).x > 0 and (_center(e) - iris).length < 1.2 * g["ew"]]
        # eyeball center: the eyeball mesh if there is one, else behind the surface the iris lands on
        g["eye"][s] = (_center(min(balls, key=lambda e: (_center(e) - iris).length)) if balls
                       else iris + Vector((0, 0.4 * g["ew"], 0)))
    return g


# ------------------------------------------------------------------ FaceForge rig

def bone_specs(P, g):
    """Lean face rig: list of dicts {name, head, tail, parent, anchor, radius}. anchor/radius drive the
    head mesh weights (None = no skin influence by distance; jaw and head have their own rules)."""
    ew, mw, line = g["ew"], g["mw"], g["line"]
    fwd = lambda d: Vector((0, -d, 0))  # noqa: E731
    specs = []

    def add(name, head, tail, parent, anchor=None, radius=0.0):
        specs.append({"name": name, "head": Vector(head), "tail": Vector(tail), "parent": parent,
                      "anchor": None if anchor is None else Vector(anchor), "radius": radius})

    cx, ym = g["cx"], g["y_mid"]
    add("head", (cx, ym, P["chin"].z), (cx, ym, P["top"].z), None)
    z_hinge = line.z + 0.4 * (g["eye"]["L"].z - line.z)
    add("jaw", (cx, ym, z_hinge), P["chin"], "head")
    for s in SIDES:
        c = g["eye"][s]
        add(f"eye.{s}", c, c + fwd(0.5 * ew), "head")
        add(f"lid.T.{s}", c, P[f"eye_up.{s}"], "head", P[f"eye_up.{s}"], 0.4 * ew)
        add(f"lid.B.{s}", c, P[f"eye_low.{s}"], "head", P[f"eye_low.{s}"], 0.4 * ew)
        for part in ("in", "mid", "out"):
            p = P[f"brow_{part}.{s}"]
            add(f"brow.{part}.{s}", p, p + UP * 0.25 * ew, "head", p, 0.4 * ew)
        add(f"mouth.corner.{s}", P[f"mouth.{s}"], P[f"mouth.{s}"] + fwd(0.15 * mw), "head", P[f"mouth.{s}"], 0.3 * mw)
        add(f"lip.T.{s}", P[f"lip_up.{s}"], P[f"lip_up.{s}"] + fwd(0.12 * mw), "head", P[f"lip_up.{s}"], 0.25 * mw)
        add(f"lip.B.{s}", P[f"lip_low.{s}"], P[f"lip_low.{s}"] + fwd(0.12 * mw), "jaw", P[f"lip_low.{s}"], 0.25 * mw)
        add(f"cheek.{s}", P[f"cheek.{s}"], P[f"cheek.{s}"] + fwd(0.15 * ew), "head", P[f"cheek.{s}"], 0.7 * ew)
    add("lip.T", P["lip_up"], P["lip_up"] + fwd(0.12 * mw), "head", P["lip_up"], 0.25 * mw)
    add("lip.B", P["lip_low"], P["lip_low"] + fwd(0.12 * mw), "jaw", P["lip_low"], 0.25 * mw)
    base = Vector((line.x, line.y + 0.5 * mw, line.z - 0.05 * mw))
    mid = base + Vector((0, -0.3 * mw, 0))
    add("tongue", base, mid, "jaw")
    add("tongue.tip", mid, mid + fwd(0.25 * mw), "tongue")
    return specs


def _smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def skin_weights(co, specs, g):
    """{bone: (n,) weights} for world-space points co on the head mesh. Distance falloff around each bone's
    anchor; jaw = everything below the lip line and in front of the hinge; head takes the rest. Rows sum to 1."""
    mw = g["mw"]
    jaw_spec = next(s for s in specs if s["name"] == "jaw")
    w = {}
    for s in specs:
        if s["anchor"] is not None:
            d = np.linalg.norm(co - np.array(s["anchor"]), axis=1)
            w[s["name"]] = _smooth(1.0 - d / s["radius"]) ** 2
    z_split = g["line"].z + 0.1 * mw
    w["jaw"] = _smooth((z_split - co[:, 2]) / (0.25 * mw)) * _smooth((jaw_spec["head"].y - co[:, 1]) / (0.3 * mw) + 0.5)
    total = sum(w.values())
    scale = np.maximum(total, 1.0)
    w = {k: v / scale for k, v in w.items()}
    w["head"] = np.maximum(0.0, 1.0 - sum(w.values()))
    return w


def create_armature(name, specs, collection):
    """Armature object with edit bones from specs (needs a mode switch, so it goes through bpy.ops)."""
    arm = bpy.data.objects.new(name, bpy.data.armatures.new(name))
    collection.objects.link(arm)
    view = bpy.context.view_layer
    prev = view.objects.active
    view.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        eb = arm.data.edit_bones
        for s in specs:
            b = eb.new(s["name"])
            b.head, b.tail = s["head"], s["tail"]
        for s in specs:
            if s["parent"]:
                eb[s["name"]].parent = eb[s["parent"]]
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        view.objects.active = prev
    return arm


def _bind(obj, arm, weights):
    """Vertex groups from {bone: (n,) weights} plus an Armature modifier."""
    for bone, w in weights.items():
        vg = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
        for i in np.flatnonzero(w > 1e-4):
            vg.add([int(i)], float(w[i]), "REPLACE")
    mod = obj.modifiers.get("Armature") or obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm


def rigid_bone(obj, specs, g):
    """Which bone an extra mesh follows: eyeballs -> the closest eye, tongue by name, below the lip line -> jaw."""
    c = _center(obj)
    if "tongue" in obj.name.lower():
        return "tongue"
    for s in SIDES:
        if (c - g["eye"][s]).length < 0.8 * g["ew"]:
            return f"eye.{s}"
    return "jaw" if c.z < g["line"].z + 0.1 * g["mw"] else "head"


def build_faceforge_rig(P, head, extras=(), name="FaceRig"):
    """Armature + weights from mapped landmarks. head gets distance-falloff skin weights; each extra mesh is
    bound rigidly to one bone. Returns the armature object."""
    g = face_geometry(P, head, extras)
    specs = bone_specs(P, g)
    arm = create_armature(name, specs, head.users_collection[0])
    mesh = head.data
    co = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", co)
    m = np.array(head.matrix_world)
    world = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
    _bind(head, arm, skin_weights(world, specs, g))
    for e in extras:
        _bind(e, arm, {rigid_bone(e, specs, g): np.ones(len(e.data.vertices))})
    return arm


# ------------------------------------------------------------------ Rigify face metarig

def fit_rigify(P, head, extras=(), name="FaceMetarig"):
    """Rigify face sample metarig scaled and moved to the face (axis-aligned affine fit on the eyes and chin).
    Raises ValueError if Rigify is not available and enabled. Generate the final rig with Rigify afterwards."""
    try:
        from rigify.rigs.faces import super_face
    except ImportError as e:
        raise ValueError("Rigify is not available: enable it in Preferences > Add-ons") from e
    if not hasattr(bpy.types.PoseBone, "rigify_type"):
        raise ValueError("Rigify is not enabled: Preferences > Add-ons > Rigify")
    g = face_geometry(P, head, extras)
    arm = bpy.data.objects.new(name, bpy.data.armatures.new(name))
    head.users_collection[0].objects.link(arm)
    view = bpy.context.view_layer
    prev = view.objects.active
    view.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        super_face.create_sample(arm)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        view.objects.active = prev
    # Sample anchors: eye.L head (0.036, -0.069, 0.111), chin head z = 0.004.
    src = {"eye": arm.data.bones["eye.L"].head_local, "chin": arm.data.bones["chin"].head_local}
    eye_c = (g["eye"]["L"] + g["eye"]["R"]) / 2
    sx = abs(g["eye"]["L"].x - g["eye"]["R"].x) / (2 * src["eye"].x)
    sz = (eye_c.z - P["chin"].z) / (src["eye"].z - src["chin"].z)
    sy = (sx + sz) / 2
    arm.scale = (sx, sy, sz)
    arm.location = (eye_c.x, eye_c.y - sy * src["eye"].y, eye_c.z - sz * src["eye"].z)
    view.update()  # matrix_world is read right after
    return arm


# ------------------------------------------------------------------ all steps

def fit_from_landmarks(landmarks, cam, head, extras=(), mode="FACEFORGE", name=None, depsgraph=None):
    """Map landmarks (478 normalized points) onto head and build the rig. mode: FACEFORGE or RIGIFY."""
    depsgraph = depsgraph or bpy.context.evaluated_depsgraph_get()
    P = map_landmarks(landmarks, cam, head, depsgraph)
    if mode == "RIGIFY":
        return fit_rigify(P, head, extras, name or "FaceMetarig")
    return build_faceforge_rig(P, head, extras, name or "FaceRig")


def fit(scene, head, extras, python, model, mode="FACEFORGE", size=768, name=None):
    """Render the front view of head (+ extras), run MediaPipe on it and build the rig."""
    cam = front_camera([head, *extras])
    tmp = tempfile.mkdtemp(prefix="faceforge_fit_")
    try:
        image = render_front(scene, [head, *extras], os.path.join(tmp, "front.png"), cam, size)
        lm = video.landmarks(python, model, image)["landmarks"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return fit_from_landmarks(lm, cam, head, extras, mode, name)
