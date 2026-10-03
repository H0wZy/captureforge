"""Thin operator wrappers (faceforge.*) around the core modules."""

import os
import tempfile

import bpy

from . import bake, markers, mocap, presets, quality, sheet, split, video


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


def _import_csv(context, path):
    s = context.scene.faceforge
    if not os.path.isfile(path):
        raise ValueError(f"CSV not found: {path}")
    matched, unmatched, n = mocap.import_csv(context.scene, _targets(context), path, s.csv_fps,
                                             s.mocap_start_frame, mocap.parse_mapping(s.csv_mapping))
    msg = f"{len(matched)} keys animated, {n} rows"
    if unmatched:
        msg += f"; unmatched columns: {', '.join(unmatched)}"
    return msg


def _pref(context, name, env):
    """Add-on preference `name`, falling back to an environment variable (CI, headless agents)."""
    addon = context.preferences.addons.get(__package__)
    return (getattr(addon.preferences, name, "") if addon else "") or os.environ.get(env, "")


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
        return _import_csv(context, bpy.path.abspath(context.scene.faceforge.csv_path))


class FACEFORGE_OT_video_to_face(_Op):
    bl_idname = "faceforge.video_to_face"
    bl_label = "Video to face"
    bl_description = "Run MediaPipe on the video (separate Python, see Setup instructions) and key the result"

    def run(self, context):
        s = context.scene.faceforge
        src = bpy.path.abspath(s.video_path)
        out = os.path.splitext(src)[0] + "_faceforge.csv"
        python = bpy.path.abspath(_pref(context, "python_path", "FACEFORGE_PYTHON"))
        model = bpy.path.abspath(_pref(context, "model_path", "FACEFORGE_MODEL"))
        info = video.run(python, model, src, out, s.video_smooth, s.video_neutral, s.video_gain)
        s.csv_path = out
        return f"{info}. {_import_csv(context, out)}"


class FACEFORGE_OT_setup_help(bpy.types.Operator):
    bl_idname = "faceforge.setup_help"
    bl_label = "Setup instructions"
    bl_description = "How to install MediaPipe and the face model for Video to face and Live webcam"

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=620)

    def draw(self, context):
        for line in video.SETUP_LINES:
            self.layout.label(text=line)

    def execute(self, context):
        self.report({"INFO"}, video.SETUP_TEXT)
        return {"FINISHED"}


class FACEFORGE_OT_inspect(_Op):
    bl_idname = "faceforge.inspect"
    bl_label = "Inspect keys"
    bl_description = "Check every shape key of the targets (empty, symmetry, inside collider, flipped, crushed)"

    def run(self, context):
        s = context.scene.faceforge
        depsgraph = context.evaluated_depsgraph_get()
        reports = [quality.inspect(o, depsgraph, s.quality_collider, s.quality_group or None, s.quality_sym_tol)
                   for o in _targets(context) if o.data.shape_keys and o != s.quality_collider]
        if not reports:
            raise ValueError("No target with shape keys (make targets and bake first)")
        s.report.clear()
        for r in reports:
            for row in r["keys"]:
                item = s.report.add()
                item.name, item.text, item.bad = f"{r['object']}/{row['name']}", quality.summary_line(row), bool(row["problems"])
        if s.report_path:
            quality.write_report(reports, bpy.path.abspath(s.report_path))
        bad = sum(1 for i in s.report if i.bad)
        return f"{len(s.report)} keys checked, {bad} with problems"


class FACEFORGE_OT_heatmap(_Op):
    bl_idname = "faceforge.heatmap"
    bl_label = "Delta heatmap"
    bl_description = ("Color attribute of the active shape key's delta on the active mesh "
                      "(blue = still, red = most moved); view it with Solid shading > Color > Attribute")

    @classmethod
    def poll(cls, context):
        o = context.object
        return o is not None and o.type == "MESH" and o.active_shape_key_index > 0

    def run(self, context):
        obj = context.object
        quality.delta_heatmap(obj, obj.active_shape_key.name)
        return f"Color attribute {quality.HEATMAP_PREFIX}{obj.active_shape_key.name} created"


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
    FACEFORGE_OT_import_csv, FACEFORGE_OT_video_to_face, FACEFORGE_OT_setup_help,
    FACEFORGE_OT_inspect, FACEFORGE_OT_heatmap, FACEFORGE_OT_render_sheet,
)
