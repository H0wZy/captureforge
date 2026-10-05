"""Scene settings (scene.faceforge) and the View3D > Sidebar > FaceForge panel."""

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       IntProperty, PointerProperty, StringProperty)

from .. import prefs
from . import live


# One sidebar tab for the whole suite: sibling modules (body, scan) put their panels in the same category.
CATEGORY = "CaptureForge"
# The add-on (extension) id: the suite package that contains this module. Preferences live under it.
ADDON_ID = prefs.ADDON_ID


def _live_record_changed(self, context):
    """Recording can be switched on mid-capture: it starts at the current frame."""
    if live.SESSION.active:
        live.SESSION.record, live.SESSION.rec_t0 = self.live_record, None
        live.SESSION.start_frame = context.scene.frame_current


def _is_mesh(self, obj):
    return obj.type == "MESH"


def _is_armature(self, obj):
    return obj.type == "ARMATURE"


class FFPair(bpy.types.PropertyGroup):
    source: PointerProperty(name="Source", type=bpy.types.Object, poll=_is_mesh,
                            description="Rigged mesh that is posed")
    target: PointerProperty(name="Target", type=bpy.types.Object, poll=_is_mesh,
                            description="Unrigged duplicate that receives the shape keys")


class FFReportRow(bpy.types.PropertyGroup):
    name: StringProperty()
    text: StringProperty()
    bad: BoolProperty()


class FFSettings(bpy.types.PropertyGroup):
    preset: EnumProperty(name="Preset", default="ARKIT_52", items=[
        ("ARKIT_52", "ARKit 52", "The 52 Apple ARKit blendshapes"),
        ("ARKIT_SYMMETRIC", "ARKit symmetric (34)", "Left/Right pairs posed once, split later"),
        ("CUSTOM", "Custom", "Names typed below"),
    ])
    custom_names: StringProperty(name="Names", description="Shape names separated by commas")
    start_frame: IntProperty(name="Start frame", default=1)
    neutral_frame: IntProperty(name="Neutral frame", default=0)
    pairs: CollectionProperty(type=FFPair)
    pairs_index: IntProperty()
    overwrite: BoolProperty(name="Overwrite keys", default=True)
    skip_empty: BoolProperty(name="Skip empty", default=False,
                             description="Do not create keys that do not move this target")
    split_width: FloatProperty(name="Falloff width", default=0.02, min=0.0, subtype="DISTANCE",
                               description="Half width of the smooth blend around X = 0")
    split_suffix: EnumProperty(name="Suffix", default="ARKIT", items=[
        ("ARKIT", "Left / Right", "eyeBlinkLeft, eyeBlinkRight"),
        ("BLENDER", ".L / .R", "eyeBlink.L, eyeBlink.R"),
    ])
    split_delete_source: BoolProperty(name="Delete source key", default=True)
    csv_path: StringProperty(name="CSV", subtype="FILE_PATH")
    csv_fps: FloatProperty(name="CSV FPS", default=60.0, min=1.0,
                           description="Frame rate of the Timecode column (Live Link Face default 60)")
    csv_mapping: StringProperty(name="Rename", description="Optional column=key pairs, comma separated")
    mocap_start_frame: IntProperty(name="Start frame", default=1)
    head_pose: BoolProperty(name="Head pose", default=True,
                            description="Also key the head rotation of the CSV (headRot columns) on a bone")
    head_armature: PointerProperty(name="Rig", type=bpy.types.Object, poll=_is_armature,
                                   description="Armature with the head bone; empty = the one on the targets, "
                                               "else the only one in the scene that has the bone")
    head_bone: StringProperty(name="Head bone", default="Head", description="Matched without caring about case")
    neck_bone: StringProperty(name="Neck bone", default="Neck")
    neck_share: FloatProperty(name="Neck share", default=0.0, min=0.0, max=1.0, subtype="FACTOR",
                              description="Part of the rotation given to the neck bone (0.3 = 30 %); "
                                          "the head bone keeps the rest")
    head_gain: FloatProperty(name="Head gain", default=1.0, min=0.0,
                             description="Multiplies the head angles (0.5 = half as much)")
    head_translate: BoolProperty(name="Translation", default=False,
                                 description="Also move the head bone with the head position of the video")
    head_translate_scale: FloatProperty(name="Scale", default=0.01, min=0.0,
                                        description="Scene units per centimeter of head movement (0.01 = meters)")
    fit_mode: EnumProperty(name="Rig", default="FACEFORGE", items=[
        ("FACEFORGE", "FaceForge rig", "Lean face rig with automatic weights"),
        ("RIGIFY", "Rigify metarig", "Rigify face metarig fitted to the face (needs the Rigify add-on)"),
    ])
    fit_size: IntProperty(name="Render size", default=768, min=256, max=4096,
                          description="Pixels of the front render MediaPipe looks at")
    live_port: IntProperty(name="Port", default=9876, min=1024, max=65535,
                           description="UDP port on 127.0.0.1 the capture listens on")
    live_camera: IntProperty(name="Camera", default=0, min=0, description="Webcam index for the helper")
    live_launch: BoolProperty(name="Start helper", default=True,
                              description="Launch the webcam helper; off = only listen (another sender drives it)")
    live_record: BoolProperty(name="Record", default=False, update=_live_record_changed,
                              description="Keyframe the live values into an action while capturing")
    video_path: StringProperty(name="Video", subtype="FILE_PATH")
    video_smooth: FloatProperty(name="Smooth", default=0.3, min=0.0, max=1.0,
                                description="Light smoothing; 0 = off, higher lags the motion")
    video_neutral: FloatProperty(name="Neutral s", default=2.0, min=0.0,
                                 description="Seconds at the start used as the neutral face (0 = off)")
    video_gain: FloatProperty(name="Gain", default=1.0, min=0.0,
                              description="Multiplies every channel after the neutral is removed")
    quality_collider: PointerProperty(name="Collider", type=bpy.types.Object, poll=_is_mesh,
                                      description="Closed mesh the keys must not poke into "
                                                  "(eyeball, teeth); empty = skip the check")
    quality_group: StringProperty(name="Group", description="Only test this vertex group of the "
                                                            "inspected mesh (eyelids, lips); empty = all")
    quality_sym_tol: FloatProperty(name="Symmetry tol", default=0.001, min=0.0, subtype="DISTANCE",
                                   description="Largest allowed Left/Right mismatch")
    report_path: StringProperty(name="Report file", subtype="FILE_PATH",
                                description="Optional .txt or .json file for the report")
    report: CollectionProperty(type=FFReportRow)
    report_index: IntProperty()
    sheet_path: StringProperty(name="Sheet", subtype="FILE_PATH", default="//faceforge_sheet.png")
    sheet_tile: IntProperty(name="Tile", default=256, min=16)
    sheet_columns: IntProperty(name="Columns", default=8, min=1)


class FACEFORGE_UL_report(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.alert = item.bad
        layout.label(text=f"{item.name}: {item.text}", icon="ERROR" if item.bad else "CHECKMARK")


class FACEFORGE_UL_pairs(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "source", text="")
        row.prop(item, "target", text="")


class FACEFORGE_PT_main(bpy.types.Panel):
    bl_label = "FaceForge"
    bl_idname = "FACEFORGE_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY

    def draw(self, context):
        s = context.scene.faceforge
        lay = self.layout

        box = lay.box()
        box.label(text="0. Auto rig (optional)", icon="ARMATURE_DATA")
        box.prop(s, "fit_mode")
        box.prop(s, "fit_size")
        box.operator("faceforge.auto_rig", icon="OUTLINER_OB_ARMATURE")

        box = lay.box()
        box.label(text="1. Pose markers", icon="MARKER_HLT")
        box.prop(s, "preset")
        if s.preset == "CUSTOM":
            box.prop(s, "custom_names")
        row = box.row(align=True)
        row.prop(s, "neutral_frame")
        row.prop(s, "start_frame")
        box.operator("faceforge.create_markers")
        box.operator("faceforge.key_pose")

        box = lay.box()
        box.label(text="2. Bake", icon="SHAPEKEY_DATA")
        box.operator("faceforge.make_target")
        row = box.row()
        row.template_list("FACEFORGE_UL_pairs", "", s, "pairs", s, "pairs_index", rows=3)
        col = row.column(align=True)
        col.operator("faceforge.pair_add", icon="ADD", text="")
        col.operator("faceforge.pair_remove", icon="REMOVE", text="")
        row = box.row()
        row.prop(s, "overwrite")
        row.prop(s, "skip_empty")
        box.operator("faceforge.bake", icon="REC")
        box.operator("faceforge.reset_keys")

        box = lay.box()
        box.label(text="3. Split L/R", icon="MOD_MIRROR")
        box.prop(s, "split_width")
        row = box.row()
        row.prop(s, "split_suffix", expand=True)
        box.prop(s, "split_delete_source")
        row = box.row(align=True)
        row.operator("faceforge.split_lr")
        row.operator("faceforge.split_all")

        box = lay.box()
        box.label(text="4. Mocap CSV", icon="FILE_TEXT")
        box.prop(s, "csv_path")
        row = box.row(align=True)
        row.prop(s, "csv_fps")
        row.prop(s, "mocap_start_frame")
        box.prop(s, "csv_mapping")
        box.prop(s, "head_pose")
        if s.head_pose:
            box.prop(s, "head_armature")
            row = box.row(align=True)
            row.prop(s, "head_bone", text="")
            row.prop(s, "neck_bone", text="")
            row = box.row(align=True)
            row.prop(s, "neck_share")
            row.prop(s, "head_gain")
            row = box.row(align=True)
            row.prop(s, "head_translate")
            sub = row.row()
            sub.active = s.head_translate
            sub.prop(s, "head_translate_scale")
        box.operator("faceforge.import_csv")

        box = lay.box()
        box.label(text="4b. Video to face", icon="FILE_MOVIE")
        box.prop(s, "video_path")
        row = box.row(align=True)
        row.prop(s, "video_smooth")
        row.prop(s, "video_neutral")
        row.prop(s, "video_gain")
        box.operator("faceforge.video_to_face", icon="PLAY")
        box.operator("faceforge.setup_help", icon="QUESTION")

        box = lay.box()
        box.label(text="4c. Live webcam", icon="CAMERA_DATA")
        row = box.row(align=True)
        row.prop(s, "live_port")
        row.prop(s, "live_camera")
        row = box.row(align=True)
        row.prop(s, "live_launch")
        row.prop(s, "live_record")
        if live.SESSION.active:
            box.operator("faceforge.live_stop", icon="PAUSE")
            box.label(text=f"{live.SESSION.state}, {live.SESSION.packets} packets"
                      + ("  (hold a still neutral face)" if live.SESSION.state == "calibrating" else ""))
        else:
            box.operator("faceforge.live_start", icon="PLAY")
        for line in live.SESSION.error.splitlines():
            box.label(text=line, icon="ERROR")

        box = lay.box()
        box.label(text="5. Quality inspector", icon="VIEWZOOM")
        box.prop(s, "quality_collider")
        box.prop(s, "quality_group")
        box.prop(s, "quality_sym_tol")
        box.prop(s, "report_path")
        row = box.row(align=True)
        row.operator("faceforge.inspect", icon="ZOOM_ALL")
        row.operator("faceforge.heatmap", icon="COLOR")
        box.template_list("FACEFORGE_UL_report", "", s, "report", s, "report_index", rows=4)

        box = lay.box()
        box.label(text="6. Review sheet", icon="RENDER_STILL")
        box.prop(s, "sheet_path")
        row = box.row(align=True)
        row.prop(s, "sheet_tile")
        row.prop(s, "sheet_columns")
        box.operator("faceforge.render_sheet")


classes = (FFPair, FFReportRow, FFSettings, FACEFORGE_UL_report, FACEFORGE_UL_pairs, FACEFORGE_PT_main)
