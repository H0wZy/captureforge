"""Thin operator wrappers (faceforge.*) around the core modules."""

import os
import tempfile

import bpy

from . import bake, markers, mocap, presets, sheet, split


def preset_names(settings):
    if settings.preset == "ARKIT_52":
        return list(presets.ARKIT_52)
    if settings.preset == "ARKIT_SYMMETRIC":
        return list(presets.ARKIT_SYMMETRIC)
    return presets.parse_names(settings.custom_names)


def _targets(context):
    """Targets of every pair; falls back to the active mesh."""
    out = [p.target for p in context.scene.faceforge.pairs if p.target]
    if not out and context.object and context.object.type == "MESH":
        out = [context.object]
    return out


class _Op(bpy.types.Operator):
    bl_options = {"REGISTER", "UNDO"}

    def run(self, context):
        raise NotImplementedError

    def execute(self, context):
        try:
            msg = self.run(context)
        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        if msg:
            self.report({"INFO"}, msg)
        return {"FINISHED"}


class FACEFORGE_OT_create_markers(_Op):
    bl_idname = "faceforge.create_markers"
    bl_label = "Create markers"
    bl_description = "Replace the timeline markers with neutral + one marker per shape"

    def run(self, context):
        s = context.scene.faceforge
        names = preset_names(s)
        if not names:
            raise ValueError("The custom name list is empty")
        n = markers.create_markers(context.scene, names, s.start_frame, s.neutral_frame)
        return f"{n} markers created"


class FACEFORGE_OT_key_pose(_Op):
    bl_idname = "faceforge.key_pose"
    bl_label = "Key pose"
    bl_description = "Keyframe every bone of the active armature on the current frame"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "ARMATURE"

    def run(self, context):
        n = markers.key_pose(context.object, context.scene.frame_current)
        return f"{n} bones keyed on frame {context.scene.frame_current}"


class FACEFORGE_OT_make_target(_Op):
    bl_idname = "faceforge.make_target"
    bl_label = "Make target"
    bl_description = "Duplicate each selected mesh without rig/modifiers and add it as a pair"

    def run(self, context):
        sources = [o for o in context.selected_objects if o.type == "MESH"]
        if not sources:
            raise ValueError("Select the rigged meshes (head, eyes, teeth, tongue)")
        for src in sources:
            pair = context.scene.faceforge.pairs.add()
            pair.source, pair.target = src, bake.make_target(src)
        return f"{len(sources)} targets created"


class FACEFORGE_OT_pair_add(_Op):
    bl_idname = "faceforge.pair_add"
    bl_label = "Add pair"

    def run(self, context):
        s = context.scene.faceforge
        pair = s.pairs.add()
        if context.object and context.object.type == "MESH":
            pair.source = context.object
        s.pairs_index = len(s.pairs) - 1


class FACEFORGE_OT_pair_remove(_Op):
    bl_idname = "faceforge.pair_remove"
    bl_label = "Remove pair"

    @classmethod
    def poll(cls, context):
        return len(context.scene.faceforge.pairs) > 0

    def run(self, context):
        s = context.scene.faceforge
        s.pairs.remove(s.pairs_index)
        s.pairs_index = max(0, min(s.pairs_index, len(s.pairs) - 1))


class FACEFORGE_OT_bake(_Op):
    bl_idname = "faceforge.bake"
    bl_label = "Bake shape keys"
    bl_description = "One shape key per marker on every target: evaluated(pose) - evaluated(neutral)"

    def run(self, context):
        s, scene = context.scene.faceforge, context.scene
        pairs = [(p.source, p.target) for p in s.pairs if p.source and p.target]
        neutral = markers.neutral_frame(scene)
        if neutral is None:
            neutral = s.neutral_frame
        names = bake.bake_shapes(scene, pairs, markers.frames_from_markers(scene), neutral,
                                 overwrite=s.overwrite, skip_empty=s.skip_empty)
        return f"Baked {len(names)} shapes on {len(pairs)} targets"


class FACEFORGE_OT_reset_keys(_Op):
    bl_idname = "faceforge.reset_keys"
    bl_label = "Reset keys"
    bl_description = "Set every shape key value on the targets to 0"

    def run(self, context):
        n = sum(bake.reset_keys(o) for o in _targets(context))
        return f"{n} keys reset"


class FACEFORGE_OT_split_lr(_Op):
    bl_idname = "faceforge.split_lr"
    bl_label = "Split active"
    bl_description = "Split the active shape key into Left (+X) and Right (-X)"

    @classmethod
    def poll(cls, context):
        o = context.object
        return o is not None and o.type == "MESH" and o.active_shape_key_index > 0

    def run(self, context):
        s, obj = context.scene.faceforge, context.object
        left, right = split.split_lr(obj, obj.active_shape_key.name, s.split_width,
                                     s.split_suffix, s.split_delete_source)
        return f"Split into {left} / {right}"


class FACEFORGE_OT_split_all(_Op):
    bl_idname = "faceforge.split_all"
    bl_label = "Split all"
    bl_description = "Split every symmetric ARKit key (eyeBlink, mouthSmile, ...) on the targets"

    def run(self, context):
        s = context.scene.faceforge
        n = sum(len(split.split_all(o, s.split_width, s.split_suffix, s.split_delete_source))
                for o in _targets(context))
        return f"{n} keys split"


class FACEFORGE_OT_import_csv(_Op):
    bl_idname = "faceforge.import_csv"
    bl_label = "Import CSV"
    bl_description = "Key the targets' shape keys from a face mocap CSV (Live Link Face or generic)"

    def run(self, context):
        s, scene = context.scene.faceforge, context.scene
        path = bpy.path.abspath(s.csv_path)
        if not os.path.isfile(path):
            raise ValueError(f"CSV not found: {path}")
        names, times, rows = mocap.read_csv(path, s.csv_fps)
        fps = scene.render.fps / scene.render.fps_base
        mapping = mocap.parse_mapping(s.csv_mapping)
        matched, unmatched = set(), set(names)
        for obj in _targets(context):
            if obj.data.shape_keys is None:
                continue
            m, u = mocap.apply_mocap(obj, names, times, rows, fps, s.mocap_start_frame, mapping)
            matched |= set(m)
            unmatched &= set(u)  # unmatched = no target took the column
        if not matched:
            raise ValueError("No CSV column matches a shape key on the targets")
        msg = f"{len(matched)} keys animated, {len(times)} rows"
        if unmatched:
            msg += f"; unmatched columns: {', '.join(sorted(unmatched))}"
        return msg


class FACEFORGE_OT_render_sheet(_Op):
    bl_idname = "faceforge.render_sheet"
    bl_label = "Render review sheet"
    bl_description = "Render neutral + every shape key of the targets into one PNG grid"

    def run(self, context):
        s = context.scene.faceforge
        path = s.sheet_path
        if path.startswith("//") and not bpy.data.filepath:
            path = os.path.join(tempfile.gettempdir(), path[2:])
        out = sheet.render_sheet(context.scene, _targets(context), path,
                                 tile=s.sheet_tile, columns=s.sheet_columns)
        return f"Sheet saved: {out}"


classes = (
    FACEFORGE_OT_create_markers, FACEFORGE_OT_key_pose, FACEFORGE_OT_make_target,
    FACEFORGE_OT_pair_add, FACEFORGE_OT_pair_remove, FACEFORGE_OT_bake,
    FACEFORGE_OT_reset_keys, FACEFORGE_OT_split_lr, FACEFORGE_OT_split_all,
    FACEFORGE_OT_import_csv, FACEFORGE_OT_render_sheet,
)
