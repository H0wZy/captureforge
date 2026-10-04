"""Scene settings (scene.bodyforge) and the View3D > Sidebar > CaptureForge > BodyForge panel."""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

CATEGORY = "CaptureForge"  # one sidebar tab for the whole suite; FaceForge uses the same


def _is_armature(self, obj):
    return obj.type == "ARMATURE"


class BFSettings(bpy.types.PropertyGroup):
    video_path: StringProperty(name="Video", subtype="FILE_PATH", description="Phone or webcam video of one person")
    landmarks_path: StringProperty(
        name="Landmarks", subtype="FILE_PATH",
        description="landmarks.npz written by the helper; a file from another producer works too")
    armature: PointerProperty(name="Armature", type=bpy.types.Object, poll=_is_armature,
                              description="Mixamo-style humanoid armature that receives the clip")
    use_hands: BoolProperty(name="Hands and fingers", default=False,
                            description="Track the hands too (needs the hand model); fingers and wrist twist")
    neutral_seconds: FloatProperty(
        name="Neutral s", default=1.5, min=0.0, max=10.0,
        description="Seconds at the start of the video where the person stands still, used to measure the body")
    keep_source_fps: BoolProperty(name="Keep video frame rate", default=False,
                                  description="Key at the video's own rate (60 fps footage) instead of the scene rate")
    keep_travel: BoolProperty(name="Keep hip travel", default=False,
                              description="Keep the hips' sideways movement seen in the picture; off = in place")
    in_place: BoolProperty(name="In place", default=True, description="Remove horizontal hip drift in clean-up")
    smooth_mode: EnumProperty(name="Smoothing", default="FINAL", items=[
        ("FINAL", "Final", "Zero-phase low-pass: no lag, for the clip you keep"),
        ("PREVIEW", "Preview", "Causal One Euro filter: what a live preview would show"),
    ])
    smooth_strength: FloatProperty(name="Strength", default=1.0, min=0.1, max=4.0,
                                   description="Scales the filter cut-off frequency down: higher smooths more")
    foot_lock_left: BoolProperty(name="Lock left foot", default=True)
    foot_lock_right: BoolProperty(name="Lock right foot", default=True)
    loop_blend_frames: IntProperty(name="Blend frames", default=8, min=1, max=120,
                                   description="Frames spent cross-fading the end of the clip into its start")
    trim_start: IntProperty(name="Start", default=0, min=0, description="First frame to keep (0 = clip start)")
    trim_end: IntProperty(name="End", default=0, min=0, description="Last frame to keep (0 = clip end)")
    export_path: StringProperty(name="FBX", subtype="FILE_PATH", default="//bodyforge_clip.fbx")
    export_meshes: BoolProperty(name="Include meshes", default=False,
                                description="Also export the meshes skinned to the armature")
    warnings: StringProperty(description="Warnings from the last solve, one per line")
    report_text: StringProperty(description="Quality report summary, one line per entry")


def _lines(layout, text, icon="NONE"):
    for line in text.splitlines():
        layout.label(text=line, icon=icon)


class BODYFORGE_PT_main(bpy.types.Panel):
    bl_label = "BodyForge"
    bl_idname = "BODYFORGE_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY

    def draw(self, context):
        s = context.scene.bodyforge
        lay = self.layout

        box = lay.box()
        box.label(text="0. Helper (one time)", icon="PREFERENCES")
        row = box.row(align=True)
        row.operator("bodyforge.install_helper", icon="IMPORT")
        row.operator("bodyforge.check_helper", icon="CHECKMARK")

        box = lay.box()
        box.label(text="1. Rig", icon="ARMATURE_DATA")
        box.prop(s, "armature")
        box.operator("bodyforge.create_reference", icon="OUTLINER_OB_ARMATURE")

        box = lay.box()
        box.label(text="2. Video to body", icon="FILE_MOVIE")
        box.prop(s, "video_path")
        row = box.row(align=True)
        row.prop(s, "neutral_seconds")
        row.prop(s, "keep_source_fps", toggle=True)
        row = box.row(align=True)
        row.prop(s, "keep_travel", toggle=True)
        row.prop(s, "use_hands", toggle=True)
        row = box.row(align=True)
        row.operator("bodyforge.video_to_body", icon="PLAY")
        row.operator("bodyforge.video_to_body_and_face", icon="USER")
        box.prop(s, "landmarks_path")
        box.operator("bodyforge.landmarks_to_body", icon="FILE_TICK")
        if s.warnings:
            _lines(box, s.warnings, "ERROR")

        box = lay.box()
        box.label(text="3. Clean up", icon="MOD_SMOOTH")
        row = box.row(align=True)
        row.prop(s, "smooth_mode", expand=True)
        box.prop(s, "smooth_strength")
        row = box.row(align=True)
        row.prop(s, "foot_lock_left", toggle=True)
        row.prop(s, "foot_lock_right", toggle=True)
        box.prop(s, "in_place")
        box.operator("bodyforge.cleanup", icon="BRUSH_DATA")

        box = lay.box()
        box.label(text="4. Edit the clip", icon="NLA")
        row = box.row(align=True)
        row.prop(s, "trim_start")
        row.prop(s, "trim_end")
        box.operator("bodyforge.trim", icon="CUT")
        row = box.row(align=True)
        row.prop(s, "loop_blend_frames")
        row.operator("bodyforge.loop", icon="FILE_REFRESH")
        row = box.row(align=True)
        row.operator("bodyforge.in_place", icon="PIVOT_BOUNDBOX")
        row.operator("bodyforge.mirror", icon="MOD_MIRROR")

        box = lay.box()
        box.label(text="5. Report", icon="VIEWZOOM")
        box.operator("bodyforge.report", icon="TEXT")
        if s.report_text:
            _lines(box, s.report_text)

        box = lay.box()
        box.label(text="6. Export for Unity", icon="EXPORT")
        box.prop(s, "export_path")
        box.prop(s, "export_meshes")
        box.operator("bodyforge.export_unity", icon="EXPORT")


classes = (BFSettings, BODYFORGE_PT_main)
