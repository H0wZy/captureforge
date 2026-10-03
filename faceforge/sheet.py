"""Review sheet: one Workbench render per shape key, assembled into a labelled PNG grid."""

import math
import os
import shutil
import tempfile

import bpy
import numpy as np
from mathutils import Vector

from .presets import NEUTRAL_MARKER

BACKGROUND = (0.08, 0.08, 0.08, 1.0)


def _key_names(targets):
    names = []
    for obj in targets:
        keys = obj.data.shape_keys
        if keys:
            names += [kb.name for kb in keys.key_blocks
                      if kb != keys.reference_key and kb.name not in names]
    return names


def _world_bbox(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def _set_values(targets, shot):
    for obj in targets:
        keys = obj.data.shape_keys
        if keys is None:
            continue
        for kb in keys.key_blocks:
            if kb != keys.reference_key:
                kb.value = 1.0 if kb.name == shot else 0.0


def _read_png(path, tile):
    img = bpy.data.images.load(path, check_existing=False)
    try:
        px = np.empty(tile * tile * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(img)
    return px.reshape(tile, tile, 4)


def render_sheet(scene, targets, out_path, names=None, tile=256, columns=8):
    """Render ['neutral'] + names (default: every key on the targets) and save a PNG grid."""
    if not targets:
        raise ValueError("No targets to render")
    shots = [NEUTRAL_MARKER] + list(names if names is not None else _key_names(targets))
    columns = max(1, columns)
    r, im = scene.render, scene.render.image_settings
    saved = (r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath,
             scene.camera, im.file_format, im.color_mode)
    hidden = {o.name: o.hide_render for o in scene.objects}
    values = {(o.name, kb.name): kb.value
              for o in targets if o.data.shape_keys for kb in o.data.shape_keys.key_blocks}
    tmp = tempfile.mkdtemp(prefix="faceforge_")
    cam = label = None
    try:
        lo, hi = _world_bbox(targets)
        size = max(hi.x - lo.x, hi.z - lo.z) * 1.15
        label_h = size * 0.12
        cx = (lo.x + hi.x) / 2

        cam_data = bpy.data.cameras.new("FF_SheetCam")
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = size + label_h * 2
        cam_data.clip_end = (hi.y - lo.y) + size * 10
        cam = bpy.data.objects.new("FF_SheetCam", cam_data)
        cam.location = (cx, lo.y - size * 4, (lo.z + hi.z) / 2 - label_h)
        cam.rotation_euler = (math.pi / 2, 0.0, 0.0)  # looks +Y, up +Z
        scene.collection.objects.link(cam)

        font = bpy.data.curves.new("FF_SheetLabel", "FONT")
        font.align_x = "CENTER"
        font.size = label_h * 0.7
        label = bpy.data.objects.new("FF_SheetLabel", font)
        label.location = (cx, lo.y - size * 0.05, lo.z - label_h)
        label.rotation_euler = (math.pi / 2, 0.0, 0.0)  # faces -Y, toward the camera
        scene.collection.objects.link(label)

        for o in scene.objects:
            o.hide_render = not (o in targets or o in (cam, label))
        scene.camera = cam
        r.engine = "BLENDER_WORKBENCH"
        r.resolution_x = r.resolution_y = tile
        r.resolution_percentage = 100
        im.file_format, im.color_mode = "PNG", "RGBA"

        rows = math.ceil(len(shots) / columns)
        width = min(len(shots), columns) * tile
        grid = np.empty((rows * tile, width, 4), dtype=np.float32)
        grid[:] = BACKGROUND
        for i, shot in enumerate(shots):
            _set_values(targets, shot)
            font.body = shot
            r.filepath = os.path.join(tmp, f"{i:03d}.png")
            bpy.ops.render.render(write_still=True, scene=scene.name)
            # Image rows run bottom-up in Blender: sheet row 0 is the top band.
            row, col = divmod(i, columns)
            y = (rows - 1 - row) * tile
            grid[y:y + tile, col * tile:(col + 1) * tile] = _read_png(r.filepath, tile)

        out_path = bpy.path.abspath(out_path)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        img = bpy.data.images.new("FF_Sheet", width, rows * tile, alpha=True)
        try:
            img.pixels.foreach_set(grid.ravel())
            img.filepath_raw = out_path
            img.file_format = "PNG"
            img.save()
        finally:
            bpy.data.images.remove(img)
        return out_path
    finally:
        if cam is not None:
            data = cam.data
            bpy.data.objects.remove(cam)
            bpy.data.cameras.remove(data)
        if label is not None:
            data = label.data
            bpy.data.objects.remove(label)
            bpy.data.curves.remove(data)
        (r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath,
         scene.camera, im.file_format, im.color_mode) = saved
        for o in scene.objects:
            if o.name in hidden:
                o.hide_render = hidden[o.name]
        for (oname, kname), v in values.items():
            bpy.data.objects[oname].data.shape_keys.key_blocks[kname].value = v
        shutil.rmtree(tmp, ignore_errors=True)
